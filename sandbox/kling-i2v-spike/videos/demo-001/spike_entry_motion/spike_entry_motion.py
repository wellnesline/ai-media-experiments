"""i2v dramatic motion spike — Vidu Q1 (anime) + MiniMax Director を並列起動。

目的: 「キャラAが工房の扉から入って中へ進む」 を i2v で出せる API を探す。
入力: char_a_entry_1920x1080.png (扉を開けて入る直前のアニメ静止画)
出力:
  spike_entry_motion/vidu_anime.mp4   (Vidu Q1 anime style, ~$0.40)
  spike_entry_motion/minimax_dir.mp4  (MiniMax I2V Director with camera move, ~$0.50)
予算: ~$1.0 で 2 モデル比較
"""
from __future__ import annotations

import concurrent.futures
import os
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[5]
sys.path.insert(0, str(ROOT / "src"))
from _dotenv import load_dotenv  # noqa: E402
load_dotenv()

try:
    import fal_client  # noqa: E402
except ImportError:
    print("missing: fal_client", file=sys.stderr)
    sys.exit(2)

HERE = Path(__file__).resolve().parent
REFS = ROOT / "sandbox" / "character-refs-demo" / "refs"
SRC_IMG = REFS / "char_a_entry_1920x1080.png"

# 共通 motion 指示文 (両モデルに同じものを渡す)
MOTION_PROMPT = (
    "The character with short hair and a green jacket walks through the "
    "doorway of the workshop and moves forward between the tool shelves "
    "with bright excitement, her face lit up, both hands eventually "
    "raised in a cheerful shout. Camera holds steady, anime illustration style, "
    "smooth dramatic motion."
)


def run_vidu_q1(src_url: str) -> dict:
    """Vidu Q1 image-to-video (anime-friendly base, 5sec)."""
    t0 = time.time()
    print("  [Vidu Q1] starting...", flush=True)
    result = fal_client.subscribe(
        "fal-ai/vidu/q1/image-to-video",
        arguments={
            "image_url": src_url,
            "prompt": MOTION_PROMPT,
            "duration": 5,
        },
        with_logs=False,
    )
    elapsed = time.time() - t0
    video_url = (result.get("video") or {}).get("url")
    print(f"  [Vidu Q1] done in {elapsed:.1f}s  url={(video_url or '')[:80]}", flush=True)
    return {"name": "vidu_anime", "url": video_url, "elapsed": elapsed, "raw": result}


def run_minimax_director(src_url: str) -> dict:
    """MiniMax Hailuo video-01-director image-to-video with camera_movement.

    camera_movement のカッコ書きで動きを明示できる仕様 (e.g. [Push in,Pan left])。
    "push in" でカメラ自体を扉に近づけることで、 静止画から「近づいてくる」 錯覚を作る。
    """
    t0 = time.time()
    print("  [MiniMax Dir] starting...", flush=True)
    prompt_with_motion = f"[Push in,Truck right]{MOTION_PROMPT}"
    result = fal_client.subscribe(
        "fal-ai/minimax/video-01-director/image-to-video",
        arguments={
            "image_url": src_url,
            "prompt": prompt_with_motion,
            "prompt_optimizer": True,
        },
        with_logs=False,
    )
    elapsed = time.time() - t0
    video_url = (result.get("video") or {}).get("url")
    print(f"  [MiniMax Dir] done in {elapsed:.1f}s  url={(video_url or '')[:80]}", flush=True)
    return {"name": "minimax_dir", "url": video_url, "elapsed": elapsed, "raw": result}


def main():
    if "FAL_KEY" not in os.environ:
        print("missing env: FAL_KEY", file=sys.stderr)
        return 2
    if not SRC_IMG.exists():
        print(f"missing src: {SRC_IMG}", file=sys.stderr)
        return 2

    print(f"[1/3] Uploading source image: {SRC_IMG.name}")
    src_url = fal_client.upload_file(str(SRC_IMG))
    print(f"  {src_url[:80]}...")

    print(f"\n[2/3] Running 2 models in parallel (~$1 total)...")
    t0 = time.time()
    results = []
    with concurrent.futures.ThreadPoolExecutor(max_workers=2) as ex:
        futs = {
            ex.submit(run_vidu_q1, src_url): "vidu",
            ex.submit(run_minimax_director, src_url): "minimax",
        }
        for fut in concurrent.futures.as_completed(futs):
            tag = futs[fut]
            try:
                results.append(fut.result())
            except Exception as e:
                print(f"  [{tag}] FAILED: {type(e).__name__}: {str(e)[:300]}", flush=True)
                results.append({"name": tag, "url": None, "error": str(e)})
    print(f"\n  total parallel time: {time.time()-t0:.1f}s")

    print(f"\n[3/3] Downloading + copying to review/...")
    review = ROOT / "review"
    review.mkdir(exist_ok=True)
    for r in results:
        if not r.get("url"):
            print(f"  [{r['name']}] no url, skipped")
            continue
        dst = HERE / f"{r['name']}.mp4"
        urllib.request.urlretrieve(r["url"], dst)
        rv = review / f"demo-001_spike_entry_{r['name']}.mp4"
        subprocess.run(["cp", str(dst), str(rv)], check=True)
        print(f"  {r['name']}: {dst} -> {rv}  ({dst.stat().st_size/1024:.0f}KB)")

    print(f"\n[done] review/ で 2 ファイル比較してください")
    return 0


if __name__ == "__main__":
    sys.exit(main())
