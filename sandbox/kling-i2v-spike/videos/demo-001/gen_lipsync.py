"""PoC 001 v2 — Kling LipSync で口パクをセリフに同期.

入力:
  clips/{cut_id}.mp4              (gen_clips.py の出力、 Kling i2v 5秒)
  audio_lines/{scene}_l{idx}_{speaker}.wav  (synth_with_timing.py の出力)

ロジック:
  1. cuts.py を読み、 covers_lines がある cut だけ対象
  2. cut の duration に合わせて video を trim (3.6s, etc.)
  3. covers_lines.range に従って line wav から該当区間を slice
  4. Kling LipSync (fal-ai/kling-video/lipsync/audio-to-video) に投入
  5. clips_lipsync/{cut_id}.mp4 として保存

費用:
  $0.014 / 5秒インクリメント (3.6s → 5秒分課金 = $0.014)

注意:
  - LipSync は処理 ~12分/本 と遅い (精度優先設計)
  - 並列実行可
  - 2秒未満の video は対象外 (C003 0.7s 等は呼ばない)

Usage:
  python gen_lipsync.py --only C012                # 単発テスト
  python gen_lipsync.py                            # セリフ全 cut
  python gen_lipsync.py --regen --only C012
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
CLIPS_DIR = HERE / "clips"
AUDIO_LINES_DIR = HERE / "audio_lines"
OUT_DIR = HERE / "clips_lipsync"
WORK_DIR = OUT_DIR / "_work"

MODEL_ID = "fal-ai/kling-video/lipsync/audio-to-video"
PRICE_PER_5S = 0.014
MIN_DURATION = 2.0   # LipSync 最小入力

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


def is_lipsync_target(cut: dict) -> tuple[bool, str]:
    """Cut が lipsync 対象かどうか + 理由."""
    if cut.get("anim_method") != "kling":
        return False, "not kling"
    if not cut.get("covers_lines"):
        return False, "no dialogue"
    if cut["main_char"] == "none":
        return False, "no character"
    if cut["duration"] < MIN_DURATION:
        return False, f"under {MIN_DURATION}s min"
    if cut["shot_size"] in ("ECU",):
        # ECU は目元等の極端な寄りで口元が映らないことが多い → デフォルト除外
        # 必要なら個別に force_lipsync フラグで上書き可
        return False, "ECU (no mouth visible)"
    return True, "OK"


def slice_audio(cut: dict, dst: Path) -> Path:
    """cut.covers_lines を元に audio segment を抽出 (複数行は concat)."""
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
            # 行全体
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
        # 単一 segment ならそのまま
        run_ff([
            "ffmpeg", "-y", "-loglevel", "error",
            "-i", str(parts[0]),
            "-c:a", "pcm_s16le",
            str(dst),
        ])
    else:
        # concat
        list_path = WORK_DIR / f"{cut['id']}_audio_list.txt"
        list_path.write_text("\n".join(f"file '{p.resolve()}'" for p in parts))
        run_ff([
            "ffmpeg", "-y", "-loglevel", "error",
            "-f", "concat", "-safe", "0",
            "-i", str(list_path),
            "-c:a", "pcm_s16le",
            str(dst),
        ])
    return dst


def trim_video(cut: dict, dst: Path) -> Path:
    """clips/{cut_id}.mp4 を cut.duration に trim."""
    src = CLIPS_DIR / f"{cut['id']}.mp4"
    if not src.exists():
        raise FileNotFoundError(f"i2v clip missing: {src}")
    run_ff([
        "ffmpeg", "-y", "-loglevel", "error",
        "-i", str(src),
        "-t", f"{cut['duration']:.3f}",
        "-c:v", "libx264", "-crf", "18", "-preset", "fast",
        "-pix_fmt", "yuv420p",
        "-an",
        str(dst),
    ])
    return dst


def upload_and_lipsync(video_path: Path, audio_path: Path, cut_id: str) -> str:
    """Fal にファイルを upload → LipSync 呼び出し → 出力 video URL."""
    print(f"  {cut_id}: uploading video + audio to Fal storage...")
    video_url = fal_client.upload_file(str(video_path))
    audio_url = fal_client.upload_file(str(audio_path))

    payload = {
        "video_url": video_url,
        "audio_url": audio_url,
    }
    print(f"  {cut_id}: invoking Kling LipSync (~minutes)...")
    t0 = time.time()
    result = fal_client.subscribe(MODEL_ID, arguments=payload, with_logs=False)
    elapsed = time.time() - t0
    print(f"  {cut_id}: lipsync done in {elapsed:.1f}s")
    return result["video"]["url"]


def process_one(cut: dict) -> dict:
    cid = cut["id"]
    print(f"\n[{cid}] {cut['kind']} {cut['shot_size']} {cut['duration']:.2f}s  main={cut['main_char']}")

    # 1) 入力素材を一時生成
    trimmed_video = WORK_DIR / f"{cid}_video.mp4"
    sliced_audio = WORK_DIR / f"{cid}_audio.wav"
    trim_video(cut, trimmed_video)
    slice_audio(cut, sliced_audio)

    # 2) 上限チェック (LipSync は 2-10秒)
    v_dur = float(subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration",
         "-of", "default=noprint_wrappers=1:nokey=1", str(trimmed_video)],
        capture_output=True, text=True, check=True).stdout.strip())
    a_dur = float(subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration",
         "-of", "default=noprint_wrappers=1:nokey=1", str(sliced_audio)],
        capture_output=True, text=True, check=True).stdout.strip())
    print(f"  inputs(pre): video {v_dur:.2f}s, audio {a_dur:.2f}s")

    # audio が video より短い場合、 末尾を silence pad (口閉じる)
    if a_dur < v_dur - 0.05:
        padded = WORK_DIR / f"{cid}_audio_padded.wav"
        pad_sec = v_dur - a_dur
        run_ff([
            "ffmpeg", "-y", "-loglevel", "error",
            "-i", str(sliced_audio),
            "-af", f"apad=pad_dur={pad_sec:.3f}",
            "-t", f"{v_dur:.3f}",
            "-c:a", "pcm_s16le",
            str(padded),
        ])
        sliced_audio = padded
        a_dur = float(subprocess.run(
            ["ffprobe", "-v", "error", "-show_entries", "format=duration",
             "-of", "default=noprint_wrappers=1:nokey=1", str(sliced_audio)],
            capture_output=True, text=True, check=True).stdout.strip())
        print(f"  pad silence -> audio {a_dur:.2f}s")

    # 3) Fal LipSync 呼び出し
    out_url = upload_and_lipsync(trimmed_video, sliced_audio, cid)

    # 4) Download
    out_path = OUT_DIR / f"{cid}.mp4"
    print(f"  {cid}: downloading -> {out_path.name}")
    urllib.request.urlretrieve(out_url, out_path)

    # 5) Meta 保存
    cost = PRICE_PER_5S * max(1, int((v_dur + 4.999) // 5))
    meta = {
        "cut_id": cid,
        "model": MODEL_ID,
        "video_duration": round(v_dur, 3),
        "audio_duration": round(a_dur, 3),
        "cost_usd": round(cost, 4),
        "video_url": out_url,
    }
    (OUT_DIR / f"{cid}.meta.json").write_text(json.dumps(meta, ensure_ascii=False, indent=2))
    print(f"  ✓ {cid} OK  cost=${cost:.4f}")
    return meta


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--regen", action="store_true")
    ap.add_argument("--only", help="特定 cut ID")
    ap.add_argument("--parallel", type=int, default=2)
    args = ap.parse_args()

    if "FAL_KEY" not in os.environ:
        print("FAL_KEY 未設定", file=sys.stderr)
        return 2

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    WORK_DIR.mkdir(parents=True, exist_ok=True)

    # 対象選定
    targets = []
    for c in CUTS:
        if args.only and c["id"] != args.only:
            continue
        ok, reason = is_lipsync_target(c)
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

    print(f"\n[gen_lipsync] 対象 {len(targets)} cut, model={MODEL_ID}, parallel={args.parallel}")

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

    print(f"\n[gen_lipsync] done  success={len(targets)-len(failures)}/{len(targets)}")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
