"""
script_gen.py
-------------
Uses the Hermes LLM API (OpenAI-compatible) to generate a horror
narration script and per-scene image prompts.

Endpoint : https://hermes.ai.unturf.com/v1
Model    : adamo1139/Hermes-3-Llama-3.1-8B-FP8-Dynamic
"""

import json
import re
from openai import OpenAI

GROQ_BASE_URL = "https://api.groq.com/openai/v1"
GROQ_MODEL    = "llama-3.3-70b-versatile"


def generate_horror_script(
    topic:      str,
    num_scenes: int,
    api_key:    str,
    base_url:   str = GROQ_BASE_URL,
    model:      str = GROQ_MODEL,
) -> dict:
    """
    Returns:
    {
        "title":         str,
        "narration":     str,          # full voice-over (~100-180 words)
        "image_prompts": [str, ...]    # one DALL-E prompt per scene
    }
    """
    client = OpenAI(base_url=base_url, api_key=api_key or "no-key")

    prompt = f"""You create content for horror short-form vertical videos (Instagram Reels / TikTok style, ~60-90 seconds).
Format: AI-generated cinematic still images with slow zoom/pan while a creepy narrator reads a short story.

Topic: {topic}
Number of scenes: {num_scenes}

Return ONLY valid JSON (no markdown, no code fences) in this exact structure:
{{
  "title": "5-7 word catchy horror title",
  "narration": "The full narration text. 100-180 words. Written for voice-over — short dramatic sentences, present tense, second-person or first-person perspective. Build dread slowly. No chapter markers or scene labels — continuous prose only.",
  "image_prompts": [
    "Detailed DALL-E 3 image prompt for scene 1",
    "Detailed DALL-E 3 image prompt for scene 2"
  ]
}}

Image prompt rules:
- Photorealistic, cinematic photography, VERTICAL/PORTRAIT composition (9:16)
- Dark, atmospheric, unsettling — not gory
- Specify shot type, lighting, time of day, mood
- Subjects: abandoned structures, dark forests, fog, dim corridors, silhouettes, underwater, caves, night
- End every prompt with: "cinematic 35mm film grain, dark atmospheric lighting, ultra-detailed, 4K, portrait orientation, no text, no watermarks"

Return ONLY the JSON object, nothing else."""

    response = client.chat.completions.create(
        model=model,
        messages=[{"role": "user", "content": prompt}],
        max_tokens=2500,
        temperature=0.85,
    )

    raw = response.choices[0].message.content.strip()

    # Strip markdown code fences if present
    raw = re.sub(r"^```(?:json)?\s*", "", raw)
    raw = re.sub(r"\s*```$", "", raw)

    return json.loads(raw)
