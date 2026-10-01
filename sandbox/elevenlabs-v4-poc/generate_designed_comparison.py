"""Paired v3/v4 samples for representative registered Voice Design voices."""
from __future__ import annotations

import base64
import json
import os
import subprocess
import time
from pathlib import Path

from run_poc import load_key

HERE = Path(__file__).resolve().parent
# Voice IDs of the registered Voice Design voices to compare, comma-separated
# in the environment (placeholders only; no real IDs are shipped).
VOICE_IDS = [v for v in os.environ.get("DESIGNED_VOICE_IDS", "<VOICE_ID_1>,<VOICE_ID_2>").split(",") if v]
TEXT = "ここでは、会議の議事録を整える手順を、短い例で順番に確かめていきます。"
SETTINGS = {"stability": 0.85, "similarity_boost": 0.85}


def main() -> None:
    voices = {v["voice_id"]: v for v in json.loads((HERE / "generated_voices.json").read_text(encoding="utf-8"))}
    key = load_key()
    results = []
    path = HERE / "designed_comparison.json"
    for voice_id in VOICE_IDS:
        voice = voices[voice_id]
        for model in ("eleven_v3", "eleven_v4"):
            name = f"designed_{voice_id}_{model}.mp3"
            mp3 = HERE / name
            request_path = HERE / f".{name}.request.json"
            response_path = HERE / f".{name}.response.json"
            body = {
                "text": TEXT, "model_id": model, "voice_settings": SETTINGS,
                "output_format": "mp3_44100_192", "seed": 42,
            }
            started = time.monotonic()
            if not mp3.exists():
                request_path.write_text(json.dumps(body, ensure_ascii=False), encoding="utf-8")
                try:
                    proc = subprocess.run(
                        ["curl.exe", "--silent", "--show-error", "--fail-with-body", "--max-time", "120",
                         "--config", "-", "--data-binary", "@" + str(request_path),
                         "--output", str(response_path),
                         f"https://api.elevenlabs.io/v1/text-to-speech/{voice_id}/with-timestamps"],
                        input=f'header = "xi-api-key: {key}"\nheader = "Content-Type: application/json"\n',
                        text=True, encoding="utf-8", capture_output=True, timeout=130,
                    )
                    if proc.returncode:
                        msg = response_path.read_text(encoding="utf-8", errors="replace")[:500] if response_path.exists() else proc.stderr[:500]
                        raise RuntimeError(f"{voice_id} {model}: {msg}")
                    response = json.loads(response_path.read_text(encoding="utf-8"))
                    mp3.write_bytes(base64.b64decode(response["audio_base64"]))
                finally:
                    request_path.unlink(missing_ok=True)
                    response_path.unlink(missing_ok=True)
            item = {
                "voice_id": voice_id, "voice_name": voice["name"], "voice_category": "generated",
                "model_id": model, "text": TEXT, "settings": SETTINGS, "seed": 42,
                "output_format": "mp3_44100_192", "mp3": name, "bytes": mp3.stat().st_size,
            }
            results.append(item)
            path.write_text(json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8")
            print(f"{voice_id} {model}: {item['bytes']} bytes, {time.monotonic() - started:.1f}s", flush=True)


if __name__ == "__main__":
    main()
