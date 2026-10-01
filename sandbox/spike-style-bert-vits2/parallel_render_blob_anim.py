#!/usr/bin/env python3
"""全 30 slide の blob reveal アニメ mp4 を並列レンダリング。

build_demo001_seminar_v2.py の Phase B3 を **multiprocessing.Pool で6並列** に展開した独立スクリプト。
完了後、build_demo001_seminar_v2.py を実行すれば cache hit で B3 を skip できる。

使い方:
  python sandbox/spike-style-bert-vits2/parallel_render_blob_anim.py [--workers 6]
"""
from __future__ import annotations
import argparse
import json
import subprocess
import sys
from multiprocessing import Pool, set_start_method
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SBV2 = Path(__file__).resolve().parent
WORK = SBV2 / "demo001_video"
AUDIO_DIR = ROOT / "sandbox/spike-elevenlabs/audio_v3eleven"  # generated locally; not bundled

SLIDES_RAW = WORK / "slides_v2_raw"
SLIDES_BLOB = WORK / "slides_blob_anim"
BLOBS_DIR = WORK / "work/blobs"
ORDERS_DIR = WORK / "work/orders"
SLIDES_JSON = WORK / "slides_v2.json"

HEAD_PAD = 0.05


def _slide_duration(slide: dict) -> float:
    """slide の合計 duration を計算(line wav + adaptive gap + tail silence)。"""
    cur = 0.0
    sid = slide["id"]
    for li, line in enumerate(slide["lines"]):
        wav = AUDIO_DIR / f"{sid}_{li:02d}.wav"
        if not wav.exists():
            continue
        r = subprocess.run(
            ["ffprobe", "-v", "quiet", "-show_format", "-print_format", "json", str(wav)],
            capture_output=True, text=True,
        )
        d = float(json.loads(r.stdout)["format"]["duration"]) + HEAD_PAD
        cap = (line.get("caption") or "").strip()
        last = cap[-1] if cap else ""
        if last in "。!?!?":
            gap = 0.40
        elif last in "、・":
            gap = 0.20
        else:
            gap = 0.15
        cur = cur + d + gap
    return cur + 0.7


def _render_one(args: tuple) -> str:
    sid, duration = args
    out = SLIDES_BLOB / f"{sid}.mp4"
    raw = SLIDES_RAW / f"{sid}.png"
    labels = BLOBS_DIR / f"slide_{sid}/labels.npz"
    order_path = ORDERS_DIR / f"slide_{sid}_order.json"

    if not (raw.exists() and labels.exists() and order_path.exists()):
        return f"skip {sid}: deps missing"

    if out.exists() and out.stat().st_mtime > order_path.stat().st_mtime:
        return f"cached {sid}"

    sys.path.insert(0, str(ROOT / "src"))
    from diagram_blob.blob_renderer import render_diagram_anim

    order = json.loads(order_path.read_text())
    SLIDES_BLOB.mkdir(parents=True, exist_ok=True)
    # target_finish_time: 短尺 slide では更に圧縮、最大 3.0s で全描写完了
    target = min(3.0, duration * 0.6)
    try:
        render_diagram_anim(
            base_img=raw,
            labels_npz=labels,
            order=order,
            duration=duration,
            out_mp4=out,
            auto_stagger=True,
            stagger_gap=0.7,
            target_finish_time=target,
        )
        return f"OK {sid} ({duration:.1f}s, target={target:.1f}s, {out.stat().st_size // 1024}KB)"
    except Exception as e:
        return f"FAIL {sid}: {type(e).__name__}: {e}"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--workers", type=int, default=6)
    args = ap.parse_args()

    SLIDES_BLOB.mkdir(parents=True, exist_ok=True)

    slides = json.loads(SLIDES_JSON.read_text())["slides"]
    work_args = [(s["id"], _slide_duration(s)) for s in slides]
    print(f"=== parallel render: {len(work_args)} slides × {args.workers} workers ===")

    set_start_method("spawn", force=True)
    with Pool(args.workers) as pool:
        for r in pool.imap_unordered(_render_one, work_args):
            print(r, flush=True)

    print("\n=== done ===")
    return 0


if __name__ == "__main__":
    sys.exit(main())
