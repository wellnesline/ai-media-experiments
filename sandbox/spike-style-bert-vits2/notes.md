# Style-Bert-VITS2 動作検証メモ

ナレーション中心の解説動画向け。立ち絵なし。
ElevenLabs 課金回避を目的に、ローカル TTS の最有力候補として Style-Bert-VITS2 を検証した。

## 結論(先出し)

- **動作 OK**:ローカルの GPU（PyTorch）で動く。安定して wav 出力できる。
- **速度**:初回ロード後は **RTF 0.03〜0.15**(実時間の3〜30倍速)。1分のナレーションが2-20秒で生成される。十分量産に耐える。
- **品質**:実聴で判定する(下の「品質所感」は実聴前の予測)。
- **ライセンス**:`amitaro` は商用 OK・クレジット表記必要。JVNV 系は非商用。
  - ElevenLabs Voice Library の日本人ネイティブは無料プランの API 経由では使えない(有料プランが必要)
  - SBV2 の配布モデルに、商用 OK の男性ボイスは無い

## 環境

| 項目 | 値 |
|---|---|
| OS | ローカル検証機 |
| CPU/GPU | ローカル GPU |
| Python | 3.12 |
| venv | `sandbox/spike-style-bert-vits2/.venv`(本体 .venv とは独立) |
| torch | 2.3.1(SBV2 が `<2.4` を要求) |
| numpy | 1.26.4(SBV2 が `<2` を要求) |
| transformers | 4.55.4(5.x は torch 2.4+ を要求するためダウングレード) |
| setuptools | 80.10.2(81+ は pkg_resources 廃止) |

## セットアップで踏んだ罠

1. **本体 venv との衝突**:workspace/.venv は numpy 2.x。SBV2 は numpy<2 必須なので spike 専用 venv に隔離。
2. **PyAV ビルド失敗**:`pyannote.audio` が依存する `av` のビルドに `pkg-config` 必須。OS のパッケージマネージャで導入して解決。
3. **pyannote.audio 不要判定**:学習データ前処理用なので、推論最小セット用に `requirements_inference.txt` を別作成して回避。
4. **transformers 5.x が torch 2.4+ 要求**:`transformers>=4.45,<5` にダウングレード。
5. **setuptools 82+ で pkg_resources 削除**:librosa が pkg_resources を使うため `setuptools<81` に戻す。
6. **transformers が soxr 必須**:audio_utils が soxr を import するため別途 `pip install soxr`。

## 使ったモデル(配布デフォルト)

`initialize.py` を走らせると以下が `repo/model_assets/` に DL される:

- **amitaro**:明るめ女性、キャラ寄り
- **jvnv-F1-jp / F2-jp**:JVNV データセット女性、感情表現あり、解説に寄り添う
- **jvnv-M1-jp / M2-jp**:JVNV データセット男性
- **koharune-ami**:こはるねあみベース

BERT/SLM は別途約 5GB DL される(`bert/` と `slm/`)。

## 検証サンプル(`infer_test.py`)

合成の 4 サンプル（園芸をテーマにした架空の文。実在の記事の文ではない）:

1. `01_short_intro`:短文(~30字)
2. `02_mid_paragraph`:中文(~70字)
3. `03_explainer`:説明文(~100字、列挙を含む)
4. `04_call_to_action`:CTA(~50字)

## 計測結果(ローカル GPU・概数)

| モデル | RTF の目安 | 備考 |
|---|---|---|
| amitaro | 約 0.04〜0.15 | 初回の 1 サンプルだけモデルロード込みで遅い |
| jvnv-F1-jp | 約 0.03〜0.15 | 2 サンプル目以降は 0.05 未満 |

- **初回 1 サンプル目だけ GPU グラフコンパイル+モデルロードで遅い**(RTF 1.98)。2 サンプル目以降は爆速。
- 量産時は同モデルで連続生成すれば、実時間の **20-30 倍速** で wav が出る。
- 1 本 6 分の動画(ナレーション約 4 分)なら **生成 12-15 秒程度**。量産でも余裕。

## 品質所感(コードからの推測、要・実聴判定)

実聴前なので予測ベース:

- **jvnv-F1-jp**:JVNV(感情ラベル付き音声コーパス)ベース。女性、解説寄り、感情コントロール可。
- **amitaro**:キャラ寄り、明るめ。技術解説にはやや軽い可能性。
- **jvnv-F2-jp / M1 / M2**:バリエーション用。男性ナレーターが欲しいなら M1/M2 試聴。
- **koharune-ami**:配布物の中で一番ナレーション系っぽい名前。要試聴。

## 商用利用ライセンス確認(モデル別、要・別途確認)

SBV2 本体は AGPL-3.0(SaaS 提供しなければ動画作成用途では問題なし)。
モデルは配布元別に規約あり:

- **JVNV**:CC BY-NC-SA 4.0(**非商用**)→ 収益化動画では使えない可能性大、要確認。JVNV 由来の声で作った試聴用音声は、社内の声質判定にだけ使い、公開・配布しない
- **amitaro**:商用利用可、クレジット表記必須(動画概要欄)。配布元の規約を確認すること
- **こはるねあみ**:配布元規約確認

→ 収益化前提では、JVNV 系はライセンス上使えない。商用 OK のモデルか独自学習が選択肢になる。

## 次にやること

1. **生成した wav を実聴して品質判定**(`sandbox/spike-style-bert-vits2/out/`)。
2. ライセンス OK な配布モデルを試す。
3. 記事から動画を作るパイプラインへ統合する設計を固める:
   - text → SBV2(wav) → ffmpeg(画像スライド + テロップ + BGM) → mp4
   - 既存 compose.py 系の流用 or Remotionで別パイプライン。
4. ElevenLabs 比較サンプル(同テキスト)を 1 本だけ作って音質差を確認。

## 残タスク / オープン論点

- [ ] 商用 OK モデルのクレジット表記の扱い
- [ ] イラスト系コンテンツの語り手 SBV2 化検討
- [ ] ファインチューニング(独自に収録した、権利処理済みの声で学習)に踏み込むか?要 GPU/データ
- [ ] 句点で短く切って `line_split=True` にすると自然?要パラメータ調整

## ファイル

- `repo/`:Style-Bert-VITS2 公式リポ(clone、commit pin はせず最新)
- `.venv/`:spike 専用 venv
- `requirements_inference.txt`:推論最小セット
- `infer_test.py`:動作検証スクリプト
- `out/`:生成 wav(非同梱)
