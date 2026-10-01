"""ComfyUI Phase A — Test 3: SD1.5 + Counterfeit V3.0 + AnimateDiff v3.

SDXL beta motion module が出力崩壊したため、 community 実証のある SD1.5 路線に降格。
- checkpoint: Counterfeit-V3.0_fp16.safetensors (anime SD1.5 community standard)
- motion: mm_sd_v15_v2.ckpt (AnimateDiff v3, SD1.5 安定版)
- 解像度: 512x768 (SD1.5 native, anime portrait)
- 16 frames @ 8fps = 2 秒

実行: python test_animatediff_sd15.py
出力: comfyui_tests/out_sd15_<timestamp>.mp4
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

WIDTH = 512
HEIGHT = 768
FRAMES = 16  # 2.0 sec @ 8fps
FPS = 8
STEPS = 24

# Counterfeit-V3.0 は Danbooru-style tag prompt が前提
PROMPT_POS = (
    "masterpiece, best quality, 1girl, solo, japanese, "
    "short black hair, brown eyes, "
    "green jacket, gray shirt, "
    "cheerful expression, parted lips, slightly turning head, "
    "indoors, workshop, afternoon light, "
    "cinematic lighting, soft shading"
)
PROMPT_NEG = (
    "EasyNegative, (worst quality, low quality:1.4), "
    "bad anatomy, bad hands, missing fingers, extra digit, "
    "fewer digits, jpeg artifacts, signature, watermark, "
    "username, blurry, text, chinese text, kanji"
)

WORKFLOW = {
    "4": {
        "class_type": "CheckpointLoaderSimple",
        "inputs": {"ckpt_name": "Counterfeit-V3.0_fp16.safetensors"},
    },
    "10": {
        "class_type": "ADE_LoadAnimateDiffModel",
        "inputs": {"model_name": "mm_sd_v15_v2.ckpt"},
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
    "5": {
        "class_type": "ADE_EmptyLatentImageLarge",
        "inputs": {"width": WIDTH, "height": HEIGHT, "batch_size": FRAMES},
    },
    "6": {
        "class_type": "CLIPTextEncode",
        "inputs": {"text": PROMPT_POS, "clip": ["4", 1]},
    },
    "7": {
        "class_type": "CLIPTextEncode",
        "inputs": {"text": PROMPT_NEG, "clip": ["4", 1]},
    },
    "3": {
        "class_type": "KSampler",
        "inputs": {
            "seed": 42,
            "steps": STEPS,
            "cfg": 7.0,
            "sampler_name": "dpmpp_2m",
            "scheduler": "karras",
            "denoise": 1.0,
            "model": ["13", 0],
            "positive": ["6", 0],
            "negative": ["7", 0],
            "latent_image": ["5", 0],
        },
    },
    "8": {
        "class_type": "VAEDecode",
        "inputs": {"samples": ["3", 0], "vae": ["4", 2]},
    },
    "20": {
        "class_type": "VHS_VideoCombine",
        "inputs": {
            "images": ["8", 0],
            "frame_rate": float(FPS),
            "loop_count": 0,
            "filename_prefix": "phase_a_sd15_test",
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
    print(f"\n[1/3] Queueing SD1.5 + AnimateDiff v3 workflow:")
    print(f"      Counterfeit-V3.0 + mm_sd_v15_v2")
    print(f"      {WIDTH}x{HEIGHT}, {FRAMES} frames @ {FPS}fps ({FRAMES/FPS:.1f}sec), {STEPS} steps")
    t0 = time.time()
    pid = post_prompt(WORKFLOW, client_id)
    print(f"  prompt_id={pid}")

    print(f"\n[2/3] Waiting for completion...")
    result = wait_history(pid)
    elapsed = time.time() - t0
    print(f"  finished in {elapsed:.1f}s ({elapsed/60:.1f} min)")

    print(f"\n[3/3] Downloading output mp4...")
    outputs = result.get("outputs", {})
    save_node = outputs.get("20", {})
    files_list = save_node.get("gifs") or save_node.get("images") or []
    if not files_list:
        print(f"  ERROR: no output files: {save_node}", file=sys.stderr)
        return 1
    f = files_list[0]
    ts = time.strftime("%Y%m%d_%H%M%S")
    ext = Path(f["filename"]).suffix
    dst = HERE / f"out_sd15_{ts}{ext}"
    download_file(f["filename"], f["subfolder"], f["type"], dst)
    print(f"  saved: {dst} ({dst.stat().st_size/1024:.0f}KB)")
    print(f"\n[done] total {elapsed:.1f}s, {elapsed/FRAMES:.1f}s/frame")
    return 0


if __name__ == "__main__":
    sys.exit(main())
