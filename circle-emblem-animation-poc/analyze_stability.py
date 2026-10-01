import json
import sys
from pathlib import Path
import numpy as np
from PIL import Image

root = Path(__file__).resolve().parent
sets = {
    "pulse": root / "outputs_pulse", "spin": root / "outputs_spin",
    "activate": root / "outputs_activate",
    "combat_shot": root / "outputs_combat_shot",
    "combat_parry": root / "outputs_combat_parry",
    "combat_hit": root / "outputs_combat_hit",
    "combat_ultimate": root / "outputs_combat_ultimate",
}
report = {}
for name, folder in sets.items():
    centers, sizes, areas = [], [], []
    files = sorted((folder / "frames_rgba").glob("*.png"))
    for f in files:
        a = np.asarray(Image.open(f).convert("RGBA"))[:, :, 3]
        yy, xx = np.where(a > 32)
        centers.append(((float(xs := xx.mean())), float(ys := yy.mean())))
        sizes.append((int(xx.max() - xx.min() + 1), int(yy.max() - yy.min() + 1)))
        areas.append(int(len(xx)))
    c, s, ar = np.asarray(centers), np.asarray(sizes), np.asarray(areas)
    report[name] = {
        "frames": len(files),
        "centroid_std_px": [round(float(x), 3) for x in c.std(axis=0)],
        "bbox_size_mean_px": [round(float(x), 2) for x in s.mean(axis=0)],
        "bbox_size_std_px": [round(float(x), 3) for x in s.std(axis=0)],
        "visible_area_cv_percent": round(float(ar.std() / ar.mean() * 100), 3),
    }
(root / "stability_metrics.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
print(json.dumps(report, ensure_ascii=False, indent=2))
