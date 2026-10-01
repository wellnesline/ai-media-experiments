"""PoC 001 — 全 shots の一枚絵を gpt-image-1 + 参考画像 2 枚で生成.

参考画像:
  - sandbox/character-refs-demo/refs/char_a_base.png   (キャラA顔の正解)
  - sandbox/character-refs-demo/refs/char_b_base.png (キャラB顔の正解)

OpenAI /v1/images/edits を multi-reference モードで叩く。
出力: input/S001.png ... SNNN.png (1536x864, 16:9, テキスト無し)

Usage:
  python gen_stills_refs.py             # 全 shot、 既存はスキップ
  python gen_stills_refs.py --regen     # 既存も再生成
  python gen_stills_refs.py --only S001 # 特定 shot だけ
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

# リポ規約: openai_image_config が 単一真実源 (hardlock: gpt-image-2 / quality=low)
from openai_image_config import DEFAULT_IMAGE_MODEL, DEFAULT_IMAGE_QUALITY  # noqa: E402

from openai import OpenAI  # noqa: E402

# 設定
REFS_DIR = ROOT / "sandbox" / "character-refs-demo" / "refs"
OUT_DIR = Path(__file__).parent / "input"
MODEL = DEFAULT_IMAGE_MODEL          # "gpt-image-2"  (hardlock by src/openai_image_config.py)
GEN_SIZE = "1536x1024"               # gpt-image-2 edits ランドスケープ最大 (3:2)。 後段 16:9 に crop
FINAL_W = 1536
FINAL_H = 864                        # 16:9 (Kling 入力 + 視認性ターゲット)
QUALITY = DEFAULT_IMAGE_QUALITY      # "low"  (hardlock)
N = 1                                # 1 shot あたり 1 枚

# shots.py を import
spec = importlib.util.spec_from_file_location("shots", Path(__file__).parent / "shots.py")
shots_mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(shots_mod)
SHOTS = shots_mod.SHOTS
build_prompt = shots_mod.build_prompt


def _crop_to_16x9(img: Image.Image) -> Image.Image:
    """画像を中央 crop で 16:9 (FINAL_W x FINAL_H) に整形."""
    w, h = img.size
    # まず幅を FINAL_W にスケール
    if w != FINAL_W:
        scale = FINAL_W / w
        img = img.resize((FINAL_W, int(h * scale)), Image.LANCZOS)
        w, h = img.size
    if h == FINAL_H:
        return img
    # 中央 crop で 16:9 化
    top = (h - FINAL_H) // 2
    return img.crop((0, top, FINAL_W, top + FINAL_H))


def gen_one(client: OpenAI, shot: dict) -> Path:
    out_path = OUT_DIR / f"{shot['id']}.png"
    prompt = build_prompt(shot)
    ref_path = REFS_DIR / shot["expression_ref"]
    if not ref_path.exists():
        raise FileNotFoundError(f"expression_ref not found: {ref_path}")

    t0 = time.time()
    with open(ref_path, "rb") as f:
        result = client.images.edit(
            model=MODEL,
            image=[f],          # 立ち絵 1 枚のみ (シーン背景を引きずらない)
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
    print(f"  ✓ {shot['id']} ({shot['speaker']:9s} {shot['duration_sec']:>5.2f}s)  "
          f"ref={shot['expression_ref']:28s}  {elapsed:>5.1f}s  -> {out_path.name}")
    return out_path


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--regen", action="store_true", help="既存も再生成")
    ap.add_argument("--only", help="特定 shot ID のみ (例: S001)")
    ap.add_argument("--parallel", type=int, default=3, help="同時並列数 (default 3)")
    args = ap.parse_args()

    if "OPENAI_API_KEY" not in os.environ:
        print("OPENAI_API_KEY 未設定", file=sys.stderr)
        return 2
    if not REFS_DIR.exists():
        print(f"参考画像ディレクトリが見つかりません: {REFS_DIR}", file=sys.stderr)
        return 2

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    client = OpenAI()

    targets = SHOTS
    if args.only:
        targets = [s for s in SHOTS if s["id"] == args.only]
        if not targets:
            print(f"shot id {args.only} not found", file=sys.stderr)
            return 2

    pending = []
    for shot in targets:
        out = OUT_DIR / f"{shot['id']}.png"
        if out.exists() and not args.regen:
            print(f"  - {shot['id']} skip (exists, use --regen to override)")
            continue
        pending.append(shot)

    if not pending:
        print("\n全 shot 既に存在、 何もせず終了 (--regen で再生成)")
        return 0

    print(f"\n[gen_stills] 生成対象: {len(pending)} shot  ref=立ち絵1枚  gen={GEN_SIZE} -> final {FINAL_W}x{FINAL_H}  quality={QUALITY}  parallel={args.parallel}")
    t0 = time.time()
    failures = []
    with concurrent.futures.ThreadPoolExecutor(max_workers=args.parallel) as ex:
        futures = {ex.submit(gen_one, client, s): s for s in pending}
        for fut in concurrent.futures.as_completed(futures):
            s = futures[fut]
            try:
                fut.result()
            except Exception as e:  # noqa: BLE001
                print(f"  ✗ {s['id']} FAILED: {e}", file=sys.stderr)
                failures.append(s["id"])
    total = time.time() - t0
    print(f"\n[gen_stills] done in {total:.1f}s  success={len(pending)-len(failures)}/{len(pending)}")
    if failures:
        print(f"  failures: {failures}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
