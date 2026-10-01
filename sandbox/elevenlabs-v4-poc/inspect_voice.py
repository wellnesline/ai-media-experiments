"""Verify the exact voice ID used by both sides of the POC."""
import json
import subprocess
from pathlib import Path

from run_poc import VOICE_ID, load_key

here = Path(__file__).resolve().parent
response = here / ".voice_response.json"
cmd = ["curl.exe", "--silent", "--show-error", "--fail-with-body", "--max-time", "25",
       "--config", "-", "--output", str(response),
       f"https://api.elevenlabs.io/v1/voices/{VOICE_ID}"]
config = f'header = "xi-api-key: {load_key()}"\n'
proc = subprocess.run(cmd, input=config, text=True, capture_output=True, timeout=30)
if proc.returncode:
    raise RuntimeError(response.read_text(encoding="utf-8", errors="replace")[:500] if response.exists() else proc.stderr[:500])
data = json.loads(response.read_text(encoding="utf-8"))
response.unlink(missing_ok=True)
selected = {field: data.get(field) for field in
            ("voice_id", "name", "category", "labels", "high_quality_base_model_ids", "is_legacy")}
selected["fine_tuning_state"] = (data.get("fine_tuning") or {}).get("state")
selected["verified_language_models"] = sorted({item.get("model_id") for item in (data.get("verified_languages") or []) if item.get("language") == "ja" and item.get("model_id")})
(here / "voice_metadata.json").write_text(json.dumps(selected, ensure_ascii=False, indent=2), encoding="utf-8")
print(json.dumps(selected, ensure_ascii=False))
