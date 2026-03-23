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
    "Andrew — US Male (natural)":        "en-US-AndrewNeural",
    "Brian — US Male (storytelling)":    "en-US-BrianNeural",
    "Christopher — US Male (deep)":      "en-US-ChristopherNeural",
    "Guy — US Male (narrator)":          "en-US-GuyNeural",
    "Ryan — British Male":               "en-GB-RyanNeural",
    "Thomas — British Male":             "en-GB-ThomasNeural",
    "William — Australian Male":         "en-AU-WilliamNeural",
    "Aria — US Female":                  "en-US-AriaNeural",
    "Sonia — British Female":            "en-GB-SoniaNeural",
}

RATES = {
    "Natural (recommended)": "-3%",
    "Slightly measured":     "-8%",
    "Slow and deliberate":   "-15%",
}

# Pitch offset applied to all voices — slight lowering gives a darker, more
# cinematic quality without making the voice sound processed or robotic.
PITCHES = {
    "Normal":        "+0Hz",
    "Slightly deep": "-5Hz",
    "Deep":          "-10Hz",
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

async def _edge_synthesize(text: str, voice: str, rate: str, pitch: str, output_path: str) -> None:
    communicate = edge_tts.Communicate(text, voice, rate=rate, pitch=pitch)
    await communicate.save(output_path)


def generate_narration_edge(
    text:        str,
    output_path: str,
    voice:       str = "en-US-AndrewNeural",
    rate:        str = "-3%",
    pitch:       str = "-5Hz",
    log=print,
) -> str:
    """Generate TTS using Edge TTS (free, no API key). Returns output_path."""
    log(f"  TTS (Edge)  voice={voice!r}  rate={rate}  pitch={pitch}")
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        loop.run_until_complete(_edge_synthesize(text, voice, rate, pitch, output_path))
    finally:
        loop.close()
    return output_path


# ── Unified entry point ────────────────────────────────────────────────────────

def generate_narration(
    text:          str,
    output_path:   str,
    provider:      str  = "edge",
    api_key:       str  = "",
    model:         str  = "",
    voice:         str  = "en-US-AndrewNeural",
    rate:          str  = "-3%",
    pitch:         str  = "-5Hz",
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

    return generate_narration_edge(text, output_path, voice, rate, pitch, log)


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
