"""The showrunner agent — orchestrates premise -> finished vertical episode.

Stages, per the AI Showrunner track: scriptwriting -> shot video (Wan) + voice
(TTS) -> post-production (subtitle burn + concat). Every step emits an event via
the optional `on_event` callback so a live dashboard (or the CLI) can narrate it.
"""
from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Callable

from . import assembler, config, script_writer
from . import qwen_client as qc

Event = Callable[[str, dict], None]


def _emit(on_event: Event | None, stage: str, **data) -> None:
    if on_event:
        on_event(stage, data)


def _slug(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")[:40] or "episode"


def produce_episode(premise: str, language: str = "en", num_scenes: int = 3,
                    out_root: Path | None = None, fast: bool = False,
                    subtitle_lang: str = "en", on_event: Event | None = None) -> dict:
    """Run the full pipeline and return a result dict with the episode path."""
    out_root = Path(out_root or "output")
    video_model = config.MODELS["video_fast"] if fast else config.MODELS["video"]

    # 1) SCRIPT ------------------------------------------------------------
    _emit(on_event, "script_start", premise=premise, language=language, shots=num_scenes)
    script = script_writer.write_script(premise, language, num_scenes, subtitle_lang)
    ep_dir = out_root / _slug(script["title"])
    ep_dir.mkdir(parents=True, exist_ok=True)
    (ep_dir / "script.json").write_text(
        json.dumps(script, ensure_ascii=False, indent=2), encoding="utf-8")
    _emit(on_event, "script_done", title=script["title"],
          logline=script.get("logline", ""),
          characters=script.get("characters", []),
          scenes=[{"id": s["id"], "speaker": s["speaker"], "line": s["line"],
                   "subtitle": s["subtitle"]} for s in script["scenes"]])

    # 2) PRODUCE each scene: video + voice -> assembled clip ---------------
    clips: list[Path] = []
    for scene in script["scenes"]:
        sid = scene["id"]
        _emit(on_event, "scene_start", id=sid, total=len(script["scenes"]),
              shot=scene["shot_prompt"], line=scene["line"])

        video_path = ep_dir / f"scene{sid}.mp4"
        qc.generate_video(scene["shot_prompt"], video_path,
                          size=config.VIDEO_SIZE, model=video_model)
        _emit(on_event, "video_done", id=sid, file=str(video_path))

        voice_path = ep_dir / f"scene{sid}.wav"
        qc.synthesize_speech(scene["line"], voice_path,
                             voice=script_writer.voice_for(script, scene["speaker"]))
        _emit(on_event, "voice_done", id=sid, file=str(voice_path))

        clip = assembler.assemble_scene(
            video_path, voice_path, scene["subtitle"],
            ep_dir / f"clip{sid}.mp4", size=config.VIDEO_SIZE)
        clips.append(clip)
        _emit(on_event, "scene_done", id=sid, file=str(clip))

    # 3) ASSEMBLE final episode -------------------------------------------
    _emit(on_event, "assemble_start", clips=len(clips))
    episode = assembler.concat_scenes(clips, ep_dir / "episode.mp4")
    _emit(on_event, "episode_done", title=script["title"], file=str(episode))

    return {
        "title": script["title"],
        "logline": script.get("logline", ""),
        "language": language,
        "episode": str(episode),
        "dir": str(ep_dir),
        "script": script,
    }
