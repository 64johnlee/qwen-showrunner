"""Generate today's episode premise — genre rotates by weekday, wording by Qwen.

Prints a single premise line to stdout (consumed by daily_episode.sh).
Costs a few hundred free qwen-max tokens.
"""
import datetime
import json

import requests

from showrunner import config

GENRES = [
    "豪门复仇爽剧",        # Monday
    "契约恋爱甜宠剧",      # Tuesday
    "都市灵异悬疑剧",      # Wednesday
    "小人物逆袭爽剧",      # Thursday
    "重生复仇剧",          # Friday
    "隐藏身份大佬剧",      # Saturday
    "亲情催泪剧",          # Sunday
]

genre = GENRES[datetime.date.today().weekday()]
prompt = (
    f"为一部竖屏微短剧想一个{genre}的开篇钩子。要求：一句话、35字以内、"
    "有强烈的悬念或反转、适合抖音/TikTok前3秒抓住观众。"
    '只返回JSON：{"premise": "……"}'
)

resp = requests.post(
    f"{config.COMPAT_BASE}/chat/completions",
    headers={"Authorization": f"Bearer {config.API_KEY}"},
    json={"model": config.MODELS["script"],
          "messages": [{"role": "user", "content": prompt}],
          "response_format": {"type": "json_object"},
          "temperature": 1.0},
    timeout=60,
)
premise = json.loads(resp.json()["choices"][0]["message"]["content"])["premise"]
print(premise.strip())
