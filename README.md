# ai-media-experiments

Small, self-contained experiments on AI media generation: image-to-video, voice synthesis comparisons, and transparent-background animation post-processing.

画像生成・動画生成・音声合成まわりの検証（PoC / スパイク）を集めたリポジトリです。制作パイプラインへ組み込む前に「使えるか、どこで壊れるか」を確かめる検証を、公開用に整理しています。成果物（音声・動画・画像）は含めず、手法と判断の材料を残しています。ElevenLabs の読み比較（`sandbox/elevenlabs-v4-poc/`）は実測値を載せません。ローカル音声合成（`sandbox/spike-style-bert-vits2/`）のメモには、速度の概数（RTF）だけ残しています。透過アニメーションの PoC（`circle-emblem-animation-poc/`、`qwen-minimax-alpha-animation-poc/`）の報告には、検証環境での参考実測（生成時間・透明率など）を載せています。

## 概要

新しい生成 AI サービスを制作パイプラインに入れる前に、品質・制約・ライセンス・コストを小さく試して判断するための実験集です。どの実験も、目的、手順、結果の読み方を文書に残し、「結果をどう解釈してよいか」まで書いています。

## 含まれる実験

| ディレクトリ | 内容 |
|---|---|
| `sandbox/kling-i2v-spike/` | 16:9 の一枚絵を生成し、画像から動画へ変換（i2v）するパイプラインの検証。撮影ルール（カット長、動きの強さ、顔アップの扱い）、絵コンテ生成、複数の動画生成サービス（i2v、リップシンク、アバター）の比較用スクリプト。`videos/demo-001/` は合成のサンプル題材 |
| `sandbox/elevenlabs-v4-poc/` | 音声合成モデルの 2 世代を、同じ声・同じ本文・同じ条件で生成して読みの精度を比較する手順。独立した ASR で書き起こし、原文との対照表を作り、聴き比べページを配信する |
| `sandbox/spike-style-bert-vits2/` | ローカルで動く音声合成（Style-Bert-VITS2）とクラウド音声合成の比較。音声の異常検知、強制アライメント、補正のスクリプト |
| `sandbox/fish-speech-spike/` | クラウド音声合成 API でのゼロショット声クローンの品質検証。着手前にライセンスと動作環境の制約を調べ、「ローカル無料で置き換え」という当初の前提が成り立たないことを先に確認している |
| `circle-emblem-animation-poc/` | 透過の円形紋章を原画に、動画生成モデルでループ動作を作り、背景を除去して RGBA の PNG 列・スプライトシート・透過動画へ変換する後処理 |
| `qwen-minimax-alpha-animation-poc/` | 透過 PNG のキャラクター原画から短いゲーム用アニメーションを作る同種の後処理 |

## 設計のポイント

- **着手前の制約確認**: 品質を試す前に、ライセンス（商用可否）と動作環境の制約を調べ、不成立なら実験の目的自体を組み替えます（音声合成の検証が代表例）。
- **条件を揃えた比較**: モデル以外の条件（seed、安定度、出力形式、言語指定）を固定し、再現性を見るために seed を変えた再試行も入れます。
- **代理指標の扱い**: ASR の一致は発音の代理指標にすぎず、最終的には人の試聴判定が必要、という前提を文書に書いています。
- **後処理の機械検証**: 透過アニメーションでは、アルファ値の範囲、透明画素率、動画コーデックとフレーム数、先頭と末尾フレームの差を機械的に検証します。
- **鍵の扱い**: 動画・音声生成は従量課金のサービスが多いため、鍵は環境変数または `.env` から読み、未設定なら呼び出す前に停止します（例: `kling_i2v.py`）。コードに鍵を書きません。

## 動かし方

実験ごとに必要なものが違います。共通の考え方は次のとおりです。

```powershell
# 例: i2v の検証（sandbox/kling-i2v-spike）。鍵は環境変数か .env に置く
$env:FAL_KEY = "<your key>"
$env:OPENAI_API_KEY = "<your key>"
python sandbox/kling-i2v-spike/gen_still.py
python sandbox/kling-i2v-spike/kling_i2v.py
```

環境変数（使うスクリプトだけ設定すれば足ります）:

| 変数 | 用途 |
|---|---|
| `OPENAI_API_KEY` | 画像生成 |
| `FAL_KEY` | 動画生成サービス（Fal 経由） |
| `ELEVENLABS_API_KEY` / `NARRATOR_VOICE_ID` / `DESIGNED_VOICE_IDS` | 音声合成（声の指定を含む） |
| `FISH_API_KEY` / `MODELS` | クラウド音声合成の検証 |
| `SOURCE_RGBA` | 透過アニメーションの原画ファイル |

動画生成モデルの本体呼び出し（透過アニメーション実験の生成部分）は、ローカルの ComfyUI などで別に行い、このリポジトリのスクリプトはその出力の後処理を担います。

## 制限事項（閉包）

- **同梱していない依存**（12 件）: `numpy`、`PIL`（Pillow）、`cv2`（OpenCV）、`fish_audio_sdk`、`fal_client`、`openai`、`soundfile`、`torch`、`style_bert_vits2`、`faster_whisper`、`elevenlabs`、`diagram_blob`。`requirements` ファイルは同梱していません。
- **他の公開リポジトリへの依存**: `diagram_blob` は `diagram-blob-animator` リポジトリにあります（`sandbox/spike-style-bert-vits2/` の一部スクリプトが使用）。
- **合成スタブ**: `src/openai_image_config.py`（画像モデルと品質の既定値だけ）、`src/_dotenv.py`（`KEY=VALUE` だけを読む最小の `.env` ローダー）は合成です。元のプロジェクトの共通モジュールの代わりに置いています。`videos/demo-001/` の題材、キャラクター、セリフも架空の合成例です。
- 同梱していないもの: 生成した音声・動画・画像、モデルの重み、各実験の入出力ディレクトリ（`input/`、`output/`、`prompts/` など）、キャラクターの参照画像、音声合成の検証の実測結果。
- 外部サービス（OpenAI、Fal 経由の動画生成、ElevenLabs、Fish Audio、ComfyUI 上の動画生成モデル）は有料または利用条件のあるサービスです。各サービスの利用規約と、モデル・声・素材の許諾の範囲で使ってください。ローカル音声合成のモデルには、商用利用が不可のものがあります（ライセンスを確認してから使うこと）。
- Qwen Image・MiniMax H3 などローカルモデルを使う PoC は、各モデルのライセンス（Qwen Research License など）に従う非商用の評価用です。JVNV など非商用ライセンスの音声モデルで作った試聴用音声は、声質の判定にだけ使い、公開・配布しません。
- 検証環境（OS・GPU バックエンド）に依存するスクリプトを含みます。パスや仮想環境の前提は環境に合わせて調整してください。日本語フォントを使う `sandbox/kling-i2v-spike/videos/demo-001/` のスクリプトは、環境変数 `JP_FONT_PATH`（通常）と `JP_FONT_BOLD_PATH`（太字）でフォントファイルを渡します（既定値なし）。
- 一部の実験メモには、当時の環境でのバージョンや手順が残っています。

## ライセンス

All rights reserved. 閲覧目的で公開しています。詳細は LICENSE を参照。
