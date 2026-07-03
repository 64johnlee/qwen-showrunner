"""Thin client over Qwen Cloud (DashScope-intl) for the four Showrunner modalities.

- chat()              OpenAI-compatible chat (scriptwriting / director reasoning)
- generate_image()    async text2image (storyboard frames)  -> saved file + url
- generate_video()    async Wan text2video (shots)          -> saved file + url
- synthesize_speech() sync qwen3-tts-flash (voices)         -> saved file

Async jobs are submitted with the X-DashScope-Async header, then polled on
/tasks/{id}. TTS must be called synchronously (async is rejected for this key).
"""
from __future__ import annotations

import time
from pathlib import Path

import requests

from . import config


class QwenError(RuntimeError):
    """Raised when a Qwen Cloud call fails or a job does not succeed."""


def _headers(async_mode: bool = False) -> dict[str, str]:
    h = {
        "Authorization": f"Bearer {config.require_key()}",
        "Content-Type": "application/json",
    }
    if async_mode:
        h["X-DashScope-Async"] = "enable"
    return h


# --------------------------------------------------------------------------- #
# Chat (OpenAI-compatible)
# --------------------------------------------------------------------------- #
def chat(prompt: str, system: str | None = None, model: str | None = None,
         temperature: float = 0.8, timeout: int = 90) -> str:
    """Return the assistant text for a single-turn prompt."""
    messages = []
    if system:
        messages.append({"role": "system", "content": system})
    messages.append({"role": "user", "content": prompt})

    resp = requests.post(
        f"{config.COMPAT_BASE}/chat/completions",
        headers=_headers(),
        json={"model": model or config.MODELS["script"],
              "messages": messages, "temperature": temperature},
        timeout=timeout,
    )
    if resp.status_code != 200:
        raise QwenError(f"chat HTTP {resp.status_code}: {resp.text[:300]}")
    return resp.json()["choices"][0]["message"]["content"].strip()


# --------------------------------------------------------------------------- #
# Async job helpers (image + video)
# --------------------------------------------------------------------------- #
def _submit_async(path: str, model: str, inp: dict, params: dict) -> str:
    resp = requests.post(
        f"{config.NATIVE_BASE}/{path}",
        headers=_headers(async_mode=True),
        json={"model": model, "input": inp, "parameters": params},
        timeout=60,
    )
    data = resp.json()
    task_id = data.get("output", {}).get("task_id")
    if not task_id:
        raise QwenError(f"submit failed ({model}): {data.get('code')} {data.get('message', resp.text[:300])}")
    return task_id


def _poll(task_id: str) -> dict:
    deadline = time.time() + config.POLL_TIMEOUT_S
    while time.time() < deadline:
        resp = requests.get(
            f"{config.NATIVE_BASE}/tasks/{task_id}",
            headers=_headers(), timeout=60,
        )
        out = resp.json().get("output", {})
        status = out.get("task_status")
        if status == "SUCCEEDED":
            return out
        if status in ("FAILED", "CANCELED", "UNKNOWN"):
            raise QwenError(f"task {task_id} {status}: {out.get('message', out)}")
        time.sleep(config.POLL_INTERVAL_S)
    raise QwenError(f"task {task_id} timed out after {config.POLL_TIMEOUT_S}s")


def _download(url: str, dest: Path) -> Path:
    dest.parent.mkdir(parents=True, exist_ok=True)
    with requests.get(url, stream=True, timeout=180) as r:
        r.raise_for_status()
        with open(dest, "wb") as f:
            for chunk in r.iter_content(chunk_size=8192):
                f.write(chunk)
    return dest


# --------------------------------------------------------------------------- #
# Image (storyboard frames)
# --------------------------------------------------------------------------- #
def generate_image(prompt: str, dest: Path, size: str | None = None,
                   model: str | None = None) -> tuple[Path, str]:
    """Generate one storyboard frame; save it to `dest`. Returns (path, url)."""
    task_id = _submit_async(
        "services/aigc/text2image/image-synthesis",
        model or config.MODELS["image"],
        {"prompt": prompt},
        {"size": size or config.IMAGE_SIZE, "n": 1},
    )
    out = _poll(task_id)
    results = out.get("results") or []
    if not results or "url" not in results[0]:
        raise QwenError(f"image job returned no url: {out}")
    url = results[0]["url"]
    return _download(url, dest), url


# --------------------------------------------------------------------------- #
# Video (Wan shots)
# --------------------------------------------------------------------------- #
def generate_video(prompt: str, dest: Path, size: str | None = None,
                   model: str | None = None) -> tuple[Path, str]:
    """Generate one video shot from a text prompt; save to `dest`. Returns (path, url)."""
    task_id = _submit_async(
        "services/aigc/video-generation/video-synthesis",
        model or config.MODELS["video"],
        {"prompt": prompt},
        {"size": size or config.VIDEO_SIZE},
    )
    out = _poll(task_id)
    url = out.get("video_url") or out.get("results", {}).get("video_url")
    if not url:
        raise QwenError(f"video job returned no url: {out}")
    return _download(url, dest), url


# --------------------------------------------------------------------------- #
# Speech (character voices) — SYNC only
# --------------------------------------------------------------------------- #
def synthesize_speech(text: str, dest: Path, voice: str | None = None,
                      model: str | None = None, timeout: int = 90) -> Path:
    """Synthesize speech synchronously; save the audio to `dest`. Returns path."""
    resp = requests.post(
        f"{config.NATIVE_BASE}/services/aigc/multimodal-generation/generation",
        headers=_headers(),  # NO async header — this key rejects async TTS
        json={"model": model or config.MODELS["tts"],
              "input": {"text": text, "voice": voice or config.TTS_VOICE}},
        timeout=timeout,
    )
    data = resp.json()
    audio = data.get("output", {}).get("audio", {})
    url = audio.get("url")
    if not url:
        raise QwenError(f"tts returned no audio url: {data.get('code')} "
                        f"{data.get('message', str(data)[:300])}")
    return _download(url, dest)
