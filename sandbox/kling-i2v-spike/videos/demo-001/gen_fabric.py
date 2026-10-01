"""PoC 001 — VEED Fabric 1.0 480p で talking head 試作.

Kling Avatar v2 Pro ($0.115/sec) の比較検証目的:
  - エンドポイント: veed/fabric-1.0
  - 入力: image + audio (prompt 不要)
  - 出力: 480p mp4 → ffmpeg で 1080p に upscale (lanczos)
  - 料金: $0.08/sec (480p) - Kling 比 30% 安

C012 で 1 cut だけ試作 → 品質確認 → OK なら P3-P5 で採用検討。

Usage:
  python gen_fabric.py --only C012
"""
from __future__ import annotations

import argparse
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
OUT_DIR = HERE / "clips_fabric"
WORK_DIR = OUT_DIR / "_work"

MODEL_ID = "veed/fabric-1.0"
RESOLUTION = "720p"          # "480p" ($0.08) or "720p" ($0.15)
PRICE_PER_SEC = {"480p": 0.08, "720p": 0.15}[RESOLUTION]

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


def slice_audio(cut: dict, dst: Path) -> Path:
    parts = []
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
        else:
            seg = WORK_DIR / f"{cut['id']}_seg_{sid}_l{lidx:02d}.wav"
            run_ff([
                "ffmpeg", "-y", "-loglevel", "error",
                "-i", str(src_wav),
                "-ss", f"{rng[0]:.3f}", "-to", f"{rng[1]:.3f}",
                "-c:a", "pcm_s16le", str(seg),
            ])
            parts.append(seg)
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
    run_ff([
        "ffmpeg", "-y", "-loglevel", "error",
        "-i", str(audio_in),
        "-af", f"apad=whole_dur={target_sec:.3f}",
        "-t", f"{target_sec:.3f}",
        "-c:a", "pcm_s16le", str(audio_out),
    ])


def get_dur(audio: Path) -> float:
    r = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration",
         "-of", "default=noprint_wrappers=1:nokey=1", str(audio)],
        capture_output=True, text=True, check=True,
    )
    return float(r.stdout.strip())


def process_one(cut: dict) -> dict:
    cid = cut["id"]
    print(f"\n[{cid}] {cut['kind']} {cut['shot_size']} target_dur={cut['duration']:.2f}s")

    image_path = INPUT_CUTS_DIR / f"{cid}.png"
    if not image_path.exists():
        raise FileNotFoundError(f"still missing: {image_path}")

    sliced_audio = WORK_DIR / f"{cid}_audio_raw.wav"
    final_audio = WORK_DIR / f"{cid}_audio.wav"
    slice_audio(cut, sliced_audio)
    a_dur = get_dur(sliced_audio)

    target = cut["duration"]
    if abs(a_dur - target) > 0.05:
        pad_audio_to(sliced_audio, target, final_audio)
        print(f"  audio padded {a_dur:.2f}s -> {target:.2f}s")
    else:
        final_audio = sliced_audio
        print(f"  audio {a_dur:.2f}s ≈ target {target:.2f}s")

    print(f"  {cid}: uploading image + audio...")
    image_url = fal_client.upload_file(str(image_path))
    audio_url = fal_client.upload_file(str(final_audio))

    payload = {
        "image_url": image_url,
        "audio_url": audio_url,
        "resolution": RESOLUTION,
    }
    print(f"  {cid}: invoking VEED Fabric 1.0 ({RESOLUTION})...")
    t0 = time.time()
    result = fal_client.subscribe(MODEL_ID, arguments=payload, with_logs=False)
    elapsed = time.time() - t0
    video_url = result["video"]["url"]
    print(f"  {cid}: done in {elapsed:.1f}s, url={video_url[:80]}...")

    raw_out = OUT_DIR / f"{cid}_{RESOLUTION}.mp4"
    out_mp4 = OUT_DIR / f"{cid}.mp4"
    urllib.request.urlretrieve(video_url, raw_out)

    # 1080p upscale (lanczos)
    print(f"  {cid}: upscaling {RESOLUTION} -> 1920x1080 (lanczos)...")
    run_ff([
        "ffmpeg", "-y", "-loglevel", "error",
        "-i", str(raw_out),
        "-vf", "scale=1920:1080:flags=lanczos",
        "-c:v", "libx264", "-crf", "18", "-preset", "fast",
        "-pix_fmt", "yuv420p",
        "-c:a", "copy",
        str(out_mp4),
    ])

    cost = PRICE_PER_SEC * target
    meta = {
        "cut_id": cid,
        "model": MODEL_ID,
        "resolution": RESOLUTION,
        "target_duration": round(target, 3),
        "audio_duration_in": round(a_dur, 3),
        "elapsed_sec": round(elapsed, 1),
        "cost_usd": round(cost, 4),
        "video_url": video_url,
        f"raw_{RESOLUTION}_path": str(raw_out.name),
    }
    (OUT_DIR / f"{cid}.meta.json").write_text(json.dumps(meta, ensure_ascii=False, indent=2))
    print(f"  ✓ {cid} OK  cost=${cost:.4f}  -> {out_mp4.name} (upscaled 1080p)")
    return meta


def is_fabric_target(cut: dict) -> tuple[bool, str]:
    """Cut が fabric 対象 (= talking avatar) かどうか."""
    if cut.get("anim_method") != "kling":
        return False, "not kling"
    if not cut.get("covers_lines"):
        return False, "no dialogue"
    if cut["main_char"] == "none":
        return False, "no character"
    if cut["shot_size"] in ("ECU",):
        return False, "ECU (no mouth visible)"
    return True, "OK"


def main() -> int:
    import concurrent.futures
    ap = argparse.ArgumentParser()
    ap.add_argument("--only", help="特定 cut ID")
    ap.add_argument("--scenes", help="comma-separated scene ids e.g. P2,P3 (default all)")
    ap.add_argument("--regen", action="store_true")
    ap.add_argument("--parallel", type=int, default=3)
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
        ok, reason = is_fabric_target(c)
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
    print(f"\n[gen_fabric] {len(targets)} cuts, model={MODEL_ID}, res={RESOLUTION}, "
          f"${PRICE_PER_SEC}/sec, parallel={args.parallel}")
    print(f"[gen_fabric] 推定コスト ${total_cost_est:.3f}\n")

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

    print(f"\n[gen_fabric] done  success={len(targets)-len(failures)}/{len(targets)}")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
