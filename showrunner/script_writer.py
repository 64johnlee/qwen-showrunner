"""Scriptwriting stage — premise -> validated structured screenplay via qwen-max.

The screenplay is a strict JSON contract so downstream stages (video, voice,
subtitles) can consume it deterministically. We validate the shape and fail
fast with a clear message rather than trusting the model blindly.
"""
from __future__ import annotations

import json
import re

from . import qwen_client as qc

# qwen3-tts-flash voices to rotate across characters (Cherry confirmed live).
VOICE_POOL = ["Cherry", "Ethan", "Serena", "Chelsie"]

_SYSTEM = (
    "You are an award-winning showrunner for vertical short-form drama (微短剧). "
    "You write tight, high-hook, cliffhanger-driven micro-episodes. "
    "You always answer with a single valid JSON object and nothing else."
)

_TEMPLATE = """\
Create a {num_scenes}-shot vertical short-drama micro-episode from this premise:

PREMISE: {premise}

Spoken language: {language} (write every `line` in this language).
Subtitle language: {subtitle_lang} (write every `subtitle` in this language; if it
differs from the spoken language, make it a faithful, natural translation of the line).

STORY DISCIPLINE — ONE CENTRAL POINT:
First decide the single central moment of this episode (ONE twist, reveal, or
emotional payoff — e.g. "the cleaner everyone humiliated is the majority
shareholder"). In under a minute you can only land ONE point. Every scene must
serve it: shots 1-2 plant the question, the middle shots escalate pressure on
that same question (no side plots, no second twist), and the final two shots
detonate the central moment and hold on its aftermath. If a scene does not
build toward the central moment, replace it with one that does.

NARRATION STYLE — VOICE-OVER, NOT LIP-SYNCED DIALOGUE:
Every `line` is VOICE-OVER narration (first-person inner monologue or a
storyteller's voice), never on-camera speech — generated video cannot lip-sync.
Therefore every `shot_prompt` must be a rich CINEMATIC shot where nobody is
seen talking: favour LONG SHOTS and WIDE establishing shots, tracking/dolly
moves, characters seen from behind, in silhouette, in profile at a distance,
plus occasional close-up inserts of hands/objects/details. Bodies act, faces
react silently — mouths never move as if speaking. Vary the shot grammar
across the episode (wide -> tracking -> insert -> slow push-in).

Return ONLY this JSON object:
{{
  "title": "short punchy title",
  "logline": "one sentence stating the central moment",
  "core_moment": "one sentence: the single point this episode lands",
  "language": "{language}",
  "characters": [
    {{"name": "Name", "voice": "one of {voices}", "persona": "one line"}}
  ],
  "scenes": [
    {{
      "shot_prompt": "vivid CINEMATIC VISUAL description for a text-to-video model: camera move, framing (favour long/wide), subject action, lighting, mood. Nobody visibly talking. No dialogue text here.",
      "speaker": "character name or Narrator",
      "line": "the voice-over line for this shot, in {language}",
      "subtitle": "the on-screen subtitle in {subtitle_lang} (translation of line if languages differ)"
    }}
  ]
}}
Exactly {num_scenes} scenes. Keep each `line` under 18 words so it fits a short shot."""


def _extract_json(text: str) -> dict:
    """Pull the JSON object out of a model response (tolerates code fences)."""
    fenced = re.search(r"```(?:json)?\s*(\{.*\})\s*```", text, re.DOTALL)
    raw = fenced.group(1) if fenced else text[text.find("{"): text.rfind("}") + 1]
    try:
        return json.loads(raw)
    except json.JSONDecodeError as exc:
        raise ValueError(f"script writer returned non-JSON: {exc}\n---\n{text[:500]}")


def _validate(script: dict, num_scenes: int) -> dict:
    for field in ("title", "language", "characters", "scenes"):
        if field not in script:
            raise ValueError(f"script missing required field '{field}'")
    scenes = script["scenes"]
    if not isinstance(scenes, list) or not scenes:
        raise ValueError("script has no scenes")
    if len(scenes) > num_scenes:
        # model over-delivered — trim so we don't burn quota on extra shots
        scenes = scenes[:num_scenes]
        script["scenes"] = scenes

    for i, scene in enumerate(scenes, 1):
        for field in ("shot_prompt", "speaker", "line"):
            if not scene.get(field):
                raise ValueError(f"scene {i} missing '{field}'")
        scene.setdefault("subtitle", scene["line"])
        scene["id"] = i
    # normalise any voice the model invented outside the pool
    for c in script["characters"]:
        if c.get("voice") not in VOICE_POOL:
            c["voice"] = VOICE_POOL[0]
    return script


def write_script(premise: str, language: str = "en", num_scenes: int = 3,
                 subtitle_lang: str = "en") -> dict:
    """Generate and validate a screenplay dict from a one-line premise."""
    prompt = _TEMPLATE.format(
        premise=premise, language=language, num_scenes=num_scenes,
        subtitle_lang=subtitle_lang, voices=VOICE_POOL,
    )
    raw = qc.chat(prompt, system=_SYSTEM, temperature=0.9)
    return _validate(_extract_json(raw), num_scenes)


def voice_for(script: dict, speaker: str) -> str:
    """Resolve a character name to a TTS voice, defaulting sensibly."""
    for c in script.get("characters", []):
        if c.get("name", "").lower() == speaker.lower():
            return c.get("voice", VOICE_POOL[0])
    return VOICE_POOL[0]
