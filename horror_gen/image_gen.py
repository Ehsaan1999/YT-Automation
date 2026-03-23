"""
image_gen.py
------------
Supports three image generation providers:

  1. Stable Horde  — completely free, no API key, community-powered inference
                     (anonymous key "0000000000" works; get a free key at
                      https://stablehorde.net/register for higher priority)
  2. HuggingFace   — free account + free monthly credits, uses SDXL
  3. DALL-E 3      — paid, OpenAI API key required

Provider selection order:
  use_dalle3=True  →  DALL-E 3
  hf_token set     →  HuggingFace  (falls back to Stable Horde on failure)
  default          →  Stable Horde (no key needed)

All providers return a list of saved image file paths.
"""

import base64
import os
import time
import requests


# ── Provider: Stable Horde (free, no key) ─────────────────────────────────────

_HORDE_BASE = "https://stablehorde.net/api/v2"
HORDE_ANON_KEY = "0000000000"   # anonymous — free, lower priority


def _generate_stable_horde(
    prompts:    list,
    output_dir: str,
    api_key:    str = HORDE_ANON_KEY,
    width:      int = 576,
    height:     int = 1024,
    log=print,
) -> list:
    """
    Generate images via Stable Horde (free community inference).
    No API key required — uses anonymous key by default.
    Register at stablehorde.net for a free key with higher priority.
    """
    headers     = {"apikey": api_key, "Content-Type": "application/json"}
    image_paths = []

    for i, prompt in enumerate(prompts, 1):
        log(f"  [Image {i}/{len(prompts)}] Stable Horde (free)...")

        payload = {
            "prompt": prompt,
            "params": {
                "width":     width,
                "height":    height,
                "steps":     20,
                "cfg_scale": 7,
                "karras":    True,
            },
            "nsfw":    False,
            "r2":      False,   # return base64 inline, no extra download step
            "shared":  False,
        }

        # Submit job — anonymous key is limited to ≤597×597.
        # If we get a kudos error, shrink to 512×512 and retry.
        resp = requests.post(f"{_HORDE_BASE}/generate/async",
                             json=payload, headers=headers, timeout=60)
        if resp.status_code == 403 and "KudosUpfront" in resp.text:
            log(f"    Portrait size needs kudos — retrying at 576×576 (free limit)...")
            payload["params"]["width"]  = 576
            payload["params"]["height"] = 576
            resp = requests.post(f"{_HORDE_BASE}/generate/async",
                                 json=payload, headers=headers, timeout=60)
        resp.raise_for_status()
        job_id = resp.json()["id"]
        log(f"    Job submitted: {job_id}")

        # Poll until done (up to 12 minutes)
        for tick in range(144):
            time.sleep(5)
            try:
                check = requests.get(
                    f"{_HORDE_BASE}/generate/check/{job_id}",
                    headers=headers, timeout=30,
                ).json()
            except Exception:
                continue   # transient network hiccup — keep polling
            if check.get("done"):
                break
            wait = check.get("wait_time", "?")
            if tick % 6 == 0:   # log every 30s
                log(f"    Waiting... ~{wait}s remaining")
        else:
            raise RuntimeError(f"Stable Horde timeout for scene {i}")

        # Retrieve result (large base64 payload — retry with generous timeout)
        result = None
        for attempt in range(1, 4):
            try:
                resp = requests.get(
                    f"{_HORDE_BASE}/generate/status/{job_id}",
                    headers=headers, timeout=120,
                )
                resp.raise_for_status()
                result = resp.json()
                break
            except Exception as fetch_err:
                log(f"    Fetch attempt {attempt} failed: {fetch_err}, retrying...")
                time.sleep(5)
        if result is None:
            raise RuntimeError(f"Could not retrieve Stable Horde result for scene {i}")

        generations = result.get("generations", [])
        if not generations:
            raise RuntimeError(f"Stable Horde returned no image for scene {i}")

        img_data = base64.b64decode(generations[0]["img"])
        img_path = os.path.join(output_dir, f"scene_{i:02d}.png")
        with open(img_path, "wb") as f:
            f.write(img_data)

        size_kb = len(img_data) / 1024
        log(f"  [Image {i}/{len(prompts)}] Saved  ({size_kb:.0f} KB) -> {img_path}")
        image_paths.append(img_path)

    return image_paths


# ── Provider: HuggingFace Inference API (free token + monthly credits) ─────────

def _generate_huggingface(
    prompts:    list,
    output_dir: str,
    api_key:    str,
    model:      str   = "stabilityai/stable-diffusion-xl-base-1.0",
    log=print,
) -> list:
    """
    Generate images via HuggingFace Inference API (free HF token).
    Uses provider="hf-inference" to force HF's own free serverless inference.
    Free monthly credits included; falls back to Stable Horde on 402.
    """
    try:
        from huggingface_hub import InferenceClient
    except ImportError:
        raise RuntimeError("huggingface_hub not installed. Run: pip install huggingface_hub")

    client      = InferenceClient(api_key=api_key, provider="hf-inference")
    image_paths = []

    for i, prompt in enumerate(prompts, 1):
        log(f"  [Image {i}/{len(prompts)}] HuggingFace ({model.split('/')[-1]})...")
        image = client.text_to_image(prompt=prompt, model=model)

        img_path = os.path.join(output_dir, f"scene_{i:02d}.png")
        image.save(img_path)

        size_kb = os.path.getsize(img_path) / 1024
        log(f"  [Image {i}/{len(prompts)}] Saved  ({size_kb:.0f} KB) -> {img_path}")
        image_paths.append(img_path)

    return image_paths


# ── Provider: DALL-E 3 (paid, OpenAI key) ─────────────────────────────────────

def _generate_dalle3(
    prompts:    list,
    output_dir: str,
    api_key:    str,
    quality:    str = "standard",
    log=print,
) -> list:
    """Generate images via DALL-E 3 (OpenAI API, paid per image)."""
    try:
        import openai
    except ImportError:
        raise RuntimeError("openai not installed. Run: pip install openai")

    client      = openai.OpenAI(api_key=api_key)
    image_paths = []

    for i, prompt in enumerate(prompts, 1):
        log(f"  [Image {i}/{len(prompts)}] DALL-E 3 ({quality})...")

        response = client.images.generate(
            model   = "dall-e-3",
            prompt  = prompt,
            size    = "1024x1792",
            quality = quality,
            n       = 1,
        )

        image_url = response.data[0].url
        img_bytes = requests.get(image_url, timeout=60).content
        img_path  = os.path.join(output_dir, f"scene_{i:02d}.png")
        with open(img_path, "wb") as f:
            f.write(img_bytes)

        size_kb = len(img_bytes) / 1024
        log(f"  [Image {i}/{len(prompts)}] Saved  ({size_kb:.0f} KB) -> {img_path}")
        image_paths.append(img_path)

    return image_paths


# ── Unified entry point ────────────────────────────────────────────────────────

def generate_images(
    prompts:    list,
    output_dir: str,
    hf_token:   str  = "",
    hf_model:   str  = "stabilityai/stable-diffusion-xl-base-1.0",
    openai_key: str  = "",
    use_dalle3: bool = False,
    horde_key:  str  = HORDE_ANON_KEY,
    log=print,
) -> list:
    """
    Smart provider selection:
      use_dalle3=True   →  DALL-E 3         (needs openai_key)
      hf_token set      →  HuggingFace SDXL (free monthly credits)
                           falls back to Stable Horde on 402/failure
      default           →  Stable Horde     (free, no key needed)

    Returns list of saved image file paths in prompt order.
    """
    os.makedirs(output_dir, exist_ok=True)

    if use_dalle3:
        if not openai_key:
            raise ValueError("DALL-E 3 requires an OpenAI API key.")
        return _generate_dalle3(prompts, output_dir, openai_key, log=log)

    if hf_token.strip():
        log("  Image provider : HuggingFace")
        try:
            return _generate_huggingface(prompts, output_dir, hf_token,
                                         model=hf_model, log=log)
        except Exception as e:
            log(f"  HuggingFace failed ({e})")
            log("  Falling back to Stable Horde (free)...")

    log("  Image provider : Stable Horde (free, no key needed)")
    return _generate_stable_horde(prompts, output_dir, horde_key, log=log)
