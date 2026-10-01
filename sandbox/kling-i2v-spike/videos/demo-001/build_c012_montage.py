"""C012「キャラA 工房へ入る」 manga 編集モンタージュ spike.

AI 補間 (Pikaframes) ではなく 漫画編集技法 で動感を作る:
  1. 2 新規 stills 生成:
     - mont_a.png : 庭の小道からドア半開きでキャラA顔覗き (insert風)
     - mont_b.png : キャラA工房に入った瞬間 (ぼやけ動感ポーズ)
  2. 既存 C012 fabric (talking head 3.6s, audio L0 入り) を末尾に接続
  3. ffmpeg で:
     - frame_a (0.5s) + ken-burns push-in
     - 速度線 flash overlay (illustcenter rdesign_7171.png) 0.15s
     - frame_b (0.5s) + ken-burns push-in
     - 速度線 flash 0.15s
     - 既存 fabric C012 (3.6s talking head)
  4. 音声 = 既存 line 0 audio (1.3s offset、 fabric C012 が始まる時から)

出力:
  clips_montage/C012_montage.mp4
  review/demo-001_C012_montage.mp4
"""
from __future__ import annotations

import base64
import io
import os
import subprocess
import sys
import time
from pathlib import Path

from PIL import Image

ROOT = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(ROOT / "src"))
from _dotenv import load_dotenv  # noqa: E402
load_dotenv()
from openai_image_config import DEFAULT_IMAGE_MODEL, DEFAULT_IMAGE_QUALITY  # noqa: E402

from openai import OpenAI  # noqa: E402

HERE = Path(__file__).resolve().parent
REFS_DIR = ROOT / "sandbox" / "character-refs-demo" / "refs"
SPEED_LINES_PNG = ROOT / "sandbox" / "kling-i2v-spike" / "assets" / "bubbles" / "illustcenter" / "rdesign_7171.png"
FABRIC_C012 = HERE / "clips_fabric" / "C012.mp4"           # 既存 talking head
AUDIO_L0 = HERE / "audio_lines" / "P1_l00_char_a.wav"      # 既存 line 0 audio
OUT_DIR = HERE / "clips_montage"
STILLS_DIR = OUT_DIR / "_stills"
WORK_DIR = OUT_DIR / "_work"

FINAL_W = 1920
FINAL_H = 1080
GEN_SIZE = "1536x1024"


# ── still prompts ──
CHAR_DESC = (
    "The reference image shows CHAR_A — the ONLY character. A young adult with "
    "short dark hair, green jacket over a gray shirt, "
    "gray tote bag, white sneakers. Reproduce face, hairstyle, outfit, body "
    "design exactly from the reference."
)
STYLE = (
    "Style: Japanese seinen manga adapted to soft color illustration, hand-drawn "
    "linework, painterly background, expressive manga-style poses."
)
CONSTRAINTS = (
    "STRICT: 16:9 cinematic frame, no text, no speech bubbles, no captions, "
    "no writing, no watermarks."
)

PROMPT_A = (
    "CHAR_A'S FACE PEEKING through a half-open glass-paned wooden door from a "
    "sunny garden path. Only her head and right shoulder visible at the edge of "
    "the open doorway, looking inward. Her expression is excited and "
    "breathless, eyes bright. View from INSIDE the workshop looking back at "
    "the doorway. The door takes the right half of the frame; warm humid light "
    "on the inside, bright garden behind. Wide shot showing tool shelves on the "
    "left half."
)

PROMPT_B = (
    "DYNAMIC ACTION POSE: CHAR_A mid-step, having just walked through the door, "
    "captured mid-stride INSIDE the workshop. Her body leans forward, "
    "one foot lifted in motion, both arms outstretched forward in a cheerful "
    "shouting gesture. Her hair and bag strap swinging with the "
    "movement. Strong sense of motion. View: medium shot from the side-front. "
    "Manga-style motion and a slight forward lean. The workshop background "
    "slightly blurred to emphasize her motion."
)


def run_ff(cmd):
    p = subprocess.run(cmd, capture_output=True, text=True)
    if p.returncode != 0:
        print(p.stderr[-2000:], file=sys.stderr)
        raise RuntimeError(f"ffmpeg failed: {' '.join(cmd[:6])}")


def crop_to_16x9(img: Image.Image) -> Image.Image:
    if img.width != FINAL_W:
        scale = FINAL_W / img.width
        img = img.resize((FINAL_W, int(img.height * scale)), Image.LANCZOS)
    if img.height > FINAL_H:
        top = (img.height - FINAL_H) // 2
        img = img.crop((0, top, FINAL_W, top + FINAL_H))
    return img


def gen_still(client, ref_path, prompt, out_path):
    with open(ref_path, "rb") as f:
        res = client.images.edit(
            model=DEFAULT_IMAGE_MODEL, image=[f], prompt=prompt,
            n=1, size=GEN_SIZE, quality=DEFAULT_IMAGE_QUALITY,
        )
    b64 = res.data[0].b64_json
    img = Image.open(io.BytesIO(base64.b64decode(b64))).convert("RGB")
    crop_to_16x9(img).save(out_path, "PNG")
    print(f"  ✓ {out_path.name}")


def make_kenburns_clip(still_path: Path, out_path: Path, duration: float, zoom_to: float = 1.08):
    """static still を ken-burns 風 (slow push-in) で動かす."""
    fps = 24
    total_frames = int(duration * fps)
    # zoompan filter: simple linear zoom 1.0 → zoom_to
    z_expr = f"min(1+{zoom_to - 1:.4f}*on/{total_frames},{zoom_to:.4f})"
    vf = (
        f"scale={FINAL_W*2}:{FINAL_H*2}:flags=lanczos,"
        f"zoompan=z='{z_expr}':d={total_frames}:"
        f"x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':"
        f"s={FINAL_W}x{FINAL_H}:fps={fps}"
    )
    run_ff([
        "ffmpeg", "-y", "-loglevel", "error",
        "-loop", "1", "-i", str(still_path),
        "-vf", vf,
        "-t", f"{duration:.3f}",
        "-c:v", "libx264", "-crf", "18", "-preset", "fast",
        "-pix_fmt", "yuv420p",
        "-r", str(fps),
        "-an",
        str(out_path),
    ])


def make_speedlines_flash(still_path: Path, out_path: Path, duration: float = 0.15):
    """still + 速度線 overlay を duration 秒分の動画化 (transition flash 用)."""
    fps = 24
    # 速度線 PNG を still サイズに resize + 透過 70% overlay
    run_ff([
        "ffmpeg", "-y", "-loglevel", "error",
        "-loop", "1", "-i", str(still_path),
        "-loop", "1", "-i", str(SPEED_LINES_PNG),
        "-filter_complex",
        f"[0:v]scale={FINAL_W}:{FINAL_H}:force_original_aspect_ratio=decrease,"
        f"pad={FINAL_W}:{FINAL_H}:(ow-iw)/2:(oh-ih)/2:color=black,setsar=1[bg];"
        f"[1:v]scale={FINAL_W}:{FINAL_H}:force_original_aspect_ratio=decrease,"
        f"format=rgba,colorchannelmixer=aa=0.75[sl];"
        f"[bg][sl]overlay=(W-w)/2:(H-h)/2[v]",
        "-map", "[v]",
        "-t", f"{duration:.3f}",
        "-c:v", "libx264", "-crf", "18", "-preset", "fast",
        "-pix_fmt", "yuv420p",
        "-r", str(fps),
        "-an",
        str(out_path),
    ])


def normalize_clip(src: Path, dst: Path, duration: float | None = None):
    """既存 mp4 を 1920x1080 24fps libx264 に統一 (concat 互換性のため)."""
    cmd = ["ffmpeg", "-y", "-loglevel", "error", "-i", str(src)]
    if duration is not None:
        cmd += ["-t", f"{duration:.3f}"]
    vf = (
        f"scale={FINAL_W}:{FINAL_H}:force_original_aspect_ratio=decrease,"
        f"pad={FINAL_W}:{FINAL_H}:(ow-iw)/2:(oh-ih)/2:color=black,setsar=1"
    )
    cmd += [
        "-vf", vf,
        "-c:v", "libx264", "-crf", "18", "-preset", "fast",
        "-pix_fmt", "yuv420p",
        "-r", "24",
        "-an",
        str(dst),
    ]
    run_ff(cmd)


def main():
    for var in ["OPENAI_API_KEY"]:
        if var not in os.environ:
            print(f"missing env: {var}", file=sys.stderr)
            return 2
    if not SPEED_LINES_PNG.exists():
        print(f"speed lines PNG missing: {SPEED_LINES_PNG}", file=sys.stderr)
        return 2
    if not FABRIC_C012.exists():
        print(f"existing Fabric C012 missing: {FABRIC_C012}", file=sys.stderr)
        return 2
    if not AUDIO_L0.exists():
        print(f"audio L0 missing: {AUDIO_L0}", file=sys.stderr)
        return 2

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    STILLS_DIR.mkdir(parents=True, exist_ok=True)
    WORK_DIR.mkdir(parents=True, exist_ok=True)

    # 1. 新規 stills 生成
    print("\n[1/4] Generating 2 new montage stills...")
    ref = REFS_DIR / "char_a_ref.png"
    client = OpenAI()
    still_a = STILLS_DIR / "mont_a.png"
    still_b = STILLS_DIR / "mont_b.png"
    if not still_a.exists():
        gen_still(client, ref, "\n\n".join([CHAR_DESC, PROMPT_A, STYLE, CONSTRAINTS]), still_a)
    else:
        print(f"  - {still_a.name} exists, skip")
    if not still_b.exists():
        gen_still(client, ref, "\n\n".join([CHAR_DESC, PROMPT_B, STYLE, CONSTRAINTS]), still_b)
    else:
        print(f"  - {still_b.name} exists, skip")

    # 2. 各 segment 生成
    print("\n[2/4] Building segments...")
    # A: 小道から覗き (0.6s push-in)
    seg_a = WORK_DIR / "seg_a.mp4"
    make_kenburns_clip(still_a, seg_a, duration=0.6, zoom_to=1.08)
    print(f"  ✓ seg_a (0.6s ken-burns)")

    # transition: 速度線 flash on still_a
    seg_flash1 = WORK_DIR / "seg_flash1.mp4"
    make_speedlines_flash(still_a, seg_flash1, duration=0.12)
    print(f"  ✓ seg_flash1 (0.12s speed lines)")

    # B: 入った瞬間 (0.5s push-in)
    seg_b = WORK_DIR / "seg_b.mp4"
    make_kenburns_clip(still_b, seg_b, duration=0.5, zoom_to=1.10)
    print(f"  ✓ seg_b (0.5s ken-burns)")

    # transition: 速度線 flash on still_b
    seg_flash2 = WORK_DIR / "seg_flash2.mp4"
    make_speedlines_flash(still_b, seg_flash2, duration=0.12)
    print(f"  ✓ seg_flash2 (0.12s speed lines)")

    # C: 既存 Fabric C012 (talking head 3.6s) - 統一化
    seg_c = WORK_DIR / "seg_c_fabric.mp4"
    normalize_clip(FABRIC_C012, seg_c, duration=3.6)
    print(f"  ✓ seg_c (3.6s fabric talking head)")

    # 3. concat all silent
    print("\n[3/4] Concat all segments (silent) + audio overlay...")
    silent_mp4 = WORK_DIR / "silent.mp4"
    list_file = WORK_DIR / "concat_list.txt"
    list_file.write_text("\n".join(
        f"file '{p.resolve()}'" for p in [seg_a, seg_flash1, seg_b, seg_flash2, seg_c]
    ))
    run_ff([
        "ffmpeg", "-y", "-loglevel", "error",
        "-f", "concat", "-safe", "0", "-i", str(list_file),
        "-c", "copy", str(silent_mp4),
    ])
    # total = 0.6 + 0.12 + 0.5 + 0.12 + 3.6 = 4.94s
    intro_dur = 0.6 + 0.12 + 0.5 + 0.12  # = 1.34s
    print(f"  intro action: {intro_dur:.2f}s + talking head 3.60s = {intro_dur+3.6:.2f}s")

    # 4. audio merge: L0 audio starts at intro_dur (when talking head begins)
    out_mp4 = OUT_DIR / "C012_montage.mp4"
    audio_offset_ms = int(intro_dur * 1000)
    run_ff([
        "ffmpeg", "-y", "-loglevel", "error",
        "-i", str(silent_mp4),
        "-i", str(AUDIO_L0),
        "-filter_complex",
        f"[1:a]aresample=44100,aformat=channel_layouts=stereo,"
        f"adelay={audio_offset_ms}|{audio_offset_ms}[aout]",
        "-map", "0:v", "-map", "[aout]",
        "-c:v", "copy", "-c:a", "aac", "-b:a", "192k", "-shortest",
        str(out_mp4),
    ])
    print(f"  ✓ {out_mp4} created")

    # review/ にコピー + 比較用に stills も
    print("\n[4/4] Copying to review/...")
    review_dir = ROOT / "review"
    subprocess.run(["cp", str(out_mp4), str(review_dir / "demo-001_C012_montage.mp4")], check=True)
    subprocess.run(["cp", str(still_a), str(review_dir / "demo-001_C012_montage_still_a.png")], check=True)
    subprocess.run(["cp", str(still_b), str(review_dir / "demo-001_C012_montage_still_b.png")], check=True)
    print(f"  review/demo-001_C012_montage.mp4")
    print(f"  review/demo-001_C012_montage_still_a.png")
    print(f"  review/demo-001_C012_montage_still_b.png")
    print("\n[done]")
    return 0


if __name__ == "__main__":
    sys.exit(main())
