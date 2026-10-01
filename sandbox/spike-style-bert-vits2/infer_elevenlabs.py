#!/usr/bin/env python3
"""ElevenLabs で同じ 4 サンプルを生成し、SBV2 と直接比較できるようにする。

商用 OK 男性ボイス候補:
- Brian(穏やか・フレンドリー、解説向き)
- Daniel(権威・ニュース、テック解説向き)
- George(ウォーム・ナレーション、ストーリーテリング向き)

モデルは eleven_multilingual_v2(日本語対応最強)。
"""
from __future__ import annotations

import os
import sys
import time
from pathlib import Path

OUT_DIR = Path(__file__).resolve().parent / "out_elevenlabs"
OUT_DIR.mkdir(exist_ok=True)


def load_dotenv() -> None:
    p = Path(__file__).resolve().parent.parent.parent / ".env"
    if not p.exists():
        return
    for line in p.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, _, v = line.partition("=")
        os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))


def main() -> int:
    load_dotenv()
    if not os.environ.get("ELEVENLABS_API_KEY"):
        sys.stderr.write("ELEVENLABS_API_KEY 未設定\n")
        return 1

    from elevenlabs.client import ElevenLabs

    client = ElevenLabs(api_key=os.environ["ELEVENLABS_API_KEY"])

    samples = {
        # synthetic sentences (not taken from any real article)
        "01_intro": "朝いちばんに窓を開けて、庭の土の湿り具合を確かめる。",
        "02_explainer": "植木鉢を並べ替えてみると、日当たりの悪い場所が意外に多いことに気づいた。置き場所を少し変えるだけで、葉の色が見違えるほど良くなった。",
        "03_long": "苗を育て始めた頃、最初につまずいたのは水の量だった。毎日あげるべきか、土が乾いてからでよいのか、迷ううちに根が弱ってしまった。",
        "04_cta": "今回は、鉢植えの基本をまとめた話をお届けしました。気に入ったら、また覗きに来てください。",
    }

    # 商用 OK の premade 男性ボイス(ElevenLabs の Default voices は商用利用可)
    # voice_id は ElevenLabs の固定 ID
    voices = {
        "Brian": "<VOICE_ID_1>",   # 穏やか・解説向き
        "Daniel": "<VOICE_ID_2>",  # ニュース・権威
        "George": "<VOICE_ID_3>",  # ウォーム・ナレーション
    }

    model_id = "eleven_multilingual_v2"

    print(f"=== model: {model_id} ===")
    total_chars = 0
    for voice_name, voice_id in voices.items():
        print(f"\n=== voice: {voice_name} ({voice_id}) ===")
        for sample_id, text in samples.items():
            out = OUT_DIR / f"{voice_name}_{sample_id}.mp3"
            t0 = time.time()
            audio_iter = client.text_to_speech.convert(
                voice_id=voice_id,
                model_id=model_id,
                text=text,
                output_format="mp3_44100_128",
            )
            audio_bytes = b"".join(audio_iter)
            out.write_bytes(audio_bytes)
            total_chars += len(text)
            print(f"  [{out.name}] {len(text)}字 / {time.time()-t0:.2f}s gen / {len(audio_bytes):,} bytes")

    print(f"\n=== done ===")
    print(f"消費文字数: {total_chars} 字 (合計 voice × sample)")
    print(f"出力: {OUT_DIR}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
