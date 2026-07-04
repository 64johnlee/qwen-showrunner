# Qwen Showrunner 🎬

**An autonomous AI showrunner for vertical short-form drama (微短剧).**
Give it one line of premise; it writes the script, films every shot with **Wan**,
voices every character with **Qwen3-TTS**, burns subtitles, and cuts a finished
~1-minute 9:16 episode — spoken in one language, subtitled in another.
All shots are submitted to Wan in parallel, so a 10-shot episode renders in
roughly the wall-clock time of one shot.

Built for the **Global AI Hackathon Series with Qwen Cloud → AI Showrunner track**.
Runs entirely on the Qwen Cloud free tier (Alibaba Cloud Model Studio), card-free.

---

## Why

Short dramas (微短剧) are a multi-billion-dollar format, and the next wave of
growth is **localization into Southeast Asia**. Producing them is slow and manual.
Qwen Showrunner turns a premise into a distributable ~1-minute episode in a few
minutes of wall-clock time —
and because it separates *spoken language* from *subtitle language*, a single run
outputs a Mandarin drama with English (or Malay) subtitles for a global audience.

## How it works

```
 premise ─▶ Qwen-Max ─▶ screenplay (JSON: title, characters, scenes)
                          │
              per shot ┌──┴───────────────────────────────┐
                       ▼            ▼             ▼
                 Wan t2v       Qwen3-TTS      subtitle
                 (the shot)    (the voice)    (translation)
                       └──────────┬───────────────┘
                                  ▼
                          ffmpeg: 9:16 crop + burn subtitle + mux voice
                                  ▼
                        concat all shots ─▶ episode.mp4
```

The orchestrator (`showrunner/pipeline.py`) is the "showrunner agent": it plans the
episode and drives each stage, emitting live events consumed by the dashboard.

### Qwen Cloud models used (all on the free tier, `dashscope-intl`)

| Stage | Model |
|-------|-------|
| Scriptwriting / direction | `qwen-max` |
| Shot video generation | `wan2.7-t2v` (HQ, audio-capable) / `wan2.1-t2v-turbo` (fast) |
| Character voices | `qwen3-tts-flash` |
| Storyboard image (optional) | `wan2.2-t2i-flash` |

## Quickstart

```bash
pip install -r requirements.txt          # + a system ffmpeg on PATH
cp .env.example .env                      # paste your free-tier key
```

**CLI**

```bash
# Mandarin drama, English subtitles (~1-minute episode: 10 shots by default)
python run.py "三年前被豪门赶出家门的女人今晚回来复仇" --lang zh --sub-lang en

# English, faster turbo model, shorter episode
python run.py "a barista realizes the regular customer is his estranged father" --fast --shots 6
```

**Live dashboard**

```bash
python server.py     # http://127.0.0.1:8000
```

Enter a premise, hit **Action**, and watch each shot get filmed, voiced, and cut in
real time; the finished episode plays in a phone frame.

## Project structure

```
showrunner/
  config.py         endpoints + confirmed model IDs + .env loader
  qwen_client.py    chat / image / video / tts over Qwen Cloud
  script_writer.py  premise -> validated screenplay JSON
  assembler.py      ffmpeg: crop, subtitle burn, mux, concat
  pipeline.py       the showrunner agent (orchestration + events)
run.py              CLI
server.py           FastAPI live-production dashboard (SSE)
smoke_test.py       one-shot end-to-end check of all four modalities
```

## Requirements

- Python 3.10+
- A system `ffmpeg`/`ffprobe` on PATH ([ffmpeg.org](https://ffmpeg.org))
- A Qwen Cloud free-tier key ([home.qwencloud.com/benefits](https://home.qwencloud.com/benefits))

## License

MIT — see [LICENSE](LICENSE).
