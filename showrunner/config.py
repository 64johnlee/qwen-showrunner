"""Central config for the Qwen Showrunner — endpoints, model IDs, and key loading.

All model IDs below were probed live against the card-free Qwen Cloud free-tier
key (2026-07-02) on the dashscope-intl region. Override any of them via env vars.
"""
from __future__ import annotations

import os
from pathlib import Path

# --- minimal .env loader (no python-dotenv dependency) ---
_ENV_PATH = Path(__file__).resolve().parent.parent / ".env"


def _load_env() -> None:
    if not _ENV_PATH.exists():
        return
    for line in _ENV_PATH.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        os.environ.setdefault(key.strip(), value.strip())


_load_env()

# --- credentials ---
API_KEY: str | None = os.getenv("DASHSCOPE_API_KEY")

# --- endpoints (Singapore / international region) ---
# OpenAI-compatible base for chat; native DashScope base for image/video/tts.
COMPAT_BASE: str = os.getenv(
    "DASHSCOPE_BASE_URL", "https://dashscope-intl.aliyuncs.com/compatible-mode/v1"
)
NATIVE_BASE: str = "https://dashscope-intl.aliyuncs.com/api/v1"

# --- confirmed model IDs (each verified usable on the free-tier key) ---
MODELS = {
    "script": os.getenv("SHOWRUNNER_LLM", "qwen-max"),          # scriptwriting / director LLM
    "image": os.getenv("SHOWRUNNER_IMAGE", "wan2.2-t2i-flash"),  # storyboard frames (fast)
    "image_hq": "wan2.2-t2i-plus",                               # higher-quality storyboard
    "video": os.getenv("SHOWRUNNER_VIDEO", "wan2.7-t2v"),        # shot video (quality)
    "video_fast": "wan2.1-t2v-turbo",                            # shot video (fast)
    "tts": os.getenv("SHOWRUNNER_TTS", "qwen3-tts-flash"),       # character voices (sync only)
}

# Free video allowance is tiny (~10s ≈ 2 clips per model, probed 2026-07-04)
# and metered per model — so video submits fall through this chain as models
# exhaust (AllocationQuota.FreeTierOnly). probe_t2v.py shows live status.
VIDEO_FALLBACKS = [s.strip() for s in os.getenv(
    "SHOWRUNNER_VIDEO_FALLBACKS",
    "wan2.7-t2v,wan2.6-t2v,wan2.5-t2v-preview,wan2.1-t2v-turbo,happyhorse-1.1-t2v,wan2.2-t2v-plus",
).split(",") if s.strip()]

# --- video backend ---
# "auto": drain the free Qwen chain first, then fail over to Veo on GCP
# free-trial credits. "qwen" / "veo" force a single backend.
VIDEO_BACKEND = os.getenv("SHOWRUNNER_VIDEO_BACKEND", "auto")
VEO_MODEL = os.getenv("SHOWRUNNER_VEO_MODEL", "veo-3.0-fast-generate-001")
GCP_PROJECT = os.getenv("GCP_PROJECT", "disco-module-487411-m0")
GCP_REGION = os.getenv("GCP_REGION", "us-central1")
VEO_DURATION_S = int(os.getenv("SHOWRUNNER_VEO_DURATION", "6"))   # veo-3 accepts 4/6/8

# --- generation defaults ---
# Wan free-tier clips are fixed ~5s (duration customization rejected, probed
# 2026-07-03), so episode length is controlled by shot count: ~10 shots ≈ 1 min.
DEFAULT_SHOTS = int(os.getenv("SHOWRUNNER_SHOTS", "10"))
VIDEO_SIZE = os.getenv("SHOWRUNNER_VIDEO_SIZE", "480*832")   # 9:16 vertical short-drama (Wan-confirmed)
IMAGE_SIZE = os.getenv("SHOWRUNNER_IMAGE_SIZE", "720*1280")  # 9:16 storyboard
TTS_VOICE = os.getenv("SHOWRUNNER_TTS_VOICE", "Cherry")

# polling for async jobs (image/video)
POLL_INTERVAL_S = 5
POLL_TIMEOUT_S = 420  # video can take a few minutes


def require_key() -> str:
    """Fail fast with a clear message if the key is missing."""
    if not API_KEY:
        raise RuntimeError(
            "DASHSCOPE_API_KEY not set. Copy the free-tier key into "
            f"{_ENV_PATH} (DASHSCOPE_API_KEY=sk-...)."
        )
    return API_KEY
