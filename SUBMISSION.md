# Qwen Showrunner — Devpost Submission

**Hackathon:** Global AI Hackathon Series with Qwen Cloud
**Track:** AI Showrunner
**Tagline:** One line of premise in, a finished subtitled short-drama episode out — an autonomous 微短剧 studio on Qwen Cloud.

---

## 💡 Inspiration

Short dramas (微短剧) are one of the fastest-growing entertainment formats in the
world, and the clear next frontier is **localizing them for Southeast Asia**. But
production is still slow, manual, and expensive: writers, storyboard artists,
camera, voice actors, and an editor for every 60-second episode.

I wanted to collapse that entire pipeline into a single autonomous agent — and to
solve the localization problem natively, so one production run yields a Mandarin
episode that a Malaysian or global audience can watch with subtitles in their own
language.

## 🎬 What it does

Give Qwen Showrunner a one-line premise and it autonomously:

1. **Writes the screenplay** — title, characters (with assigned voices), and a
   shot-by-shot script, as validated structured JSON.
2. **Films every shot** — a text-to-video prompt per scene rendered with **Wan**.
3. **Voices every character** — **Qwen3-TTS** in the chosen spoken language.
4. **Localizes** — subtitles generated as a faithful translation into a *different*
   language (e.g. spoken 中文, subtitled English).
5. **Edits the final cut** — ffmpeg crops each shot to vertical 9:16, burns
   subtitles, syncs the voice, and concatenates into one `episode.mp4`.

A one-command CLI or a **live production dashboard** (watch each shot get filmed,
voiced, and cut in real time, then play the episode in a phone frame).

## 🛠️ How I built it

Everything runs on **Qwen Cloud (Alibaba Cloud Model Studio)**, `dashscope-intl`,
on the free tier:

| Stage | Qwen Cloud model | Endpoint |
|-------|------------------|----------|
| Script / direction | `qwen-max` | `/compatible-mode/v1/chat/completions` |
| Shot video | `wan2.2-t2v-plus` / `wan2.1-t2v-turbo` | `/aigc/video-generation/video-synthesis` |
| Voices | `qwen3-tts-flash` | `/aigc/multimodal-generation/generation` |
| Storyboard image | `wan2.2-t2i-flash` | `/aigc/text2image/image-synthesis` |

- **Orchestration:** a Python "showrunner agent" (`pipeline.py`) plans the episode
  and drives each stage, emitting events over a queue.
- **Dashboard:** FastAPI + Server-Sent Events; a background thread runs the
  pipeline and streams progress to a cinematic control-room UI.
- **Post-production:** ffmpeg filtergraphs for scaling/cropping to 9:16, burning
  wrapped multilingual subtitles (CJK-capable font), padding audio/video to length,
  and concatenating shots.

## 🎯 Track alignment (AI Showrunner)

The track asks for *an agent that autonomously handles the complete short-drama
pipeline — scriptwriting, storyboarding, video generation (Wan), and
post-production editing.* Qwen Showrunner does all four, end to end, with **Wan**
as the video engine and **multimodal orchestration** (LLM + video + speech +
translation) as the core — while maximizing output quality under the free-tier
token budget.

## 🌏 Why it matters (real-world value)

The spoken/subtitle language split makes this a **localization engine**, not just a
video generator — directly targeting the SEA short-drama expansion. A studio could
produce a Mandarin episode and ship English- and Malay-subtitled cuts from the same
run, in about a minute, at near-zero marginal cost.

## 🧗 Challenges

- Mapping Beijing-region model names to their `dashscope-intl` equivalents
  (`wanx2.1-*` → `wan2.2-*`, `qwen-tts` → `qwen3-tts-flash`, which requires *sync*
  calls) — solved by probing the live API.
- ffmpeg filtergraph correctness on Windows: single `-filter_complex`, quoted +
  escaped font paths for burned CJK subtitles, and duration-matched audio/video.

## 🏆 Accomplishments

- A genuinely autonomous premise → finished episode pipeline, all on free Qwen quota.
- Native bilingual localization (spoken vs subtitle language) built in.
- A live dashboard that makes the agent's work legible shot by shot.

## 🔭 What's next

- Image-to-video shot continuity (storyboard frame → Wan i2v) for character consistency.
- Multi-voice casting and background music.
- Batch series production and a publish step.

## 🔗 Links

- **Code:** https://github.com/64johnlee/qwen-showrunner
- **Demo video:** https://youtube.com/shorts/nqahUC7aUhA
- **Example episode (full 80s, CAST mode, zh spoken / en subs):** https://youtube.com/shorts/D3U50S_b4Wo
- **Deployment proof:** see `docs/PROOF_OF_DEPLOYMENT.md` + Workbench screenshot
