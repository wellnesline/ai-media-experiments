# Kling 2.5 i2v Spike (16:9 一枚絵動画化)

**目的**: 「一枚絵 i2v 動画」 系列の本パイプ化前検証。 既存のコマ割りページ型パイプラインではなく、 **16:9 一枚絵 (吹き出し/テキスト無し) を gpt-image-2 で生成 → Kling 2.5 で i2v** という新フローを試す。

## アーキテクチャ

```
prompts/NN.txt
  ↓ gen_still.py (gpt-image-2, 1536x864)
input/NN.png       (16:9 一枚絵、吹き出し無し)
  ↓ kling_i2v.py (Kling 2.5 turbo pro, Fal.ai 経由)
output/NN_vN.mp4   (1920x1080, 5 or 10 秒, 24fps)
  + NN_vN.meta.json
```

吹き出し / セリフ / キャプションは画像段では一切付けない。 後段で別レイヤー (動画字幕 or 吹き出し合成) で重ねる前提。

## セットアップ

- `.env` に `FAL_KEY=...` (Fal.ai dashboard)
- `OPENAI_API_KEY` (gpt-image-2)
- `pip install fal-client` (1.0.0 動作確認済)

## 実行

### Step 1: 一枚絵生成

```bash
python sandbox/kling-i2v-spike/gen_still.py \
  --prompt-file sandbox/kling-i2v-spike/prompts/01_workshop.txt \
  --output sandbox/kling-i2v-spike/input/01_workshop.png
```

- size: 1536x864 (16:9)
- model: gpt-image-2, quality: low (約 $0.01-0.02 / 枚)
- prompt は **テキスト/吹き出し禁止句を必ず含める**

### Step 2: i2v 動画化

```bash
python sandbox/kling-i2v-spike/kling_i2v.py \
  --input sandbox/kling-i2v-spike/input/01_workshop.png \
  --prompt "[英語推奨] subtle motion description with style preservation" \
  --duration 5 --tag 01_workshop_v1
```

- model: `fal-ai/kling-video/v2.5-turbo/pro/image-to-video`
- 5秒 = $0.35、 10秒 = $0.70
- 出力: 1920x1080 H.264 24fps mp4
- レイテンシ: 約 80-120秒

## 1カット試作結果

| 項目 | 結果 |
|---|---|
| 入力 | `input/01_workshop.png` (1536×864, 老人 工房の中) |
| 出力 | `output/01_workshop_v1.mp4` (1920×1080, 約5秒) |
| 生成時間 | 約 80 秒 |
| コスト | **$0.35** |
| キャラ顔保持 | ◎ 同一人物識別可、 崩壊なし |
| 絵柄整合 | ◎ マンガ調維持 (3D化なし) |
| 動きの自然さ | ○ 視線移動+わずかな体揺れ、 違和感なし |
| 背景安定性 | ◎ 吊りランプ/棚の構造ほぼ静止 |

→ **品質は本パイプ化に耐える**。 prompt 設計 (subtle motion + maintain style) が効く。

## prompt 設計のコツ

### 一枚絵 (gpt-image-2) 側

- **NO text / NO speech bubbles / NO captions / NO writing** を強制句として複数回繰り返す
- **構図に余白** を持たせる (キャラ右寄せ + 背景左、 等)
- **後で動かせる要素を入れる** (持ち物、 髪、 背景の小物)
- **style references** を1-2個明示 (例: "a specific named anime style")

### i2v (Kling) 側

- **subtle / slow / gentle** 等の控えめ動詞で動きを指定 (派手な動きは破綻しやすい)
- **maintain manga illustration style** を必ず末尾に
- 背景安定: "background remains static" or "subtle background motion"
- 動かしたい要素を具体的に: "the bag sways", "shoulders rise and fall with a breath"

## 次フェーズ判断

### GO (本パイプ化) の場合

1. **対象用途の定義** (参考: ターゲット層ごとの候補)
2. `<new-project>/` 立ち上げ + scenes.py schema 設計
   - フィールド: `still_prompt` (gpt-image-2 用) + `motion_prompt` (Kling 用) + `duration`
3. `scripts/gen_still_pipe.py` + `scripts/gen_i2v_pipe.py` 本実装 (parallel batch)
4. 後段の吹き出し / 字幕 / BGM 合成は既存の動画パイプライン流用可能

### コスト見積もり (10分動画)

| 構成 | カット数 | 単価 | 合計 |
|---|---|---|---|
| 全カット Kling 5秒 + 一枚絵 | 120 | $0.36 | **$43** |
| 30秒 Shorts | 6 | $0.36 | **$2.2** |

静止画ベースの動画よりコストは上がるが、「動く」価値が乗る。

## ファイル一覧

- `gen_still.py` — gpt-image-2 一枚絵生成
- `kling_i2v.py` — Fal.ai 経由 Kling 2.5 i2v
- `prompts/` — 一枚絵プロンプト保存
- `input/` — 生成された PNG (16:9)
- `output/` — i2v 出力 mp4 + meta.json
- `frames/` — 検査用フレーム抽出 (gitignore 想定)
- `eval.md` — 評価ログ
