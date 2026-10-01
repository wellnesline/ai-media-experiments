"""PoC 001 v2 — cuts.py の anim_method=kling な cut を 並列で i2v 生成.

入力: input_cuts/{cut_id}.png + cut.motion_prompt
出力: clips/{cut_id}.mp4  (Kling 2.5 standard、 5秒、 1920x1080)

  Kling は 5秒 or 10秒 固定。 cut.duration は trim 段 (compose_p1.py) で適用。

Usage:
  python gen_clips.py                  # 未生成のみ
  python gen_clips.py --regen          # 既存も再生成
  python gen_clips.py --only C001      # 単一 cut
  python gen_clips.py --parallel 4
"""
from __future__ import annotations

import argparse
import base64
import concurrent.futures
import importlib.util
import json
import os
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
    print("fal_client not installed (pip install fal-client)", file=sys.stderr)
    sys.exit(2)

HERE = Path(__file__).resolve().parent
INPUT_DIR = HERE / "input_cuts"
OUT_DIR = HERE / "clips"

# Fal.ai Kling 2.5 standard image-to-video
MODEL_ID = "fal-ai/kling-video/v2.5-turbo/standard/image-to-video"
PRICE_PER_5S = 0.20

# cuts.py を import
spec = importlib.util.spec_from_file_location("cuts", HERE / "cuts.py")
cuts_mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(cuts_mod)
CUTS = cuts_mod.CUTS


def _image_to_data_uri(path: Path) -> str:
    b64 = base64.b64encode(path.read_bytes()).decode("ascii")
    return f"data:image/png;base64,{b64}"


def _pick_duration(target: float) -> int:
    """Kling は 5 or 10秒固定。 6秒未満は 5、 それ以上は 10."""
    return 5 if target <= 5.5 else 10


def gen_one(cut: dict) -> dict:
    """1 cut 生成。 thread-safe (fal_client.subscribe は内部で OK)."""
    cid = cut["id"]
    if cut.get("anim_method") != "kling":
        raise RuntimeError(f"{cid} is not anim_method=kling")

    image_path = INPUT_DIR / f"{cid}.png"
    if not image_path.exists():
        raise FileNotFoundError(f"still missing: {image_path}")

    out_mp4 = OUT_DIR / f"{cid}.mp4"
    out_meta = OUT_DIR / f"{cid}.meta.json"
    duration = _pick_duration(cut["duration"])
    prompt = cut.get("motion_prompt") or cut["motion_jp"]

    payload = {
        "prompt": prompt,
        "image_url": _image_to_data_uri(image_path),
        "duration": str(duration),
        "negative_prompt": "blur, distortion, low quality, deformed hands, extra limbs, text, captions, speech bubbles",
    }

    print(f"  ▶ {cid} submit  kling={duration}s  target_dur={cut['duration']}s")
    t0 = time.time()
    result = fal_client.subscribe(MODEL_ID, arguments=payload, with_logs=False)
    elapsed = time.time() - t0
    video_url = result["video"]["url"]
    urllib.request.urlretrieve(video_url, out_mp4)

    cost = PRICE_PER_5S * (duration / 5)
    meta = {
        "cut_id": cid,
        "kind": cut["kind"],
        "shot_size": cut["shot_size"],
        "kling_duration_sec": duration,
        "target_duration_sec": cut["duration"],
        "elapsed_sec": round(elapsed, 1),
        "cost_usd": round(cost, 3),
        "video_url": video_url,
        "motion_prompt": prompt[:200],
    }
    out_meta.write_text(json.dumps(meta, ensure_ascii=False, indent=2))
    print(f"  ✓ {cid} done    {elapsed:5.1f}s  ${cost:.2f}  -> {out_mp4.name}")
    return meta


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--regen", action="store_true")
    ap.add_argument("--only", help="特定 cut ID")
    ap.add_argument("--scenes", help="comma-separated scene ids e.g. P2,P3 (default all)")
    ap.add_argument("--no-talking", action="store_true",
                    help="dialogue cut (fabric/avatar 対象) を skip (i2v 無駄生成回避)")
    ap.add_argument("--parallel", type=int, default=4)
    args = ap.parse_args()

    if "FAL_KEY" not in os.environ:
        print("FAL_KEY 未設定", file=sys.stderr)
        return 2

    OUT_DIR.mkdir(parents=True, exist_ok=True)

    targets = [c for c in CUTS if c.get("anim_method") == "kling"]
    if args.scenes:
        wanted = set(args.scenes.split(","))
        targets = [c for c in targets if c["scene"] in wanted]
    if args.only:
        targets = [c for c in targets if c["id"] == args.only]
    if args.no_talking:
        # fabric/avatar 対象 (= talking head) を除外: main_char != none かつ covers_lines あり かつ shot_size != ECU
        def is_talking(c):
            return (c.get("main_char") != "none"
                    and c.get("covers_lines")
                    and c.get("shot_size") not in ("ECU",))
        targets = [c for c in targets if not is_talking(c)]

    pending = []
    for c in targets:
        out = OUT_DIR / f"{c['id']}.mp4"
        if out.exists() and not args.regen:
            print(f"  - {c['id']} skip (exists)")
            continue
        pending.append(c)

    if not pending:
        print("\n全 cut 既に生成済 (--regen で再生成)")
        return 0

    total_cost_est = sum(PRICE_PER_5S * (_pick_duration(c["duration"]) / 5) for c in pending)
    print(f"\n[gen_clips] kling={MODEL_ID}")
    print(f"[gen_clips] 対象 {len(pending)} cut, 推定コスト ${total_cost_est:.2f}, parallel={args.parallel}\n")

    t0 = time.time()
    failures = []
    with concurrent.futures.ThreadPoolExecutor(max_workers=args.parallel) as ex:
        futures = {ex.submit(gen_one, c): c for c in pending}
        for fut in concurrent.futures.as_completed(futures):
            c = futures[fut]
            try:
                fut.result()
            except Exception as e:  # noqa: BLE001
                print(f"  ✗ {c['id']} FAILED: {e}", file=sys.stderr)
                failures.append(c["id"])
    total = time.time() - t0
    print(f"\n[gen_clips] done in {total:.1f}s  success={len(pending)-len(failures)}/{len(pending)}")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
