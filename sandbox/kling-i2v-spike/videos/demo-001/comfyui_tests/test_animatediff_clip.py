"""ComfyUI Phase A — Test 2: AnimateDiff SDXL motion clip generation.

目的: Animagine XL 3.1 + AnimateDiff SDXL beta motion module で
     2秒 (16 frames @ 8fps) のアニメクリップ生成。 動きの品質と所要時間を確認。

実行: python test_animatediff_clip.py
出力: comfyui_tests/out_animatediff_<timestamp>.mp4
"""
from __future__ import annotations

import json
import time
import urllib.request
import urllib.parse
import uuid
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
COMFY = "http://127.0.0.1:8188"

# AnimateDiff SDXL beta は SD1.5 版より品質が低いが、 SDXL anime base と併用できる唯一の手段。
# Animagine XL 3.1 公式推奨: 832x1216 portrait
# AnimateDiff SDXL: context_length=16 が最適 (それより長いと不安定)。
WIDTH = 832
HEIGHT = 1216
FRAMES = 8  # 1.0 sec @ 8fps (16f hung on a low-memory local GPU — activation OOM)
FPS = 8
STEPS = 20

PROMPT_POS = (
    "masterpiece, best quality, very aesthetic, absurdres, "
    "1person, adult, short black hair, "
    "green jacket, gray shirt, gray tote bag, "
    "bright smile, eyes wide, slightly turning head, "
    "workshop, indoor, tool racks, soft afternoon light, "
    "cinematic composition, anime style, "
    "dynamic motion, subtle head turn"
)
PROMPT_NEG = (
    "lowres, bad anatomy, bad hands, text, error, missing fingers, "
    "extra digit, fewer digits, cropped, worst quality, low quality, "
    "normal quality, jpeg artifacts, signature, watermark, username, blurry, "
    "chinese text, kanji text, static, still"
)

WORKFLOW = {
    # ── checkpoint ──
    "4": {
        "class_type": "CheckpointLoaderSimple",
        "inputs": {"ckpt_name": "animagine-xl-3.1.safetensors"},
    },
    # ── AnimateDiff motion module ──
    "10": {
        "class_type": "ADE_LoadAnimateDiffModel",
        "inputs": {"model_name": "mm_sdxl_v10_beta.ckpt"},
    },
    "11": {
        "class_type": "ADE_ApplyAnimateDiffModelSimple",
        "inputs": {"motion_model": ["10", 0]},
    },
    "12": {
        "class_type": "ADE_StandardUniformContextOptions",
        "inputs": {
            "context_length": 16,
            "context_stride": 1,
            "context_overlap": 4,
            "fuse_method": "pyramid",
            "use_on_equal_length": False,
            "start_percent": 0.0,
            "guarantee_steps": 1,
        },
    },
    "13": {
        "class_type": "ADE_UseEvolvedSampling",
        "inputs": {
            "model": ["4", 0],
            "beta_schedule": "autoselect",
            "m_models": ["11", 0],
            "context_options": ["12", 0],
        },
    },
    # ── latent ──
    "5": {
        "class_type": "ADE_EmptyLatentImageLarge",
        "inputs": {"width": WIDTH, "height": HEIGHT, "batch_size": FRAMES},
    },
    # ── prompts ──
    "6": {
        "class_type": "CLIPTextEncode",
        "inputs": {"text": PROMPT_POS, "clip": ["4", 1]},
    },
    "7": {
        "class_type": "CLIPTextEncode",
        "inputs": {"text": PROMPT_NEG, "clip": ["4", 1]},
    },
    # ── sampler ──
    "3": {
        "class_type": "KSampler",
        "inputs": {
            "seed": 42,
            "steps": STEPS,
            "cfg": 7.0,
            "sampler_name": "euler_ancestral",
            "scheduler": "karras",
            "denoise": 1.0,
            "model": ["13", 0],
            "positive": ["6", 0],
            "negative": ["7", 0],
            "latent_image": ["5", 0],
        },
    },
    # ── decode ──
    "8": {
        "class_type": "VAEDecode",
        "inputs": {"samples": ["3", 0], "vae": ["4", 2]},
    },
    # ── combine into mp4 ──
    "20": {
        "class_type": "VHS_VideoCombine",
        "inputs": {
            "images": ["8", 0],
            "frame_rate": float(FPS),
            "loop_count": 0,
            "filename_prefix": "phase_a_animatediff_test",
            "format": "video/h264-mp4",
            "pingpong": False,
            "save_output": True,
        },
    },
}


def post_prompt(workflow: dict, client_id: str) -> str:
    body = json.dumps({"prompt": workflow, "client_id": client_id}).encode()
    req = urllib.request.Request(
        f"{COMFY}/prompt", data=body, headers={"Content-Type": "application/json"}
    )
    with urllib.request.urlopen(req) as r:
        resp = json.loads(r.read())
    if "prompt_id" not in resp:
        raise RuntimeError(f"queue failed: {resp}")
    return resp["prompt_id"]


def wait_history(prompt_id: str, timeout: int = 1800) -> dict:
    t0 = time.time()
    last_status = None
    while time.time() - t0 < timeout:
        try:
            with urllib.request.urlopen(f"{COMFY}/history/{prompt_id}", timeout=5) as r:
                h = json.loads(r.read())
            if prompt_id in h:
                return h[prompt_id]
        except Exception:
            pass
        try:
            with urllib.request.urlopen(f"{COMFY}/queue", timeout=5) as r:
                q = json.loads(r.read())
            running = len(q.get("queue_running", []))
            pending = len(q.get("queue_pending", []))
            status = f"running={running} pending={pending}"
            if status != last_status:
                print(f"  [{int(time.time()-t0)}s] {status}", flush=True)
                last_status = status
        except Exception:
            pass
        time.sleep(3)
    raise TimeoutError(f"prompt {prompt_id} did not finish in {timeout}s")


def download_file(filename: str, subfolder: str, type_: str, dst: Path):
    qs = urllib.parse.urlencode({"filename": filename, "subfolder": subfolder, "type": type_})
    with urllib.request.urlopen(f"{COMFY}/view?{qs}") as r:
        data = r.read()
    dst.write_bytes(data)


def main():
    client_id = str(uuid.uuid4())
    print(f"\n[1/3] Queueing AnimateDiff workflow:")
    print(f"      Animagine XL 3.1 + mm_sdxl_v10_beta")
    print(f"      {WIDTH}x{HEIGHT}, {FRAMES} frames @ {FPS}fps ({FRAMES/FPS:.1f}sec), {STEPS} steps")
    t0 = time.time()
    pid = post_prompt(WORKFLOW, client_id)
    print(f"  prompt_id={pid}")

    print(f"\n[2/3] Waiting for completion (this can take 5-15 min on a local GPU)...")
    result = wait_history(pid)
    elapsed = time.time() - t0
    print(f"  finished in {elapsed:.1f}s ({elapsed/60:.1f} min)")

    print(f"\n[3/3] Downloading output mp4...")
    outputs = result.get("outputs", {})
    save_node = outputs.get("20", {})
    # VHS_VideoCombine puts video file info under 'gifs' or 'images' key
    files_list = save_node.get("gifs") or save_node.get("images") or []
    if not files_list:
        print(f"  ERROR: no output files: {save_node}", file=sys.stderr)
        return 1
    f = files_list[0]
    ts = time.strftime("%Y%m%d_%H%M%S")
    ext = Path(f["filename"]).suffix
    dst = HERE / f"out_animatediff_{ts}{ext}"
    download_file(f["filename"], f["subfolder"], f["type"], dst)
    print(f"  saved: {dst} ({dst.stat().st_size/1024:.0f}KB)")
    print(f"\n[done] total {elapsed:.1f}s, {elapsed/FRAMES:.1f}s/frame")
    return 0


if __name__ == "__main__":
    sys.exit(main())
