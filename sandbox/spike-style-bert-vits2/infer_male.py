#!/usr/bin/env python3
"""男性ボイス試聴サンプル生成。

JVNV M1/M2 は商用NGだが、声質判定用に生成して、
他の商用OK男性モデルを探す判断材料にする。
"""
from __future__ import annotations

import sys
import time
from pathlib import Path

REPO = Path(__file__).resolve().parent / "repo"
OUT_DIR = Path(__file__).resolve().parent / "out"
OUT_DIR.mkdir(exist_ok=True)

sys.path.insert(0, str(REPO))

import torch
from style_bert_vits2.constants import Languages
from style_bert_vits2.nlp import bert_models
from style_bert_vits2.tts_model import TTSModel


def pick_device() -> str:
    if torch.backends.mps.is_available():
        return "mps"
    if torch.cuda.is_available():
        return "cuda"
    return "cpu"


def load_japanese_bert() -> None:
    bert_models.load_model(Languages.JP, "ku-nlp/deberta-v2-large-japanese-char-wwm")
    bert_models.load_tokenizer(Languages.JP, "ku-nlp/deberta-v2-large-japanese-char-wwm")


def main() -> int:
    device = pick_device()
    print(f"=== device: {device} ===")
    load_japanese_bert()

    # ナレーション解説向けのサンプル
    samples = {
        # synthetic sentences (not taken from any real article)
        "01_intro": "朝いちばんに窓を開けて、庭の土の湿り具合を確かめる。",
        "02_explainer": "植木鉢を並べ替えてみると、日当たりの悪い場所が意外に多いことに気づいた。置き場所を少し変えるだけで、葉の色が見違えるほど良くなった。",
        "03_long": "苗を育て始めた頃、最初につまずいたのは水の量だった。毎日あげるべきか、土が乾いてからでよいのか、迷ううちに根が弱ってしまった。",
        "04_cta": "今回は、鉢植えの基本をまとめた話をお届けしました。気に入ったら、また覗きに来てください。",
    }

    models = [
        ("jvnv-M1-jp", "jvnv-M1-jp/jvnv-M1-jp_e158_s14000.safetensors"),
        ("jvnv-M2-jp", "jvnv-M2-jp/jvnv-M2-jp_e159_s17000.safetensors"),
    ]

    import soundfile as sf

    for model_name, weight_rel in models:
        print(f"\n=== model: {model_name} ===")
        weight_path = REPO / "model_assets" / weight_rel
        config_path = weight_path.parent / "config.json"
        style_path = weight_path.parent / "style_vectors.npy"

        m = TTSModel(model_path=weight_path, config_path=config_path, style_vec_path=style_path, device=device)

        for sample_id, text in samples.items():
            out = OUT_DIR / f"{model_name}_{sample_id}.wav"
            t0 = time.time()
            sr, audio = m.infer(text=text, language=Languages.JP)
            sf.write(out, audio, sr)
            print(f"  [{out.name}] {len(audio)/sr:.2f}s audio / {time.time()-t0:.2f}s gen")

    print("\n=== done ===")
    return 0


if __name__ == "__main__":
    sys.exit(main())
