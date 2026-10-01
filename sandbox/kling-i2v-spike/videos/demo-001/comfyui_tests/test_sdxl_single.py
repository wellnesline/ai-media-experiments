"""ComfyUI Phase A — Test 1: SDXL anime single image gen (Animagine XL 3.1).

目的: ローカル GPU で Animagine XL 3.1 が動くか / 1枚あたり何秒かかるか / 画質はどうか を確認。

実行: python test_sdxl_single.py
出力: comfyui_tests/out_sdxl_<timestamp>.png
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

# ── workflow (ComfyUI API JSON format) ──
# Animagine XL 3.1 推奨: width=832 height=1216 (portrait) / steps=28 / cfg=7 / euler_ancestral / DPM++ 2M Karras
PROMPT_POS = (
    "masterpiece, best quality, very aesthetic, absurdres, "
    "1person, adult, short black hair, "
    "green jacket, gray shirt, gray tote bag, "
    "bright smile, eyes wide, mouth slightly open, "
    "workshop, indoor, tool racks, soft afternoon light, "
    "cinematic composition, anime style"
)
PROMPT_NEG = (
    "lowres, bad anatomy, bad hands, text, error, missing fingers, "
    "extra digit, fewer digits, cropped, worst quality, low quality, "
    "normal quality, jpeg artifacts, signature, watermark, username, blurry, "
    "chinese text, kanji text, paper, document"
)

WORKFLOW = {
    "3": {  # KSampler
        "class_type": "KSampler",
        "inputs": {
            "seed": 42,
            "steps": 28,
            "cfg": 7.0,
            "sampler_name": "euler_ancestral",
            "scheduler": "karras",
            "denoise": 1.0,
            "model": ["4", 0],
            "positive": ["6", 0],
            "negative": ["7", 0],
            "latent_image": ["5", 0],
        },
    },
    "4": {  # CheckpointLoaderSimple
        "class_type": "CheckpointLoaderSimple",
        "inputs": {"ckpt_name": "animagine-xl-3.1.safetensors"},
    },
    "5": {  # EmptyLatentImage (SDXL portrait 832x1216)
        "class_type": "EmptyLatentImage",
        "inputs": {"width": 832, "height": 1216, "batch_size": 1},
    },
    "6": {  # CLIPTextEncode positive
        "class_type": "CLIPTextEncode",
        "inputs": {"text": PROMPT_POS, "clip": ["4", 1]},
    },
    "7": {  # CLIPTextEncode negative
        "class_type": "CLIPTextEncode",
        "inputs": {"text": PROMPT_NEG, "clip": ["4", 1]},
    },
    "8": {  # VAEDecode
        "class_type": "VAEDecode",
        "inputs": {"samples": ["3", 0], "vae": ["4", 2]},
    },
    "9": {  # SaveImage
        "class_type": "SaveImage",
        "inputs": {"images": ["8", 0], "filename_prefix": "phase_a_sdxl_test"},
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


def wait_history(prompt_id: str, timeout: int = 600) -> dict:
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
        time.sleep(2)
    raise TimeoutError(f"prompt {prompt_id} did not finish in {timeout}s")


def download_image(filename: str, subfolder: str, type_: str, dst: Path):
    qs = urllib.parse.urlencode({"filename": filename, "subfolder": subfolder, "type": type_})
    with urllib.request.urlopen(f"{COMFY}/view?{qs}") as r:
        data = r.read()
    dst.write_bytes(data)


def main():
    client_id = str(uuid.uuid4())
    print(f"\n[1/3] Queueing SDXL workflow (Animagine XL 3.1, 832x1216, 28 steps)...")
    t0 = time.time()
    pid = post_prompt(WORKFLOW, client_id)
    print(f"  prompt_id={pid}")

    print(f"\n[2/3] Waiting for completion...")
    result = wait_history(pid)
    elapsed = time.time() - t0
    print(f"  finished in {elapsed:.1f}s")

    print(f"\n[3/3] Downloading output image...")
    outputs = result.get("outputs", {})
    save_node = outputs.get("9", {})
    images = save_node.get("images", [])
    if not images:
        print(f"  ERROR: no images in output: {outputs}", file=sys.stderr)
        return 1
    img = images[0]
    ts = time.strftime("%Y%m%d_%H%M%S")
    dst = HERE / f"out_sdxl_{ts}.png"
    download_image(img["filename"], img["subfolder"], img["type"], dst)
    print(f"  saved: {dst}")
    print(f"\n[done] {elapsed:.1f}s end-to-end (queue→saved)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
