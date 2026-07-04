"""Probe which text-to-video models still have free-tier allowance on this key.

Submits a minimal async t2v task per candidate and reports the gate response:
task accepted = model usable (one ~5s clip of allowance is consumed by the
accepted task); AllocationQuota.FreeTierOnly = that model's free video
seconds are exhausted; other codes = endpoint/format difference to handle.
"""
import json

import httpx

from showrunner import config

CANDIDATES = [
    "wan2.1-t2v-turbo",
    "wan2.2-t2v-plus",       # known exhausted — include as the control
    "wan2.5-t2v-preview",
    "wan2.6-t2v",
    "wan2.7-t2v",
    "happyhorse-1.1-t2v",
]

PROMPT = "一个女人站在雨中的街头，霓虹灯光，电影感"

for model in CANDIDATES:
    body = {
        "model": model,
        "input": {"prompt": PROMPT},
        "parameters": {"size": "480*832"},
    }
    try:
        resp = httpx.post(
            f"{config.NATIVE_BASE}/services/aigc/video-generation/video-synthesis",
            headers={
                "Authorization": f"Bearer {config.API_KEY}",
                "Content-Type": "application/json",
                "X-DashScope-Async": "enable",
            },
            json=body,
            timeout=30,
        )
        data = resp.json()
        code = data.get("code", "")
        task = (data.get("output") or {}).get("task_id", "")
        if task:
            print(f"{model}: ✅ ACCEPTED (task {task[:12]}…)")
        else:
            print(f"{model}: ❌ {code} — {str(data.get('message',''))[:110]}")
    except Exception as e:
        print(f"{model}: ⚠️ request error — {e}")
