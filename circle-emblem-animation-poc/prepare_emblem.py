from pathlib import Path
from PIL import Image
import numpy as np

ROOT = Path(__file__).resolve().parent
SRC = ROOT / "emblem_rgba.png"
OUT = ROOT / "emblem_green_768.png"

im = Image.open(SRC).convert("RGBA")
a = np.asarray(im.getchannel("A"))
ys, xs = np.where(a > 8)
box = (int(xs.min()), int(ys.min()), int(xs.max()) + 1, int(ys.max()) + 1)
fg = im.crop(box)
fg.thumbnail((650, 650), Image.Resampling.LANCZOS)
canvas = Image.new("RGBA", (768, 768), (0, 255, 0, 255))
canvas.alpha_composite(fg, ((768 - fg.width) // 2, (768 - fg.height) // 2))
canvas.convert("RGB").save(OUT)
print(f"bbox={box} placed={fg.size} output={OUT}")
