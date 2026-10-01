# 試作結果評価ログ

各カット試作後、 5段階で記入 (1=NG / 3=可 / 5=完璧)。

| tag | 顔保持 | 絵柄整合 | 動き自然 | 背景安定 | コスト$ | 所感 |
|---|---|---|---|---|---|---|
| A_dialogue_v1 |  |  |  |  |  |  |
| A_dialogue_v2 |  |  |  |  |  |  |
| A_dialogue_v3 |  |  |  |  |  |  |
| B_background_v1 |  |  |  |  |  |  |
| B_background_v2 |  |  |  |  |  |  |
| B_background_v3 |  |  |  |  |  |  |
| C_motion_v1 |  |  |  |  |  |  |
| C_motion_v2 |  |  |  |  |  |  |
| C_motion_v3 |  |  |  |  |  |  |

## GO/NO-GO 判断

- [ ] 平均顔保持 >= 3.5
- [ ] 平均絵柄整合 >= 3.5
- [ ] 平均動き自然 >= 3.0
- [ ] 平均コスト/カット <= $0.50
- [ ] 全 9 本中、 即使えるレベル ≥ 3 本

→ 4項目以上 OK なら **GO** (本パイプ化)。
→ 3項目以下なら **Seedance Pro で再試行** → だめなら Runway Gen-4 References。

## 次フェーズ TODO (GO 確定後)

- [ ] `scripts/gen_panel_i2v.py` 本実装
- [ ] `scenes.py` schema 拡張 (`motion_prompt`, `i2v_duration`)
- [ ] サンプルエピソードを全カット i2v 化して 1本量産検証
