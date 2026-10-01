#!/usr/bin/env python3
"""amitaro 音声の品質修正:
A) 全 wav を peak 0.92 にノーマライズ(クリップ防止)
B) hf_high(ロボット声候補)wav をパラメータ変えて再生成
"""
from __future__ import annotations

import json
import sys
import time
from pathlib import Path

import numpy as np
import soundfile as sf

ROOT = Path(__file__).resolve().parent
REPO = ROOT / "repo"
WORK = ROOT / "demo001_video"
AUDIO = WORK / "audio_v2"
SLIDES_JSON = WORK / "slides_v2.json"
ANOM_JSON = WORK / "audio_anomaly.json"

PEAK_TARGET = 0.92

sys.path.insert(0, str(REPO))


def normalize_all() -> None:
    """全 line wav を peak 0.92 にスケール。"""
    print("=== A. peak normalize ===")
    fixed = 0
    for wav in sorted(AUDIO.glob("[0-9][0-9]_[0-9][0-9].wav")):
        arr, sr = sf.read(wav)
        if arr.ndim > 1:
            arr = arr.mean(axis=1)
        arr = arr.astype(np.float32)
        peak = float(np.abs(arr).max())
        if peak > 0:
            scale = PEAK_TARGET / peak
            arr = arr * scale
            sf.write(wav, arr, sr)
            fixed += 1
    print(f"  normalized {fixed} wavs")


def regen_hf_high() -> None:
    """hf_high フラグの wav を amitaro でパラメータ変えて再生成。"""
    if not ANOM_JSON.exists():
        print("anomaly.json not found, skip regen")
        return
    anom = json.loads(ANOM_JSON.read_text(encoding="utf-8"))
    targets = [r for r in anom if any("hf_high" in f for f in r["flags"])]
    if not targets:
        print("no hf_high targets")
        return

    print(f"\n=== B. regen hf_high: {len(targets)} ===")

    import torch
    from style_bert_vits2.constants import Languages
    from style_bert_vits2.nlp import bert_models
    from style_bert_vits2.tts_model import TTSModel

    device = "mps" if torch.backends.mps.is_available() else "cpu"
    bert_models.load_model(Languages.JP, "ku-nlp/deberta-v2-large-japanese-char-wwm")
    bert_models.load_tokenizer(Languages.JP, "ku-nlp/deberta-v2-large-japanese-char-wwm")
    weight = REPO / "model_assets/amitaro/amitaro.safetensors"
    config = REPO / "model_assets/amitaro/config.json"
    style = REPO / "model_assets/amitaro/style_vectors.npy"
    m = TTSModel(model_path=weight, config_path=config, style_vec_path=style, device=device)

    # slides_v2.json から speech を取得
    slides = json.loads(SLIDES_JSON.read_text(encoding="utf-8"))["slides"]
    by_id = {s["id"]: s for s in slides}

    for r in targets:
        sid_li = r["key"]  # "04_03"
        sid, li = sid_li.split("_")
        li_idx = int(li)
        speech = by_id[sid]["lines"][li_idx]["speech"]
        out = AUDIO / f"{sid_li}.wav"
        # 安定化パラメータ:noise/noise_w を下げる、sdp_ratio 上げる(リズム強化)
        t0 = time.time()
        sr, audio = m.infer(
            text=speech, language=Languages.JP,
            noise=0.4, noise_w=0.6, sdp_ratio=0.4, length=1.0,
        )
        if audio.dtype != np.float32:
            audio = audio.astype(np.float32) / np.iinfo(audio.dtype).max
        # 直接 normalize
        peak = float(np.abs(audio).max())
        if peak > 0:
            audio = audio * (PEAK_TARGET / peak)
        sf.write(out, audio, sr)
        dur = len(audio) / sr
        print(f"  [B] {sid_li} regen {dur:.2f}s ({time.time()-t0:.1f}s) | {speech[:30]}")


def rebuild_concat_audio() -> None:
    """各スライドの concat wav を再構築(line wav 更新後)。"""
    print("\n=== C. concat 再構築 ===")
    slides = json.loads(SLIDES_JSON.read_text(encoding="utf-8"))["slides"]
    for s in slides:
        sid = s["id"]
        out = AUDIO / f"{sid}_concat.wav"
        arrs = []
        sr_out = None
        for li in range(len(s["lines"])):
            wav = AUDIO / f"{sid}_{li:02d}.wav"
            if not wav.exists():
                continue
            a, sr = sf.read(wav)
            if sr_out is None:
                sr_out = sr
            if a.ndim > 1:
                a = a.mean(axis=1)
            arrs.append(a.astype(np.float32))
            arrs.append(np.zeros(int(sr * 0.15), dtype=np.float32))  # 0.15s 無音
        if not arrs:
            continue
        sf.write(out, np.concatenate(arrs), sr_out)
    print(f"  concat 済 ({len(slides)} slides)")


def main() -> int:
    normalize_all()
    regen_hf_high()
    rebuild_concat_audio()
    return 0


if __name__ == "__main__":
    main()
