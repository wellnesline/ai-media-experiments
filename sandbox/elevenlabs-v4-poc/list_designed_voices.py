"""List account voices created with Voice Design without exposing the API key."""
from __future__ import annotations

import json
import subprocess
from pathlib import Path
from urllib.parse import urlencode

from run_poc import load_key

HERE = Path(__file__).resolve().parent


def main() -> None:
    key = load_key()
    voices: list[dict] = []
    token = None
    while True:
        params = {"category": "generated", "page_size": 100}
        if token:
            params["next_page_token"] = token
        url = "https://api.elevenlabs.io/v2/voices?" + urlencode(params)
        proc = subprocess.run(
            ["curl.exe", "--silent", "--show-error", "--fail-with-body", "--max-time", "30", "--config", "-", url],
            input=f'header = "xi-api-key: {key}"\n', text=True, encoding="utf-8", capture_output=True, timeout=35,
        )
        if proc.returncode:
            raise RuntimeError(f"Voice list failed: {proc.stdout[:300] or proc.stderr[:300]}")
        data = json.loads(proc.stdout)
        for voice in data.get("voices", []):
            if voice.get("category") == "generated":
                voices.append({
                    "voice_id": voice.get("voice_id"),
                    "name": voice.get("name"),
                    "category": voice.get("category"),
                    "description": voice.get("description"),
                    "labels": voice.get("labels") or {},
                    "created_at_unix": voice.get("created_at_unix"),
                })
        token = data.get("next_page_token") if data.get("has_more") else None
        if not token:
            break
    (HERE / "generated_voices.json").write_text(json.dumps(voices, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(voices, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
