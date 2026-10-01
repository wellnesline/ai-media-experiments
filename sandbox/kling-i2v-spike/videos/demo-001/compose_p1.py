"""PoC 001 v2 — P1 6 cuts を trim → concat → audio overlay で 1 本に統合.

Audio 配置ルール:
  - 各 line は、 covers_lines で初登場する cut の開始時刻に配置
  - 同一 line を複数 cut が covers する場合は最初の cut で開始、 audio は連続再生
  - line 間は元の pause_after を尊重(line N 終了 + pause で line N+1 を配置)
  - 解説: 「リアクションショット中も audio 続く」 を実現

出力:
  clips/p1_combined_silent.mp4   (映像のみ、 13.0s)
  clips/p1_combined.mp4          (映像+音声、 最終)
  review/demo-001_p1_combined.mp4
"""
from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
CLIPS_DIR = HERE / "clips"
CLIPS_LIPSYNC_DIR = HERE / "clips_lipsync"
CLIPS_AVATAR_DIR = HERE / "clips_avatar"
AUDIO_LINES_DIR = HERE / "audio_lines"
TRIM_DIR = CLIPS_DIR / "_trimmed"
OUT_SILENT = CLIPS_DIR / "p1_combined_silent.mp4"
OUT_FINAL = CLIPS_DIR / "p1_combined.mp4"
REVIEW_OUT = HERE.parents[3] / "review" / "demo-001_p1_combined.mp4"

# 出力先解像度 (Avatar v2 Pro が 1920x1072、 i2v が 1280x720 で混在するので統一)
FINAL_W = 1920
FINAL_H = 1080


def source_clip(cut_id: str) -> tuple[Path, str]:
    """優先順位: clips_avatar/ > clips_lipsync/ > clips/  (高品質順)."""
    avatar = CLIPS_AVATAR_DIR / f"{cut_id}.mp4"
    if avatar.exists():
        return avatar, "avatar"
    lipsync = CLIPS_LIPSYNC_DIR / f"{cut_id}.mp4"
    if lipsync.exists():
        return lipsync, "lipsync"
    return CLIPS_DIR / f"{cut_id}.mp4", "i2v"

# cuts.py + timing.json
spec = importlib.util.spec_from_file_location("cuts", HERE / "cuts.py")
cuts_mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(cuts_mod)
CUTS = cuts_mod.CUTS

with open(HERE / "timing.json") as f:
    TIMING = json.load(f)


def run_ff(cmd: list[str]) -> None:
    """ffmpeg 実行(エラー時は stderr 出力)."""
    proc = subprocess.run(cmd, capture_output=True, text=True)
    if proc.returncode != 0:
        print(f"[ffmpeg ERROR] cmd: {' '.join(cmd[:6])}...", file=sys.stderr)
        print(proc.stderr[-2000:], file=sys.stderr)
        raise RuntimeError("ffmpeg failed")


def trim_clips() -> list[Path]:
    """各 cut を target duration に trim + 1920x1080 へ統一スケール (libx264).

    Clip ソース優先順位: clips_avatar/ > clips_lipsync/ > clips/.
    解像度: Avatar 1920x1072, i2v 1280x720 混在 → scale + pad で 1920x1080 に統一.
    """
    TRIM_DIR.mkdir(parents=True, exist_ok=True)
    trimmed = []
    for cut in CUTS:
        src, src_tag = source_clip(cut["id"])
        dst = TRIM_DIR / f"{cut['id']}_trim.mp4"
        if not src.exists():
            raise FileNotFoundError(f"clip missing: {src}")
        print(f"  trim {cut['id']}  to {cut['duration']:.2f}s  (src={src_tag})")
        vf = (
            f"scale={FINAL_W}:{FINAL_H}:force_original_aspect_ratio=decrease,"
            f"pad={FINAL_W}:{FINAL_H}:(ow-iw)/2:(oh-ih)/2:color=black,"
            f"setsar=1"
        )
        run_ff([
            "ffmpeg", "-y", "-loglevel", "error",
            "-i", str(src),
            "-t", f"{cut['duration']:.3f}",
            "-vf", vf,
            "-c:v", "libx264", "-crf", "18", "-preset", "fast",
            "-pix_fmt", "yuv420p",
            "-r", "24",
            "-an",
            str(dst),
        ])
        trimmed.append(dst)
    return trimmed


def concat_silent(trimmed: list[Path]) -> None:
    """concat demuxer で結合(無音)."""
    list_path = TRIM_DIR / "concat_list.txt"
    list_path.write_text("\n".join(f"file '{p.resolve()}'" for p in trimmed))
    print(f"  concat -> {OUT_SILENT.name}")
    run_ff([
        "ffmpeg", "-y", "-loglevel", "error",
        "-f", "concat", "-safe", "0",
        "-i", str(list_path),
        "-c", "copy",
        str(OUT_SILENT),
    ])


def compute_audio_placement() -> tuple[list[tuple[Path, float]], float]:
    """各 line wav の (path, 開始 video offset 秒) を計算.

    ロジック:
      - 各 cut の covers_lines を順に走査
      - 初登場 line は、 その cut の開始 video offset で開始
      - 同じ line が次の cut でも続く場合は無視(audio は連続)
      - 異なる line に切り替わる時、 直前 line の終了 + pause_after を尊重
    """
    placements: list[tuple[Path, float]] = []
    video_offset = 0.0
    placed_line_keys: set[tuple[str, int]] = set()

    for cut in CUTS:
        for cov in cut["covers_lines"]:
            key = (cov["scene"], cov["idx"])
            if key in placed_line_keys:
                continue
            sid, lidx = key
            line_info = TIMING["scenes"][sid]["lines"][lidx]
            speaker = line_info["speaker"]
            wav = AUDIO_LINES_DIR / f"{sid}_l{lidx:02d}_{speaker}.wav"
            if not wav.exists():
                raise FileNotFoundError(f"audio missing: {wav}")
            placements.append((wav, video_offset))
            placed_line_keys.add(key)
            print(f"  audio {wav.name:32s} at video offset {video_offset:.2f}s")
        video_offset += cut["duration"]

    total_video_dur = video_offset
    return placements, total_video_dur


def merge_audio(placements: list[tuple[Path, float]], total_dur: float) -> None:
    """video + 複数 wav (各 delay 付き) を amix で結合."""
    cmd = ["ffmpeg", "-y", "-loglevel", "error", "-i", str(OUT_SILENT)]
    for wav, _ in placements:
        cmd += ["-i", str(wav)]
    # 全長ぶんの無音 base を amix の duration アンカーに
    cmd += ["-f", "lavfi", "-t", f"{total_dur:.3f}",
            "-i", "anullsrc=channel_layout=stereo:sample_rate=44100"]

    filter_parts = []
    amix_inputs = []
    for i, (_, delay_sec) in enumerate(placements, start=1):
        delay_ms = int(round(delay_sec * 1000))
        # adelay は ch ごとに ms 指定。 mono 入力でも stereo に upmix
        filter_parts.append(f"[{i}:a]aresample=44100,aformat=channel_layouts=stereo,adelay={delay_ms}|{delay_ms}[a{i}]")
        amix_inputs.append(f"[a{i}]")
    silence_idx = len(placements) + 1
    amix_inputs.append(f"[{silence_idx}:a]")
    filter_parts.append(
        f"{''.join(amix_inputs)}amix=inputs={len(amix_inputs)}:duration=longest:dropout_transition=0:normalize=0[aout]"
    )

    cmd += [
        "-filter_complex", ";".join(filter_parts),
        "-map", "0:v", "-map", "[aout]",
        "-c:v", "copy",
        "-c:a", "aac", "-b:a", "192k",
        "-shortest",
        str(OUT_FINAL),
    ]
    print(f"  merge audio + video -> {OUT_FINAL.name}")
    run_ff(cmd)


def main() -> int:
    if not CLIPS_DIR.exists():
        print(f"clips dir not found: {CLIPS_DIR}", file=sys.stderr)
        return 2

    print("\n[1/3] trim clips to target duration")
    trimmed = trim_clips()

    print("\n[2/3] concat silent video")
    concat_silent(trimmed)

    print("\n[3/3] compute audio placements + merge")
    placements, total_dur = compute_audio_placement()
    print(f"  total video duration: {total_dur:.2f}s")
    merge_audio(placements, total_dur)

    REVIEW_OUT.parent.mkdir(parents=True, exist_ok=True)
    subprocess.run(["cp", str(OUT_FINAL), str(REVIEW_OUT)], check=True)
    print(f"\n[done]")
    print(f"  final : {OUT_FINAL}")
    print(f"  review: {REVIEW_OUT}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
