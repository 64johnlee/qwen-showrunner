"""The showrunner agent — orchestrates premise -> finished vertical episode.

Stages, per the AI Showrunner track: scriptwriting -> shot video (Wan) + voice
(TTS) -> post-production (subtitle burn + concat). Every step emits an event via
the optional `on_event` callback so a live dashboard (or the CLI) can narrate it.
"""
from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path
from typing import Callable

from . import assembler, config, script_writer, veo_client
from . import qwen_client as qc

Event = Callable[[str, dict], None]


def _emit(on_event: Event | None, stage: str, **data) -> None:
    if on_event:
        on_event(stage, data)


def _safe_prompt(shot_prompt: str) -> str:
    """Rewrite a shot prompt that tripped the video model's safety filter."""
    try:
        out = qc.chat(
            "This text-to-video prompt was blocked by an automated safety filter, "
            "most likely over photoreal people. Rewrite it as a safe cinematic shot "
            "that keeps the same story beat: show people only from far away, from "
            "behind, or in silhouette — or replace them with an evocative detail of "
            "the empty scene. Keep it under 60 words, same language as the input. "
            f"Return ONLY the rewritten prompt.\n\nPROMPT: {shot_prompt}")
        return (out or "").strip() or shot_prompt
    except Exception:
        return shot_prompt


def _rerender_shot(shot_prompt: str, video_path: Path,
                   cast_path: Path | None = None,
                   cast_url: str | None = None) -> None:
    """Fallback ladder for one failed shot: safe-rewritten Veo (keeping the
    cast reference), then the wan reference chain, then the plain wan chain."""
    try:
        veo_client.await_video(
            veo_client.submit_video(_safe_prompt(shot_prompt),
                                    reference_path=cast_path), video_path)
        return
    except veo_client.VeoError:
        pass
    if cast_url:
        try:
            qc.await_video(qc.submit_video_ref_wan(shot_prompt, cast_url),
                           video_path)
            return
        except qc.QwenError:
            pass
    # last resort: whatever free wan seconds remain (no face lock)
    qc.await_video(qc.submit_video_wan(shot_prompt, size=config.VIDEO_SIZE),
                   video_path)


def _slug(text: str) -> str:
    base = re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")[:40]
    if base:
        return base
    # non-ASCII titles (e.g. 中文) strip to nothing — a stable hash keeps
    # each episode in its own directory instead of overwriting "episode/"
    return f"episode-{hashlib.md5(text.encode('utf-8')).hexdigest()[:8]}"


def produce_episode(premise: str, language: str = "en",
                    num_scenes: int = config.DEFAULT_SHOTS,
                    out_root: Path | None = None, fast: bool = False,
                    subtitle_lang: str = "en", on_event: Event | None = None) -> dict:
    """Run the full pipeline and return a result dict with the episode path."""
    out_root = Path(out_root or "output")
    video_model = config.MODELS["video_fast"] if fast else config.MODELS["video"]

    # 1) SCRIPT ------------------------------------------------------------
    _emit(on_event, "script_start", premise=premise, language=language, shots=num_scenes)
    script = script_writer.write_script(premise, language, num_scenes, subtitle_lang)
    base = _slug(script["title"])
    ep_dir = out_root / base
    serial = 1
    while True:
        try:
            ep_dir.mkdir(parents=True, exist_ok=False)
            break
        except FileExistsError:
            # never reuse a dir — concurrent or repeated runs landing on the
            # same title would clobber each other's shots mid-production
            serial += 1
            ep_dir = out_root / f"{base}-{serial}"
    (ep_dir / "script.json").write_text(
        json.dumps(script, ensure_ascii=False, indent=2), encoding="utf-8")
    _emit(on_event, "script_done", title=script["title"],
          logline=script.get("logline", ""),
          characters=script.get("characters", []),
          scenes=[{"id": s["id"], "speaker": s["speaker"], "line": s["line"],
                   "subtitle": s["subtitle"]} for s in script["scenes"]])

    # 2) PRODUCE: submit every Wan shot up-front so they render in parallel,
    #    then finish each scene (await video -> voice -> cut) in order ------
    # CAST stage: lock the protagonist's face — generate one cast photo from
    # protagonist_anchor and render every shot with it as a reference image.
    cast_path: Path | None = None
    cast_url: str | None = None
    anchor = script.get("protagonist_anchor", "")
    if config.CAST_MODE and anchor and config.VIDEO_BACKEND != "qwen":
        try:
            cast_path = ep_dir / "cast.png"
            _, cast_url = qc.generate_image(
                f"电影定妆照：{anchor}。正面半身，写实风格，中性表情，简洁背景",
                cast_path)
            _emit(on_event, "cast_done", file=str(cast_path))
        except Exception as exc:   # casting is an enhancement, not a hard dep
            cast_path = cast_url = None
            _emit(on_event, "cast_failed", reason=str(exc)[:120])

    video_tasks: dict[int, str] = {}
    for scene in script["scenes"]:
        if cast_path is not None:
            video_tasks[scene["id"]] = veo_client.submit_video(
                scene["shot_prompt"], reference_path=cast_path)
        else:
            video_tasks[scene["id"]] = qc.submit_video(
                scene["shot_prompt"], size=config.VIDEO_SIZE, model=video_model)
        _emit(on_event, "video_submitted", id=scene["id"],
              total=len(script["scenes"]))

    clips: list[Path] = []
    for scene in script["scenes"]:
        sid = scene["id"]
        _emit(on_event, "scene_start", id=sid, total=len(script["scenes"]),
              shot=scene["shot_prompt"], line=scene["line"])

        video_path = ep_dir / f"scene{sid}.mp4"
        try:
            qc.await_video(video_tasks[sid], video_path)
        except (qc.QwenError, veo_client.VeoError) as exc:
            # a shot failed (wan queue timeout, Veo safety filter, …) —
            # re-render just this shot instead of killing the episode
            if config.VIDEO_BACKEND == "qwen":
                raise
            _emit(on_event, "video_retry", id=sid, reason=str(exc)[:120])
            _rerender_shot(scene["shot_prompt"], video_path,
                           cast_path=cast_path, cast_url=cast_url)
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
