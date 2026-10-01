#!/usr/bin/env python3
"""amitaro 生成 wav の異常を検出してリストアップ。

検出基準:
- duration / chars 比が中央値から ±50% 以上ズレ(早口・遅すぎ・スタックあり)
- RMS が中央値から大きく離れる(音量極端)
- 高域エネルギー比が異常(ノイズ・ロボット声)
- ピーク値が 0.95 以上(クリップ)
- duration < 0.5s または > 25s
"""
from __future__ import annotations

import json
import sys
from pathlib import Path
import numpy as np
import soundfile as sf

ROOT = Path(__file__).resolve().parent
WORK = ROOT / "demo001_video"
AUDIO = WORK / "audio_v2"
SLIDES_JSON = WORK / "slides_v2.json"


def hf_ratio(audio: np.ndarray, sr: int) -> float:
    """高周波数帯エネルギー比(ノイズ proxy)。FFT で 4kHz以上 / 全帯域。"""
    if len(audio) < 1024:
        return 0.0
    fft = np.fft.rfft(audio.astype(np.float32)[:65536])
    mag = np.abs(fft)
    freqs = np.fft.rfftfreq(min(len(audio), 65536), d=1.0/sr)
    high = mag[freqs >= 4000].sum()
    total = mag.sum()
    return float(high / max(total, 1e-9))


def main() -> int:
    data = json.loads(SLIDES_JSON.read_text(encoding="utf-8"))
    slides = data["slides"]

    rows: list[dict] = []
    for s in slides:
        sid = s["id"]
        for li, line in enumerate(s["lines"]):
            wav = AUDIO / f"{sid}_{li:02d}.wav"
            if not wav.exists():
                continue
            arr, sr = sf.read(wav)
            if arr.ndim > 1:
                arr = arr.mean(axis=1)
            arr = arr.astype(np.float32)
            dur = len(arr) / sr
            chars = len(line["speech"])
            cps = chars / dur if dur > 0 else 0  # chars per second
            rms = float(np.sqrt((arr ** 2).mean())) if len(arr) else 0.0
            peak = float(np.abs(arr).max()) if len(arr) else 0.0
            hf = hf_ratio(arr, sr)
            rows.append({
                "key": f"{sid}_{li:02d}",
                "speech": line["speech"][:40],
                "dur": dur,
                "chars": chars,
                "cps": cps,
                "rms": rms,
                "peak": peak,
                "hf": hf,
            })

    if not rows:
        print("no wavs")
        return 0

    cps_list = [r["cps"] for r in rows]
    rms_list = [r["rms"] for r in rows]
    hf_list = [r["hf"] for r in rows]
    cps_med = float(np.median(cps_list))
    rms_med = float(np.median(rms_list))
    hf_med = float(np.median(hf_list))
    cps_std = float(np.std(cps_list))
    rms_std = float(np.std(rms_list))
    hf_std = float(np.std(hf_list))

    print(f"=== overall medians ===")
    print(f"  cps med={cps_med:.2f} std={cps_std:.2f}")
    print(f"  rms med={rms_med:.4f} std={rms_std:.4f}")
    print(f"  hf  med={hf_med:.4f} std={hf_std:.4f}")
    print()

    flagged: list[dict] = []
    for r in rows:
        flags = []
        if r["dur"] < 0.5:
            flags.append("very_short")
        if r["dur"] > 25:
            flags.append("very_long")
        if abs(r["cps"] - cps_med) > cps_med * 0.5:
            flags.append(f"cps_off({r['cps']:.1f})")
        if r["rms"] < rms_med * 0.4 or r["rms"] > rms_med * 2.5:
            flags.append(f"rms_off({r['rms']:.4f})")
        if r["hf"] > hf_med + hf_std * 1.8:
            flags.append(f"hf_high({r['hf']:.3f})")
        if r["peak"] > 0.97:
            flags.append("clip")
        if flags:
            r["flags"] = flags
            flagged.append(r)

    print(f"=== flagged: {len(flagged)} / {len(rows)} ===")
    for r in flagged:
        print(f"  {r['key']} {r['flags']}")
        print(f"    dur={r['dur']:.2f}s chars={r['chars']} cps={r['cps']:.1f} rms={r['rms']:.4f} hf={r['hf']:.3f}")
        print(f"    text: {r['speech']}")

    out = WORK / "audio_anomaly.json"
    out.write_text(json.dumps([r for r in flagged], ensure_ascii=False, indent=2))
    print(f"\nwrote: {out}")
    return 0


if __name__ == "__main__":
    main()
