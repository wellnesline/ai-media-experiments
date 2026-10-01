"""gpt-image-2 で 16:9 一枚絵を生成する spike runner.

セリフ/吹き出し/テキストは含めない (i2v 入力用)。
動画化前提なので、 動かしやすい構図 (キャラ中心 + 背景余白) を推奨。

Usage:
    python gen_still.py --prompt-file prompts/01_workshop.txt \
        --output input/01_workshop.png
"""
from __future__ import annotations

import argparse
import base64
import json
import os
import sys
import urllib.request
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "src"))
from _dotenv import load_dotenv  # type: ignore
load_dotenv()

from openai_image_config import DEFAULT_IMAGE_MODEL, DEFAULT_IMAGE_QUALITY  # type: ignore

API_URL = "https://api.openai.com/v1/images/generations"
# Kling i2v 入力には 16:9 が素直。 gpt-image-2 で 1536x864 (16:9) を採用。
DEFAULT_SIZE = "1536x864"


def call_api(prompt: str, size: str, api_key: str, timeout: int = 240) -> dict:
    payload = json.dumps({
        "model": DEFAULT_IMAGE_MODEL,
        "prompt": prompt,
        "size": size,
        "n": 1,
        "quality": DEFAULT_IMAGE_QUALITY,
    }).encode("utf-8")
    req = urllib.request.Request(
        API_URL,
        data=payload,
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        },
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode("utf-8"))


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--prompt-file", type=Path, required=True)
    ap.add_argument("--output", type=Path, required=True)
    ap.add_argument("--size", default=DEFAULT_SIZE)
    args = ap.parse_args()

    api_key = os.environ.get("OPENAI_API_KEY")
    if not api_key:
        sys.stderr.write("OPENAI_API_KEY 未設定\n")
        return 2

    prompt = args.prompt_file.read_text(encoding="utf-8")
    args.output.parent.mkdir(parents=True, exist_ok=True)

    print(f"[gen_still] generating model={DEFAULT_IMAGE_MODEL} size={args.size}")
    print(f"[gen_still] prompt preview: {prompt[:120]}...")

    resp = call_api(prompt, args.size, api_key)
    if "error" in resp:
        raise RuntimeError(f"API error: {resp['error']}")

    b64 = resp["data"][0].get("b64_json")
    if not b64:
        raise RuntimeError(f"no b64_json in response: keys={list(resp['data'][0].keys())}")
    args.output.write_bytes(base64.b64decode(b64))
    print(f"[gen_still] saved {args.output} ({args.output.stat().st_size // 1024} KB)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
