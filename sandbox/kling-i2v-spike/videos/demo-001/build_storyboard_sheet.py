"""PoC 001 — 全 stills を 1 枚の絵コンテシートに合成.

各セル: ヘッダ (shot id / scene / 話者 / 秒数) + 静止画 (16:9 縮小) + セリフ字幕
配置  : 4 列 × 5 行 (余りは空セル)
出力   : output/storyboard_sheet.png + review/demo-001_storyboard_sheet.png
"""
from __future__ import annotations

import importlib.util
import re
import sys
from pathlib import Path

import os
from PIL import Image, ImageDraw, ImageFont

HERE = Path(__file__).resolve().parent
INPUT_DIR = HERE / "input"
OUT = HERE / "output" / "storyboard_sheet.png"
REVIEW_OUT = HERE.parents[3] / "review" / "demo-001_storyboard_sheet.png"

# shots.py を import
spec = importlib.util.spec_from_file_location("shots", HERE / "shots.py")
shots_mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(shots_mod)
SHOTS = shots_mod.SHOTS

# ── レイアウト定数 ──
COLS = 4
ROWS = 5
THUMB_W = 480
THUMB_H = 270   # 16:9
HEADER_H = 32
CAPTION_H = 96
CELL_W = THUMB_W
CELL_H = HEADER_H + THUMB_H + CAPTION_H  # 398
GAP = 24
OUTER = 40
TITLE_H = 90

SHEET_W = COLS * CELL_W + (COLS - 1) * GAP + 2 * OUTER
SHEET_H = TITLE_H + ROWS * CELL_H + (ROWS - 1) * GAP + 2 * OUTER

# ── 色 ──
BG = (245, 244, 240)
HEADER_BG_CHAR_A = (52, 102, 168)   # 紺
HEADER_BG_CHAR_B = (170, 92, 130) # ピンク寄り
HEADER_FG = (255, 255, 255)
CAPTION_BG = (255, 255, 255)
CAPTION_FG = (30, 30, 30)
TITLE_FG = (30, 30, 30)
BORDER = (60, 60, 60)

# ── フォント ──
FONT_TITLE = os.environ["JP_FONT_BOLD_PATH"]  # 太字フォントのパスを環境変数で渡す(既定値なし)
FONT_HEADER = os.environ["JP_FONT_PATH"]  # 通常フォントのパスを環境変数で渡す(既定値なし)
FONT_CAPTION = os.environ["JP_FONT_PATH"]  # 通常フォントのパスを環境変数で渡す(既定値なし)

_TAG_RE = re.compile(r"\[[^\]]+\]")


def strip_tags(text: str) -> str:
    return _TAG_RE.sub("", text).strip()


def speaker_label(speaker: str) -> str:
    return {"char_a": "キャラA", "char_b": "キャラB"}[speaker]


def header_bg(speaker: str) -> tuple[int, int, int]:
    return HEADER_BG_CHAR_A if speaker == "char_a" else HEADER_BG_CHAR_B


def wrap_japanese(text: str, font: ImageFont.FreeTypeFont, max_w: int) -> list[str]:
    """日本語向け簡易折り返し (文字単位)."""
    lines: list[str] = []
    current = ""
    for ch in text:
        candidate = current + ch
        w = font.getbbox(candidate)[2]
        if w > max_w and current:
            lines.append(current)
            current = ch
        else:
            current = candidate
    if current:
        lines.append(current)
    return lines


def draw_cell(canvas: Image.Image, draw: ImageDraw.ImageDraw, x: int, y: int, shot: dict) -> None:
    # ヘッダ
    hbg = header_bg(shot["speaker"])
    draw.rectangle([x, y, x + CELL_W, y + HEADER_H], fill=hbg)
    f_hdr = ImageFont.truetype(FONT_HEADER, 18)
    hdr_text = (
        f"{shot['id']}  |  {shot['scene']} L{shot['line_idx']}  |  "
        f"{speaker_label(shot['speaker'])}  |  {shot['duration_sec']:.2f}s"
    )
    draw.text((x + 12, y + 6), hdr_text, font=f_hdr, fill=HEADER_FG)

    # 静止画
    thumb_y = y + HEADER_H
    img_path = INPUT_DIR / f"{shot['id']}.png"
    if not img_path.exists():
        draw.rectangle([x, thumb_y, x + THUMB_W, thumb_y + THUMB_H], fill=(200, 200, 200))
        draw.text((x + 20, thumb_y + 20), f"missing: {img_path.name}", fill=(120, 0, 0))
    else:
        thumb = Image.open(img_path).convert("RGB").resize((THUMB_W, THUMB_H), Image.LANCZOS)
        canvas.paste(thumb, (x, thumb_y))

    # キャプション (セリフ)
    cap_y = thumb_y + THUMB_H
    draw.rectangle([x, cap_y, x + CELL_W, cap_y + CAPTION_H], fill=CAPTION_BG)
    f_cap = ImageFont.truetype(FONT_CAPTION, 18)
    text = strip_tags(shot["text"])
    lines = wrap_japanese(text, f_cap, CELL_W - 24)
    # 表示は最大 4 行まで
    for i, line in enumerate(lines[:4]):
        draw.text((x + 12, cap_y + 10 + i * 22), line, font=f_cap, fill=CAPTION_FG)

    # 外枠
    draw.rectangle([x, y, x + CELL_W, y + CELL_H], outline=BORDER, width=1)


def main() -> int:
    canvas = Image.new("RGB", (SHEET_W, SHEET_H), BG)
    draw = ImageDraw.Draw(canvas)

    # タイトル
    f_title = ImageFont.truetype(FONT_TITLE, 36)
    f_sub = ImageFont.truetype(FONT_HEADER, 20)
    title = "PoC 001 — 冒頭シーン (P1-P5) ストーリーボード"
    sub = f"全 {len(SHOTS)} shots / 1セリフ=1ショット (gpt-image-1 with refs, 16:9 1536x864)"
    draw.text((OUTER, OUTER), title, font=f_title, fill=TITLE_FG)
    draw.text((OUTER, OUTER + 50), sub, font=f_sub, fill=(80, 80, 80))

    # グリッド
    grid_y0 = OUTER + TITLE_H
    for idx, shot in enumerate(SHOTS):
        col = idx % COLS
        row = idx // COLS
        x = OUTER + col * (CELL_W + GAP)
        y = grid_y0 + row * (CELL_H + GAP)
        draw_cell(canvas, draw, x, y, shot)

    OUT.parent.mkdir(parents=True, exist_ok=True)
    canvas.save(OUT, "PNG")
    REVIEW_OUT.parent.mkdir(parents=True, exist_ok=True)
    canvas.save(REVIEW_OUT, "PNG")
    print(f"[storyboard_sheet] saved:")
    print(f"  {OUT}")
    print(f"  {REVIEW_OUT}")
    print(f"  size: {SHEET_W}x{SHEET_H}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
