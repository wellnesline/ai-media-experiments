"""PoC 001 v2 — cuts.py を読んで一枚絵を生成 (gpt-image-2 + style_ref).

gen_stills_refs.py の cuts スキーマ対応版。
出力: input_cuts/C001.png ... CNNN.png

Usage:
  python gen_cuts.py                  # 全 cut、 既存はスキップ
  python gen_cuts.py --regen          # 既存も再生成
  python gen_cuts.py --only C001      # 特定 cut だけ
"""
from __future__ import annotations

import argparse
import base64
import concurrent.futures
import importlib.util
import io
import os
import sys
import time
from pathlib import Path

from PIL import Image

ROOT = Path(__file__).resolve().parents[4]  # workspace/
sys.path.insert(0, str(ROOT / "src"))
from _dotenv import load_dotenv  # noqa: E402
load_dotenv()

from openai_image_config import DEFAULT_IMAGE_MODEL, DEFAULT_IMAGE_QUALITY  # noqa: E402
from openai import OpenAI  # noqa: E402

REFS_DIR = ROOT / "sandbox" / "character-refs-demo" / "refs"
OUT_DIR = Path(__file__).parent / "input_cuts"
MODEL = DEFAULT_IMAGE_MODEL          # gpt-image-2
GEN_SIZE = "1536x1024"
FINAL_W = 1536
FINAL_H = 864
QUALITY = DEFAULT_IMAGE_QUALITY      # low
N = 1

spec = importlib.util.spec_from_file_location("cuts", Path(__file__).parent / "cuts.py")
cuts_mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(cuts_mod)
CUTS = cuts_mod.CUTS
build_prompt = cuts_mod.build_prompt


def _crop_to_16x9(img: Image.Image) -> Image.Image:
    w, h = img.size
    if w != FINAL_W:
        scale = FINAL_W / w
        img = img.resize((FINAL_W, int(h * scale)), Image.LANCZOS)
        w, h = img.size
    if h == FINAL_H:
        return img
    top = (h - FINAL_H) // 2
    return img.crop((0, top, FINAL_W, top + FINAL_H))


def gen_one(client: OpenAI, cut: dict) -> Path:
    out_path = OUT_DIR / f"{cut['id']}.png"
    prompt = build_prompt(cut)
    ref_path = REFS_DIR / cut["style_ref"]
    if not ref_path.exists():
        raise FileNotFoundError(f"style_ref not found: {ref_path}")

    t0 = time.time()
    with open(ref_path, "rb") as f:
        result = client.images.edit(
            model=MODEL,
            image=[f],
            prompt=prompt,
            n=N,
            size=GEN_SIZE,
            quality=QUALITY,
        )
    b64 = result.data[0].b64_json
    raw = Image.open(io.BytesIO(base64.b64decode(b64))).convert("RGB")
    cropped = _crop_to_16x9(raw)
    cropped.save(out_path, "PNG")
    elapsed = time.time() - t0
    print(f"  ✓ {cut['id']} [{cut['kind']:13s} {cut['shot_size']:8s} {cut['duration']:>4.1f}s]  "
          f"main={cut['main_char']:9s} ref={cut['style_ref']:28s} {elapsed:>5.1f}s")
    return out_path


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--regen", action="store_true")
    ap.add_argument("--only", help="特定 cut ID のみ")
    ap.add_argument("--parallel", type=int, default=3)
    args = ap.parse_args()

    if "OPENAI_API_KEY" not in os.environ:
        print("OPENAI_API_KEY 未設定", file=sys.stderr)
        return 2

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    client = OpenAI()

    targets = CUTS
    if args.only:
        targets = [c for c in CUTS if c["id"] == args.only]
        if not targets:
            print(f"cut id {args.only} not found", file=sys.stderr)
            return 2

    pending = []
    for c in targets:
        out = OUT_DIR / f"{c['id']}.png"
        if out.exists() and not args.regen:
            print(f"  - {c['id']} skip (exists)")
            continue
        pending.append(c)

    if not pending:
        print("\n全 cut 既に存在、 何もせず終了 (--regen で再生成)")
        return 0

    print(f"\n[gen_cuts] 生成対象: {len(pending)} cut  model={MODEL} quality={QUALITY}  parallel={args.parallel}")
    t0 = time.time()
    failures = []
    with concurrent.futures.ThreadPoolExecutor(max_workers=args.parallel) as ex:
        futures = {ex.submit(gen_one, client, c): c for c in pending}
        for fut in concurrent.futures.as_completed(futures):
            c = futures[fut]
            try:
                fut.result()
            except Exception as e:  # noqa: BLE001
                print(f"  ✗ {c['id']} FAILED: {e}", file=sys.stderr)
                failures.append(c["id"])
    total = time.time() - t0
    print(f"\n[gen_cuts] done in {total:.1f}s  success={len(pending)-len(failures)}/{len(pending)}")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
