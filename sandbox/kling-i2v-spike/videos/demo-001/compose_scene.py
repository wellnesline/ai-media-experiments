"""PoC 001 — 指定 SCENE の cuts を trim → concat → audio overlay で 1 本に統合.

compose_p1.py の汎用版。 --scene 引数で P1/P2/P3/P4/P5 を指定。

出力:
  clips/{scene}_combined_silent.mp4
  clips/{scene}_combined.mp4
  review/demo-001_{scene}_combined.mp4
"""
from __future__ import annotations

import argparse
import importlib.util
import json
import re
import subprocess
import sys
from pathlib import Path

import os
from PIL import Image, ImageDraw, ImageFont

HERE = Path(__file__).resolve().parent
INPUT_CUTS_DIR = HERE / "input_cuts"
CLIPS_DIR = HERE / "clips"
CLIPS_LIPSYNC_DIR = HERE / "clips_lipsync"
CLIPS_AVATAR_DIR = HERE / "clips_avatar"
CLIPS_FABRIC_DIR = HERE / "clips_fabric"
CLIPS_VIDU_DIR = HERE / "clips_vidu"
AUDIO_LINES_DIR = HERE / "audio_lines"
TRIM_DIR = CLIPS_DIR / "_trimmed"
SUBTITLE_LAYER_DIR = HERE / "_subtitle_layers"

FINAL_W = 1920
FINAL_H = 1080

JP_FONT = os.environ["JP_FONT_BOLD_PATH"]  # 太字フォントのパスを環境変数で渡す(既定値なし)


def source_clip(cut: dict) -> tuple[Path, str]:
    """優先順位:
      1. anim_method='static' → input_cuts/CXXX.png を ffmpeg で静止 mp4 化 (コスト 0)
      2. clips_vidu > clips_fabric > clips_avatar > clips_lipsync > clips (動画ソース)
         clips_vidu は Vidu Q1 anime mode による dramatic motion cut 専用 ($0.40/5sec)
    """
    cid = cut["id"]
    if cut.get("anim_method") == "static":
        png = INPUT_CUTS_DIR / f"{cid}.png"
        if png.exists():
            return png, "static"
        # fallback to video if static png missing
    vidu = CLIPS_VIDU_DIR / f"{cid}.mp4"
    if vidu.exists():
        return vidu, "vidu"
    fabric = CLIPS_FABRIC_DIR / f"{cid}.mp4"
    if fabric.exists():
        return fabric, "fabric"
    avatar = CLIPS_AVATAR_DIR / f"{cid}.mp4"
    if avatar.exists():
        return avatar, "avatar"
    lipsync = CLIPS_LIPSYNC_DIR / f"{cid}.mp4"
    if lipsync.exists():
        return lipsync, "lipsync"
    return CLIPS_DIR / f"{cid}.mp4", "i2v"


# cuts.py + timing.json
spec = importlib.util.spec_from_file_location("cuts", HERE / "cuts.py")
cuts_mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(cuts_mod)
ALL_CUTS = cuts_mod.CUTS

with open(HERE / "timing.json") as f:
    TIMING = json.load(f)


def run_ff(cmd: list[str]) -> None:
    proc = subprocess.run(cmd, capture_output=True, text=True)
    if proc.returncode != 0:
        print(f"[ffmpeg ERROR] cmd: {' '.join(cmd[:6])}...", file=sys.stderr)
        print(proc.stderr[-2000:], file=sys.stderr)
        raise RuntimeError("ffmpeg failed")


# ── 字幕 layer 生成 (動画下部 白文字+黒縁) ──────────────────────────────

_TAG_RE = re.compile(r"\[[^\]]+\]")


def _strip_tags(text: str) -> str:
    return _TAG_RE.sub("", text).strip()


def _wrap_japanese(text: str, font: ImageFont.FreeTypeFont, max_w: int) -> list[str]:
    lines: list[str] = []
    cur = ""
    for ch in text:
        cand = cur + ch
        bbox = font.getbbox(cand)
        if (bbox[2] - bbox[0]) > max_w and cur:
            lines.append(cur)
            cur = ch
        else:
            cur = cand
    if cur:
        lines.append(cur)
    return lines


def build_line_windows(cuts: list) -> list[dict]:
    """各 line の (video_start, video_end, full_text) を計算.

    audio 配置ルールに従って line ごとに video 上の [start, end] を求め、
    full_text は timing.json から scene line text を取得 (strip_tags 済)。
    """
    windows = []
    video_offset = 0.0
    placed = set()
    for c in cuts:
        for cov in c.get("covers_lines", []):
            key = (cov["scene"], cov["idx"])
            if key in placed:
                continue
            sid, lidx = key
            line_info = TIMING["scenes"][sid]["lines"][lidx]
            text = _strip_tags(line_info["text"])
            duration = float(line_info["duration"])
            windows.append({
                "scene": sid,
                "idx": lidx,
                "video_start": video_offset,
                "video_end": video_offset + duration,
                "full_text": text,
            })
            placed.add(key)
        video_offset += float(c["duration"])
    return windows


def get_subtitle_text(cut_id: str, cuts: list, windows: list[dict]) -> str | None:
    """cut の video 時間帯と重なる line の full_text を返す."""
    cum = 0.0
    cut_start = cut_end = None
    for c in cuts:
        if c["id"] == cut_id:
            cut_start = cum
            cut_end = cum + float(c["duration"])
            break
        cum += float(c["duration"])
    if cut_start is None:
        return None
    # 重なる line を探す (両端 0.05s マージン)
    for w in windows:
        if w["video_start"] < cut_end - 0.05 and w["video_end"] > cut_start + 0.05:
            return w["full_text"]
    return None


def make_subtitle_layer(cut_id: str, text: str | None) -> Path | None:
    """指定 text で動画下部 字幕 layer (透過 PNG) を生成.

    text 無し / 注記形式 / 空 は None。
    """
    if not text:
        return None
    text = text.strip()
    if not text or text.startswith("(") or "セリフ無し" in text:
        return None

    SUBTITLE_LAYER_DIR.mkdir(parents=True, exist_ok=True)
    layer_path = SUBTITLE_LAYER_DIR / f"{cut_id}_sub.png"

    layer = Image.new("RGBA", (FINAL_W, FINAL_H), (0, 0, 0, 0))
    draw = ImageDraw.Draw(layer)

    # フォントサイズ (max 2 行に収まるように自動縮小)
    fs = 56
    max_w = int(FINAL_W * 0.85)
    font = ImageFont.truetype(JP_FONT, fs)
    lines = _wrap_japanese(text, font, max_w)
    while len(lines) > 2 and fs > 32:
        fs -= 4
        font = ImageFont.truetype(JP_FONT, fs)
        lines = _wrap_japanese(text, font, max_w)
    # それでも 3 行以上なら font さらに縮小
    while len(lines) > 3 and fs > 24:
        fs -= 2
        font = ImageFont.truetype(JP_FONT, fs)
        lines = _wrap_japanese(text, font, max_w)

    line_h = int(fs * 1.25)
    total_h = len(lines) * line_h
    bottom_pad = 80
    sy = FINAL_H - total_h - bottom_pad

    for i, line in enumerate(lines):
        bbox = font.getbbox(line)
        lw = bbox[2] - bbox[0]
        x = (FINAL_W - lw) // 2
        y = sy + i * line_h
        # 白文字 + 黒縁 (stroke)
        draw.text((x, y), line, font=font, fill=(255, 255, 255),
                  stroke_width=5, stroke_fill=(0, 0, 0))

    layer.save(layer_path, "PNG")
    return layer_path


# (bubble 関連コードは削除 — subtitle 方式に統一)


def trim_clips(cuts: list, scene_label: str, all_cuts: list = None) -> list[Path]:
    if all_cuts is None:
        all_cuts = cuts
    # line-based subtitle のために事前計算
    line_windows = build_line_windows(all_cuts)
    """各 cut を target duration に trim + 1920x1080 統一.

    - anim_method='static' な cut は PNG (input_cuts/CXXX.png) を ffmpeg で
      duration ぶんの静止 mp4 に変換 (-loop 1)。 Kling i2v コスト 0 で代替。
    - 動画ソースの場合、 cut.freeze_after が指定されてれば
      motion 部 (freeze_after 秒) + 最終フレーム freeze で cut.duration まで埋める。
    """
    trim_dir = TRIM_DIR / scene_label
    trim_dir.mkdir(parents=True, exist_ok=True)
    scale_pad = (
        f"scale={FINAL_W}:{FINAL_H}:force_original_aspect_ratio=decrease,"
        f"pad={FINAL_W}:{FINAL_H}:(ow-iw)/2:(oh-ih)/2:color=black,"
        f"setsar=1"
    )
    trimmed = []
    for cut in cuts:
        src, src_tag = source_clip(cut)
        dst = trim_dir / f"{cut['id']}_trim.mp4"
        if not src.exists():
            raise FileNotFoundError(f"clip missing: {src}")
        target_dur = float(cut["duration"])

        # subtitle layer (line 単位): cut の時間帯と重なる line の full_text を字幕に
        sub_text = get_subtitle_text(cut["id"], all_cuts, line_windows)
        sub_layer = make_subtitle_layer(cut["id"], sub_text)

        def _build_cmd(input_args: list[str], vf_chain: str, output_t: float | None) -> list[str]:
            """subtitle あり/なし で ffmpeg コマンドを組み立て.

            output_t: -t を出力 option として末尾に置く秒数 (None なら省略)。
            input_args: 1st 入力までの options + -i src (-t は含めない)
            """
            cmd_x = ["ffmpeg", "-y", "-loglevel", "error"] + input_args
            if sub_layer:
                # 2nd 入力 (sub_layer PNG)。 必ず -loop 1 で同じ duration 維持
                cmd_x += ["-loop", "1", "-i", str(sub_layer)]
            if output_t is not None:
                cmd_x += ["-t", f"{output_t:.3f}"]
            if sub_layer:
                cmd_x += [
                    "-filter_complex",
                    f"[0:v]{vf_chain}[bg];[bg][1:v]overlay=0:0:format=auto[v]",
                    "-map", "[v]",
                ]
            else:
                cmd_x += ["-vf", vf_chain]
            cmd_x += [
                "-c:v", "libx264", "-crf", "18", "-preset", "fast",
                "-pix_fmt", "yuv420p",
                "-r", "24",
                "-an",
                str(dst),
            ]
            return cmd_x

        bubble_tag = " +sub" if sub_layer else ""

        if src_tag == "static":
            print(f"  trim {cut['id']}  to {target_dur:.2f}s  (src=static PNG){bubble_tag}")
            run_ff(_build_cmd(
                ["-loop", "1", "-i", str(src)],
                scale_pad,
                target_dur,
            ))
            trimmed.append(dst)
            continue

        freeze_after = cut.get("freeze_after")
        if freeze_after and 0 < float(freeze_after) < target_dur:
            motion_dur = float(freeze_after)
            freeze_dur = target_dur - motion_dur
            print(f"  trim {cut['id']}  to {target_dur:.2f}s  (src={src_tag}){bubble_tag}  "
                  f"motion={motion_dur:.2f}s + freeze={freeze_dur:.2f}s")
            vf = (
                f"trim=duration={motion_dur:.3f},setpts=PTS-STARTPTS,"
                f"tpad=stop_mode=clone:stop_duration={freeze_dur:.3f},"
                f"{scale_pad}"
            )
            run_ff(_build_cmd(["-i", str(src)], vf, target_dur))
        else:
            print(f"  trim {cut['id']}  to {target_dur:.2f}s  (src={src_tag}){bubble_tag}")
            run_ff(_build_cmd(["-i", str(src)], scale_pad, target_dur))
        trimmed.append(dst)
    return trimmed


def concat_silent(trimmed: list[Path], out_silent: Path) -> None:
    list_path = out_silent.parent / "concat_list.txt"
    list_path.write_text("\n".join(f"file '{p.resolve()}'" for p in trimmed))
    print(f"  concat -> {out_silent.name}")
    run_ff([
        "ffmpeg", "-y", "-loglevel", "error",
        "-f", "concat", "-safe", "0",
        "-i", str(list_path),
        "-c", "copy",
        str(out_silent),
    ])


def compute_audio_placement(cuts: list) -> tuple[list[tuple[Path, float]], float]:
    placements = []
    video_offset = 0.0
    placed_keys = set()
    for cut in cuts:
        for cov in cut["covers_lines"]:
            key = (cov["scene"], cov["idx"])
            if key in placed_keys:
                continue
            sid, lidx = key
            line_info = TIMING["scenes"][sid]["lines"][lidx]
            speaker = line_info["speaker"]
            wav = AUDIO_LINES_DIR / f"{sid}_l{lidx:02d}_{speaker}.wav"
            if not wav.exists():
                raise FileNotFoundError(f"audio missing: {wav}")
            placements.append((wav, video_offset))
            placed_keys.add(key)
            print(f"  audio {wav.name:32s} at video offset {video_offset:.2f}s")
        video_offset += cut["duration"]
    return placements, video_offset


def merge_audio(silent_video: Path, placements, total_dur: float, out_final: Path) -> None:
    cmd = ["ffmpeg", "-y", "-loglevel", "error", "-i", str(silent_video)]
    for wav, _ in placements:
        cmd += ["-i", str(wav)]
    cmd += ["-f", "lavfi", "-t", f"{total_dur:.3f}",
            "-i", "anullsrc=channel_layout=stereo:sample_rate=44100"]
    filter_parts = []
    amix_inputs = []
    for i, (_, delay_sec) in enumerate(placements, start=1):
        delay_ms = int(round(delay_sec * 1000))
        filter_parts.append(
            f"[{i}:a]aresample=44100,aformat=channel_layouts=stereo,"
            f"adelay={delay_ms}|{delay_ms}[a{i}]"
        )
        amix_inputs.append(f"[a{i}]")
    silence_idx = len(placements) + 1
    amix_inputs.append(f"[{silence_idx}:a]")
    filter_parts.append(
        f"{''.join(amix_inputs)}amix=inputs={len(amix_inputs)}:"
        f"duration=longest:dropout_transition=0:normalize=0[aout]"
    )
    cmd += [
        "-filter_complex", ";".join(filter_parts),
        "-map", "0:v", "-map", "[aout]",
        "-c:v", "copy",
        "-c:a", "aac", "-b:a", "192k",
        "-shortest",
        str(out_final),
    ]
    print(f"  merge audio + video -> {out_final.name}")
    run_ff(cmd)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--scene", required=True, help="scene id e.g. P2")
    args = ap.parse_args()

    cuts = [c for c in ALL_CUTS if c["scene"] == args.scene]
    if not cuts:
        print(f"no cuts for scene {args.scene}", file=sys.stderr)
        return 2

    label = args.scene.lower()
    out_silent = CLIPS_DIR / f"{label}_combined_silent.mp4"
    out_final = CLIPS_DIR / f"{label}_combined.mp4"
    review_out = HERE.parents[3] / "review" / f"demo-001_{label}_combined.mp4"

    print(f"\n[compose {args.scene}] {len(cuts)} cuts")
    print("\n[1/3] trim clips")
    trimmed = trim_clips(cuts, label)

    print("\n[2/3] concat silent video")
    concat_silent(trimmed, out_silent)

    print("\n[3/3] compute audio placements + merge")
    placements, total_dur = compute_audio_placement(cuts)
    print(f"  total video duration: {total_dur:.2f}s")
    merge_audio(out_silent, placements, total_dur, out_final)

    review_out.parent.mkdir(parents=True, exist_ok=True)
    subprocess.run(["cp", str(out_final), str(review_out)], check=True)
    print(f"\n[done]")
    print(f"  final : {out_final}")
    print(f"  review: {review_out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
