"""漫画吹き出し 13 種類 サンプル描画スクリプト (PIL).

合成可能な吹き出し全種類を 1 枚のサンプルシートに描画。 user に視覚的に
選んでもらう用。

出力:
  review/demo-001_bubble_samples.png
"""
from __future__ import annotations

import math
import random
from pathlib import Path

import os
from PIL import Image, ImageDraw, ImageFont

OUT = Path(__file__).resolve().parents[4] / "review" / "demo-001_bubble_samples.png"

FONT_TEXT = os.environ["JP_FONT_PATH"]  # 通常フォントのパスを環境変数で渡す(既定値なし)
FONT_LABEL = os.environ["JP_FONT_BOLD_PATH"]  # 太字フォントのパスを環境変数で渡す(既定値なし)

CELL_W, CELL_H = 480, 360
COLS, ROWS = 4, 4
GAP = 20
OUTER = 40
TITLE_H = 80
SHEET_W = COLS * CELL_W + (COLS - 1) * GAP + 2 * OUTER
SHEET_H = TITLE_H + ROWS * CELL_H + (ROWS - 1) * GAP + 2 * OUTER

BG = (250, 248, 244)
CELL_BG = (255, 255, 255)
TEXT_FG = (20, 20, 20)
LABEL_FG = (60, 60, 60)
BORDER = (200, 200, 200)


def draw_bubble_box(canvas: Image.Image, cell_x: int, cell_y: int, title_jp: str,
                    title_en: str, sample_text: str, drawer):
    """1 セル: 上に label、 中央に吹き出し描画."""
    draw = ImageDraw.Draw(canvas)
    # セル外枠
    draw.rectangle([cell_x, cell_y, cell_x + CELL_W, cell_y + CELL_H],
                   fill=CELL_BG, outline=BORDER, width=1)

    # 上部 label
    f_label = ImageFont.truetype(FONT_LABEL, 22)
    f_sub = ImageFont.truetype(FONT_TEXT, 14)
    draw.text((cell_x + 16, cell_y + 12), title_jp, font=f_label, fill=TEXT_FG)
    draw.text((cell_x + 16, cell_y + 40), title_en, font=f_sub, fill=LABEL_FG)

    # 吹き出し描画エリア (label の下、 セル中央)
    bub_x0 = cell_x + 40
    bub_y0 = cell_y + 80
    bub_w = CELL_W - 80
    bub_h = CELL_H - 100
    drawer(canvas, draw, bub_x0, bub_y0, bub_w, bub_h, sample_text)


def text_size(font, text):
    bbox = font.getbbox(text)
    return bbox[2] - bbox[0], bbox[3] - bbox[1]


# ── 各 bubble 描画関数 ────────────────────────────────────────────────

def _draw_text_centered(draw, x0, y0, w, h, text, font_size=24, fill=(20, 20, 20)):
    f = ImageFont.truetype(FONT_TEXT, font_size)
    # 簡易折返し (15 文字超で改行)
    lines = []
    cur = ""
    for ch in text:
        if len(cur) >= 14 and ch not in "、。!?":
            lines.append(cur)
            cur = ch
        else:
            cur += ch
    if cur:
        lines.append(cur)
    line_h = font_size + 6
    total_h = len(lines) * line_h
    sy = y0 + (h - total_h) // 2
    for i, line in enumerate(lines):
        tw, _ = text_size(f, line)
        draw.text((x0 + (w - tw) // 2, sy + i * line_h), line, font=f, fill=fill)


def bub_oval(canvas, draw, x, y, w, h, text):
    bw, bh = w - 40, h - 60
    bx, by = x + 20, y + 20
    draw.ellipse([bx, by, bx + bw, by + bh], fill="white", outline="black", width=3)
    # 尻尾
    cx, cy = bx + bw // 2 - 30, by + bh
    draw.polygon([(cx, cy), (cx + 30, cy + 35), (cx + 50, cy)], fill="white", outline="black")
    draw.line([(cx, cy), (cx + 30, cy + 35), (cx + 50, cy)], fill="black", width=3)
    draw.line([(cx, cy + 1), (cx + 50, cy + 1)], fill="white", width=3)  # 内側の線消し
    _draw_text_centered(draw, bx, by, bw, bh, text)


def bub_rect(canvas, draw, x, y, w, h, text):
    bw, bh = w - 40, h - 60
    bx, by = x + 20, y + 30
    draw.rounded_rectangle([bx, by, bx + bw, by + bh], radius=8,
                            fill="white", outline="black", width=3)
    _draw_text_centered(draw, bx, by, bw, bh, text)


def bub_jagged(canvas, draw, x, y, w, h, text):
    """ギザギザ (叫び)"""
    bw, bh = w - 40, h - 60
    cx, cy = x + 20 + bw // 2, y + 20 + bh // 2
    rx, ry = bw // 2, bh // 2
    n = 28
    pts = []
    for i in range(n):
        ang = 2 * math.pi * i / n
        r_mult = 1.0 if i % 2 == 0 else 0.72
        px = cx + rx * r_mult * math.cos(ang)
        py = cy + ry * r_mult * math.sin(ang)
        pts.append((px, py))
    draw.polygon(pts, fill="white", outline="black")
    # outline で polygon の境界を強調
    for i in range(len(pts)):
        p1, p2 = pts[i], pts[(i + 1) % len(pts)]
        draw.line([p1, p2], fill="black", width=3)
    _draw_text_centered(draw, x + 50, cy - 40, bw - 60, 80, text, font_size=26)


def bub_wavy(canvas, draw, x, y, w, h, text):
    """ガタガタ (動揺)"""
    bw, bh = w - 40, h - 60
    cx, cy = x + 20 + bw // 2, y + 20 + bh // 2
    rx, ry = bw // 2, bh // 2
    n = 40
    pts = []
    random.seed(7)
    for i in range(n):
        ang = 2 * math.pi * i / n
        jitter = 1 + 0.06 * math.sin(ang * 8) + random.uniform(-0.04, 0.04)
        px = cx + rx * jitter * math.cos(ang)
        py = cy + ry * jitter * math.sin(ang)
        pts.append((px, py))
    draw.polygon(pts, fill="white", outline="black")
    for i in range(len(pts)):
        p1, p2 = pts[i], pts[(i + 1) % len(pts)]
        draw.line([p1, p2], fill="black", width=2)
    _draw_text_centered(draw, x + 40, cy - 30, bw - 40, 60, text)


def bub_cloud(canvas, draw, x, y, w, h, text):
    """雲型 (思考)"""
    bw, bh = w - 60, h - 80
    bx, by = x + 30, y + 20
    # 複数の楕円を重ねて雲化
    bumps = [
        (bx, by + bh*0.3, bw*0.25, bh*0.45),
        (bx + bw*0.18, by, bw*0.35, bh*0.55),
        (bx + bw*0.45, by - bh*0.05, bw*0.32, bh*0.55),
        (bx + bw*0.68, by + bh*0.05, bw*0.32, bh*0.5),
        (bx + bw*0.05, by + bh*0.45, bw*0.4, bh*0.5),
        (bx + bw*0.35, by + bh*0.5, bw*0.4, bh*0.5),
        (bx + bw*0.6, by + bh*0.4, bw*0.35, bh*0.55),
    ]
    for bx0, by0, bw0, bh0 in bumps:
        draw.ellipse([bx0, by0, bx0 + bw0, by0 + bh0], fill="white", outline="black", width=3)
    # 中央メインの bg を 1 回 fill 白で塗り直し (枠線交差除去)
    inner = [bx + bw*0.15, by + bh*0.2, bx + bw*0.85, by + bh*0.8]
    draw.ellipse(inner, fill="white")
    # 思考泡 (尻尾)
    for i, (px, py, ps) in enumerate([(bx + bw*0.3, by + bh + 10, 18), (bx + bw*0.27, by + bh + 35, 12), (bx + bw*0.25, by + bh + 55, 7)]):
        draw.ellipse([px, py, px + ps, py + ps], fill="white", outline="black", width=2)
    _draw_text_centered(draw, bx, by + 10, bw, bh - 20, text)


def bub_star(canvas, draw, x, y, w, h, text):
    """星型 (ご機嫌)"""
    bw, bh = w - 40, h - 60
    cx, cy = x + 20 + bw // 2, y + 20 + bh // 2
    rx, ry = bw // 2, bh // 2
    n = 24
    pts = []
    for i in range(n):
        ang = 2 * math.pi * i / n - math.pi / 2
        r_mult = 1.0 if i % 2 == 0 else 0.55
        px = cx + rx * r_mult * math.cos(ang)
        py = cy + ry * r_mult * math.sin(ang)
        pts.append((px, py))
    draw.polygon(pts, fill="white", outline="black")
    for i in range(len(pts)):
        p1, p2 = pts[i], pts[(i + 1) % len(pts)]
        draw.line([p1, p2], fill="black", width=3)
    _draw_text_centered(draw, x + 50, cy - 30, bw - 60, 60, text)


def bub_dotted(canvas, draw, x, y, w, h, text):
    """点線 (ささやき)"""
    bw, bh = w - 40, h - 60
    bx, by = x + 20, y + 20
    # 楕円を点線で
    n = 60
    cx, cy = bx + bw // 2, by + bh // 2
    rx, ry = bw // 2, bh // 2
    for i in range(n):
        if i % 2 == 0:
            ang1 = 2 * math.pi * i / n
            ang2 = 2 * math.pi * (i + 0.8) / n
            p1 = (cx + rx * math.cos(ang1), cy + ry * math.sin(ang1))
            p2 = (cx + rx * math.cos(ang2), cy + ry * math.sin(ang2))
            draw.line([p1, p2], fill="black", width=2)
    _draw_text_centered(draw, bx, by, bw, bh, text, fill=(80, 80, 80))


def bub_bold(canvas, draw, x, y, w, h, text):
    """太線 (強調)"""
    bw, bh = w - 40, h - 60
    bx, by = x + 20, y + 20
    draw.ellipse([bx, by, bx + bw, by + bh], fill="white", outline="black", width=8)
    _draw_text_centered(draw, bx, by, bw, bh, text, font_size=28)


def bub_multi(canvas, draw, x, y, w, h, text):
    """多重囲み (電話/放送)"""
    bw, bh = w - 40, h - 60
    bx, by = x + 20, y + 20
    # 二重楕円
    draw.ellipse([bx, by, bx + bw, by + bh], fill="white", outline="black", width=3)
    draw.ellipse([bx + 10, by + 8, bx + bw - 10, by + bh - 8],
                 fill="white", outline="black", width=2)
    _draw_text_centered(draw, bx, by, bw, bh, text)


def bub_phone(canvas, draw, x, y, w, h, text):
    """異形枠 (機械音・ロボ)"""
    bw, bh = w - 40, h - 60
    bx, by = x + 20, y + 30
    # 角張った多角形 (異形)
    pts = [
        (bx, by + 20),
        (bx + 30, by),
        (bx + bw - 40, by),
        (bx + bw, by + 30),
        (bx + bw, by + bh - 20),
        (bx + bw - 30, by + bh),
        (bx + 30, by + bh),
        (bx, by + bh - 30),
    ]
    draw.polygon(pts, fill=(240, 240, 250), outline="black")
    for i in range(len(pts)):
        p1, p2 = pts[i], pts[(i + 1) % len(pts)]
        draw.line([p1, p2], fill="black", width=3)
    _draw_text_centered(draw, bx, by + 10, bw, bh - 20, text)


def bub_wave_line(canvas, draw, x, y, w, h, text):
    """波線 (怪奇)"""
    bw, bh = w - 40, h - 60
    bx, by = x + 20, y + 20
    cx, cy = bx + bw // 2, by + bh // 2
    rx, ry = bw // 2, bh // 2
    n = 200
    pts = []
    for i in range(n):
        ang = 2 * math.pi * i / n
        wave = 1 + 0.04 * math.sin(ang * 12)
        px = cx + rx * wave * math.cos(ang)
        py = cy + ry * wave * math.sin(ang)
        pts.append((px, py))
    draw.polygon(pts, fill=(255, 250, 240), outline="black")
    # 二重描画で波線感
    for i in range(0, len(pts), 1):
        p1, p2 = pts[i], pts[(i + 1) % len(pts)]
        draw.line([p1, p2], fill="black", width=2)
    _draw_text_centered(draw, bx, by, bw, bh, text)


def bub_no_border(canvas, draw, x, y, w, h, text):
    """枠なし (独白)"""
    # 何も描かず、 文字だけ斜めに
    bw, bh = w - 40, h - 60
    bx, by = x + 20, y + 20
    f = ImageFont.truetype(FONT_TEXT, 24)
    lines = [text]
    line_h = 30
    sy = by + (bh - line_h) // 2
    tw, _ = text_size(f, text)
    draw.text((bx + (bw - tw) // 2, sy), text, font=f, fill=(20, 20, 20))


def bub_solid(canvas, draw, x, y, w, h, text):
    """ベタフラッシュ (衝撃) — 黒地に白文字"""
    bw, bh = w - 40, h - 60
    cx, cy = x + 20 + bw // 2, y + 20 + bh // 2
    rx, ry = bw // 2, bh // 2
    # 放射状の鋭利な多角形 (黒)
    n = 40
    pts = []
    for i in range(n):
        ang = 2 * math.pi * i / n
        r_mult = 1.0 if i % 2 == 0 else 0.5
        px = cx + rx * r_mult * math.cos(ang)
        py = cy + ry * r_mult * math.sin(ang)
        pts.append((px, py))
    draw.polygon(pts, fill="black")
    _draw_text_centered(draw, x + 50, cy - 30, bw - 60, 60, text, font_size=26, fill="white")


def bub_uni_flash(canvas, draw, x, y, w, h, text):
    """ウニフラッシュ (決意・思いつめ)"""
    bw, bh = w - 40, h - 60
    cx, cy = x + 20 + bw // 2, y + 20 + bh // 2
    rx_out, ry_out = bw // 2 + 20, bh // 2 + 20
    rx_in, ry_in = bw // 3.2, bh // 3.2
    # 放射線
    n_rays = 40
    for i in range(n_rays):
        ang = 2 * math.pi * i / n_rays
        p1 = (cx + rx_out * math.cos(ang), cy + ry_out * math.sin(ang))
        p2 = (cx + rx_in * math.cos(ang), cy + ry_in * math.sin(ang))
        draw.line([p1, p2], fill="black", width=2)
    # 中央の白楕円
    draw.ellipse([cx - rx_in, cy - ry_in, cx + rx_in, cy + ry_in],
                 fill="white", outline="black", width=3)
    _draw_text_centered(draw, cx - rx_in + 10, cy - ry_in + 10,
                        2 * rx_in - 20, 2 * ry_in - 20, text, font_size=22)


# ── サンプルシート構築 ────────────────────────────────────────────────

BUBBLES = [
    # (タイトルJP, タイトルEN, サンプルテキスト, drawer)
    ("楕円 (普通会話)",     "Oval - normal speech",      "おはよう",                 bub_oval),
    ("四角 (ナレ・説明)",   "Rectangle - narration",     "そして次の日 —",           bub_rect),
    ("ギザギザ (叫び)",     "Jagged - shouting",         "ヤバいっす!!",             bub_jagged),
    ("ガタガタ (動揺)",     "Wavy - anxiety",            "えっ…まじ…?",            bub_wavy),
    ("雲型 (心の声)",       "Cloud - thought",           "どうしよう…",              bub_cloud),
    ("星型 (ご機嫌)",       "Star - cheerful",           "やった〜♪",                bub_star),
    ("点線 (ささやき)",     "Dotted - whisper",          "…来てる",                  bub_dotted),
    ("太線 (強調)",         "Bold - emphasis",           "絶対やる",                 bub_bold),
    ("多重 (電話)",         "Multi-line - phone",        "もしもし",                 bub_multi),
    ("異形 (機械音)",       "Polygon - robot/PA",        "ケイコク",                 bub_phone),
    ("波線 (怪奇)",         "Wavy line - eerie",         "うらめしや",               bub_wave_line),
    ("枠なし (独白)",       "No border - monologue",     "あいつ…",                  bub_no_border),
    ("ベタフラッシュ (衝撃)", "Solid black - shock",       "終わった…",                bub_solid),
    ("ウニフラッシュ (決意)", "Radial - resolve",          "やるしかない",             bub_uni_flash),
]


def main():
    canvas = Image.new("RGB", (SHEET_W, SHEET_H), BG)
    draw = ImageDraw.Draw(canvas)

    # タイトル
    f_title = ImageFont.truetype(FONT_LABEL, 32)
    f_sub = ImageFont.truetype(FONT_TEXT, 16)
    draw.text((OUTER, OUTER), "漫画 吹き出し サンプル 14 種 (PIL 描画可能)",
              font=f_title, fill=(20, 20, 20))
    draw.text((OUTER, OUTER + 42),
              "compose 段で各 cut の冒頭フレームに合成可能。 type 別の draw 関数を持つ。",
              font=f_sub, fill=(80, 80, 80))

    grid_y0 = OUTER + TITLE_H
    for idx, (jp, en, text, drawer) in enumerate(BUBBLES):
        col = idx % COLS
        row = idx // COLS
        cx = OUTER + col * (CELL_W + GAP)
        cy = grid_y0 + row * (CELL_H + GAP)
        draw_bubble_box(canvas, cx, cy, jp, en, text, drawer)

    OUT.parent.mkdir(parents=True, exist_ok=True)
    canvas.save(OUT, "PNG")
    print(f"saved: {OUT}")


if __name__ == "__main__":
    main()
