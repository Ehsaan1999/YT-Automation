"""
tts_gen.py
----------
Text-to-speech with two providers:

  1. Unturf Speech API  (https://speech.ai.unturf.com/v1)
     OpenAI-compatible /v1/audio/speech endpoint.
     Models fetched dynamically from /v1/models.

  2. Edge TTS  (free, Microsoft neural voices — used as fallback)
"""

import asyncio
import os
import re
import subprocess

from openai import OpenAI
import edge_tts

SPEECH_BASE_URL = "https://speech.ai.unturf.com/v1"

# ── Edge TTS voice options (fallback) ─────────────────────────────────────────
EDGE_VOICES = {
    "Ryan — British Male (recommended)": "en-GB-RyanNeural",
    "Thomas — British Male":             "en-GB-ThomasNeural",
    "Christopher — US Male":             "en-US-ChristopherNeural",
    "Eric — US Male":                    "en-US-EricNeural",
    "Guy — US Male":                     "en-US-GuyNeural",
    "William — Australian Male":         "en-AU-WilliamNeural",
    "Sonia — British Female":            "en-GB-SoniaNeural",
    "Aria — US Female":                  "en-US-AriaNeural",
}

RATES = {
    "Normal":        "+0%",
    "Slightly slow": "-10%",
    "Slow (eerie)":  "-20%",
    "Very slow":     "-30%",
}


# ── Unturf Speech API ──────────────────────────────────────────────────────────

def fetch_speech_models(api_key: str = "", base_url: str = SPEECH_BASE_URL) -> list[str]:
    """
    Return list of model IDs available on the speech endpoint.
    Returns [] if the endpoint is unreachable.
    """
    try:
        client = OpenAI(base_url=base_url, api_key=api_key or "no-key", timeout=8)
        models = client.models.list()
        return [m.id for m in models.data]
    except Exception:
        return []


def generate_narration_unturf(
    text:        str,
    output_path: str,
    api_key:     str,
    model:       str,
    voice:       str,
    base_url:    str = SPEECH_BASE_URL,
    log=print,
) -> str:
    """Generate TTS using the Unturf Speech API. Returns output_path."""
    client = OpenAI(base_url=base_url, api_key=api_key or "no-key", timeout=120)
    log(f"  TTS (Unturf)  model={model!r}  voice={voice!r}")
    response = client.audio.speech.create(
        model=model,
        input=text,
        voice=voice,
        response_format="mp3",
    )
    with open(output_path, "wb") as f:
        for chunk in response.iter_bytes(chunk_size=4096):
            f.write(chunk)
    return output_path


# ── Edge TTS (fallback) ────────────────────────────────────────────────────────

async def _edge_synthesize(text: str, voice: str, rate: str, output_path: str) -> None:
    communicate = edge_tts.Communicate(text, voice, rate=rate)
    await communicate.save(output_path)


def generate_narration_edge(
    text:        str,
    output_path: str,
    voice:       str = "en-GB-RyanNeural",
    rate:        str = "-20%",
    log=print,
) -> str:
    """Generate TTS using Edge TTS (free, no API key). Returns output_path."""
    log(f"  TTS (Edge)  voice={voice!r}  rate={rate}")
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        loop.run_until_complete(_edge_synthesize(text, voice, rate, output_path))
    finally:
        loop.close()
    return output_path


# ── Unified entry point ────────────────────────────────────────────────────────

def generate_narration(
    text:          str,
    output_path:   str,
    provider:      str  = "edge",      # "unturf" or "edge"
    api_key:       str  = "",
    model:         str  = "",          # for unturf provider
    voice:         str  = "en-GB-RyanNeural",
    rate:          str  = "-20%",      # for edge provider
    base_url:      str  = SPEECH_BASE_URL,
    log=print,
) -> str:
    """
    Generate TTS narration. Returns output_path.
    Falls back to Edge TTS if the Unturf endpoint fails.
    """
    if provider == "unturf" and model:
        try:
            return generate_narration_unturf(text, output_path, api_key, model, voice, base_url, log)
        except Exception as e:
            log(f"  Unturf TTS failed ({e}), falling back to Edge TTS...")

    return generate_narration_edge(text, output_path, voice, rate, log)


# ── Duration helper ────────────────────────────────────────────────────────────

def get_audio_duration(ffmpeg_exe: str, audio_path: str) -> float:
    """Return duration of an audio file in seconds (uses ffmpeg, no ffprobe needed)."""
    result = subprocess.run(
        [ffmpeg_exe, "-i", audio_path],
        capture_output=True, encoding="utf-8", errors="replace"
    )
    m = re.search(r"Duration:\s*(\d+):(\d+):(\d+\.\d+)", result.stderr)
    if not m:
        raise RuntimeError(f"Could not determine duration of {audio_path}")
    h, mn, s = int(m.group(1)), int(m.group(2)), float(m.group(3))
    return h * 3600 + mn * 60 + s
