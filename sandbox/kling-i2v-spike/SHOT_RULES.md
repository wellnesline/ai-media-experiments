# 一枚絵 i2v 動画 — 撮影ルール + 台割スキーマ

「一枚絵 i2v 動画」 系列の制作ルール ドラフト。 sandbox spike で 1カット試作確認済。

---

## 1. Kling 2.5 turbo standard の仕様制約

| 制約 | 仕様 | 影響 |
|---|---|---|
| Duration | **5秒 or 10秒の二択** (連続値不可) | セリフ長を 5/10秒に絞り込む必要 |
| 解像度 | 1920×1080 固定 (16:9) | 一枚絵は 1536×864 (16:9) で生成 |
| FPS | 24 | 字幕合成も 24fps 揃え |
| 1 generation = 1 cut | 同一 still 内のみ、シーンチェンジ不可 | 場面/カメラ変えるなら別 shot |
| 動き | **subtle / slow / gentle** が安定 | 派手な動作は破綻、控えめが安全 |
| 顔アップ | 崩れやすい | ミディアム〜ロングショット推奨 |
| テキスト | 画像内テキストを動かすと壊れる | 一枚絵段で **文字一切入れない** |
| コスト | $0.20 / 5秒、 $0.40 / 10秒 | 5秒主体で組むほうが柔軟 |
| レイテンシ | 60-90秒 / カット | 並列実行で吸収 (max 同時 5-10) |

---

## 2. 1 shot = 1 cut の基本単位

```
Shot
├── still (一枚絵 1536×864 PNG, gpt-image-2)
├── motion_prompt (Kling 用 動き指示)
├── duration (5 or 10 秒)
└── lines [n本] (このカットで再生するセリフ群)
    ├── speaker
    ├── text
    ├── estimated_sec (合成時の予測秒数)
    └── pause_after
```

**Shot duration の決定ロジック**:
```
total_speech_sec = sum(line.estimated_sec + line.pause_after for line in lines)
buffer = 0.5
target = total_speech_sec + buffer

duration = 5 if target <= 5.0 else 10
```

`target > 10.0` の場合は **shot 分割が必須** (キャラ立ち位置・表情をリセット)。

---

## 3. Shot 分割判断基準 (どこで切るか)

連続する line を 1 shot にまとめるか分けるか:

| シグナル | 同一 shot 維持 | shot 分割 |
|---|---|---|
| 話者交代 | ◯ (片方ずっと話す) | **◎ 話者ごとにカット切り替えが自然** |
| 感情の極端な変化 | ✗ 顔崩壊リスク | **◎ 別カット推奨** |
| 場所・カメラアングル変化 | ✗ Kling 不可 | **必須** |
| 同一場所・同一表情の連続説明 | **◎ 一発 10秒** | △ 不要分割 |
| セリフ合計 > 10秒 | ✗ Kling 制約超 | **必須** |

**目安**: 「マンガで考えてコマ割り変える箇所」 = shot 分割点。

---

## 4. 一枚絵 (still) プロンプト ルール

### 必須要素

1. **構図指定**: "16:9 cinematic frame", "medium shot", "long shot", "close-up" のいずれか
2. **キャラ指定**: 既存キャラ (合成例: キャラA / キャラB) は外見の特徴を毎回明示
   - キャラA: "young adult, short dark hair, green jacket over a gray shirt, gray tote bag, bright curious face"
   - キャラB: "elderly Japanese man in his late 60s, short white hair, round glasses, green apron over a plaid shirt, gentle dry-humored expression"
3. **シーン**: 工房 / 庭の小道 / 作業小屋等、場所を一行で
4. **動き余地**: 後で動かせる要素を入れる (持ち物、 髪、 背景の時計やカーテン)
5. **NO text** 句を末尾に必ず:
   ```
   Strict constraints: No text. No speech bubbles. No captions. No writing of any kind. No watermarks.
   ```

### 推奨スタイル句

```
Style: Japanese seinen manga adapted to soft color illustration,
hand-drawn linework, painterly background, expressive but restrained
character design.
```

### キャラ一貫性 (現状の暫定対策)

- 同一エピソード内では **同一スタイル句 + 同一キャラ説明** を全 shot で機械コピー
- 顔の特徴 (髪型 / 服装 / アクセサリ) を 5-7 単語の固定句に圧縮し reuse
- 厳密一貫性が必要なら 後段で LoRA 学習 or Runway References へ昇格 (本パイプ化フェーズ)

---

## 5. motion_prompt ルール

### 推奨形

```
[subject motion (1-2 actions)] + [secondary motion (背景要素)] +
[camera (任意、slow zoom等)] + "Maintain manga illustration style."
```

### 動詞リスト (動作別)

| カテゴリ | 動詞例 |
|---|---|
| 顔 | softens, blinks slowly, lips part faintly, glances aside |
| 体 | shoulders rise and fall, leans forward slightly, head tilts |
| 手 | hand gestures gently, fingers fidget, holds tighter |
| 背景 | hanging lamps sway, leaves flutter, dust drifts |
| カメラ | slow push-in, gentle dolly, slight tilt |

### NG パターン

- "runs", "jumps", "punches" (派手すぎ → 物理破綻)
- "transforms into", "fades to" (シーンチェンジ系 → Kling 範囲外)
- 顔アップで「驚きで目を見開く」 を要求 (高確率で目が崩れる)

---

## 6. セリフ → カット長 マッピング表

VOICEVOX or ElevenLabs 合成時の **目安 mora/sec**:
- VOICEVOX (4.x): 約 7-8 mora/sec
- ElevenLabs (v3): 約 6-7 mora/sec

| 文字数 (日本語平仮名換算) | 合成秒数 | 推奨 duration |
|---|---|---|
| 〜20 文字 | 〜3.0 sec | 5 |
| 20-30 文字 | 3.0-4.5 sec | 5 |
| 30-50 文字 | 4.5-7.0 sec | 10 |
| 50-70 文字 | 7.0-9.5 sec | 10 |
| 70 文字超 | >10 sec | **分割必須** |

合計値で判断、buffer 0.5sec。

---

## 7. 台割ファイル形式 (proposal)

`videos/<episode>/shots.py` (or .yaml):

```python
SHOTS = [
    {
        "id": "S001",
        "scene_ref": "P1",                         # 旧 SCENES.id (互換)
        "still_prompt_file": "prompts/S001.txt",   # gpt-image-2
        "motion_prompt": "CharA steps one pace into the workshop, slightly out of breath, hand reaching toward a parts tray. Hanging lamps sway. Maintain manga illustration style.",
        "duration": 5,
        "lines": [
            {"speaker": "char_a", "text": "(synthetic sample line A)", "estimated_sec": 3.2, "pause_after": 0.4},
        ],
        "reuse_still_from": None,                  # null or shot_id
    },
    ...
]
```

### 既存の動画パイプラインとの差分

- `kind: "manga"` → `kind: "motion_still"` 新設 (or デフォルト化)
- `asset` → `still_prompt_file` (静的画像参照 → プロンプト参照に)
- `panels_reveal` → 廃止 (1 cut 内 reveal 不要)
- `motion_prompt` 追加
- `lines.estimated_sec` 追加 (build 前 calibration 用)

---

## 8. エピソードの shot 分解 (形式の例・合成)

| 旧 SCENES.id | 内容 (合成例) | 旧 line 数 | 新 shot 数 | 新 shot 合計時間 | 新 shot 合計コスト |
|---|---|---|---|---|---|
| P1 | 道具の紹介 | 4 | 2 | 10秒 | $0.40 |
| P2 | 使い方の実演 | 6 | 3 | 15秒 | $0.60 |
| P3 | 補足の説明 | 3 | 1 | 5秒 | $0.20 |
| P4 | 片付けの手順 | 4 | 2 | 10秒 | $0.40 |
| P5 | まとめ | 2 | 1 | 5秒 | $0.20 |
| **合計** | | **19** | **9** | **45秒** | **$1.80** |

(+ still 9枚 × $0.02 = $0.18、合計 **約 $1.98 / 45秒**)

サンプル動画なら 45秒 = 9〜11カット程度に収まる → リスク・コスト両面で sandbox に最適。

---

## 9. 最初のシーンの shot 案の書き方 (合成例)

### Shot S001 (5秒)

**セリフ**: (synthetic sample line, 約 3.5sec + pause 0.4)

**still_prompt (要点)**:
```
Manga / anime style illustration, 16:9 cinematic medium shot.
A young adult with short dark hair, wearing a green
jacket and a gray tote bag, stepping through a glass-paned doorway
into a small workshop. Excited expression, eyes bright. Background:
soft-focus rows of tool racks, hanging lamps, a wooden work table,
afternoon light through the skylight.
Camera angle: slightly low, from inside the workshop looking toward the door.

Style: Japanese seinen manga adapted to soft color illustration,
hand-drawn linework, painterly background, expressive but restrained.

Strict constraints: No text. No speech bubbles. No captions. No writing.
```

**motion_prompt**:
```
The character steps one small pace forward, hair swinging, bag strap
shifting with quick breaths. Hanging lamps sway gently. Slow camera push-in.
Maintain manga illustration style.
```

---

## 10. 実装時の Build Flow (proposal)

```
shots.py
  ↓ gen_stills.py (parallel, gpt-image-2)
input/S001.png ... S010.png
  ↓ gen_i2v.py (parallel max 5, fal-client Kling 2.5 standard)
clips/S001.mp4 ... S010.mp4
  ↓ synth.py (VOICEVOX, 既存流用)
audio/S001.wav ... + lines.estimated_sec を実測値で更新
  ↓ compose_episode.py
final_silent.mp4 + 字幕レイヤー (既存流用)
  ↓ mux audio
final.mp4
```

**キャッシュ層**:
- still: prompt sha → PNG キャッシュ
- i2v: (still sha + motion_prompt sha + duration) → MP4 キャッシュ
- 再ビルド時の重複コスト 0

---

## 11. 次のアクション

1. **このルール / 台割案 を user 確認** ← 今ココ
2. 確認後、 P1 (S001 + S002) を sandbox spike で実装し 2 カット試作
3. 良ければ P2-P5 を順次、 全 9 カット (45秒) 完成
4. 後段の音声合成 + 字幕合成 + 結合は既存の動画パイプラインを最小改修して流用

判断ポイント:
- shot 分割粒度 (10 カット = 妥当 / 多すぎ / 少なすぎ?)
- キャラ一貫性をどこまで重視するか (LoRA 学習を本パイプ化前にやるか後でやるか)
- 音声合成は ElevenLabs / VOICEVOX どっち
