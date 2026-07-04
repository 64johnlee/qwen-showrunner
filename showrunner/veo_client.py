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


def _ref_b64(path: Path, max_side: int = 512) -> str:
    """Downscale the cast photo to a small JPEG — a full-res PNG payload made
    submit requests time out at the HTTP layer."""
    import io

    from PIL import Image

    img = Image.open(path).convert("RGB")
    img.thumbnail((max_side, max_side))
    buf = io.BytesIO()
    img.save(buf, "JPEG", quality=85)
    return base64.b64encode(buf.getvalue()).decode()


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


def _host(location: str) -> str:
    return ("aiplatform.googleapis.com" if location == "global"
            else f"{location}-aiplatform.googleapis.com")


def _model_base(model: str | None = None) -> str:
    loc = config.VEO_LOCATION
    return (
        f"https://{_host(loc)}/v1/projects/"
        f"{config.GCP_PROJECT}/locations/{loc}"
        f"/publishers/google/models/{model or config.VEO_MODEL}"
    )


def _post(url: str, body: dict) -> dict:
    last = ""
    for attempt in range(8):
        resp = requests.post(
            url,
            headers={"Authorization": f"Bearer {_access_token(force=attempt > 0)}",
                     "Content-Type": "application/json"},
            json=body, timeout=60,
        )
        if resp.status_code == 401 and attempt == 0:
            continue   # stale token — refresh and retry
        if resp.status_code == 429:
            # concurrent long-running-request quota — a 10-shot parallel burst
            # can exceed it; back off and let in-flight renders drain
            last = resp.text[:200]
            time.sleep(30)
            continue
        data = resp.json()
        if resp.status_code >= 300:
            raise VeoError(f"Veo API {resp.status_code}: {str(data)[:300]}")
        return data
    raise VeoError(f"Veo API rate-limited after {8 * 30}s of backoff: {last}")


def submit_video(prompt: str, reference_path: Path | None = None) -> str:
    """Submit one Veo shot; returns the long-running operation name.

    With `reference_path`, the cast photo is attached as a Veo 3.1 reference
    image ("asset") so the protagonist keeps the same face in every shot.
    """
    instance: dict = {"prompt": prompt}
    model = config.VEO_MODEL
    duration = config.VEO_DURATION_S
    if reference_path is not None:
        model = config.VEO_REF_MODEL
        duration = 8   # reference_to_video only supports 8s (API-enforced)
        instance["referenceImages"] = [{
            "image": {
                "bytesBase64Encoded": _ref_b64(reference_path),
                "mimeType": "image/jpeg",
            },
            "referenceType": "asset",
        }]
    data = _post(f"{_model_base(model)}:predictLongRunning", {
        "instances": [instance],
        "parameters": {
            "aspectRatio": "9:16",
            "durationSeconds": duration,
            "sampleCount": 1,
        },
    })
    name = data.get("name")
    if not name:
        raise VeoError(f"Veo submit returned no operation name: {str(data)[:200]}")
    return name


def await_video(operation_name: str, dest: Path) -> tuple[Path, str]:
    """Poll a Veo operation and save the resulting mp4 to `dest`."""
    # fetchPredictOperation must be called on the model AND location that own
    # the operation — both are encoded in the operation name's prefix.
    model_path = operation_name.split("/operations/")[0]
    op_location = operation_name.split("/locations/")[1].split("/")[0]
    fetch_url = (f"https://{_host(op_location)}/v1/"
                 f"{model_path}:fetchPredictOperation")
    deadline = time.time() + config.POLL_TIMEOUT_S
    while time.time() < deadline:
        data = _post(fetch_url, {"operationName": operation_name})
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
