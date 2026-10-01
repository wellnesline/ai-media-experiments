#!/usr/bin/env python3
"""slide 04 だけで blob_renderer を試す PoC スクリプト。

出力:
  sandbox/spike-style-bert-vits2/demo001_video/test_blob_render_slide04.mp4
"""
from __future__ import annotations
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SBV2 = ROOT / "sandbox/spike-style-bert-vits2"
WORK = SBV2 / "demo001_video"

sys.path.insert(0, str(ROOT / "src"))


def main() -> int:
    from diagram_blob.blob_renderer import render_diagram_anim

    # base 画像(完成形)
    base = WORK / "slides_v2_raw/04.png"
    labels_npz = WORK / "work/blobs/slide_04/labels.npz"

    # order JSON(resolve_blobs 済み)
    order_path = WORK / "work/orders/slide_04_order.json"
    order = json.loads(order_path.read_text())

    # line timings 計算(ffprobe で wav duration → 累積)
    slides = json.loads((WORK / "slides_v2.json").read_text())["slides"]
    slide04 = next(s for s in slides if s["id"] == "04")

    AUDIO = ROOT / "sandbox/spike-elevenlabs/audio_v3eleven"
    HEAD_PAD = 0.05

    def dur(p: Path) -> float:
        r = subprocess.run(
            ["ffprobe", "-v", "quiet", "-show_format", "-print_format", "json", str(p)],
            capture_output=True, text=True,
        )
        return float(json.loads(r.stdout)["format"]["duration"])

    cur = 0.0
    timings = []
    for li, line in enumerate(slide04["lines"]):
        d = dur(AUDIO / f"04_{li:02d}.wav") + HEAD_PAD
        start = cur
        end = cur + d
        timings.append({"li": li, "start": start, "end": end})
        cap = (line.get("caption") or "").strip()
        last = cap[-1] if cap else ""
        if last in "。!?!?":
            gap = 0.40
        elif last in "、・":
            gap = 0.20
        else:
            gap = 0.15
        cur = end + gap
    duration = cur + 0.7  # tail silence

    out = WORK / "test_blob_render_slide04.mp4"
    print(f"=== blob render PoC: slide 04 ===")
    print(f"  base : {base.name}")
    print(f"  order: {order_path.name} (groups={len(order.get('groups', []))})")
    print(f"  dur  : {duration:.2f}s")
    print(f"  out  : {out}")
    print()

    render_diagram_anim(
        base_img=base,
        labels_npz=labels_npz,
        order=order,
        line_timings=timings,
        duration=duration,
        out_mp4=out,
        canvas_size=None,  # base size を維持(1536x1024)
        fps=30,
    )
    print(f"\n=> {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
