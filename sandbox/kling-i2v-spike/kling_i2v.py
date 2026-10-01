"""Kling 2.5 i2v spike runner (Fal.ai 経由).

Usage:
    python kling_i2v.py --input input/sample_dialogue.png \
        --prompt "二人が会話している。少女が笑顔で口を動かす。背景は固定。" \
        --duration 5 --tag sample_dialogue_v1

Output:
    output/<tag>.mp4
    output/<tag>.meta.json  (prompt / cost / latency / model)
"""

from __future__ import annotations

import argparse
import base64
import json
import os
import sys
import time
from pathlib import Path

# Re-use repo's shared dotenv loader so FAL_KEY is picked up from .env
REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "src"))
try:
    from _dotenv import load_dotenv  # type: ignore
    load_dotenv()
except Exception:
    pass

try:
    import fal_client  # type: ignore
except ImportError:
    print("fal_client not installed. Run: pip install fal-client", file=sys.stderr)
    sys.exit(1)

import urllib.request

# Kling 2.5 i2v endpoint on Fal.ai
# ref: https://fal.ai/models/fal-ai/kling-video/v2.5-turbo/{pro,standard}/image-to-video
TIER_MODELS = {
    "pro": "fal-ai/kling-video/v2.5-turbo/pro/image-to-video",
    "standard": "fal-ai/kling-video/v2.5-turbo/standard/image-to-video",
}

# Pricing per 5sec (公称の例。契約前に最新を要確認)
TIER_PRICE_5S_USD = {
    "pro": 0.35,
    "standard": 0.20,
}


def _image_to_data_uri(path: Path) -> str:
    ext = path.suffix.lstrip(".").lower()
    if ext == "jpg":
        ext = "jpeg"
    b64 = base64.b64encode(path.read_bytes()).decode("ascii")
    return f"data:image/{ext};base64,{b64}"


def run(image_path: Path, prompt: str, duration: int, tag: str, out_dir: Path, tier: str) -> dict:
    if "FAL_KEY" not in os.environ:
        raise SystemExit("FAL_KEY not set. Add it to .env and reload.")
    if tier not in TIER_MODELS:
        raise SystemExit(f"invalid tier {tier}, choose from {list(TIER_MODELS)}")

    model_id = TIER_MODELS[tier]
    price_per_5s = TIER_PRICE_5S_USD[tier]

    out_dir.mkdir(parents=True, exist_ok=True)
    out_mp4 = out_dir / f"{tag}.mp4"
    out_meta = out_dir / f"{tag}.meta.json"

    image_uri = _image_to_data_uri(image_path)
    payload = {
        "prompt": prompt,
        "image_url": image_uri,
        "duration": str(duration),  # Fal API は文字列 "5" or "10"
        "negative_prompt": "blur, distortion, low quality, deformed hands, extra limbs",
    }

    print(f"[kling i2v] submit  tag={tag} tier={tier} duration={duration}s prompt={prompt[:60]}...")
    t0 = time.time()

    result = fal_client.subscribe(
        model_id,
        arguments=payload,
        with_logs=False,
    )

    elapsed = time.time() - t0
    video_url = result["video"]["url"]
    print(f"[kling i2v] done    tag={tag} elapsed={elapsed:.1f}s url={video_url}")

    # download mp4
    urllib.request.urlretrieve(video_url, out_mp4)

    cost = price_per_5s * (duration / 5)
    meta = {
        "tag": tag,
        "input_image": str(image_path.name),
        "prompt": prompt,
        "duration_sec": duration,
        "tier": tier,
        "model": model_id,
        "elapsed_sec": round(elapsed, 1),
        "estimated_cost_usd": round(cost, 3),
        "video_url": video_url,
    }
    out_meta.write_text(json.dumps(meta, ensure_ascii=False, indent=2))
    print(f"[kling i2v] saved   {out_mp4}  cost=${cost:.3f}")
    return meta


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--input", required=True, help="Input panel PNG path")
    ap.add_argument("--prompt", required=True, help="Motion prompt (Japanese ok)")
    ap.add_argument("--duration", type=int, default=5, choices=[5, 10])
    ap.add_argument("--tag", required=True, help="Output file tag, e.g. A_dialogue_v1")
    ap.add_argument("--tier", default="pro", choices=list(TIER_MODELS))
    ap.add_argument("--out-dir", default=str(Path(__file__).parent / "output"))
    args = ap.parse_args()

    run(
        image_path=Path(args.input),
        prompt=args.prompt,
        duration=args.duration,
        tag=args.tag,
        out_dir=Path(args.out_dir),
        tier=args.tier,
    )


if __name__ == "__main__":
    main()
