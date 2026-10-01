#!/usr/bin/env python
"""Fish Audio (OpenAudio S1 / S2-Pro) ローカルTTS PoC 合成スクリプト。

local-tts-spike と同じ 10 line + 同じ reference 音声を使い、 fish.audio クラウドAPI で
ゼロショット声クローン合成 → output/<model>/ に書き出す。
ElevenLabs / Style-Bert-VITS2 の既存出力と横並び試聴するための比較用。

実行:
  FISH_API_KEY=xxxx python fish_synth.py            # s1 + s2-pro 両方 (専用の仮想環境を有効化してから)
  MODELS=s1 python fish_synth.py                     # s1 のみ

キーは環境変数 or 同階層 .env の FISH_API_KEY=... を読む(非空のみ上書き。
env が空のときだけ .env を使う方針)。
"""
import json
import os
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent

# --- API key 読込 (.env を非空のみ上書き) ---------------------------------
def load_api_key() -> str:
    key = os.getenv("FISH_API_KEY", "").strip()
    env_path = HERE / ".env"
    if env_path.exists():
        for line in env_path.read_text().splitlines():
            line = line.strip()
            if line.startswith("FISH_API_KEY="):
                v = line.split("=", 1)[1].strip().strip('"').strip("'")
                if v and not key:  # env が空のときだけ .env を採用
                    key = v
    if not key:
        sys.exit("FISH_API_KEY 未設定 (環境変数 or .env を確認)")
    return key


# --- [tag] → OpenAudio S1 感情/トーンマーカー --------------------------------
# S1 は括弧マーカーで感情・パラ言語を制御できる。 SBV2 が style に割り当てたのと同じ発想で
# 既存の 9 tag を S1 が解釈しやすい語に寄せる。 sighs は特殊マーカー (sigh) を本文頭に置く。
TAG_TO_FISH = {
    "thoughtful": "(thoughtful)",
    "excited":    "(excited)",
    "annoyed":    "(annoyed)",
    "happy":      "(happy)",
    "surprised":  "(surprised)",
    "appalled":   "(disgusted)",
    "sighs":      "(sigh)",
    "curious":    "(curious)",
    "hesitant":   "(nervous)",
    "neutral":    "",
}


def build_text(raw: str, tag: str) -> str:
    """先頭の [tag] を除去し、 fish のマーカーを前置した本文を返す。"""
    body = raw
    if body.startswith("[") and "]" in body:
        body = body.split("]", 1)[1].strip()
    marker = TAG_TO_FISH.get(tag, "")
    return f"{marker} {body}".strip() if marker else body


def main() -> None:
    from fish_audio_sdk import Session, TTSRequest, ReferenceAudio, ASRRequest

    api_key = load_api_key()
    session = Session(api_key)

    models = [m.strip() for m in os.getenv("MODELS", "s1,s2-pro").split(",") if m.strip()]
    lines = json.loads((HERE / "lines.json").read_text())["lines"]

    # --- reference 音声をロード + (best-effort) fish ASR で transcript 取得 ----
    speakers = {"speaker_a": "reference/speaker_a_ref.mp3",
                "speaker_b": "reference/speaker_b_ref.mp3"}
    refs: dict[str, ReferenceAudio] = {}
    for spk, rel in speakers.items():
        audio = (HERE / rel).read_bytes()
        ref_text = ""
        try:  # 参照テキストがあるとクローン精度が上がる。 取れなければ空でも可。
            asr = session.asr(ASRRequest(audio=audio, language="ja"))
            ref_text = (asr.text or "").strip()
            print(f"[asr] {spk}: {ref_text[:40]!r}")
        except Exception as e:
            print(f"[asr] {spk}: skip ({e})")
        refs[spk] = ReferenceAudio(audio=audio, text=ref_text)

    summary: dict[str, list] = {}
    for model in models:
        out_dir = HERE / "output" / f"fish_{model.replace('-', '')}"
        out_dir.mkdir(parents=True, exist_ok=True)
        print(f"\n===== model={model} -> {out_dir.name} =====")
        timings = []
        for ln in lines:
            text = build_text(ln["text"], ln["tag"])
            req = TTSRequest(
                text=text,
                references=[refs[ln["speaker"]]],
                format="mp3",
                mp3_bitrate=128,
                normalize=True,
                temperature=0.7,
                top_p=0.7,
            )
            fname = f'{ln["id"]}_{ln["speaker"]}_{ln["tag"]}.mp3'
            fpath = out_dir / fname
            t0 = time.time()
            try:
                with open(fpath, "wb") as f:
                    for chunk in session.tts(req, backend=model):
                        f.write(chunk)
                dt = time.time() - t0
                size = fpath.stat().st_size
                ok = size > 0
                print(f'  {ln["id"]} {ln["speaker"]:9} {ln["tag"]:10} '
                      f'{dt:5.2f}s {size//1024:4d}KB {"OK" if ok else "EMPTY"}  "{text[:30]}"')
                timings.append({"id": ln["id"], "sec": round(dt, 2), "bytes": size, "text": text})
            except Exception as e:
                print(f'  {ln["id"]} FAILED: {e}')
                timings.append({"id": ln["id"], "error": str(e), "text": text})
        summary[model] = timings

    (HERE / "output" / "fish_timings.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2))
    # --- 集計 ---
    print("\n===== summary =====")
    for model, ts in summary.items():
        good = [t for t in ts if t.get("bytes")]
        total = sum(t["sec"] for t in good)
        print(f"{model}: {len(good)}/{len(ts)} OK, total {total:.1f}s, "
              f"avg {total/max(len(good),1):.2f}s/line")


if __name__ == "__main__":
    main()
