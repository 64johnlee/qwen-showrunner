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
_SUBMIT_RETRIES = 3


def _submit_async(path: str, model: str, inp: dict, params: dict) -> str:
    last_exc: Exception | None = None
    for attempt in range(_SUBMIT_RETRIES):
        try:
            resp = requests.post(
                f"{config.NATIVE_BASE}/{path}",
                headers=_headers(async_mode=True),
                json={"model": model, "input": inp, "parameters": params},
                timeout=60,
            )
            data = resp.json()
        except (requests.RequestException, ValueError) as exc:
            # transient network/JSON hiccup — retry rather than abort a
            # multi-minute episode over one dropped submit call
            last_exc = exc
            time.sleep(2 * (attempt + 1))
            continue
        task_id = data.get("output", {}).get("task_id")
        if task_id:
            return task_id
        code = str(data.get("code") or "")
        if "Throttling" in code and attempt < _SUBMIT_RETRIES - 1:
            # rate-limited (parallel shot submits) — back off and retry
            last_exc = QwenError(f"{code}: {data.get('message')}")
            time.sleep(10 * (attempt + 1))
            continue
        raise QwenError(f"submit failed ({model}): {code} {data.get('message', resp.text[:300])}")
    raise QwenError(f"submit failed ({model}) after {_SUBMIT_RETRIES} attempts: {last_exc}")


def _poll(task_id: str) -> dict:
    deadline = time.time() + config.POLL_TIMEOUT_S
    last_error = ""
    while time.time() < deadline:
        try:
            resp = requests.get(
                f"{config.NATIVE_BASE}/tasks/{task_id}",
                headers=_headers(), timeout=60,
            )
            out = resp.json().get("output", {})
        except (requests.RequestException, ValueError) as exc:
            # transient network/JSON hiccup — keep polling until the deadline
            last_error = str(exc)
            time.sleep(config.POLL_INTERVAL_S)
            continue
        status = out.get("task_status")
        if status == "SUCCEEDED":
            return out
        if status in ("FAILED", "CANCELED", "UNKNOWN"):
            raise QwenError(f"task {task_id} {status}: {out.get('message', out)}")
        time.sleep(config.POLL_INTERVAL_S)
    detail = f" (last error: {last_error})" if last_error else ""
    raise QwenError(f"task {task_id} timed out after {config.POLL_TIMEOUT_S}s{detail}")


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
def submit_video(prompt: str, size: str | None = None,
                 model: str | None = None) -> str:
    """Submit one Wan text-to-video job; returns its task_id immediately.

    Submitting every shot up-front lets Wan render them in parallel — a
    10-shot episode takes roughly one shot's wall-clock time, not ten.
    """
    if config.VIDEO_BACKEND == "veo":
        from . import veo_client
        return veo_client.submit_video(prompt)
    chain = [model or config.MODELS["video"]]
    for m in config.VIDEO_FALLBACKS:
        if m not in chain:
            chain.append(m)
    last: QwenError | None = None
    for m in chain:
        # only the wan2.1/2.2 generation accepts WxH sizes like 480*832; newer
        # models reject it at render time ("size is not supported") — let them
        # use their defaults, the assembler normalizes to 9:16 anyway.
        params = {}
        if m.startswith(("wan2.1", "wan2.2", "wanx2.0")):
            params["size"] = size or config.VIDEO_SIZE
        try:
            return _submit_async(
                "services/aigc/video-generation/video-synthesis",
                m,
                {"prompt": prompt},
                params,
            )
        except QwenError as exc:
            # this model's free video seconds are gone — fall through to the next
            if "AllocationQuota" in str(exc):
                last = exc
                continue
            raise
    if config.VIDEO_BACKEND == "auto":
        # Qwen free pool is dry — fail over to Veo on GCP credits
        from . import veo_client
        return veo_client.submit_video(prompt)
    raise QwenError(
        "every video model in the fallback chain is out of free quota — "
        f"redeem the hackathon coupon or wait for a reset. Last: {last}"
    )


def await_video(task_id: str, dest: Path) -> tuple[Path, str]:
    """Wait for a submitted video job and save the result to `dest`."""
    if task_id.startswith("projects/"):   # Veo long-running operation name
        from . import veo_client
        return veo_client.await_video(task_id, dest)
    out = _poll(task_id)
    results = out.get("results")
    url = out.get("video_url") or (
        results.get("video_url") if isinstance(results, dict) else None)
    if not url:
        raise QwenError(f"video job returned no url: {out}")
    return _download(url, dest), url


def generate_video(prompt: str, dest: Path, size: str | None = None,
                   model: str | None = None) -> tuple[Path, str]:
    """Generate one video shot from a text prompt; save to `dest`. Returns (path, url)."""
    return await_video(submit_video(prompt, size, model), dest)


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
