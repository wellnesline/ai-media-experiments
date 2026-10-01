"""Allowlisted POC page and MP3s, served locally for listening tests."""
from __future__ import annotations

import html
import json
import mimetypes
import os
import re
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import unquote, urlsplit

HERE = Path(__file__).resolve().parent
PREFIX = "/elevenlabs-v4-poc"
RELEASE_FILES: dict = {}  # no release artifacts are bundled in this public copy

PAGE = """<!doctype html>
<html lang="ja"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>ElevenLabs v3 / v4 聴き比べ</title>
<style>
:root{font-family:system-ui,-apple-system,"Segoe UI",sans-serif;color:#eaf0fa;background:#101827}
*{box-sizing:border-box}body{margin:0}main{max-width:980px;margin:auto;padding:28px 18px 52px}
h1{font-size:clamp(1.45rem,4vw,2.2rem);line-height:1.25;margin:0 0 8px}
p{color:#b5c3d8;margin:0 0 20px;line-height:1.6}.summary{font-size:.92rem}
.case{background:#1b2738;border:1px solid #31425a;border-radius:16px;padding:17px;margin:12px 0}
.case-head{display:flex;align-items:baseline;gap:10px;margin-bottom:14px;flex-wrap:wrap}
.number{font-size:.8rem;color:#8da7c9;font-variant-numeric:tabular-nums}h2{font-size:1rem;line-height:1.5;margin:0;font-weight:650}
.repeat{color:#adcbff;border:1px solid #48699a;border-radius:99px;padding:1px 8px;font-size:.72rem}
.players{display:grid;grid-template-columns:1fr 1fr;gap:14px}.player{min-width:0}
.player strong{display:block;color:#a9c7f3;font-size:.85rem;margin-bottom:5px}audio{width:100%;height:42px;display:block}
.quality{border:1px solid #6586b5;background:#202f45;border-radius:18px;padding:18px;margin:22px 0 30px}
.quality h2{font-size:1.25rem;margin:0 0 7px}.quality p{margin-bottom:13px}.quality-grid{display:grid;grid-template-columns:1fr 1fr;gap:12px}
.quality-card{background:#142238;border:1px solid #405979;border-radius:12px;padding:12px}.quality-card strong{display:block;margin-bottom:8px}
.quality-card small{display:block;color:#aabbd2;margin-top:6px;line-height:1.4}
a{color:#9ec6ff}footer{display:flex;flex-wrap:wrap;gap:9px 22px;margin-top:28px;font-size:.9rem}
@media(max-width:620px){main{padding:20px 12px 42px}.case{padding:14px}.players,.quality-grid{grid-template-columns:1fr;gap:11px}}
</style>
<main><h1>ElevenLabs v3 / v4 聴き比べ</h1>
<p class="summary">Voice Design ボイスの v3/v4 比較、声質確認、読みの比較。再生ボタンを押すと聴けます。</p>
__DESIGNED__
__QUALITY__
__CARDS__
<footer><a href="/elevenlabs-v4-poc/REPORT.md">評価レポート</a><a href="/elevenlabs-v4-poc/TRANSCRIPTS.md">全件の文字起こし</a><a href="/elevenlabs-v4-poc/FULL_ASR.md">追加 ASR</a><a href="/elevenlabs-v4-poc/results.json">API と ASR の記録</a></footer></main>
<script>document.querySelectorAll('audio').forEach(a=>a.addEventListener('play',()=>{document.querySelectorAll('audio').forEach(b=>{if(b!==a)b.pause()})}))</script>
</html>"""


def results() -> list[dict]:
    return json.loads((HERE / "results.json").read_text(encoding="utf-8"))


def quality_section() -> str:
    path = HERE / "voice_quality.json"
    if not path.exists():
        return ""
    samples = json.loads(path.read_text(encoding="utf-8"))
    players = []
    for item in samples:
        src = f'{PREFIX}/{html.escape(item["mp3"], quote=True)}'
        label = html.escape(item["label"])
        tag = item["text"].split("]", 1)[0] + "]" if item["text"].startswith("[") else "タグなし"
        players.append(
            f'<div class="quality-card"><strong>{label}</strong>'
            f'<audio controls preload="none" playsinline aria-label="{label} の音声" src="{src}">'
            f'<a href="{src}">音声を開く</a></audio><small>{html.escape(tag)}</small></div>'
        )
    return (
        '<section class="quality" id="voice-quality"><h2>先に声質を確認</h2>'
        '<p>全て同じナレーター声の voice_id と本文です。v3 は基準の API 設定、v4 はタグなしと語り方タグの違いを比較できます。音声は API 出力の MP3 で、動画用の音量調整前です。</p>'
        f'<div class="quality-grid">{"".join(players)}</div></section>'
    )


def designed_section() -> str:
    path = HERE / "designed_comparison.json"
    if not path.exists():
        return ""
    samples = json.loads(path.read_text(encoding="utf-8"))
    cards = []
    for voice_id in dict.fromkeys(item["voice_id"] for item in samples):
        pair = [item for item in samples if item["voice_id"] == voice_id]
        if len(pair) != 2:
            continue
        name = html.escape(pair[0]["voice_name"])
        players = []
        for item in pair:
            model = "v3" if item["model_id"] == "eleven_v3" else "v4"
            src = f'{PREFIX}/{html.escape(item["mp3"], quote=True)}'
            players.append(
                f'<div class="player"><strong>{model}</strong>'
                f'<audio controls preload="none" playsinline aria-label="{name} {model} の音声" src="{src}">'
                f'<a href="{src}">音声を開く</a></audio></div>'
            )
        cards.append(f'<section class="case"><div class="case-head"><h2>{name}</h2></div>'
                     f'<div class="players">{"".join(players)}</div></section>')
    return (
        '<section id="designed-voices"><h2 style="font-size:1.25rem">Voice Design ボイスの声質比較</h2>'
        '<p>同じ声 ID・本文・seed=42・stability=0.85・similarity=0.85。タグなし。'
        'v3 と v4 で変わる声色や話し方を聴き比べできます。対象は声質の幅を見て選んだ声です。</p>'
        f'<div class="case"><strong>共通の本文</strong><p style="margin:6px 0 0">{html.escape(samples[0]["text"])}</p></div>'
        f'{"".join(cards)}</section>'
    )


def index() -> bytes:
    cards = []
    entries = results()
    for n, case in enumerate(dict.fromkeys(item["id"] for item in entries), 1):
        pair = [item for item in entries if item["id"] == case]
        label = html.escape(pair[0]["text"])
        repeat = '<span class="repeat">再試行</span>' if case.endswith("_r2") else ""
        players = []
        for item in pair:
            model = "v3" if item["model"] == "eleven_v3" else "v4"
            src = f'{PREFIX}/{html.escape(item["mp3"], quote=True)}'
            players.append(
                f'<div class="player"><strong>{model}</strong>'
                f'<audio controls preload="none" playsinline aria-label="{n}番 {model} の音声" src="{src}">'
                f'<a href="{src}">音声を開く</a></audio></div>'
            )
        cards.append(
            f'<section class="case"><div class="case-head"><span class="number">{n:02d}</span>'
            f'<h2>{label}</h2>{repeat}</div><div class="players">{"".join(players)}</div></section>'
        )
    return PAGE.replace("__DESIGNED__", designed_section()).replace("__QUALITY__", quality_section()).replace("__CARDS__", "\n".join(cards)).encode("utf-8")


class Handler(BaseHTTPRequestHandler):
    def do_HEAD(self):
        self.respond(head_only=True)

    def do_GET(self):
        self.respond(head_only=False)

    def respond(self, head_only: bool):
        path = unquote(urlsplit(self.path).path)
        if path in (PREFIX, PREFIX + "/"):
            data, mime = index(), "text/html; charset=utf-8"
        elif path.startswith(PREFIX + "/"):
            name = path[len(PREFIX) + 1:]
            allowed = {"REPORT.md", "TRANSCRIPTS.md", "FULL_ASR.md", "results.json"} | {item["mp3"] for item in results()} | RELEASE_FILES.keys()
            quality_path = HERE / "voice_quality.json"
            if quality_path.exists():
                allowed |= {item["mp3"] for item in json.loads(quality_path.read_text(encoding="utf-8"))}
            designed_path = HERE / "designed_comparison.json"
            if designed_path.exists():
                allowed |= {item["mp3"] for item in json.loads(designed_path.read_text(encoding="utf-8"))}
            if name not in allowed or "/" in name or "\\" in name:
                self.send_error(404)
                return
            data = RELEASE_FILES.get(name, HERE / name).read_bytes()
            mime = mimetypes.guess_type(name)[0] or "application/octet-stream"
            if name.endswith((".md", ".json")):
                mime += "; charset=utf-8"
        else:
            self.send_error(404)
            return

        audio = mime == "audio/mpeg"
        start, end, status = 0, len(data) - 1, 200
        requested = self.headers.get("Range") if audio else None
        if requested:
            match = re.fullmatch(r"bytes=(\d*)-(\d*)", requested.strip())
            if not match or (not match[1] and not match[2]):
                self.send_error(416)
                return
            if match[1]:
                start = int(match[1])
                end = min(int(match[2]), end) if match[2] else end
            else:
                start = max(0, len(data) - int(match[2]))
            if start > end or start >= len(data):
                self.send_response(416)
                self.send_header("Content-Range", f"bytes */{len(data)}")
                self.end_headers()
                return
            status = 206

        self.send_response(status)
        self.send_header("Content-Type", mime)
        self.send_header("Content-Length", str(end - start + 1))
        if audio:
            self.send_header("Accept-Ranges", "bytes")
        if status == 206:
            self.send_header("Content-Range", f"bytes {start}-{end}/{len(data)}")
        self.send_header("Cache-Control", "private, no-store")
        self.end_headers()
        if not head_only:
            self.wfile.write(data[start:end + 1])


if __name__ == "__main__":
    ThreadingHTTPServer(("127.0.0.1", int(os.environ.get("POC_PORT", "8091"))), Handler).serve_forever()
