"""Check that delivery tags are not spoken as words in the new samples."""
import json
import subprocess
from pathlib import Path

from transcribe import key

HERE = Path(__file__).resolve().parent
path = HERE / "voice_quality.json"
samples = json.loads(path.read_text(encoding="utf-8"))
token = key()
for item in samples:
    if item.get("transcript"):
        continue
    response = HERE / ".quality_transcription.json"
    config = f'header = "Authorization: Bearer {token}"\n'
    cmd = ["curl.exe", "--silent", "--show-error", "--fail-with-body", "--max-time", "120",
           "--config", "-", "-F", "model=gpt-4o-mini-transcribe", "-F", "language=ja",
           "-F", "file=@" + str(HERE / item["mp3"]), "--output", str(response),
           "https://api.openai.com/v1/audio/transcriptions"]
    proc = subprocess.run(cmd, input=config, text=True, capture_output=True, timeout=130)
    if proc.returncode:
        raise RuntimeError(response.read_text(encoding="utf-8", errors="replace")[:500] if response.exists() else proc.stderr[:500])
    item["transcript"] = json.loads(response.read_text(encoding="utf-8"))["text"]
    response.unlink(missing_ok=True)
    path.write_text(json.dumps(samples, ensure_ascii=False, indent=2), encoding="utf-8")
    print(item["id"], "ok", flush=True)
