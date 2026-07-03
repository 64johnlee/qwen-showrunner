"""FastAPI live-production dashboard for the Qwen Showrunner.

Start:  python server.py   ->  http://127.0.0.1:8000
A premise is submitted to /produce, which runs the showrunner pipeline in a
background thread; the browser watches progress over an SSE stream (/stream/{id})
and plays the finished vertical episode in a phone frame.
"""
from __future__ import annotations

import asyncio
import json
import queue
import threading
import uuid
from pathlib import Path

import uvicorn
from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, JSONResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles

from showrunner.pipeline import produce_episode

OUTPUT = Path("output")
OUTPUT.mkdir(exist_ok=True)

app = FastAPI(title="Qwen Showrunner")
app.mount("/media", StaticFiles(directory="output"), name="media")

_jobs: dict[str, queue.Queue] = {}


def _media_url(fs_path: str) -> str:
    try:
        rel = Path(fs_path).resolve().relative_to(OUTPUT.resolve()).as_posix()
        return f"/media/{rel}"
    except ValueError:
        return fs_path


def _run_job(job_id: str, params: dict) -> None:
    q = _jobs[job_id]

    def on_event(stage: str, data: dict) -> None:
        if stage == "episode_done" and data.get("file"):
            data = {**data, "url": _media_url(data["file"])}
        q.put({"stage": stage, "data": data})

    try:
        result = produce_episode(
            params["premise"], params.get("lang", "en"), int(params.get("shots", 3)),
            OUTPUT, bool(params.get("fast", False)),
            subtitle_lang=params.get("sub_lang", "en"), on_event=on_event,
        )
        q.put({"stage": "done", "data": {"url": _media_url(result["episode"]),
                                         "title": result["title"],
                                         "logline": result.get("logline", "")}})
    except Exception as exc:  # surface any failure to the dashboard
        q.put({"stage": "error", "data": {"message": str(exc)}})
    finally:
        q.put(None)


@app.post("/produce")
async def produce(req: Request):
    params = await req.json()
    if not params.get("premise"):
        return JSONResponse({"error": "premise required"}, status_code=400)
    job_id = uuid.uuid4().hex[:12]
    _jobs[job_id] = queue.Queue()
    threading.Thread(target=_run_job, args=(job_id, params), daemon=True).start()
    return {"job_id": job_id}


@app.get("/stream/{job_id}")
async def stream(job_id: str):
    q = _jobs.get(job_id)
    if q is None:
        return JSONResponse({"error": "unknown job"}, status_code=404)

    async def gen():
        while True:
            try:
                item = q.get_nowait()
            except queue.Empty:
                await asyncio.sleep(0.2)
                continue
            if item is None:
                break
            yield f"data: {json.dumps(item, ensure_ascii=False)}\n\n"
        _jobs.pop(job_id, None)

    return StreamingResponse(gen(), media_type="text/event-stream")


@app.get("/health")
async def health():
    return {"ok": True}


@app.get("/", response_class=HTMLResponse)
async def index():
    return _HTML


_HTML = """<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Qwen Showrunner — 微短剧 AI Studio</title>
<style>
  :root{
    --bg:#0b0b0f; --panel:#14141b; --edge:#23232e; --ink:#f4f1ea;
    --muted:#8a8a99; --gold:#e8b04b; --gold-dim:#7a5f27; --live:#4ade80; --red:#f87171;
    --film:linear-gradient(180deg,#191921,#101017);
  }
  *{box-sizing:border-box}
  body{margin:0;background:var(--bg);color:var(--ink);
    font-family:"Segoe UI",system-ui,-apple-system,sans-serif;
    background-image:radial-gradient(1200px 600px at 80% -10%,#1c1c27 0,transparent 60%);}
  .app{display:grid;grid-template-columns:340px 1fr;min-height:100vh}
  .console{background:var(--panel);border-right:1px solid var(--edge);
    padding:26px 22px;display:flex;flex-direction:column;gap:20px}
  .brand{line-height:1.1}
  .brand b{font-size:20px;letter-spacing:.5px}
  .brand b span{color:var(--gold)}
  .brand small{display:block;color:var(--muted);margin-top:6px;font-size:12px;letter-spacing:.4px}
  form{display:flex;flex-direction:column;gap:14px}
  label{font-size:11px;text-transform:uppercase;letter-spacing:.12em;color:var(--muted);margin-bottom:6px;display:block}
  textarea,select{width:100%;background:#0e0e14;border:1px solid var(--edge);color:var(--ink);
    border-radius:10px;padding:11px 12px;font-size:14px;font-family:inherit;resize:vertical}
  textarea:focus,select:focus{outline:none;border-color:var(--gold-dim)}
  .row{display:flex;gap:10px}.row>div{flex:1}
  button{background:linear-gradient(180deg,#f0bd5b,#d99a2f);color:#1a1206;border:0;
    border-radius:10px;padding:13px;font-weight:700;font-size:15px;cursor:pointer;letter-spacing:.3px}
  button:disabled{filter:grayscale(.6) brightness(.7);cursor:not-allowed}
  .log{margin-top:auto;background:#0e0e14;border:1px solid var(--edge);border-radius:10px;
    padding:10px;height:150px;overflow:auto;font:12px/1.5 ui-monospace,Consolas,monospace;color:#9aa}
  .log b{color:var(--gold)}
  .stage{padding:26px 30px;display:flex;flex-direction:column;gap:20px}
  .status{background:var(--film);border:1px solid var(--edge);border-radius:12px;
    padding:14px 18px;font-size:14px;display:flex;align-items:center;gap:12px}
  .dot{width:9px;height:9px;border-radius:50%;background:var(--muted)}
  .dot.live{background:var(--live);animation:pulse 1.4s infinite}
  @keyframes pulse{0%{box-shadow:0 0 0 0 rgba(74,222,128,.5)}70%{box-shadow:0 0 0 8px rgba(74,222,128,0)}100%{box-shadow:0 0 0 0 rgba(74,222,128,0)}}
  .head{display:flex;align-items:baseline;gap:14px;min-height:24px}
  .head h1{margin:0;font-size:26px;letter-spacing:.5px}
  .head span{color:var(--muted);font-size:14px}
  .content{display:grid;grid-template-columns:1fr 320px;gap:24px;align-items:start}
  .scenes{display:flex;flex-direction:column;gap:12px}
  .card{background:var(--film);border:1px solid var(--edge);border-radius:12px;padding:14px 16px;
    display:flex;gap:14px;align-items:center;opacity:.55;transition:.25s}
  .card.active{opacity:1;border-color:var(--gold-dim);box-shadow:0 0 24px -12px var(--gold)}
  .card.done{opacity:1}
  .slate{width:44px;height:44px;flex:none;border-radius:9px;background:#000;border:1px solid #333;
    display:grid;place-items:center;font-weight:800;color:var(--gold);font-size:18px;position:relative}
  .slate:before{content:"";position:absolute;top:-4px;left:-1px;right:-1px;height:8px;
    background:repeating-linear-gradient(45deg,#eee 0 6px,#222 6px 12px);border-radius:3px}
  .card .lines{flex:1;min-width:0}
  .card .spoken{font-size:15px;margin:0 0 3px}
  .card .sub{font-size:12.5px;color:var(--muted);margin:0}
  .card .who{font-size:11px;color:var(--gold);text-transform:uppercase;letter-spacing:.1em;margin-bottom:4px}
  .steps{display:flex;gap:6px;flex:none}
  .step{font-size:10px;color:var(--muted);border:1px solid var(--edge);border-radius:20px;
    padding:3px 8px;display:flex;gap:4px;align-items:center}
  .step.on{color:var(--live);border-color:#264b34}
  .phone-wrap{position:sticky;top:26px;display:flex;flex-direction:column;align-items:center;gap:12px}
  .phone{width:290px;aspect-ratio:9/16;background:#000;border-radius:34px;border:8px solid #1c1c22;
    box-shadow:0 30px 60px -20px #000,inset 0 0 0 2px #000;position:relative;overflow:hidden;display:grid;place-items:center}
  .phone .notch{position:absolute;top:10px;left:50%;transform:translateX(-50%);width:90px;height:18px;
    background:#000;border-radius:12px;z-index:2}
  .phone video{width:100%;height:100%;object-fit:cover}
  .phone .placeholder{color:#3a3a46;font-size:13px;text-align:center;padding:0 26px;line-height:1.6}
  .dl{font-size:12px;color:var(--gold);text-decoration:none}
  .badge{font-size:11px;color:var(--muted)}
  @media(max-width:900px){.app{grid-template-columns:1fr}.content{grid-template-columns:1fr}}
</style></head>
<body>
<div class="app">
  <aside class="console">
    <div class="brand"><b>QWEN <span>SHOWRUNNER</span></b>
      <small>微短剧 AI Studio · script → shot → voice → cut</small></div>
    <form id="f">
      <div>
        <label>Premise</label>
        <textarea id="premise" rows="3" placeholder="A woman cast out of a wealthy family returns for revenge...">三年前被豪门赶出家门的女人，如今是让所有人下跪的商业女王，今晚她带着证据回来复仇</textarea>
      </div>
      <div class="row">
        <div><label>Spoken</label>
          <select id="lang"><option value="zh">中文</option><option value="en">English</option><option value="ms">Malay</option></select></div>
        <div><label>Subtitles</label>
          <select id="sub"><option value="en">English</option><option value="zh">中文</option><option value="ms">Malay</option></select></div>
      </div>
      <div class="row">
        <div><label>Shots</label>
          <select id="shots"><option>2</option><option selected>3</option><option>4</option><option>5</option></select></div>
        <div><label>Quality</label>
          <select id="fast"><option value="false">Wan-Plus (HQ)</option><option value="true">Turbo (fast)</option></select></div>
      </div>
      <button id="go" type="submit">🎬 Action</button>
    </form>
    <div class="log" id="log"></div>
  </aside>

  <main class="stage">
    <div class="status"><span class="dot" id="sdot"></span><span id="stext">Idle — write a premise and hit Action.</span></div>
    <div class="head"><h1 id="title"></h1><span id="logline"></span></div>
    <div class="content">
      <div class="scenes" id="scenes"></div>
      <div class="phone-wrap">
        <div class="phone"><div class="notch"></div>
          <div class="placeholder" id="ph">Your episode will play here</div></div>
        <a class="dl" id="dl" style="display:none" download>⬇ download episode.mp4</a>
        <div class="badge">powered by Qwen-Max · Wan · Qwen3-TTS</div>
      </div>
    </div>
  </main>
</div>
<script>
const $=id=>document.getElementById(id);
const log=(m,gold)=>{const l=$('log');l.innerHTML+=(gold?`<b>${m}</b>`:m)+'<br>';l.scrollTop=l.scrollHeight;};
const STEP={video:'🎬 shot',voice:'🎙 voice',assembled:'✂ cut'};
function status(t,live){$('stext').textContent=t;$('sdot').classList.toggle('live',!!live);}
function sceneCard(s){
  return `<div class="card" id="c${s.id}">
    <div class="slate">${s.id}</div>
    <div class="lines"><div class="who">${s.speaker||'Narrator'}</div>
      <p class="spoken">${s.line}</p><p class="sub">${s.subtitle||''}</p></div>
    <div class="steps">
      <span class="step" data-k="video">${STEP.video}</span>
      <span class="step" data-k="voice">${STEP.voice}</span>
      <span class="step" data-k="assembled">${STEP.assembled}</span></div></div>`;
}
function markStep(id,k){const c=$('c'+id);if(!c)return;const s=[...c.querySelectorAll('.step')].find(e=>e.dataset.k===k);if(s)s.classList.add('on');}

$('f').addEventListener('submit',async e=>{
  e.preventDefault();$('go').disabled=true;
  $('scenes').innerHTML='';$('title').textContent='';$('logline').textContent='';
  $('ph').style.display='';$('ph').textContent='Rolling…';$('dl').style.display='none';
  $('log').innerHTML='';
  const body={premise:$('premise').value,lang:$('lang').value,sub_lang:$('sub').value,
    shots:$('shots').value,fast:$('fast').value==='true'};
  status('Submitting to the writers room…',true);
  const r=await fetch('/produce',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)});
  const {job_id,error}=await r.json();
  if(error){status('Error: '+error);$('go').disabled=false;return;}
  const es=new EventSource('/stream/'+job_id);
  es.onmessage=ev=>{
    const {stage,data}=JSON.parse(ev.data);
    if(stage==='script_start'){status('✍️ Writing the script…',true);log('writing script ('+data.shots+' shots)');}
    else if(stage==='script_done'){
      $('title').textContent=data.title;$('logline').textContent=data.logline;
      $('scenes').innerHTML=data.scenes.map(sceneCard).join('');
      log('script: '+data.title,true);status('Script locked — heading to set.',true);}
    else if(stage==='scene_start'){document.querySelectorAll('.card').forEach(c=>c.classList.remove('active'));
      $('c'+data.id)?.classList.add('active');status(`Filming shot ${data.id}/${data.total}…`,true);log('shot '+data.id+': '+data.line);}
    else if(stage==='video_done'){markStep(data.id,'video');}
    else if(stage==='voice_done'){markStep(data.id,'voice');}
    else if(stage==='scene_done'){markStep(data.id,'assembled');$('c'+data.id)?.classList.add('done');}
    else if(stage==='assemble_start'){status('✂ Editing the final cut…',true);log('assembling '+data.clips+' clips');}
    else if(stage==='done'){
      status('✅ Episode ready.',false);log('done: '+data.title,true);
      $('ph').style.display='none';
      const ph=document.querySelector('.phone');ph.querySelector('video')?.remove();
      const v=document.createElement('video');v.src=data.url;v.controls=true;v.autoplay=true;v.loop=true;
      ph.appendChild(v);$('dl').href=data.url;$('dl').style.display='';$('go').disabled=false;es.close();}
    else if(stage==='error'){status('❌ '+data.message);log(data.message);$('go').disabled=false;es.close();}
  };
  es.onerror=()=>{es.close();$('go').disabled=false;};
});
</script>
</body></html>"""


if __name__ == "__main__":
    uvicorn.run(app, host="127.0.0.1", port=8000)
