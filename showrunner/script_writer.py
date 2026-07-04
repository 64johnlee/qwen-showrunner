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

STORY DISCIPLINE — ONE CONTINUOUS MOMENT, ONE CENTRAL POINT:
The whole episode covers ONE continuous moment of story time — roughly ten
seconds of real events in a SINGLE location, unfolded in fine detail beat by
beat, like one film sequence cut into consecutive shots. No time jumps, no
location changes, no flashbacks, no montage. Decide the single central point
(ONE twist, reveal, or emotional payoff) and make the beats march straight at
it: the first shots plant the question, each following shot tightens the same
screw a little more, and the final two shots detonate the point and hold on
its aftermath. If a beat does not push toward the central point, cut it.

CHARACTER & SCENE LOCK (the video model has NO memory between shots):
Create exactly ONE protagonist. Write one reusable sentence that pins their
look — age, build, hair, exact clothing, one distinctive prop (e.g. "a
50-year-old woman in a worn blue cleaner's uniform, grey-streaked bun, faded
red brooch") — put it in `protagonist_anchor`. Pin the place the same way in
`location_anchor`. EVERY shot_prompt MUST begin by repeating BOTH anchors
WORD-FOR-WORD, then add only that shot's new beat. Other people stay distant,
from behind, or blurred — never a second recognizable face.

VOICE-OVER — DRAMATIC, NOT LIP-SYNCED:
Every `line` is VOICE-OVER (inner monologue or a storyteller), never
on-camera speech — nobody in frame may be seen talking. Write the VO like a
dramatic trailer narrator: short punchy sentences, rising tension, rhetorical
questions, deliberate repetition ("她擦了十年地。十年。"), a gut-punch on the
final line. Shots favour LONG/WIDE framing, tracking moves, silhouettes,
close-up inserts of hands/objects; bodies act, faces react silently.

Return ONLY this JSON object:
{{
  "title": "short punchy title",
  "logline": "one sentence stating the central moment",
  "core_moment": "one sentence: the single point this episode lands",
  "protagonist_anchor": "one reusable visual-lock sentence for the protagonist",
  "location_anchor": "one reusable visual-lock sentence for the single location",
  "language": "{language}",
  "characters": [
    {{"name": "Name", "voice": "one of {voices}", "persona": "one line"}}
  ],
  "scenes": [
    {{
      "shot_prompt": "MUST start with protagonist_anchor + location_anchor word-for-word, then this beat's camera move, framing (favour long/wide), action, lighting. Nobody visibly talking. No dialogue text.",
      "speaker": "character name or Narrator",
      "line": "the dramatic voice-over line for this shot, in {language}",
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
