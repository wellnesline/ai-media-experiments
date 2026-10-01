"""Small, isolated v3/v4 pronunciation comparison. Nothing outside this folder is changed."""
from __future__ import annotations

import base64
import importlib.util
import json
import os
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
HERE = Path(__file__).resolve().parent
VOICE_ID = os.environ.get("NARRATOR_VOICE_ID", "<VOICE_ID>")  # narrator voice; set via environment
CASES = [
    # Synthetic sentences chosen only to exercise reading problems (rare kanji,
    # counters, acronyms, identifiers, numerals). They are not taken from any real video.
    {"id": "rare_kanji", "text": "漁協の総会で議案を採決します。", "target": "ぎょきょう、そうかい、さいけつ"},
    {"id": "kun_reading", "text": "雨脚が強まる前に洗濯物を取り込みます。", "target": "あまあし、せんたくもの"},
    {"id": "counter_a", "text": "3台の機材を、12本のケーブルでつなぎます。", "target": "さんだい、じゅうにほん"},
    {"id": "counter_b", "text": "7階の会議室に、6時半に集まります。", "target": "ななかい、ろくじはん"},
    {"id": "counter_c", "text": "この路線は8駅ごとに急行が止まります。", "target": "はちえき"},
    {"id": "food_kanji", "text": "蒟蒻を薄く切って炒めます。", "target": "こんにゃく、うすく、いためます"},
    {"id": "civil_terms", "text": "橋脚と護岸の点検を行います。", "target": "きょうきゃく、ごがん"},
    {"id": "large_number", "text": "参加者は2万4600人でした。", "target": "にまんよんせんろっぴゃくにん"},
    {"id": "acronym", "text": "APIとSDKの違いを説明します。", "target": "エーピーアイ、エスディーケー"},
    {"id": "snake_case", "text": "config_loaderとcache keyを並べて比べます。", "target": "コンフィグローダー、キャッシュキー"},
    {"id": "dotted_call", "text": "pathlib.Pathでパスを組み立てます。", "target": "パスリブ、パス"},
    {"id": "times_sign", "text": "5×5のマスを並べます。", "target": "ごかけるご"},
    {"id": "decimal_val", "text": "精度は0.75でした。", "target": "れいてんななご"},
    {"id": "ambiguous_reading", "text": "今日は風が強く、人気の少ない道です。", "target": "ひとけ"},
    {"id": "rare_kanji_r2", "text": "漁協の総会で議案を採決します。", "target": "ぎょきょう、そうかい、さいけつ", "seed": 43},
    {"id": "counter_a_r2", "text": "3台の機材を、12本のケーブルでつなぎます。", "target": "さんだい、じゅうにほん", "seed": 43},
    {"id": "snake_case_r2", "text": "config_loaderとcache keyを並べて比べます。", "target": "コンフィグローダー、キャッシュキー", "seed": 43},
]


def load_key() -> str:
    if os.getenv("ELEVENLABS_API_KEY"):
        return os.environ["ELEVENLABS_API_KEY"]
    env = ROOT / ".env"
    for line in env.read_text(encoding="utf-8").splitlines():
        key, sep, value = line.partition("=")
        if sep and key.strip() == "ELEVENLABS_API_KEY":
            return value.strip().strip("\"").strip("'")
    raise RuntimeError("ELEVENLABS_API_KEY is not configured")


def generate(key: str, case: dict, model: str) -> dict:
    stem = f"{case['id']}_{model}"
    mp3 = HERE / f"{stem}.mp3"
    meta = HERE / f"{stem}.json"
    if mp3.exists() and meta.exists():
        return json.loads(meta.read_text(encoding="utf-8"))
    body = {
        "text": case["text"],
        "model_id": model,
        "output_format": "mp3_44100_128",
        "seed": case.get("seed", 42),
        "language_code": "ja",
        "voice_settings": {"stability": 0.85, "similarity_boost": 0.85},
    }
    body_path = HERE / f".{stem}.request.json"
    response_path = HERE / f".{stem}.response.json"
    body_path.write_text(json.dumps(body, ensure_ascii=False), encoding="utf-8")
    start = time.monotonic()
    try:
        curl_config = f'header = "xi-api-key: {key}"\nheader = "Content-Type: application/json"\n'
        cmd = ["curl.exe", "--silent", "--show-error", "--fail-with-body", "--max-time", "120",
               "--config", "-", "--data-binary", "@" + str(body_path),
               "--output", str(response_path),
               f"https://api.elevenlabs.io/v1/text-to-speech/{VOICE_ID}/with-timestamps"]
        proc = subprocess.run(cmd, input=curl_config, text=True, capture_output=True, timeout=130)
        if proc.returncode:
            detail = response_path.read_text(encoding="utf-8", errors="replace")[:800] if response_path.exists() else proc.stderr[:800]
            raise RuntimeError(f"{model} {case['id']}: curl {proc.returncode}: {detail}")
        data = json.loads(response_path.read_text(encoding="utf-8"))
    finally:
        body_path.unlink(missing_ok=True)
        response_path.unlink(missing_ok=True)
    audio = base64.b64decode(data["audio_base64"])
    mp3.write_bytes(audio)
    align = data.get("alignment") or {}
    normalized = data.get("normalized_alignment") or {}
    result = {
        "id": case["id"], "model": model, "text": case["text"],
        "target": case["target"], "voice_id": VOICE_ID,
        "settings": body["voice_settings"], "seed": body["seed"],
        "latency_seconds": round(time.monotonic() - start, 2),
        "bytes": len(audio), "alignment_chars": len(align.get("characters", [])),
        "normalized_alignment_chars": len(normalized.get("characters", [])),
        "mp3": mp3.name,
    }
    meta.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    return result


def main() -> int:
    if "--preflight" in sys.argv:
        env_text = (ROOT / ".env").read_text(encoding="utf-8")
        print(json.dumps({
            "key_available": bool(load_key()),
            "faster_whisper": bool(importlib.util.find_spec("faster_whisper")),
            "elevenlabs": bool(importlib.util.find_spec("elevenlabs")),
            "openai": bool(importlib.util.find_spec("openai")),
            "openai_key_configured": any(line.startswith("OPENAI_API_KEY=") for line in env_text.splitlines()),
            "case_count": len(CASES),
        }))
        return 0
    key = load_key()
    old = {item["mp3"]: item for item in json.loads((HERE / "results.json").read_text(encoding="utf-8"))}
    results = []
    for case in CASES:
        for model in ("eleven_v3", "eleven_v4"):
            try:
                result = generate(key, case, model)
                result.update({k: v for k, v in old.get(result["mp3"], {}).items() if k.startswith("transcript")})
                results.append(result)
                print(f"{case['id']} {model}: {result['bytes']} bytes, {result['latency_seconds']}s, alignment={result['alignment_chars']}", flush=True)
            except Exception as e:
                print(f"ERROR {e}", flush=True)
                (HERE / "results.json").write_text(json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8")
                return 1
    (HERE / "results.json").write_text(json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
