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

    prompt = f"""You write scripts for horror short-form vertical videos (Instagram Reels / TikTok, ~50-70 seconds).

━━━ STYLE REFERENCE ━━━
Study this real example carefully — every script you write must match this exact tone, structure, and delivery:

"that you can only reach between 3.30 and 3.33 a.m. Before you travel, I must advise you of a few rules.
Rule number one. No matter how lovely they are, do not pick the flowers. If you do, you'll never get rid of them.
Rule number two. If you see a tall man with no face, just keep walking. Whatever you do, don't stop to look at him.
Rule number three. If someone offers you tea, politely decline and keep walking. If they follow you, run. Anything is better than drinking the tea.
And rule number four, the most important of them all. Wear a watch at all times. Time is weird there, and if you don't have a clock on you, time will warp into nothingness and you won't know when to leave.
That's all, safe travels."

━━━ WHAT MAKES THIS WORK ━━━
1. HOOK — Drop in mid-concept. Assume the viewer already knows the premise. Start with the specific detail, not "there is a place."
2. RULES FORMAT — Numbered rules (3–5 rules). Each rule = one short sentence stating the rule, then one sentence explaining the consequence if broken.
3. TONE — Calm. Advisory. Matter-of-fact. Like a knowledgeable friend warning you before a trip. NEVER panicked, dramatic, or over-the-top. Treat supernatural as completely normal.
4. ESCALATION — Rule 1 is mildly strange. Each rule gets more dangerous. The final rule is "the most important of them all."
5. DETAILS — Be specific. Not "late at night" — "3:30 a.m." Not "a strange figure" — "a tall man with no face." Specific details feel real.
6. CONSEQUENCES — Every rule has a clear, understated consequence. "If you do, you'll never get rid of them." Short. Final. No elaboration.
7. SIGN-OFF — End with something casual and ominous. "That's all, safe travels." "Good luck." "You'll be fine, probably." Never dramatic.
8. LENGTH — 100–140 words maximum. Each sentence earns its place.
9. SENTENCE STRUCTURE — Short. Imperative. Punchy. Commands and warnings.
10. SECOND PERSON — Always "you." Never first-person. The viewer IS the one being warned.

━━━ TOPIC & SCENES ━━━
Topic: {topic}
Number of scenes: {num_scenes}

━━━ FORMATS TO USE (rotate between these, pick the best fit for the topic) ━━━
- Rules for visiting [place/entity]
- Things you must never do in [situation]
- Survival guide for [supernatural scenario]
- What to do if you encounter [entity/place]
- Signs that [something is wrong] — and what to do

━━━ OUTPUT FORMAT ━━━
Return ONLY valid JSON, no markdown, no code fences:
{{
  "title": "Short punchy title, 4-6 words, no 'The' at start",
  "narration": "Full narration, 100-140 words, rules format, calm advisory tone, second person, no scene labels",
  "image_prompts": [
    "Scene 1 image prompt",
    "Scene 2 image prompt"
  ]
}}

Image prompt rules:
- Photorealistic, cinematic, VERTICAL/PORTRAIT (9:16 ratio)
- Dark, atmospheric, unsettling — never gory, no gore, no blood
- Liminal spaces, abandoned places, fog, dim corridors, silhouettes, dark forests, night
- Each scene matches the mood of its rule — escalate visual tension across scenes
- End every prompt with: "cinematic 35mm film grain, dark atmospheric lighting, ultra-detailed, portrait orientation, no text, no watermarks"

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
