"""PoC 001 v2 — Kling AI Avatar v2 Pro で「静止画 + セリフ wav → 口パク同期動画」 を一発生成.

エンドポイント: fal-ai/kling-video/ai-avatar/v2/pro
  入力: image (PNG/JPG) + audio (WAV) + 任意 prompt
  出力: 音声同期済み MP4 (尺 = audio 長さ)
  料金: $0.115/秒

i2v + 別 lipsync の 2 段階チェーンを 1 step に統合した別モデル。
タイミングずれが構造的に起きない。

対象: cuts.py の anim_method=kling で main_char != "none" かつ shot_size!=ECU
      (= 口元が映る talking cut のみ)

Usage:
  python gen_avatar.py --only C012
  python gen_avatar.py --regen --only C012
  python gen_avatar.py --parallel 3
"""
from __future__ import annotations

import argparse
import concurrent.futures
import importlib.util
import json
import os
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(ROOT / "src"))
from _dotenv import load_dotenv  # noqa: E402
load_dotenv()

try:
    import fal_client  # type: ignore
except ImportError:
    print("fal_client not installed", file=sys.stderr)
    sys.exit(2)

HERE = Path(__file__).resolve().parent
INPUT_CUTS_DIR = HERE / "input_cuts"
AUDIO_LINES_DIR = HERE / "audio_lines"
OUT_DIR = HERE / "clips_avatar"
WORK_DIR = OUT_DIR / "_work"

MODEL_ID = "fal-ai/kling-video/ai-avatar/v2/pro"
PRICE_PER_SEC = 0.115

# cuts.py + timing.json
spec = importlib.util.spec_from_file_location("cuts", HERE / "cuts.py")
cuts_mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(cuts_mod)
CUTS = cuts_mod.CUTS

with open(HERE / "timing.json") as f:
    TIMING = json.load(f)


def run_ff(cmd: list[str]) -> None:
    proc = subprocess.run(cmd, capture_output=True, text=True)
    if proc.returncode != 0:
        print(proc.stderr[-1500:], file=sys.stderr)
        raise RuntimeError(f"ffmpeg failed: {' '.join(cmd[:6])}")


def is_avatar_target(cut: dict) -> tuple[bool, str]:
    if cut.get("anim_method") != "kling":
        return False, "not kling"
    if not cut.get("covers_lines"):
        return False, "no dialogue"
    if cut["main_char"] == "none":
        return False, "no character"
    if cut["shot_size"] in ("ECU",):
        return False, "ECU"
    return True, "OK"


def slice_audio(cut: dict, dst: Path) -> Path:
    parts: list[Path] = []
    for cov in cut["covers_lines"]:
        sid = cov["scene"]
        lidx = cov["idx"]
        line_info = TIMING["scenes"][sid]["lines"][lidx]
        speaker = line_info["speaker"]
        src_wav = AUDIO_LINES_DIR / f"{sid}_l{lidx:02d}_{speaker}.wav"
        if not src_wav.exists():
            raise FileNotFoundError(f"audio missing: {src_wav}")
        rng = cov.get("range")
        if rng is None:
            parts.append(src_wav)
            continue
        seg_path = WORK_DIR / f"{cut['id']}_seg_{sid}_l{lidx:02d}.wav"
        run_ff([
            "ffmpeg", "-y", "-loglevel", "error",
            "-i", str(src_wav),
            "-ss", f"{rng[0]:.3f}",
            "-to", f"{rng[1]:.3f}",
            "-c:a", "pcm_s16le",
            str(seg_path),
        ])
        parts.append(seg_path)

    if len(parts) == 1:
        run_ff(["ffmpeg", "-y", "-loglevel", "error",
                "-i", str(parts[0]), "-c:a", "pcm_s16le", str(dst)])
    else:
        list_path = WORK_DIR / f"{cut['id']}_audio_list.txt"
        list_path.write_text("\n".join(f"file '{p.resolve()}'" for p in parts))
        run_ff(["ffmpeg", "-y", "-loglevel", "error",
                "-f", "concat", "-safe", "0", "-i", str(list_path),
                "-c:a", "pcm_s16le", str(dst)])
    return dst


def pad_audio_to(audio_in: Path, target_sec: float, audio_out: Path) -> None:
    """音声を末尾 silence で target_sec まで pad."""
    run_ff([
        "ffmpeg", "-y", "-loglevel", "error",
        "-i", str(audio_in),
        "-af", f"apad=whole_dur={target_sec:.3f}",
        "-t", f"{target_sec:.3f}",
        "-c:a", "pcm_s16le",
        str(audio_out),
    ])


def process_one(cut: dict) -> dict:
    cid = cut["id"]
    print(f"\n[{cid}] {cut['kind']} {cut['shot_size']} target_dur={cut['duration']:.2f}s  main={cut['main_char']}")

    image_path = INPUT_CUTS_DIR / f"{cid}.png"
    if not image_path.exists():
        raise FileNotFoundError(f"still missing: {image_path}")

    sliced_audio = WORK_DIR / f"{cid}_audio_raw.wav"
    final_audio = WORK_DIR / f"{cid}_audio.wav"
    slice_audio(cut, sliced_audio)

    # 音声の長さ確認
    a_dur = float(subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration",
         "-of", "default=noprint_wrappers=1:nokey=1", str(sliced_audio)],
        capture_output=True, text=True, check=True).stdout.strip())

    # cut.duration に合わせて pad / trim (Avatar 出力 = audio 長さ)
    target = cut["duration"]
    if abs(a_dur - target) > 0.05:
        pad_audio_to(sliced_audio, target, final_audio)
        print(f"  audio padded {a_dur:.2f}s -> {target:.2f}s")
    else:
        final_audio = sliced_audio
        print(f"  audio {a_dur:.2f}s ≈ target {target:.2f}s")

    # Fal upload + Avatar v2 Pro 呼び出し
    print(f"  {cid}: uploading image + audio...")
    image_url = fal_client.upload_file(str(image_path))
    audio_url = fal_client.upload_file(str(final_audio))

    payload = {
        "image_url": image_url,
        "audio_url": audio_url,
        # Kling は中国製モデルで、 ぼかし紙面を勝手に漢字で埋める癖がある (C015 で発覚) → 抑止
        "negative_prompt": (
            "text, chinese characters, japanese characters, kanji, hiragana, "
            "captions, subtitles, writing, calligraphy, written words, "
            "watermarks, logos, signage, on-screen text"
        ),
    }
    # 動き指示 (任意) — motion_prompt があれば渡す
    if cut.get("motion_prompt"):
        payload["prompt"] = cut["motion_prompt"]

    print(f"  {cid}: invoking Kling Avatar v2 Pro...")
    t0 = time.time()
    result = fal_client.subscribe(MODEL_ID, arguments=payload, with_logs=False)
    elapsed = time.time() - t0
    video_url = result["video"]["url"]
    print(f"  {cid}: done in {elapsed:.1f}s")

    out_mp4 = OUT_DIR / f"{cid}.mp4"
    urllib.request.urlretrieve(video_url, out_mp4)

    cost = PRICE_PER_SEC * target
    meta = {
        "cut_id": cid,
        "model": MODEL_ID,
        "target_duration": round(target, 3),
        "audio_duration_in": round(a_dur, 3),
        "elapsed_sec": round(elapsed, 1),
        "cost_usd": round(cost, 4),
        "video_url": video_url,
        "prompt": cut.get("motion_prompt", "")[:200],
    }
    (OUT_DIR / f"{cid}.meta.json").write_text(json.dumps(meta, ensure_ascii=False, indent=2))
    print(f"  ✓ {cid} OK  cost=${cost:.4f}  -> {out_mp4.name}")
    return meta


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--regen", action="store_true")
    ap.add_argument("--only", help="特定 cut ID")
    ap.add_argument("--scenes", help="comma-separated scene ids e.g. P2,P3 (default all)")
    ap.add_argument("--parallel", type=int, default=2)
    args = ap.parse_args()

    if "FAL_KEY" not in os.environ:
        print("FAL_KEY 未設定", file=sys.stderr)
        return 2

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    WORK_DIR.mkdir(parents=True, exist_ok=True)

    wanted_scenes = set(args.scenes.split(",")) if args.scenes else None
    targets = []
    for c in CUTS:
        if args.only and c["id"] != args.only:
            continue
        if wanted_scenes and c["scene"] not in wanted_scenes:
            continue
        ok, reason = is_avatar_target(c)
        if not ok:
            print(f"  - {c['id']} skip ({reason})")
            continue
        out = OUT_DIR / f"{c['id']}.mp4"
        if out.exists() and not args.regen:
            print(f"  - {c['id']} already exists (use --regen)")
            continue
        targets.append(c)

    if not targets:
        print("\n対象 cut 無し")
        return 0

    total_cost_est = sum(c["duration"] * PRICE_PER_SEC for c in targets)
    print(f"\n[gen_avatar] {len(targets)} cut, model={MODEL_ID}, parallel={args.parallel}")
    print(f"[gen_avatar] 推定コスト ${total_cost_est:.3f}\n")

    failures = []
    if args.parallel <= 1 or len(targets) == 1:
        for c in targets:
            try:
                process_one(c)
            except Exception as e:  # noqa: BLE001
                print(f"  ✗ {c['id']} FAILED: {e}", file=sys.stderr)
                failures.append(c["id"])
    else:
        with concurrent.futures.ThreadPoolExecutor(max_workers=args.parallel) as ex:
            futures = {ex.submit(process_one, c): c for c in targets}
            for fut in concurrent.futures.as_completed(futures):
                c = futures[fut]
                try:
                    fut.result()
                except Exception as e:  # noqa: BLE001
                    print(f"  ✗ {c['id']} FAILED: {e}", file=sys.stderr)
                    failures.append(c["id"])

    print(f"\n[gen_avatar] done  success={len(targets)-len(failures)}/{len(targets)}")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
