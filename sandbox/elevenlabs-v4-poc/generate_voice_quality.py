"""Baseline-settings reference and controlled v4 delivery-tag samples."""
from __future__ import annotations

import base64
import json
import subprocess
import time
from pathlib import Path

from run_poc import VOICE_ID, load_key

HERE = Path(__file__).resolve().parent
TEXT = "今日は、写真の整理を手早く終えるための、基本の手順を順番に説明します。"
SETTINGS_V3 = {
    "stability": 0.85, "similarity_boost": 0.85,
    "style": 0.0, "use_speaker_boost": True,
}
SETTINGS_V4 = {"stability": 0.85, "similarity_boost": 0.85}
SAMPLES = [
    {"id": "baseline_v3", "label": "v3 基準設定・タグなし", "model_id": "eleven_v3", "text": TEXT, "settings": SETTINGS_V3},
    {"id": "plain_v4", "label": "v4 タグなし", "model_id": "eleven_v4", "text": TEXT, "settings": SETTINGS_V4},
    {"id": "calm_v4", "label": "v4 落ち着いた語り", "model_id": "eleven_v4", "text": "[calm, confident narration] " + TEXT, "settings": SETTINGS_V4},
    {"id": "warm_v4", "label": "v4 親しみやすい語り", "model_id": "eleven_v4", "text": "[warm, conversational tone] " + TEXT, "settings": SETTINGS_V4},
]


def generate(sample: dict, key: str) -> dict:
    mp3 = HERE / f"quality_{sample['id']}.mp3"
    body = {
        "text": sample["text"], "model_id": sample["model_id"],
        "voice_settings": sample["settings"], "output_format": "mp3_44100_192", "seed": 42,
    }
    if not mp3.exists():
        request_file = HERE / f".quality_{sample['id']}.request.json"
        response_file = HERE / f".quality_{sample['id']}.response.json"
        request_file.write_text(json.dumps(body, ensure_ascii=False), encoding="utf-8")
        try:
            config = f'header = "xi-api-key: {key}"\nheader = "Content-Type: application/json"\n'
            cmd = ["curl.exe", "--silent", "--show-error", "--fail-with-body", "--max-time", "120",
                   "--config", "-", "--data-binary", "@" + str(request_file),
                   "--output", str(response_file),
                   f"https://api.elevenlabs.io/v1/text-to-speech/{VOICE_ID}/with-timestamps"]
            proc = subprocess.run(cmd, input=config, text=True, capture_output=True, timeout=130)
            if proc.returncode:
                message = response_file.read_text(encoding="utf-8", errors="replace")[:500] if response_file.exists() else proc.stderr[:500]
                raise RuntimeError(f"{sample['id']}: {message}")
            data = json.loads(response_file.read_text(encoding="utf-8"))
            mp3.write_bytes(base64.b64decode(data["audio_base64"]))
        finally:
            request_file.unlink(missing_ok=True)
            response_file.unlink(missing_ok=True)
    result = {
        "id": sample["id"], "label": sample["label"], "model_id": sample["model_id"],
        "voice_id": VOICE_ID, "text": sample["text"], "settings": sample["settings"],
        "seed": 42, "output_format": "mp3_44100_192", "mp3": mp3.name,
        "bytes": mp3.stat().st_size,
    }
    return result


def main() -> None:
    key = load_key()
    items = []
    for sample in SAMPLES:
        started = time.monotonic()
        item = generate(sample, key)
        items.append(item)
        (HERE / "voice_quality.json").write_text(json.dumps(items, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"{item['id']}: {item['bytes']} bytes, {time.monotonic() - started:.1f}s", flush=True)


if __name__ == "__main__":
    main()
