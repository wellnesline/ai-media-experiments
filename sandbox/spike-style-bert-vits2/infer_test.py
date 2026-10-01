#!/usr/bin/env python3
"""Style-Bert-VITS2 推論動作検証スクリプト。

記事を動画化するナレーション用途を想定:
- 複数モデル (amitaro / jvnv-F1) を試す
- 短文・中文・記事冒頭を生成
- GPU が使えれば使う、なければ CPU
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
    bert_models.load_model(
        Languages.JP, "ku-nlp/deberta-v2-large-japanese-char-wwm"
    )
    bert_models.load_tokenizer(
        Languages.JP, "ku-nlp/deberta-v2-large-japanese-char-wwm"
    )


def synth(model: TTSModel, text: str, out_path: Path, **kwargs) -> float:
    t0 = time.time()
    sr, audio = model.infer(text=text, language=Languages.JP, **kwargs)
    elapsed = time.time() - t0

    import soundfile as sf
    sf.write(out_path, audio, sr)
    audio_sec = len(audio) / sr
    rtf = elapsed / audio_sec if audio_sec else float("inf")
    print(f"  [{out_path.name}] {audio_sec:.2f}s audio / {elapsed:.2f}s gen / RTF={rtf:.2f}")
    return rtf


def main() -> int:
    device = pick_device()
    print(f"=== device: {device} ===")

    print("=== loading Japanese BERT ===")
    t0 = time.time()
    load_japanese_bert()
    print(f"  BERT loaded in {time.time()-t0:.1f}s")

    samples = {
        # synthetic sentences (not taken from any real article)
        "01_short_intro": (
            "朝いちばんに窓を開けて、庭の土の湿り具合を確かめる。"
        ),
        "02_mid_paragraph": (
            "苗を育て始めた頃、最初につまずいたのは水の量だった。"
            "毎日あげるべきか、土が乾いてからでよいのか、迷ううちに根が弱ってしまった。"
        ),
        "03_explainer": (
            "植木鉢を並べ替えてみると、日当たりの悪い場所が意外に多いこと"
            "に気づいた。置き場所を少し変えるだけで、葉の色が見違えるほど良くなった。"
            "やったことは三つだけで、置き場所を記録すること、水やりの間隔を決めること、枯れた葉をこまめに取ること。"
        ),
        "04_call_to_action": (
            "今回は、鉢植えの基本をまとめた話をお届けしました。"
            "気に入ったら、また覗きに来てください。"
        ),
    }

    models = [
        ("amitaro", "amitaro/amitaro.safetensors"),
        ("jvnv-F1-jp", "jvnv-F1-jp/jvnv-F1-jp_e160_s14000.safetensors"),
    ]

    for model_name, weight_rel in models:
        print(f"\n=== model: {model_name} ===")
        weight_path = REPO / "model_assets" / weight_rel
        config_path = weight_path.parent / "config.json"
        style_path = weight_path.parent / "style_vectors.npy"

        m = TTSModel(
            model_path=weight_path,
            config_path=config_path,
            style_vec_path=style_path,
            device=device,
        )

        for sample_id, text in samples.items():
            out = OUT_DIR / f"{model_name}_{sample_id}.wav"
            try:
                synth(m, text, out)
            except Exception as e:
                print(f"  [{out.name}] ERROR: {e}")

    print("\n=== done ===")
    print(f"出力ディレクトリ: {OUT_DIR}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
