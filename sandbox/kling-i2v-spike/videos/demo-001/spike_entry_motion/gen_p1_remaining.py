"""P1 残り 3 cut (C001/C005/C006) を Vidu Q1 で並列生成.

入力: input_cuts/{C001,C005,C006}.png + cuts.py の motion_prompt
出力: clips_vidu/{C001,C005,C006}.mp4
予算: $0.40 × 3 = $1.20
"""
from __future__ import annotations

import concurrent.futures
import importlib.util
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

HERE = Path(__file__).resolve().parent.parent
INPUT_CUTS = HERE / "input_cuts"
CLIPS_VIDU = HERE / "clips_vidu"
CLIPS_VIDU.mkdir(exist_ok=True)

# cuts.py 読込
spec = importlib.util.spec_from_file_location("cuts", HERE / "cuts.py")
cuts_mod = importlib.util.module_from_spec(spec); spec.loader.exec_module(cuts_mod)
ALL_CUTS = {c["id"]: c for c in cuts_mod.CUTS}

TARGETS = ["C001", "C005", "C006"]


def gen_vidu_for_cut(cid: str) -> dict:
    cut = ALL_CUTS[cid]
    png = INPUT_CUTS / f"{cid}.png"
    if not png.exists():
        return {"cid": cid, "error": f"missing input: {png}"}

    motion = cut.get("motion_prompt") or cut.get("scene_desc") or ""
    target_dur = float(cut.get("duration", 2.0))

    t0 = time.time()
    print(f"  [{cid}] upload + queue (target_dur={target_dur:.1f}s)...", flush=True)
    src_url = fal_client.upload_file(str(png))

    try:
        result = fal_client.subscribe(
            "fal-ai/vidu/q1/image-to-video",
            arguments={
                "image_url": src_url,
                "prompt": motion,
                "duration": 5,
            },
            with_logs=False,
        )
    except Exception as e:
        return {"cid": cid, "error": str(e)[:300], "elapsed": time.time() - t0}

    elapsed = time.time() - t0
    video_url = (result.get("video") or {}).get("url")
    if not video_url:
        return {"cid": cid, "error": f"no video url in result: {result}", "elapsed": elapsed}

    raw_dst = CLIPS_VIDU / f"_{cid}_raw.mp4"
    urllib.request.urlretrieve(video_url, raw_dst)

    # cut.duration に合わせて trim + 不足分は freeze pad
    final_dst = CLIPS_VIDU / f"{cid}.mp4"
    # raw は 5sec、 target_dur が 5以下なら trim、 超えたら freeze pad
    if target_dur <= 5.0:
        # 前から target_dur 切り出し
        subprocess.run([
            "ffmpeg", "-y", "-loglevel", "error",
            "-i", str(raw_dst),
            "-t", f"{target_dur:.3f}",
            "-c:v", "libx264", "-crf", "18", "-preset", "fast", "-pix_fmt", "yuv420p",
            "-an", str(final_dst),
        ], check=True)
    else:
        # 5sec + freeze pad で target_dur へ
        pad = target_dur - 5.0
        subprocess.run([
            "ffmpeg", "-y", "-loglevel", "error",
            "-i", str(raw_dst),
            "-vf", f"tpad=stop_mode=clone:stop_duration={pad:.3f}",
            "-c:v", "libx264", "-crf", "18", "-preset", "fast", "-pix_fmt", "yuv420p",
            "-an", str(final_dst),
        ], check=True)

    print(f"  [{cid}] done in {elapsed:.1f}s  -> {final_dst.name} ({final_dst.stat().st_size/1024:.0f}KB)", flush=True)
    return {"cid": cid, "elapsed": elapsed, "raw": raw_dst, "final": final_dst}


def main():
    if "FAL_KEY" not in os.environ:
        print("missing env: FAL_KEY", file=sys.stderr)
        return 2

    print(f"[1/2] Generating {len(TARGETS)} cuts in parallel via Vidu Q1 (~${0.40*len(TARGETS):.2f})...")
    t0 = time.time()
    results = []
    with concurrent.futures.ThreadPoolExecutor(max_workers=3) as ex:
        futs = {ex.submit(gen_vidu_for_cut, cid): cid for cid in TARGETS}
        for fut in concurrent.futures.as_completed(futs):
            results.append(fut.result())
    print(f"\n  total: {time.time()-t0:.1f}s")

    print(f"\n[2/2] Results:")
    for r in sorted(results, key=lambda x: x["cid"]):
        if "error" in r:
            print(f"  [{r['cid']}] FAIL: {r['error']}")
        else:
            print(f"  [{r['cid']}] OK  {r['elapsed']:.1f}s  {r['final']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
