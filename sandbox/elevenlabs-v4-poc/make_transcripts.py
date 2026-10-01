"""Build a compact, reviewable ASR comparison table from saved results."""
import json
from pathlib import Path

here = Path(__file__).resolve().parent
items = json.loads((here / "results.json").read_text(encoding="utf-8"))
rows = ["# ASR 比較一覧", "", "ASR 結果は発音の目安にすぎません。表記ゆれ・略語・専門用語では誤差が出ます。", "", "| ID | 原文 | v3: mini / Whisper | v4: mini / Whisper |", "|---|---|---|---|"]
for id_ in dict.fromkeys(item["id"] for item in items):
    pair = {item["model"]: item for item in items if item["id"] == id_}
    if len(pair) != 2:
        continue
    v3, v4 = pair["eleven_v3"], pair["eleven_v4"]
    def safe(s):
        return (s or "未実施").replace("|", "\\|").replace("\n", " ")
    rows.append(f"| {id_} | {safe(v3['text'])} | {safe(v3.get('transcript'))} / {safe(v3.get('transcript_whisper'))} | {safe(v4.get('transcript'))} / {safe(v4.get('transcript_whisper'))} |")
(here / "TRANSCRIPTS.md").write_text("\n".join(rows) + "\n", encoding="utf-8")
full_rows = ["# 追加 ASR 確認", "", "| ID | v3 full | v4 full |", "|---|---|---|"]
for id_ in dict.fromkeys(item["id"] for item in items if item.get("transcript_full")):
    pair = {item["model"]: item for item in items if item["id"] == id_}
    full_rows.append(f"| {id_} | {pair['eleven_v3'].get('transcript_full', '')} | {pair['eleven_v4'].get('transcript_full', '')} |")
(here / "FULL_ASR.md").write_text("\n".join(full_rows) + "\n", encoding="utf-8")
for model in ("eleven_v3", "eleven_v4"):
    subset = [item for item in items if item["model"] == model]
    mean = sum(item["latency_seconds"] for item in subset) / len(subset)
    aligned = sum(item["alignment_chars"] == len(item["text"]) for item in subset)
    print(f"{model}: {len(subset)} clips, mean latency {mean:.2f}s, alignment {aligned}/{len(subset)}")
