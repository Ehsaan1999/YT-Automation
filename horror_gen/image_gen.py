"""
image_gen.py
------------
Supports three image generation providers:

  1. Pollinations.AI  — completely free, no API key, uses FLUX
  2. HuggingFace      — free account + free token, uses FLUX.1-dev
  3. DALL-E 3         — paid, OpenAI API key required

All providers return a list of saved image file paths.
"""

import os
import time
import urllib.parse
import requests


# ── Provider: Pollinations.AI (free, no key) ───────────────────────────────────

def _generate_pollinations(
    prompts:    list,
    output_dir: str,
    width:      int   = 576,
    height:     int   = 1024,   # standard 9:16 SD portrait — avoids 500 errors
    log=print,
) -> list:
    """
    Generate images via Pollinations.AI (100% free, no account needed).
    Sends a GET request per prompt; response body is the raw image bytes.
    Note: extreme resolutions (e.g. 1080x1920) cause 500 errors; use 576x1024.
    """
    image_paths = []
    for i, prompt in enumerate(prompts, 1):
        log(f"  [Image {i}/{len(prompts)}] Pollinations...")

        encoded = urllib.parse.quote(prompt)
        url = (
            f"https://image.pollinations.ai/prompt/{encoded}"
            f"?width={width}&height={height}&nologo=true&seed={i * 7919}"
        )

        # Pollinations can be slow — retry up to 3 times
        for attempt in range(1, 4):
            try:
                resp = requests.get(url, timeout=120)
                if resp.status_code == 200 and resp.content:
                    break
                log(f"    Attempt {attempt}: status {resp.status_code}, retrying...")
                time.sleep(5)
            except Exception as e:
                log(f"    Attempt {attempt} error: {e}, retrying...")
                time.sleep(5)
        else:
            raise RuntimeError(f"Pollinations failed after 3 attempts for scene {i}")

        img_path = os.path.join(output_dir, f"scene_{i:02d}.png")
        with open(img_path, "wb") as f:
            f.write(resp.content)

        size_kb = len(resp.content) / 1024
        log(f"  [Image {i}/{len(prompts)}] Saved  ({size_kb:.0f} KB) -> {img_path}")
        image_paths.append(img_path)

        # Small delay to be polite to the free service
        if i < len(prompts):
            time.sleep(2)

    return image_paths


# ── Provider: HuggingFace Inference API (free token) ──────────────────────────

def _generate_huggingface(
    prompts:    list,
    output_dir: str,
    api_key:    str,
    model:      str   = "stabilityai/stable-diffusion-xl-base-1.0",
    log=print,
) -> list:
    """
    Generate images via HuggingFace Inference API (free HF token).
    Uses provider="hf-inference" to force HF's own free serverless inference
    (avoids paid third-party providers like fal-ai or together.ai).
    Recommended free models:
      - stabilityai/stable-diffusion-xl-base-1.0  (best free quality)
      - stabilityai/stable-diffusion-2-1
    """
    try:
        from huggingface_hub import InferenceClient
    except ImportError:
        raise RuntimeError("huggingface_hub not installed. Run: pip install huggingface_hub")

    # provider="hf-inference" forces HF's own free backend, no credits needed
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
    quality:    str = "standard",   # "standard" or "hd"
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
            size    = "1024x1792",   # portrait — closest to 9:16
            quality = quality,
            n       = 1,
        )

        image_url  = response.data[0].url
        img_bytes  = requests.get(image_url, timeout=60).content
        img_path   = os.path.join(output_dir, f"scene_{i:02d}.png")
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
    hf_token:   str  = "",                              # free HF token; leave blank for Pollinations
    hf_model:   str  = "black-forest-labs/FLUX.1-dev",  # used only when hf_token is set
    openai_key: str  = "",                              # only needed for DALL-E 3
    use_dalle3: bool = False,                           # set True to use DALL-E 3 instead
    log=print,
) -> list:
    """
    Smart provider selection:
      - use_dalle3=True          → DALL-E 3  (needs openai_key)
      - hf_token provided        → HuggingFace FLUX.1-dev  (free token)
      - hf_token empty (default) → Pollinations FLUX  (no key, 100% free)

    Returns list of saved image file paths in prompt order.
    """
    os.makedirs(output_dir, exist_ok=True)

    if use_dalle3:
        if not openai_key:
            raise ValueError("DALL-E 3 requires an OpenAI API key.")
        return _generate_dalle3(prompts, output_dir, openai_key, log=log)

    if hf_token.strip():
        log("  Image provider : HuggingFace (FLUX)")
        try:
            return _generate_huggingface(prompts, output_dir, hf_token, model=hf_model, log=log)
        except Exception as e:
            log(f"  HuggingFace failed ({e}), falling back to Pollinations...")

    log("  Image provider : Pollinations (free, no key)")
    return _generate_pollinations(prompts, output_dir, log=log)
