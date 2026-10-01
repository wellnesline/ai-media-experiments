# Fish Audio (OpenAudio S1 / S2-Pro) TTS PoC

**目的**: Fish Speech / OpenAudio が、 既存の動画パイプラインで使っている ElevenLabs v3 を置き換える/補完する候補になるか、
**日本語品質 + ゼロショット声クローン** を実生成して ElevenLabs / Style-Bert-VITS2 と
横並び比較する。

**環境**: ローカル検証機 / Python 3.12 / fish-audio-sdk 1.3.0

---

## ⚠️ 着手前に判明した重要事実(品質より先に効く)

| 論点 | 結果 | 出典 |
|---|---|---|
| ローカル重みのライセンス | **s1-mini = CC-BY-NC-SA-4.0(非商用)** / 本体 S1・S2-Pro = FISH AUDIO RESEARCH LICENSE(研究用) | HF model card |
| 自前ホストのローカル動作 | 公式は **Linux/Windows のみ**。公式対象外の環境での自前ホストは**実用外(1短文 約25〜70秒)** | fish docs / GitHub |
| 商用での現実解 | **fish.audio クラウド有料API のみ**(ElevenLabs と同じ構図) | — |

→ 当初の「ローカルで無料の ElevenLabs 代替」は**ライセンス + 公式対応環境の両面で不成立**。
本 PoC は **クラウドAPI で品質だけを検証**し、「有料APIを使ってまで ElevenLabs から乗り換える/
併用する価値があるか」を判断材料にする。

---

## 比較設計(apples-to-apples)

local-tts-spike と**同じ 10 line・同じ reference 音声**を流用:

- `lines.json` … 9 感情tag + neutral の 10 line(サンプルエピソードから抽出した例文)
- `reference/speaker_a_ref.mp3`, `reference/speaker_b_ref.mp3` … クローン元（参照音声は、自前で合成した音声、または本人の許諾がある録音に限る。リポジトリには同梱しない。第三者の声を無断でクローンしないこと）
- `output/elevenlabs_baseline/` … ElevenLabs v3(現状品質、symlink)
- `output/sbv2_baseline/` … Style-Bert-VITS2(ローカル候補、symlink)
- `output/fish_s1/`, `output/fish_s2pro/` … 本PoCで生成(S1 と S2-Pro 両方)

感情は S1 のマーカー機能を使う(`[excited]`→`(excited)` 等、`fish_synth.py` の `TAG_TO_FISH`)。
reference は fish ASR で transcript を best-effort 取得してクローン精度を上げる。

---

## 実行方法(API キー入手後)

1. https://fish.audio → サインアップ → 課金登録 → API キー発行(Settings → API Keys)
2. キーを置く:
   ```
   echo 'FISH_API_KEY=fa-xxxxxxxx' > .env   # この spike 直下
   ```
3. 合成:
   ```
   python fish_synth.py          # s1 + s2-pro 両方(専用の仮想環境を有効化してから)
   MODELS=s1 python fish_synth.py # s1 のみ(Windows PowerShell では $env:MODELS='s1')
   ```
4. `output/` 配下を ElevenLabs/SBV2 と聴き比べ、`report.md` に判定追記。

---

## ステータス

- [x] API 仕様確定(`POST /v1/tts`, msgpack, `model:` ヘッダ, ゼロショット references)
- [x] SDK インターフェース実機検証(`session.tts(req, backend="s1"|"s2-pro")`)
- [x] 比較素材 集約(10 line + reference + ベースライン symlink)
- [x] `fish_synth.py` 実装・コンパイル確認済
- [ ] API キー入手(利用者側の操作)
- [ ] 実生成 → 横並び試聴 → report.md 判定
