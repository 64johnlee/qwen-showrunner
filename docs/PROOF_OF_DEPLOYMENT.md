# Proof of Alibaba Cloud Deployment

This project runs entirely on **Qwen Cloud (Alibaba Cloud Model Studio)** via the
international `dashscope-intl` endpoints. Below are the code samples showing the
Qwen Cloud Base URLs, plus where the Workbench screenshot lives.

## 1. Base URLs (code sample)

From [`showrunner/config.py`](../showrunner/config.py):

```python
# OpenAI-compatible base for chat; native DashScope base for image/video/tts.
COMPAT_BASE = "https://dashscope-intl.aliyuncs.com/compatible-mode/v1"
NATIVE_BASE = "https://dashscope-intl.aliyuncs.com/api/v1"
```

## 2. Live calls (code samples)

From [`showrunner/qwen_client.py`](../showrunner/qwen_client.py):

```python
# Chat (Qwen-Max) — scriptwriting
requests.post(f"{config.COMPAT_BASE}/chat/completions", ...)

# Wan text-to-video — the shot
_submit_async("services/aigc/video-generation/video-synthesis", "wan2.2-t2v-plus", ...)

# Qwen3-TTS — the voice (sync)
requests.post(f"{config.NATIVE_BASE}/services/aigc/multimodal-generation/generation",
              json={"model": "qwen3-tts-flash", "input": {"text": ..., "voice": ...}})
```

## 3. Models consumed (Qwen Cloud)

| Capability | Model | Verified |
|-----------|-------|----------|
| LLM | `qwen-max` | ✅ HTTP 200 |
| Video | `wan2.2-t2v-plus`, `wan2.1-t2v-turbo` | ✅ task SUCCEEDED |
| TTS | `qwen3-tts-flash` | ✅ audio returned |
| Image | `wan2.2-t2i-flash` | ✅ image returned |

## 4. Workbench screenshot

[`qwen-workbench-proof.png`](qwen-workbench-proof.png) — a screenshot of the
authenticated Qwen Cloud / Model Studio console (captured 2026-07-03) showing the
active account, the LLM free-tier quota table (qwen-plus / qwen-flash / qwen-vl-max),
and 246 eligible free-quota models valid through 2026-09-01.

## 5. Reproduce

```bash
cp .env.example .env         # paste your free-tier key
python smoke_test.py --video # exercises chat + image + video + tts live
```

A successful run writes real assets to `output/smoke/` (storyboard PNG, voice WAV,
Wan MP4), confirming end-to-end Qwen Cloud usage.
