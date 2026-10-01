"""DL したフリー素材 (illustcenter) を 1 枚の比較シートに並べる."""
from pathlib import Path
import os
from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parents[4]
ASSETS = ROOT / "sandbox" / "kling-i2v-spike" / "assets" / "bubbles" / "illustcenter"
OUT = ROOT / "review" / "demo-001_bubble_freeassets_illustcenter.png"

FONT_LABEL = os.environ["JP_FONT_BOLD_PATH"]  # 太字フォントのパスを環境変数で渡す(既定値なし)
FONT_TEXT = os.environ["JP_FONT_PATH"]  # 通常フォントのパスを環境変数で渡す(既定値なし)

# (file 名, ラベル) — sdesign_00117 = 漫画の吹き出し(001) 〜 14
LABELS = [
    ("sdesign_00117.png", "001 通常会話"),
    ("sdesign_00118.png", "002 通常会話"),
    ("sdesign_00119.png", "003 叫び/トゲ"),
    ("sdesign_00120.png", "004 叫び/トゲ"),
    ("sdesign_00121.png", "005 雲型/思考"),
    ("sdesign_00122.png", "006 雲型/思考"),
    ("sdesign_00123.png", "007 四角/ナレ"),
    ("sdesign_00124.png", "008 多角形"),
    ("sdesign_00125.png", "009 通常"),
    ("sdesign_00126.png", "010 強調"),
    ("sdesign_00127.png", "011 ガタガタ/動揺"),
    ("sdesign_00128.png", "012 ギザギザ強"),
    ("sdesign_00129.png", "013 雲型大"),
    ("sdesign_00130.png", "014 異形/特殊"),
    ("rdesign_7171.png", "集中線吹き出し"),
    ("rdesign_7170.png", "セット (18 種 全部入り)"),
]

CELL_W, CELL_H = 440, 400
COLS, ROWS = 4, 4
GAP = 20
OUTER = 40
TITLE_H = 80
SHEET_W = COLS * CELL_W + (COLS - 1) * GAP + 2 * OUTER
SHEET_H = TITLE_H + ROWS * CELL_H + (ROWS - 1) * GAP + 2 * OUTER

BG = (250, 248, 244)
CELL_BG = (255, 255, 255)


def draw_cell(canvas, x, y, fname, label):
    draw = ImageDraw.Draw(canvas)
    # セル外枠
    draw.rectangle([x, y, x + CELL_W, y + CELL_H], fill=CELL_BG, outline=(200, 200, 200))
    # ラベル
    f_label = ImageFont.truetype(FONT_LABEL, 20)
    f_sub = ImageFont.truetype(FONT_TEXT, 13)
    draw.text((x + 12, y + 10), label, font=f_label, fill=(20, 20, 20))
    draw.text((x + 12, y + 38), fname, font=f_sub, fill=(120, 120, 120))

    # 画像読み込み + フィット
    img_path = ASSETS / fname
    if not img_path.exists():
        draw.text((x + 12, y + 80), "(missing)", font=f_label, fill=(180, 0, 0))
        return
    img = Image.open(img_path).convert("RGBA")
    area_w, area_h = CELL_W - 24, CELL_H - 80
    # アスペクト比保持してフィット
    iw, ih = img.size
    scale = min(area_w / iw, area_h / ih)
    new_w, new_h = int(iw * scale), int(ih * scale)
    img = img.resize((new_w, new_h), Image.LANCZOS)
    # 中央配置
    paste_x = x + 12 + (area_w - new_w) // 2
    paste_y = y + 65 + (area_h - new_h) // 2
    canvas.paste(img, (paste_x, paste_y), img)


def main():
    canvas = Image.new("RGB", (SHEET_W, SHEET_H), BG)
    draw = ImageDraw.Draw(canvas)

    f_title = ImageFont.truetype(FONT_LABEL, 32)
    f_sub = ImageFont.truetype(FONT_TEXT, 16)
    draw.text((OUTER, OUTER), "フリー素材 吹き出し 16 種 (illustcenter.com 商用OK/クレジット不要)",
              font=f_title, fill=(20, 20, 20))
    draw.text((OUTER, OUTER + 42),
              "DL 元: https://illustcenter.com  保存先: sandbox/kling-i2v-spike/assets/bubbles/illustcenter/",
              font=f_sub, fill=(80, 80, 80))

    grid_y0 = OUTER + TITLE_H
    for idx, (fname, label) in enumerate(LABELS):
        col = idx % COLS
        row = idx // COLS
        cx = OUTER + col * (CELL_W + GAP)
        cy = grid_y0 + row * (CELL_H + GAP)
        draw_cell(canvas, cx, cy, fname, label)

    OUT.parent.mkdir(parents=True, exist_ok=True)
    canvas.save(OUT, "PNG")
    print(f"saved: {OUT}")


if __name__ == "__main__":
    main()
