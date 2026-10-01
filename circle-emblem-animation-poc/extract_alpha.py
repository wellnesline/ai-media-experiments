"""MiniMaxのグリーン背景動画をゲーム用RGBA素材へ変換する。"""
import argparse
import json
import math
import subprocess
from pathlib import Path

import cv2
import numpy as np
from PIL import Image, ImageDraw


def smoothstep(x, lo, hi):
    x = np.clip((x - lo) / (hi - lo), 0.0, 1.0)
    return x * x * (3.0 - 2.0 * x)


def estimate_bg(rgb):
    b = 18
    border = np.concatenate([
        rgb[:b].reshape(-1, 3), rgb[-b:].reshape(-1, 3),
        rgb[:, :b].reshape(-1, 3), rgb[:, -b:].reshape(-1, 3)
    ])
    # 緑優勢の境界画素のみを使い、キャラが端へ寄った場合も保護する。
    keep = (border[:, 1] > border[:, 0] * 1.18) & (border[:, 1] > border[:, 2] * 1.18)
    sample = border[keep] if keep.sum() > 100 else border
    return np.median(sample, axis=0)


def matte(rgb):
    f = rgb.astype(np.float32)
    bg = estimate_bg(f)
    dist = np.linalg.norm(f - bg[None, None, :], axis=2)
    # 緑の優勢度も利用。圧縮で色が揺れても背景は透明になる。
    dominance = f[:, :, 1] - np.maximum(f[:, :, 0], f[:, :, 2])
    a_dist = smoothstep(dist, 24.0, 82.0)
    a_green = 1.0 - smoothstep(dominance, 12.0, 48.0)
    # 色距離だけだと圧縮で暗くなった緑の縁を前景と誤認する。
    # 緑優勢の画素に限り、dominance判定との小さい方を採用する。
    alpha = np.where(dominance > 12.0, np.minimum(a_dist, a_green), a_dist)
    alpha = cv2.medianBlur((alpha * 255).astype(np.uint8), 3)
    alpha = cv2.GaussianBlur(alpha, (0, 0), 0.9)
    # H3が背景上に作る孤立した小粒を除去。キャラと足元影は十分大きいので保持される。
    n, labels, stats, _ = cv2.connectedComponentsWithStats((alpha > 64).astype(np.uint8), 8)
    for label in range(1, n):
        if stats[label, cv2.CC_STAT_AREA] < 256:
            speck = (labels == label).astype(np.uint8)
            speck = cv2.dilate(speck, np.ones((7, 7), np.uint8), iterations=1)
            alpha[speck > 0] = 0
    # green spill suppression at semi-transparent edges
    spill = np.clip((f[:, :, 1] - np.maximum(f[:, :, 0], f[:, :, 2])) * (1 - alpha[..., None] / 255.0), 0, 90)
    f[:, :, 1] = np.clip(f[:, :, 1] - spill[:, :, 0] * 0.8, 0, 255)
    return f.astype(np.uint8), alpha, bg


def checker(rgba, size=24):
    h, w = rgba.shape[:2]
    yy, xx = np.indices((h, w))
    c = np.where(((xx // size + yy // size) % 2)[..., None] == 0, 224, 176).astype(np.uint8)
    c = np.repeat(c, 3, axis=2)
    a = rgba[:, :, 3:4].astype(np.float32) / 255
    return (rgba[:, :, :3] * a + c * (1 - a)).astype(np.uint8)


def run(cmd):
    subprocess.run(cmd, check=True)


ap = argparse.ArgumentParser()
ap.add_argument("video")
ap.add_argument("--out", required=True)
ap.add_argument("--fps", type=int, default=24)
ap.add_argument("--sprite-frames", type=int, default=24)
args = ap.parse_args()

video = Path(args.video).resolve()
out = Path(args.out).resolve()
frames_dir = out / "frames_rgba"
raw_dir = out / "frames_raw"
for d in (out, frames_dir, raw_dir):
    d.mkdir(parents=True, exist_ok=True)

run(["ffmpeg", "-y", "-loglevel", "error", "-i", str(video), "-an", str(raw_dir / "%04d.png")])
raws = sorted(raw_dir.glob("*.png"))
alphas, bgs, rgba_frames = [], [], []
for p in raws:
    rgb = np.asarray(Image.open(p).convert("RGB"))
    clean, alpha, bg = matte(rgb)
    rgba_frames.append(np.dstack([clean, alpha]))
    alphas.append(alpha)
    bgs.append(bg.tolist())

# 軽い時間方向メディアンでalphaのちらつきを抑える。
for i, rgba in enumerate(rgba_frames):
    lo, hi = max(0, i - 1), min(len(rgba_frames), i + 2)
    rgba[:, :, 3] = np.median(np.stack(alphas[lo:hi]), axis=0).astype(np.uint8)
    Image.fromarray(rgba, "RGBA").save(frames_dir / f"frame_{i:04d}.png", compress_level=4)

# VP9 alpha と ProRes 4444。ffmpegは偶数寸法のyuva420pを要求する。
run(["ffmpeg", "-y", "-loglevel", "error", "-framerate", str(args.fps),
     "-i", str(frames_dir / "frame_%04d.png"), "-c:v", "libvpx-vp9", "-pix_fmt", "yuva420p",
     "-lossless", "1", "-an", str(out / "animation_alpha.webm")])
run(["ffmpeg", "-y", "-loglevel", "error", "-framerate", str(args.fps),
     "-i", str(frames_dir / "frame_%04d.png"), "-c:v", "prores_ks", "-profile:v", "4",
     "-pix_fmt", "yuva444p10le", "-an", str(out / "animation_alpha_prores4444.mov")])

# 全尺チェッカープレビュー
preview_dir = out / "preview_frames"
preview_dir.mkdir(exist_ok=True)
for i, rgba in enumerate(rgba_frames):
    Image.fromarray(checker(rgba)).save(preview_dir / f"frame_{i:04d}.jpg", quality=88)
run(["ffmpeg", "-y", "-loglevel", "error", "-framerate", str(args.fps),
     "-i", str(preview_dir / "frame_%04d.jpg"), "-c:v", "libx264", "-crf", "20", "-pix_fmt", "yuv420p",
     "-movflags", "+faststart", str(out / "preview_checker.mp4")])

# 24コマを均等抽出した6x4スプライトシート（各セル256px）。
n = min(args.sprite_frames, len(rgba_frames))
indices = np.linspace(0, len(rgba_frames) - 1, n).round().astype(int)
cols, cell = 6, 256
rows = math.ceil(n / cols)
sheet = Image.new("RGBA", (cols * cell, rows * cell), (0, 0, 0, 0))
for j, idx in enumerate(indices):
    tile = Image.fromarray(rgba_frames[idx], "RGBA").resize((cell, cell), Image.Resampling.LANCZOS)
    sheet.alpha_composite(tile, ((j % cols) * cell, (j // cols) * cell))
sheet.save(out / "spritesheet_6x4_rgba.png")

# 数値検証
a_all = np.stack([x[:, :, 3] for x in rgba_frames])
first = rgba_frames[0].astype(np.float32)
last = rgba_frames[-1].astype(np.float32)
metrics = {
    "input_video": str(video), "frame_count": len(rgba_frames), "fps": args.fps,
    "width": int(rgba_frames[0].shape[1]), "height": int(rgba_frames[0].shape[0]),
    "alpha_min": int(a_all.min()), "alpha_max": int(a_all.max()),
    "transparent_pixel_ratio": float((a_all < 8).mean()),
    "opaque_pixel_ratio": float((a_all > 247).mean()),
    "first_last_rgba_mae": float(np.abs(first - last).mean()),
    "estimated_background_rgb_median": np.median(np.asarray(bgs), axis=0).round(2).tolist(),
    "spritesheet_indices": indices.tolist(),
}
(out / "metrics.json").write_text(json.dumps(metrics, ensure_ascii=False, indent=2), encoding="utf-8")
print(json.dumps(metrics, ensure_ascii=False, indent=2))
