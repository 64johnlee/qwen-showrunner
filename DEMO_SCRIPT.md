# Demo Video Script — Qwen Showrunner (~3 min)

**Goal:** show the payoff in the first 30 seconds, then prove it's real and autonomous.
**Format:** screen recording of the dashboard + the finished vertical episode.
Record at 1080p; keep the browser at `http://127.0.0.1:8000`.

---

### 0:00–0:30 — The hook (payoff first)
- **On screen:** the finished 《女王归来》 episode playing full-frame (vertical), sound on.
- **VO:** "This is a Mandarin short-drama with English subtitles — script, video,
  voices, and edit. No actors, no camera, no editor. It was produced by a single AI
  agent from one line of text, on Qwen Cloud's free tier. Here's how."

### 0:30–0:50 — The problem
- **On screen:** dashboard idle state; type a fresh premise into the box.
- **VO:** "Short dramas are exploding, and the next market is Southeast Asia. But
  every 60-second episode still needs writers, camera, voice actors, and an editor.
  Qwen Showrunner collapses all of it into one agent."

### 0:50–1:50 — Watch it work (the proof)
- **On screen:** click **Action**. Let the dashboard run live:
  - script appears (title + scene cards),
  - each card lights up shot-by-shot — 🎬 shot (Wan), 🎙 voice (Qwen3-TTS), ✂ cut.
- **VO (over the run):** "It starts with Qwen-Max, which writes a structured
  screenplay — characters, shots, dialogue. Then for every shot it films with Wan,
  voices the line with Qwen3-TTS, and writes a subtitle as a translation into a
  different language. Everything you're seeing is real API calls on Qwen Cloud."

### 1:50–2:20 — The localization angle (the differentiator)
- **On screen:** the script.json side-by-side — spoken 中文 lines vs English subtitles.
- **VO:** "Here's the key idea: spoken language and subtitle language are separate.
  One production run gives you a Mandarin episode subtitled in English — or Malay —
  for a global audience. It's a localization engine, not just a video generator."

### 2:20–2:45 — The result
- **On screen:** the new episode auto-plays in the phone frame; show the download link.
- **VO:** "About a minute later, a finished, vertical, subtitled episode — ready to
  publish. At near-zero marginal cost, because it runs on the free tier."

### 2:45–3:00 — Close
- **On screen:** README / architecture diagram; the Qwen Cloud logo/models list.
- **VO:** "Qwen Showrunner — an autonomous 微短剧 studio, built entirely on Qwen
  Cloud, for the AI Showrunner track. Thanks for watching."

---

**Shot list checklist**
- [ ] Clean full-frame playthrough of the flagship episode (for the 0:00 hook)
- [ ] One live dashboard production, uncut, from Action → phone-frame playback
- [ ] script.json close-up showing zh line + en subtitle
- [ ] Architecture diagram (`docs/architecture.svg`)

**Tips**
- Pre-warm one production before recording so you know the timing; record a fresh one live.
- Keep total runtime under 3:00. Front-load the finished episode — judges decide fast.
