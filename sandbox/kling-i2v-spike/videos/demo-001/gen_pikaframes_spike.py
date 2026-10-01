"""Pikaframes spike — 2 stills (start + end) を補間して dynamic action 動画化.

ステップ:
  1. gpt-image-2 + char_a_ref ref で 2 stills 生成:
     - C012_pf_start.png : キャラA庭の小道 (ドア外、 構え)
     - C012_pf_end.png   : キャラA工房中央 (両手を上げて歓声)
  2. Pikaframes (fal-ai/pika/v2.2/pikaframes) で 5秒 動画補間 720p $0.20
  3. clips_pikaframes/C012_pf.mp4 出力
  4. review/demo-001_C012_pikaframes.mp4 にコピー

費用見積もり: stills $0.04 + Pikaframes $0.20 = ~$0.24
"""
from __future__ import annotations

import base64
import io
import json
import os
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

from PIL import Image

ROOT = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(ROOT / "src"))
from _dotenv import load_dotenv  # noqa: E402
load_dotenv()

from openai_image_config import DEFAULT_IMAGE_MODEL, DEFAULT_IMAGE_QUALITY  # noqa: E402

try:
    from openai import OpenAI  # noqa: E402
    import fal_client  # noqa: E402
except ImportError as e:
    print(f"missing: {e}", file=sys.stderr)
    sys.exit(2)

HERE = Path(__file__).resolve().parent
REFS_DIR = ROOT / "sandbox" / "character-refs-demo" / "refs"
OUT_DIR = HERE / "clips_pikaframes"
STILLS_DIR = OUT_DIR / "_stills"
OUT_DIR.mkdir(parents=True, exist_ok=True)
STILLS_DIR.mkdir(parents=True, exist_ok=True)

PIKAFRAMES_MODEL = "fal-ai/pika/v2.2/pikaframes"
GEN_SIZE = "1536x1024"
FINAL_W = 1536
FINAL_H = 864


# ── still prompts ──

CHAR_DESC = (
    "The reference image shows CHAR_A — the ONLY character in this illustration. "
    "She is a young adult with short dark hair, "
    "wearing a green jacket over a gray shirt, a gray tote bag, "
    "white sneakers. Reproduce her exact face, "
    "hairstyle, outfit, body proportions and overall design from the reference."
)

SETTING_CTX = (
    "Setting: a small craft workshop. Wooden shelves of tool "
    "racks, hanging lamps, soft afternoon light through a skylight. "
    "Workshop viewed from inside, looking toward the entrance door area."
)

STYLE = (
    "Style: Japanese seinen manga adapted to soft color illustration, hand-drawn "
    "linework, painterly background, expressive but restrained character design."
)

CONSTRAINTS = (
    "STRICT CONSTRAINTS: 16:9 cinematic single frame, no comic panel split, "
    "no panel borders, no text, no speech bubbles, no captions, no on-screen "
    "writing of any kind, no watermarks. Plain single illustration only."
)

SCENE_START = (
    "CHAR_A stands JUST OUTSIDE the workshop on the sunny garden path, "
    "right hand gripping the frame of the half-open glass door. Her body is still "
    "partially outside (right side of frame), she's peeking inside with an "
    "eager, excited face — eyes bright, lips parted but not yet shouting. "
    "She hasn't entered the workshop yet. View is from INSIDE the workshop "
    "looking back at the doorway. The doorway occupies the right-center of the "
    "frame. Warm humid light fills the workshop, contrasting with the "
    "brighter garden behind her."
)

SCENE_END = (
    "CHAR_A is NOW in the middle of the workshop, having walked through "
    "the door. She stands at the center-left of the frame, both hands raised "
    "forward and upward in a cheerful shout — palms open, fingers extended. "
    "Her face shows delight with eyes wide, mouth wide open mid-shout, "
    "eyebrows raised, a few leaves caught in her hair. Her bag is askew "
    "from moving. The door is fully open behind her in the right side of "
    "frame, the garden path visible. Same camera position as before (inside "
    "the workshop), same wide medium shot. Background shows the plant "
    "shelves and soft afternoon light."
)


def call_image_edit(client: OpenAI, ref_path: Path, prompt: str, out_path: Path):
    with open(ref_path, "rb") as f:
        result = client.images.edit(
            model=DEFAULT_IMAGE_MODEL,
            image=[f],
            prompt=prompt,
            n=1,
            size=GEN_SIZE,
            quality=DEFAULT_IMAGE_QUALITY,
        )
    b64 = result.data[0].b64_json
    raw = Image.open(io.BytesIO(base64.b64decode(b64))).convert("RGB")
    # 16:9 crop (center)
    if raw.width != FINAL_W:
        scale = FINAL_W / raw.width
        raw = raw.resize((FINAL_W, int(raw.height * scale)), Image.LANCZOS)
    if raw.height > FINAL_H:
        top = (raw.height - FINAL_H) // 2
        raw = raw.crop((0, top, FINAL_W, top + FINAL_H))
    raw.save(out_path, "PNG")
    print(f"  ✓ {out_path.name} saved ({raw.size[0]}x{raw.size[1]})")


def gen_stills():
    print("\n[1/3] Generating 2 stills (start + end) with gpt-image-2 + char_a_ref ref...")
    ref = REFS_DIR / "char_a_ref.png"
    if not ref.exists():
        raise FileNotFoundError(f"ref missing: {ref}")
    client = OpenAI()

    start_prompt = "\n\n".join([CHAR_DESC, SCENE_START, SETTING_CTX, STYLE, CONSTRAINTS])
    end_prompt = "\n\n".join([CHAR_DESC, SCENE_END, SETTING_CTX, STYLE, CONSTRAINTS])

    start_path = STILLS_DIR / "C012_pf_start.png"
    end_path = STILLS_DIR / "C012_pf_end.png"

    t0 = time.time()
    call_image_edit(client, ref, start_prompt, start_path)
    call_image_edit(client, ref, end_prompt, end_path)
    print(f"  stills generated in {time.time()-t0:.1f}s")
    return start_path, end_path


def call_pikaframes(start_path: Path, end_path: Path, prompt: str, dst: Path):
    print("\n[2/3] Calling Pikaframes API (720p, 5sec)...")
    start_url = fal_client.upload_file(str(start_path))
    end_url = fal_client.upload_file(str(end_path))

    payload = {
        "image_urls": [start_url, end_url],
        "prompt": prompt,
        "resolution": "720p",
        "duration": 5,  # min duration
    }
    t0 = time.time()
    result = fal_client.subscribe(PIKAFRAMES_MODEL, arguments=payload, with_logs=False)
    elapsed = time.time() - t0
    video_url = result["video"]["url"]
    print(f"  done in {elapsed:.1f}s  url={video_url[:80]}...")
    urllib.request.urlretrieve(video_url, dst)
    print(f"  saved to {dst}")
    return result


def main():
    for var in ["OPENAI_API_KEY", "FAL_KEY"]:
        if var not in os.environ:
            print(f"missing env: {var}", file=sys.stderr)
            return 2

    start_path, end_path = gen_stills()

    out_mp4 = OUT_DIR / "C012_pf.mp4"
    motion_prompt = (
        "CHAR_A walks through the doorway of the workshop, "
        "moves in with bright excitement, then stops in the middle, "
        "raising both hands forward and upward in a cheerful shout. "
        "Camera holds steady, maintains anime illustration style throughout."
    )
    call_pikaframes(start_path, end_path, motion_prompt, out_mp4)

    print("\n[3/3] Copying to review/")
    review = ROOT / "review" / "demo-001_C012_pikaframes.mp4"
    review.parent.mkdir(parents=True, exist_ok=True)
    subprocess.run(["cp", str(out_mp4), str(review)], check=True)
    print(f"  review: {review}")

    # 参考にstill 2枚も review に置く
    subprocess.run(["cp", str(start_path), str(ROOT / "review" / "demo-001_C012_pikaframes_start.png")], check=True)
    subprocess.run(["cp", str(end_path), str(ROOT / "review" / "demo-001_C012_pikaframes_end.png")], check=True)

    print("\n[done]")
    return 0


if __name__ == "__main__":
    sys.exit(main())
