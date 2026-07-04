"""Veo (Vertex AI) video backend — renders shots on GCP free-trial credits.

Used when the Qwen free video allowances run dry (VIDEO_BACKEND=auto) or when
forced with VIDEO_BACKEND=veo. Native 9:16 output at 720x1280, ~30s per shot.

Auth: `gcloud auth print-access-token` — works with plain gcloud CLI login,
no ADC file needed. Tokens are cached ~30 min and refreshed on demand.
"""
from __future__ import annotations

import base64
import subprocess
import time
from pathlib import Path

import requests

from . import config

_TOKEN: dict = {"value": None, "ts": 0.0}


class VeoError(RuntimeError):
    pass


def _access_token(force: bool = False) -> str:
    if force or not _TOKEN["value"] or time.time() - _TOKEN["ts"] > 1800:
        proc = subprocess.run(
            ["gcloud", "auth", "print-access-token"],
            capture_output=True, text=True, timeout=30,
        )
        if proc.returncode != 0:
            raise VeoError(f"gcloud auth print-access-token failed: {proc.stderr[:200]}")
        _TOKEN["value"] = proc.stdout.strip()
        _TOKEN["ts"] = time.time()
    return _TOKEN["value"]


def _model_base() -> str:
    return (
        f"https://{config.GCP_REGION}-aiplatform.googleapis.com/v1/projects/"
        f"{config.GCP_PROJECT}/locations/{config.GCP_REGION}"
        f"/publishers/google/models/{config.VEO_MODEL}"
    )


def _post(url: str, body: dict) -> dict:
    for attempt in (1, 2):
        resp = requests.post(
            url,
            headers={"Authorization": f"Bearer {_access_token(force=attempt == 2)}",
                     "Content-Type": "application/json"},
            json=body, timeout=60,
        )
        if resp.status_code == 401 and attempt == 1:
            continue   # stale token — refresh and retry once
        data = resp.json()
        if resp.status_code >= 300:
            raise VeoError(f"Veo API {resp.status_code}: {str(data)[:300]}")
        return data
    raise VeoError("unreachable")


def submit_video(prompt: str) -> str:
    """Submit one Veo shot; returns the long-running operation name."""
    data = _post(f"{_model_base()}:predictLongRunning", {
        "instances": [{"prompt": prompt}],
        "parameters": {
            "aspectRatio": "9:16",
            "durationSeconds": config.VEO_DURATION_S,
            "sampleCount": 1,
        },
    })
    name = data.get("name")
    if not name:
        raise VeoError(f"Veo submit returned no operation name: {str(data)[:200]}")
    return name


def await_video(operation_name: str, dest: Path) -> tuple[Path, str]:
    """Poll a Veo operation and save the resulting mp4 to `dest`."""
    deadline = time.time() + config.POLL_TIMEOUT_S
    while time.time() < deadline:
        data = _post(f"{_model_base()}:fetchPredictOperation",
                     {"operationName": operation_name})
        if data.get("done"):
            if "error" in data:
                raise VeoError(f"Veo render failed: {str(data['error'])[:300]}")
            videos = data.get("response", {}).get("videos") or []
            if not videos:
                rai = data.get("response", {}).get("raiMediaFilteredReasons")
                if rai:
                    raise VeoError(f"safety filter blocked this shot — rephrase it: {str(rai[0])[:160]}")
                raise VeoError(f"Veo returned no videos: {str(data)[:200]}")
            v = videos[0]
            if v.get("bytesBase64Encoded"):
                dest.write_bytes(base64.b64decode(v["bytesBase64Encoded"]))
                return dest, "veo"
            raise VeoError(f"Veo video has no inline bytes: {str(v)[:200]}")
        time.sleep(config.POLL_INTERVAL_S)
    raise VeoError(f"Veo render timed out after {config.POLL_TIMEOUT_S}s")
