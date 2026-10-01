"""Independent ASR check for the generated samples."""
from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
HERE = Path(__file__).resolve().parent


def key() -> str:
    if os.getenv("OPENAI_API_KEY"):
        return os.environ["OPENAI_API_KEY"]
    for line in (ROOT / ".env").read_text(encoding="utf-8").splitlines():
        name, sep, value = line.partition("=")
        if sep and name.strip() == "OPENAI_API_KEY":
            return value.strip().strip("\"").strip("'")
    raise RuntimeError("OPENAI_API_KEY missing")


def main() -> int:
    results = json.loads((HERE / "results.json").read_text(encoding="utf-8"))
    token = key()
    model = ("whisper-1" if "--whisper" in sys.argv else
             "gpt-4o-transcribe" if "--full" in sys.argv else "gpt-4o-mini-transcribe")
    field = ("transcript_whisper" if model == "whisper-1" else
             "transcript_full" if model == "gpt-4o-transcribe" else "transcript")
    for item in results:
        if model == "gpt-4o-transcribe" and item["id"] not in {
            "rare_kanji", "kun_reading", "counter_a", "civil_terms", "snake_case",
            "dotted_call", "ambiguous_reading", "rare_kanji_r2", "counter_a_r2",
        }:
            continue
        if item.get(field):
            continue
        response = HERE / ".transcription_response.json"
        config = f'header = "Authorization: Bearer {token}"\n'
        cmd = ["curl.exe", "--silent", "--show-error", "--fail-with-body", "--max-time", "120",
               "--config", "-", "-F", "model=" + model,
               "-F", "language=ja", "-F", "file=@" + str(HERE / item["mp3"]),
               "--output", str(response), "https://api.openai.com/v1/audio/transcriptions"]
        proc = subprocess.run(cmd, input=config, text=True, capture_output=True, timeout=130)
        if proc.returncode:
            detail = response.read_text(encoding="utf-8", errors="replace")[:500] if response.exists() else proc.stderr[:500]
            raise RuntimeError(f"ASR failed for {item['mp3']}: {detail}")
        data = json.loads(response.read_text(encoding="utf-8"))
        response.unlink(missing_ok=True)
        item[field] = data["text"]
        (HERE / "results.json").write_text(json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"{item['id']} {item['model']}: {item[field]}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
