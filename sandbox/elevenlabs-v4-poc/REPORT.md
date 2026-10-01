# ElevenLabs v3 / v4 読み精度 POC（手法メモ）

> 公開版では実測結果（件数・秒数・文ごとの判定）を載せていない。ここには比較の手順と、結果をどう読むかの方針だけを残す。音声・`results.json` も非同梱。

## 目的

同じ声・同じ本文で `eleven_v3` と `eleven_v4` を生成し、日本語の読みにくい語句（難読漢字、助数詞、英字の略語、識別子、記号、数値）で読みの差が出るかを調べる。

## 手順

1. `run_poc.py` の `CASES`（合成した短文）を、モデルごとに同じ条件で生成する。声 ID は環境変数 `NARRATOR_VOICE_ID`、API キーは `ELEVENLABS_API_KEY`。
2. 条件はモデル以外すべて揃える。seed、stability、similarity、出力形式、`language_code`。再現性の確認用に、一部の文は seed を変えて再試行する（`_r2`）。
3. `transcribe.py` で独立した ASR（複数モデル）にかけ、`make_transcripts.py` が原文と文字起こしの対照表を作る。
4. `generate_voice_quality.py` は、基準設定の v3 と、タグなし／語り方タグ付きの v4 を同じ本文で並べる。`generate_designed_comparison.py` は Voice Design で作った声を v3/v4 で並べる。`serve.py` が聴き比べページをローカルで出す。

## 結果の読み方

- ASR は発音の代理指標にすぎない。同音異字、英字の表記、人名は ASR の揺れが大きく、文字列一致で得点化しない。
- 人間の試聴判定は別工程。ASR だけで「改善」「悪化」を断定せず、疑いがあるものは聴いて確認する。
- 少数のサンプルでは速度や品質の一般的な差とは扱わない。
- 文脈によって読みが変わる語（助数詞など）は、短文と長文の両方で確認する。
- v4 を既存の合成モジュールに組み込む場合は、モデル別の設定とキャッシュの分離が必要になる。

## 公式資料

- https://elevenlabs.io/docs/eleven-creative/playground/text-to-speech
- https://elevenlabs.io/docs/api-reference/text-to-speech/convert-with-timestamps