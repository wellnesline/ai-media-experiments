# 一枚絵 i2v 動画 パイプライン (サンプル制作版)

> 本書の題材は公開用の合成例です。エピソード名・キャラクター・セリフ・秒数は架空で、実制作物とは無関係です。

サンプルエピソードの **冒頭シーン群 (P1-P5、約 60 秒分)** を 「16:9一枚絵 + i2v」 形式で再構成するための制作フロー。

---

## 0. インプット (既存資産、 そのまま流用)

```
episodes/demo-001/
├── scenes.py              ← P1-P5 の SCENES (lines = ストーリー本体)
└── work/
    ├── audio_P1.wav  (約 10s)
    ├── audio_P2.wav  (約 15s)
    └── ...                合計 約 60s

sandbox/character-refs-demo/
├── char_a_base.png        ← キャラリファレンス (キャラA)
└── char_b_base.png        ← キャラリファレンス (キャラB)
```

ストーリー (lines) と音声 (wav) は **一切作り直さない**。
新しく作るのは 一枚絵 (png) と 動画化 (mp4)、 そして合成のみ。

---

## 1. パイプライン全体図

```
STAGE 1: SHOT DEFINITION  (人 + LLM、 設計フェーズ)
   scenes.py (P1-P5)  ─▶  shots.py (S001-S010)
   各 shot: scene_ref / lines_idx / duration (5 or 10 sec) / still_prompt / motion_prompt
                              │
                              ▼
STAGE 2: STILL GENERATION  (参考画像付き、 OpenAI)
   refs/char_a_base.png ┐
   refs/char_b_base.png ┼─▶ /v1/images/edits (size=1536x864, quality=low)
   shot.still_prompt    ┘
   → input/S001.png ... (16:9 一枚絵、 キャラ整合性保持、 テキスト無し)
   キャッシュ: prompt_sha + refs_sha → PNG
                              │
                              ▼
STAGE 3: I2V GENERATION  (Kling 2.5 turbo standard)
   input/S001.png + shot.motion_prompt + duration
   → fal-ai/kling-video/v2.5-turbo/standard/i2v
   → clips/S001.mp4 ... (1920×1080, 24fps, 5 or 10 sec, 無音)
   並列実行: 同時 max 5 / キャッシュ: still_sha + motion_sha + duration → MP4
                              │
                              ▼
STAGE 4: AUDIO ALIGN  (既存 audio_P*.wav を流用)
   ffmpeg silencedetect で line 境界検出 → audio_S001.wav ...
   各 P-SCENE を含まれる shot 数に分割し timing.json に保存
                              │
                              ▼
STAGE 5: SHOT COMPOSE  (mp4 + wav を 1 shot 単位で合体)
   mp4 を audio に合わせて trim or freeze 延長 → shots/S001_av.mp4
   audio > video: 警告 (shot 分割不足) / video > audio: 末尾を trim
                              │
                              ▼
STAGE 6: EPISODE CONCAT + 字幕
   ffmpeg concat → intermediate.mp4 → 字幕レイヤー (既存の字幕合成を流用)
   → output/demo_001_output.mp4
```

---

## 2. ディレクトリ構成 (sandbox 内)

```
sandbox/kling-i2v-spike/
├── README.md / SHOT_RULES.md / PIPELINE.md
├── kling_i2v.py               (Stage 3 で利用)
├── gen_still.py               (参考画像対応に拡張予定)
├── gen_still_refs.py          (Stage 2 専用、 /v1/images/edits)
├── split_audio_by_silence.py  (Stage 4)
├── compose_shot_av.py         (Stage 5)
├── concat_episode.py          (Stage 6)
├── videos/
│   └── demo-001-motion/
│       ├── shots.py / timing.json
│       ├── input/ clips/ audio/ shots/ output/
└── prompts/
    └── 001_chars.txt          (キャラ固定句、 全 still で reuse)
```

---

## 3. 各 Stage の実装方針

### Stage 1: SHOT DEFINITION (人手 + LLM)

- SHOT_RULES.md の分割基準で 10 shots 程度を `shots.py` に書き起こす
- still_prompt は キャラ固定句 (`prompts/001_chars.txt`) を冒頭に貼って、 シーン記述を後段に
- 1 shot 1 still。 再利用 (`reuse_still_from`) は使わない (キャラ一貫性検証フェーズ)

### Stage 2: STILL GENERATION (gpt-image-1 with refs)

- `POST /v1/images/edits`、 image[] に両キャラの ref を常に渡す
  (単独キャラのカットでも両方渡すことで、 出てこない側の見た目を内部で固定)
- size 1536x864 (16:9)、 quality low。 1枚 約 $0.02

### Stage 3: I2V GENERATION (Kling 2.5 standard)

- `kling_i2v.py` をそのまま使用 (--tier standard 固定)。 spike 段階は逐次でも可
- 10 shots (5sec 6本 + 10sec 4本) で約 $2.8 想定

### Stage 4: AUDIO ALIGN

- ffmpeg `silencedetect=noise=-35dB:d=0.25` で line 境界 (= 静寂区間) を検出
- shots.py の lines_idx_range に基づき該当 line 群を抜き出し、 timing.json に start/end を記録

### Stage 5: SHOT COMPOSE

| mp4 duration | audio duration | 処理 |
|---|---|---|
| 5.0s | 4.5s | mp4 を 4.5s に trim |
| 5.0s | 5.7s | 警告、 shot を 10s に作り直しすべきだった |
| 10.0s | 8.0s | mp4 を 8.0s に trim |
| 10.0s | 4.5s | mp4 を 4.5s に trim (10s 取りすぎ警告) |

```
ffmpeg -y -i clips/S001.mp4 -i audio/S001.wav \
  -c:v copy -c:a aac -map 0:v -map 1:a -shortest shots/S001_av.mp4
```

### Stage 6: CONCAT + 字幕

- concat list 生成 → ffmpeg concat demuxer
- 字幕は既存の字幕合成を抽出して流用し、 lines は scenes.py から取得

---

## 4. shots テーブルの形式 (合成例)

| shot | scene | 担当 lines (idx) | speaker | dur | est. audio | 推奨カット |
|---|---|---|---|---|---|---|
| S001 | P1 | [0] | char_a | 5 | ~4.0s | キャラA 登場 |
| S002 | P1 | [1] | char_b | 5 | ~4.8s | キャラB 受け |
| S003 | P2 | [0,1] | char_a | 10 | ~7.5s | 状況説明 |
| S004 | P2 | [2,3] | char_b+char_a | 5 | ~4.5s | 掛け合い (両者横並び) |
| ... | | | | | | |

目安として video 70 秒 (5sec × 6 + 10sec × 4) に対し audio 約 60 秒、 差分は各 shot 末尾の trim で吸収する。
10 秒枠を超えそうな shot は実測後に a/b へ再分割する。

---

## 5. コスト試算

| 項目 | 単価 | 数量 | 合計 |
|---|---|---|---|
| gpt-image-1 (with refs) | $0.02 | 10枚 | $0.20 |
| Kling 2.5 standard 5sec | $0.20 | 6本 | $1.20 |
| Kling 2.5 standard 10sec | $0.40 | 4本 | $1.60 |
| 合計 | | | 約 $3.00 |

既存音声・字幕は再利用なのでコスト 0。

---

## 6. リスクと打ち手

| リスク | 打ち手 |
|---|---|
| キャラ一貫性が崩れる (refs の限界) | 同一 prompt の n=3 で生成して目視で best 採用、 ダメなら LoRA / References 系へ |
| audio 境界が silencedetect で検出できない | pause_after 値とほぼ一致するので閾値調整 (-25dB / 0.20s 等) |
| 10s 内にセリフが収まらない | 実測後に a/b へ分割 |
| 字幕パイプ流用がうまく動かない | 一旦字幕無しで音声+映像のみ完成、 字幕は後工程 |
| Kling の動きが想定と違う | motion_prompt 調整 (1 shot 再生成 約 $0.20) で 2-3 回試行 |
