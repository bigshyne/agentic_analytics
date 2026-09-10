"""
query_bench.py
==============

A local, throwaway web UI on top of agentic_analytics_prototype.py.

You ask a question. The agent picks {metrics, dimensions, filters}. The bench
shows its work as expandable steps, validates the query, compiles the SQL, runs
it against the sample data, renders the result, and asks the one thing that
matters: is this query correct? Every verdict appends to verifications.jsonl,
which becomes your growing answer key.

Keep this file next to agentic_analytics_prototype.py, then:

    pip install flask sidemantic duckdb pandas anthropic
    AGENT_MODE=stub python query_bench.py                 # no API key needed
    AGENT_MODE=live ANTHROPIC_API_KEY=sk-... python query_bench.py

Open http://127.0.0.1:5000 .

STUB mode uses a tiny keyword matcher so you can click around offline. It is a
stand-in, not the agent. LIVE mode calls the real model through the skeleton.
"""

import json
import os
import time
from pathlib import Path

from flask import Flask, jsonify, request

import agentic_analytics_prototype as loop

AGENT_MODE = os.environ.get("AGENT_MODE", "stub")
LOG_PATH = Path("verifications.jsonl")
FAIL_REASONS = [
    "wrong metric",
    "wrong dimension",
    "wrong filter",
    "right query, wrong number",
    "misleading result",
    "should have declined",
]

app = Flask(__name__)

LAYER = loop.build_demo_layer()
CATALOG = loop.build_catalog(LAYER)


def heuristic_stub(question, cat):
    q = question.lower()
    metrics, dimensions, filters = [], [], []
    if any(w in q for w in ("active", "reporting", "pinged", "ping")):
        metrics = ["fleet.active_assets"]
    else:
        metrics = ["fleet.billable_assets"]
    if "customer" in q or "each" in q or "by customer" in q:
        dimensions.append("fleet.customer")
    if "type" in q or "dry vs" in q or "breakdown" in q:
        dimensions.append("fleet.asset_type")
    for val in cat["allowed_values"].get("fleet.asset_type", []):
        if val.lower() in q:
            filters.append({"attribute": "fleet.asset_type", "operator": "=", "value": val})
    for val in cat["allowed_values"].get("fleet.customer", []):
        if val.lower() in q:
            filters.append({"attribute": "fleet.customer", "operator": "=", "value": val})
    return {"metrics": metrics, "dimensions": dimensions, "filters": filters}


def _cell(v):
    try:
        f = float(v)
        return int(f) if f.is_integer() else round(f, 4)
    except (TypeError, ValueError):
        return str(v)


def run_question(question):
    agent = (heuristic_stub if AGENT_MODE == "stub"
             else loop.ask_agent_live)(question, CATALOG)
    errs = loop.validate(agent, CATALOG)
    out = {"question": question, "agent": agent, "declined": bool(errs), "errors": errs}
    if errs:
        return out
    filters = loop.compile_filters(agent["filters"])
    out["sql"] = LAYER.compile(metrics=agent["metrics"], dimensions=agent["dimensions"],
                               filters=filters)
    df = LAYER.query(metrics=agent["metrics"], dimensions=agent["dimensions"],
                     filters=filters).fetchdf()
    out["columns"] = [str(c) for c in df.columns]
    out["rows"] = [[_cell(v) for v in row] for row in df.itertuples(index=False)]
    out["chart"] = loop.pick_chart(agent, CATALOG)
    return out


def _log_count():
    if not LOG_PATH.exists():
        return 0
    return sum(1 for ln in LOG_PATH.read_text().splitlines() if ln.strip())


@app.get("/meta")
def meta():
    return jsonify({
        "mode": AGENT_MODE,
        "model": loop.MODEL if AGENT_MODE == "live" else "keyword stub",
        "space": "fleet",
        "metric_refs": CATALOG["metric_refs"],
        "dim_refs": CATALOG["dim_refs"],
        "allowed_values": CATALOG["allowed_values"],
        "catalog_text": CATALOG["text"],
        "count": _log_count(),
    })


@app.post("/ask")
def ask():
    question = (request.json or {}).get("question", "").strip()
    if not question:
        return jsonify({"error": "empty question"}), 400
    try:
        return jsonify(run_question(question))
    except Exception as e:
        return jsonify({"error": f"{type(e).__name__}: {e}"}), 500


@app.post("/verify")
def verify():
    rec = request.json or {}
    rec["ts"] = time.strftime("%Y-%m-%d %H:%M:%S")
    with LOG_PATH.open("a") as f:
        f.write(json.dumps(rec) + "\n")
    return jsonify({"ok": True, "count": _log_count()})


@app.get("/log")
def log():
    items = []
    if LOG_PATH.exists():
        for line in LOG_PATH.read_text().splitlines():
            if line.strip():
                items.append(json.loads(line))
    items.reverse()
    return jsonify(items)


@app.get("/")
def index():
    return PAGE


PAGE = r"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Query bench</title>
<style>
  :root{
    --bg:#ffffff; --sidebar:#fbfbfd; --raise:#f4f4f7;
    --ink:#1b1b1f; --muted:#70737c; --faint:#9aa0a8; --line:#e7e7ec;
    --accent:#5b50e6; --accent-ink:#4a40c9; --accent-soft:#eeecfd;
    --metric:#a56410; --metric-bg:#fbf1e1; --metric-ln:#eddcbf;
    --dim:#0c8a83;   --dim-bg:#e2f4f2;   --dim-ln:#c6e9e5;
    --filter:#6f52cf;--filter-bg:#efeafd; --filter-ln:#ddd3f6;
    --ok:#12764a; --ok-bg:#e6f4ec; --bad:#c1352f; --bad-bg:#fbe9e8;
    --mono:ui-monospace,SFMono-Regular,Menlo,Consolas,monospace;
    --sans:-apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,Helvetica,Arial,sans-serif;
  }
  *{box-sizing:border-box}
  html,body{height:100%}
  body{margin:0;background:var(--bg);color:var(--ink);font-family:var(--sans);
       font-size:15px;line-height:1.5;-webkit-font-smoothing:antialiased}
  button{font-family:var(--sans);cursor:pointer}

  /* top bar */
  .topbar{display:flex;align-items:center;gap:12px;height:56px;padding:0 20px;
          border-bottom:1px solid var(--line)}
  .logo{width:26px;height:26px;border-radius:7px;
        background:linear-gradient(135deg,#6d5ef0,#5b50e6 55%,#4335b8)}
  .brand{font-weight:650;letter-spacing:-.01em}
  .crumb{color:var(--faint)}
  .space{color:var(--muted);font-weight:550}
  .badge{font-size:12px;font-weight:600;padding:2px 9px;border-radius:999px;
         background:var(--accent-soft);color:var(--accent-ink)}
  .badge.mode{background:var(--raise);color:var(--muted)}
  .spacer{flex:1}
  .tabbtn{border:none;background:none;color:var(--muted);font-size:14px;font-weight:550;
          padding:6px 4px;position:relative}
  .tabbtn.active{color:var(--ink)}
  .tabbtn.active::after{content:"";position:absolute;left:0;right:0;bottom:-17px;height:2px;background:var(--accent)}
  .verified-btn{border:1px solid var(--line);background:var(--bg);border-radius:8px;
                padding:7px 12px;font-size:13px;color:var(--muted);font-weight:550}
  .verified-btn b{color:var(--ink)}
  .avatar{width:28px;height:28px;border-radius:50%;background:#6b63d6;color:#fff;
          display:grid;place-items:center;font-size:13px;font-weight:650}

  /* shell */
  .shell{display:flex;height:calc(100% - 56px)}
  .side{width:262px;border-right:1px solid var(--line);background:var(--sidebar);
        display:flex;flex-direction:column;padding:14px}
  .newbtn{border:1px solid var(--line);background:var(--bg);border-radius:9px;
          padding:10px;font-weight:600;font-size:14px;color:var(--ink);width:100%}
  .newbtn:hover{border-color:var(--accent);color:var(--accent-ink)}
  .side h4{font-size:12px;color:var(--faint);font-weight:600;margin:18px 4px 6px}
  .hist{overflow:auto;flex:1;margin:0 -6px}
  .histitem{display:block;width:100%;text-align:left;border:none;background:none;
            color:var(--muted);font-size:13.5px;padding:7px 10px;border-radius:7px;
            white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
  .histitem:hover{background:var(--raise);color:var(--ink)}
  .side-foot{border-top:1px solid var(--line);margin:8px -14px -14px;padding:12px 14px}
  .voctoggle{border:none;background:none;color:var(--muted);font-size:13px;padding:4px 0}
  .voctoggle:hover{color:var(--accent-ink)}

  /* main */
  .main{flex:1;display:flex;flex-direction:column;min-width:0}
  .stream{flex:1;overflow:auto;padding:0}
  .inner{max-width:760px;margin:0 auto;padding:26px 24px 40px;width:100%}

  /* welcome hero */
  .hero{max-width:760px;margin:0 auto;padding:64px 24px;width:100%}
  .hero h1{font-size:30px;letter-spacing:-.02em;font-weight:680;margin:0 0 6px}
  .hero h1 span{color:var(--accent)}
  .hero p{color:var(--muted);margin:0 0 22px}
  .askwrap{position:relative}
  textarea.ask{width:100%;min-height:120px;resize:vertical;border:1px solid var(--line);
       border-radius:14px;padding:16px 52px 16px 16px;font-size:16px;font-family:var(--sans);
       color:var(--ink);background:var(--bg)}
  textarea.ask:focus{outline:none;border-color:var(--accent);box-shadow:0 0 0 3px var(--accent-soft)}
  .send{position:absolute;right:12px;bottom:12px;width:34px;height:34px;border-radius:9px;
        border:none;background:var(--accent);color:#fff;font-size:16px;display:grid;place-items:center}
  .send:disabled{opacity:.45}
  .examples{display:flex;gap:8px;flex-wrap:wrap;margin-top:14px}
  .ex{font-size:13px;color:var(--muted);background:var(--bg);border:1px solid var(--line);
      border-radius:999px;padding:7px 13px}
  .ex:hover{border-color:var(--accent);color:var(--accent-ink)}
  .herohint{margin-top:34px;color:var(--faint);font-size:13px}

  /* turns */
  .turn{margin-bottom:30px}
  .userpill{display:inline-block;background:var(--accent);color:#fff;border-radius:14px 14px 4px 14px;
            padding:9px 14px;font-size:15px;float:right;max-width:80%;margin-bottom:16px}
  .clearfix{clear:both}

  .steps{border:1px solid var(--line);border-radius:12px;overflow:hidden;margin:6px 0 16px}
  .step + .step{border-top:1px solid var(--line)}
  .step-head{display:flex;align-items:center;gap:9px;padding:11px 14px;cursor:pointer;
             font-size:14px;color:var(--ink);background:var(--bg)}
  .step-head:hover{background:var(--raise)}
  .chev{color:var(--faint);transition:transform .15s;font-size:11px;width:10px}
  .step.open .chev{transform:rotate(90deg)}
  .step-ic{font-family:var(--mono);font-size:12px;color:var(--muted)}
  .step-title{font-weight:550}
  .step-note{color:var(--faint);font-weight:400;margin-left:auto;font-size:12.5px}
  .step-body{display:none;padding:0 14px 14px 33px;background:var(--bg)}
  .step.open .step-body{display:block}
  .step.bad .step-title{color:var(--bad)}

  .chips{display:flex;gap:7px;flex-wrap:wrap;margin:2px 0}
  .chiprow + .chiprow{margin-top:8px}
  .chip{font-family:var(--mono);font-size:12.5px;border-radius:7px;padding:5px 9px;border:1px solid;
        display:inline-flex;gap:7px;align-items:center}
  .chip .kind{font-family:var(--sans);font-size:10.5px;color:var(--faint);text-transform:none}
  .chip.m{color:var(--metric);background:var(--metric-bg);border-color:var(--metric-ln)}
  .chip.d{color:var(--dim);background:var(--dim-bg);border-color:var(--dim-ln)}
  .chip.f{color:var(--filter);background:var(--filter-bg);border-color:var(--filter-ln)}
  .empty{color:var(--faint);font-size:13px;font-style:italic}
  .voc{font-size:13px;color:var(--muted)}
  .voc code{font-family:var(--mono);color:var(--ink);font-size:12.5px}
  pre{background:var(--raise);border:1px solid var(--line);border-radius:8px;padding:12px;
      overflow:auto;font-family:var(--mono);font-size:12.5px;color:#33373f;margin:0}

  .thinking{display:flex;align-items:center;gap:9px;color:var(--muted);padding:12px 2px;font-size:14px}
  .spin{width:15px;height:15px;border:2px solid var(--line);border-top-color:var(--accent);
        border-radius:50%;animation:sp .7s linear infinite}
  @keyframes sp{to{transform:rotate(360deg)}}

  /* result */
  .answer{border:1px solid var(--line);border-radius:12px;padding:18px;margin-bottom:14px}
  .alabel{font-size:12px;color:var(--faint);margin:0 0 12px}
  .bignum{font-size:40px;font-weight:680;letter-spacing:-.02em}
  .bignum small{display:block;font-size:13px;font-weight:500;color:var(--muted);margin-top:2px;font-family:var(--mono)}
  .bars{display:flex;flex-direction:column;gap:9px}
  .bar{display:grid;grid-template-columns:150px 1fr auto;gap:12px;align-items:center;font-size:13px}
  .bar .lab{color:var(--muted);white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
  .bar .track{background:var(--raise);border-radius:6px;height:22px;overflow:hidden}
  .bar .fill{height:100%;background:linear-gradient(90deg,#6d5ef0,#5b50e6);border-radius:6px}
  .bar .val{font-family:var(--mono)}
  table{width:100%;border-collapse:collapse;font-size:14px;margin-top:12px}
  th,td{text-align:left;padding:8px 10px;border-bottom:1px solid var(--line)}
  th{color:var(--faint);font-weight:600;font-size:12px}
  td.num,th.num{text-align:right;font-family:var(--mono)}
  .decline{color:var(--bad);font-size:14px}
  .decline ul{margin:8px 0 0;padding-left:18px}

  /* verify */
  .verify{display:flex;gap:9px;align-items:center;flex-wrap:wrap}
  .vq{font-size:13px;color:var(--muted);margin-right:4px}
  .vbtn{border-radius:8px;padding:8px 15px;font-size:14px;font-weight:600;border:1px solid}
  .vbtn.ok{border-color:var(--ok);color:var(--ok);background:var(--bg)}
  .vbtn.ok:hover{background:var(--ok-bg)}
  .vbtn.bad{border-color:var(--bad);color:var(--bad);background:var(--bg)}
  .vbtn.bad:hover{background:var(--bad-bg)}
  select,textarea.note{font-family:var(--sans);background:var(--bg);color:var(--ink);
         border:1px solid var(--line);border-radius:8px;padding:8px 10px;font-size:14px}
  textarea.note{width:100%;margin-top:9px;min-height:46px;resize:vertical}
  .verdict{font-size:12px;font-weight:650;padding:4px 10px;border-radius:999px}
  .verdict.ok{color:var(--ok);background:var(--ok-bg)}
  .verdict.bad{color:var(--bad);background:var(--bad-bg)}

  /* bottom input (conversation mode) */
  .composer{border-top:1px solid var(--line);padding:14px 24px;background:var(--bg)}
  .composer .inner2{max-width:760px;margin:0 auto;position:relative}
  textarea.ask2{width:100%;min-height:52px;max-height:160px;resize:none;border:1px solid var(--line);
       border-radius:12px;padding:14px 52px 14px 16px;font-size:15px;font-family:var(--sans);color:var(--ink)}
  textarea.ask2:focus{outline:none;border-color:var(--accent);box-shadow:0 0 0 3px var(--accent-soft)}

  /* verified panel */
  .logrow{display:grid;grid-template-columns:auto 1fr auto;gap:12px;align-items:center;
          border-bottom:1px solid var(--line);padding:12px 2px}
  .logq{overflow:hidden}
  .logq .qt{font-size:14px}
  .logmeta{color:var(--faint);font-size:12px;font-family:var(--mono)}
  .logreason{color:var(--muted);font-size:12px}
  .hide{display:none}
</style>
</head>
<body>
<div class="topbar">
  <div class="logo"></div>
  <span class="brand">querybench</span>
  <span class="badge mode" id="modebadge">…</span>
  <span class="crumb">/</span>
  <span class="space" id="spacename">…</span>
  <div class="spacer"></div>
  <button class="tabbtn active" id="tab-ask" onclick="showTab('ask')">Ask</button>
  <button class="tabbtn" id="tab-ver" onclick="showTab('ver')">Verified</button>
  <button class="verified-btn" onclick="showTab('ver')">verified <b id="vcount">0</b></button>
  <div class="avatar">S</div>
</div>

<div class="shell">
  <aside class="side">
    <button class="newbtn" onclick="newConversation()">+ New question</button>
    <h4>This session</h4>
    <div class="hist" id="hist"></div>
    <div class="side-foot">
      <button class="voctoggle" onclick="toggleVoc()">View model vocabulary</button>
      <div id="vocbox" class="voc hide" style="margin-top:8px"></div>
    </div>
  </aside>

  <main class="main">
    <!-- ASK VIEW -->
    <div id="view-ask" style="display:flex;flex-direction:column;flex:1;min-height:0">
      <div class="stream" id="stream">
        <!-- welcome hero (empty state) -->
        <div class="hero" id="hero">
          <h1>Welcome to <span id="heromodel">the model</span></h1>
          <p>Ask a question about your data. See the query the agent chose, then mark whether it's right.</p>
          <div class="askwrap">
            <textarea class="ask" id="q1" placeholder="Ask about your data..."></textarea>
            <button class="send" id="send1" onclick="ask('q1')">↑</button>
          </div>
          <div class="examples" id="examples"></div>
          <p class="herohint">Every verdict you give builds the answer key in verifications.jsonl.</p>
        </div>
        <!-- conversation turns render here -->
        <div class="inner" id="turns" style="display:none"></div>
      </div>
      <div class="composer" id="composer" style="display:none">
        <div class="inner2">
          <textarea class="ask2" id="q2" placeholder="Ask about your data..."></textarea>
          <button class="send" id="send2" onclick="ask('q2')">↑</button>
        </div>
      </div>
    </div>

    <!-- VERIFIED VIEW -->
    <div id="view-ver" class="stream hide">
      <div class="inner">
        <h1 style="font-size:20px;margin:0 0 4px">Verified questions</h1>
        <p style="color:var(--muted);margin:0 0 18px">Your answer key so far. Persists in verifications.jsonl.</p>
        <div id="logbox"></div>
      </div>
    </div>
  </main>
</div>

<script>
const $ = s => document.querySelector(s);
let META=null, turns=[];

async function boot(){
  META = await (await fetch('/meta')).json();
  $('#modebadge').textContent = META.mode;
  $('#spacename').textContent = META.space;
  $('#heromodel').textContent = META.space;
  $('#vcount').textContent = META.count;
  const ex = ["How many reefers is each customer billed for?",
              "How many assets are active by customer?",
              "Billable assets by asset type",
              "Active assets for Acme Freight"];
  $('#examples').innerHTML = ex.map(e=>`<button class="ex">${e}</button>`).join('');
  document.querySelectorAll('.ex').forEach(b=>b.onclick=()=>{ $('#q1').value=b.textContent; ask('q1'); });
  const voc = META.metric_refs.map(m=>`<code>${m}</code>`).join('  ') + '<br>' +
              META.dim_refs.map(d=>`<code>${d}</code>`).join('  ');
  $('#vocbox').innerHTML = 'metrics<br>'+META.metric_refs.map(m=>`<code>${m}</code>`).join(' ') +
                           '<br><br>dimensions<br>'+META.dim_refs.map(d=>`<code>${d}</code>`).join(' ');
  document.querySelectorAll('.ask2,.ask').forEach(t=>t.addEventListener('keydown',e=>{
    if(e.key==='Enter' && !e.shiftKey){ e.preventDefault(); ask(t.id); }
  }));
}

function showTab(t){
  $('#tab-ask').classList.toggle('active', t==='ask');
  $('#tab-ver').classList.toggle('active', t==='ver');
  $('#view-ask').style.display = t==='ask' ? 'flex' : 'none';
  $('#view-ver').classList.toggle('hide', t!=='ver');
  if(t==='ver') renderLog();
}
function toggleVoc(){ $('#vocbox').classList.toggle('hide'); }
function newConversation(){ turns=[]; render(); $('#q1').value=''; }

async function ask(srcId){
  const box = $('#'+srcId);
  const question = box.value.trim();
  if(!question) return;
  box.value='';
  const turn = {question, res:null, verdict:null};
  turns.push(turn); render();
  try{
    turn.res = await (await fetch('/ask',{method:'POST',headers:{'Content-Type':'application/json'},
                      body:JSON.stringify({question})})).json();
  }catch(err){
    turn.res = {error:String(err)};
  }
  render();
}

function chip(kind,text,cls){ return `<span class="chip ${cls}"><span class="kind">${kind}</span>${text}</span>`; }
function isNum(v){ return typeof v === 'number'; }

function stepEl(title, note, open, body, tone){
  return `<div class="step ${open?'open':''} ${tone||''}">
    <div class="step-head" onclick="this.closest('.step').classList.toggle('open')">
      <span class="chev">▸</span><span class="step-title">${title}</span>
      ${note?`<span class="step-note">${note}</span>`:''}</div>
    <div class="step-body">${body}</div></div>`;
}

function renderQueryBody(a){
  const m = a.metrics.length ? a.metrics.map(x=>chip('metric',x,'m')).join('') : '<span class="empty">no metric</span>';
  const d = a.dimensions.length ? a.dimensions.map(x=>chip('group by',x,'d')).join('') : '<span class="empty">no grouping</span>';
  const f = a.filters.length ? a.filters.map(x=>chip('filter',`${x.attribute} ${x.operator} ${x.value}`,'f')).join('') : '<span class="empty">no filter</span>';
  return `<div class="chiprow chips">${m}</div><div class="chiprow chips">${d}</div><div class="chiprow chips">${f}</div>`;
}

function renderAnswer(r){
  const cols=r.columns, rows=r.rows, chart=r.chart;
  if(chart==='single_number' && rows.length===1 && rows[0].length===1){
    return `<div class="answer"><p class="alabel">Result</p><div class="bignum">${rows[0][0]}<small>${cols[0]}</small></div></div>`;
  }
  let bars='';
  if((chart==='bar'||chart==='line') && rows.length && isNum(rows[0][rows[0].length-1])){
    const vals=rows.map(x=>x[x.length-1]); const max=Math.max(...vals,0)||1;
    bars = rows.map(x=>{ const v=x[x.length-1]; const lab=x.slice(0,-1).join(' · ');
      return `<div class="bar"><span class="lab" title="${lab}">${lab}</span>
              <span class="track"><span class="fill" style="width:${(v/max*100).toFixed(1)}%"></span></span>
              <span class="val">${v}</span></div>`; }).join('');
    bars = `<div class="bars">${bars}</div>`;
  }
  const head = cols.map((c,i)=>`<th class="${isNum(rows[0]?.[i])?'num':''}">${c}</th>`).join('');
  const body = rows.map(x=>'<tr>'+x.map(v=>`<td class="${isNum(v)?'num':''}">${v}</td>`).join('')+'</tr>').join('');
  return `<div class="answer"><p class="alabel">Result${chart!=='table'?' · '+chart:''}</p>${bars}
          <table><thead><tr>${head}</tr></thead><tbody>${body}</tbody></table></div>`;
}

function renderVerify(idx, turn){
  if(turn.verdict){
    const cls = turn.verdict==='correct'?'ok':'bad';
    const extra = turn.reason ? ' · '+turn.reason : '';
    return `<div><span class="verdict ${cls}">${turn.verdict}${extra}</span></div>`;
  }
  return `<div>
    <div class="verify">
      <span class="vq">Is this query correct?</span>
      <button class="vbtn ok" onclick="verify(${idx},'correct')">Correct</button>
      <button class="vbtn bad" onclick="showReason(${idx})">Incorrect</button>
      <span id="rw${idx}" class="hide">
        <select id="rs${idx}">__REASONS__</select>
        <button class="vbtn bad" onclick="verify(${idx},'incorrect')">Log</button>
      </span>
    </div>
    <textarea class="note" id="nt${idx}" placeholder="optional note: what the right query should have been"></textarea>
  </div>`;
}

function renderTurn(turn, idx){
  let html = `<div class="turn" id="turn${idx}"><div class="userpill">${turn.question}</div><div class="clearfix"></div>`;
  if(!turn.res){
    html += `<div class="thinking"><span class="spin"></span>Thinking…</div></div>`;
    return html;
  }
  if(turn.res.error){
    html += `<div class="decline">Something broke: ${turn.res.error}</div></div>`;
    return html;
  }
  const r = turn.res;
  // step 1: grounding
  const voc = `<div class="voc">Grounded in ${META.metric_refs.length} metrics and ${META.dim_refs.length} dimensions.<br>`+
              META.metric_refs.map(m=>`<code>${m}</code>`).join(' ')+'<br>'+
              META.dim_refs.map(d=>`<code>${d}</code>`).join(' ')+'</div>';
  html += `<div class="steps">`;
  html += stepEl('Read the model', '', false, voc);
  // step 2: chose query (open)
  html += stepEl('Chose the query', '', true, renderQueryBody(r.agent));
  // step 3: validate + run OR decline
  if(r.declined){
    html += stepEl('Validated', 'declined', true,
      `<div class="decline">Not runnable against the model:<ul>${r.errors.map(e=>`<li>${e}</li>`).join('')}</ul></div>`, 'bad');
    html += `</div>`;
  }else{
    html += stepEl('Ran the query', r.chart, false, `<pre>${r.sql.replace(/</g,'&lt;')}</pre>`);
    html += `</div>`;
    html += renderAnswer(r);
  }
  html += renderVerify(idx, turn);
  html += `</div>`;
  return html;
}

function render(){
  const empty = turns.length===0;
  $('#hero').style.display = empty ? 'block' : 'none';
  $('#turns').style.display = empty ? 'none' : 'block';
  $('#composer').style.display = empty ? 'none' : 'block';
  $('#turns').innerHTML = turns.map(renderTurn).join('');
  $('#hist').innerHTML = turns.map((t,i)=>`<button class="histitem" onclick="jump(${i})">${t.question}</button>`).reverse().join('');
  const s=$('#stream'); s.scrollTop = s.scrollHeight;
}
function jump(i){ const el=$('#turn'+i); if(el) el.scrollIntoView({behavior:'smooth'}); }
function showReason(idx){ $('#rw'+idx).classList.remove('hide'); }

async function verify(idx, verdict){
  const turn = turns[idx];
  turn.verdict = verdict;
  turn.reason = verdict==='incorrect' ? ($('#rs'+idx)?.value || null) : null;
  turn.note = $('#nt'+idx)?.value.trim() || null;
  const rec = {question:turn.question, verdict, reason:turn.reason, note:turn.note,
               query:turn.res.agent, declined:turn.res.declined, sql:turn.res.sql||null};
  const res = await (await fetch('/verify',{method:'POST',headers:{'Content-Type':'application/json'},
                     body:JSON.stringify(rec)})).json();
  $('#vcount').textContent = res.count;
  render();
}

async function renderLog(){
  const items = await (await fetch('/log')).json();
  $('#logbox').innerHTML = items.map(it=>{
    const cls = it.verdict==='correct'?'ok':'bad';
    const q = (it.query?.metrics||[]).join(', ') + (it.query?.dimensions?.length?' by '+it.query.dimensions.join(', '):'');
    const reason = it.reason?`<div class="logreason">${it.reason}${it.note?' — '+it.note:''}</div>`:'';
    return `<div class="logrow"><span class="verdict ${cls}">${it.verdict}</span>
      <span class="logq"><div class="qt">${it.question}</div><div class="logmeta">${q||'—'}</div>${reason}</span>
      <span class="logmeta">${it.ts||''}</span></div>`;
  }).join('') || '<p class="empty">No verdicts yet.</p>';
}

boot();
</script>
</body>
</html>"""

PAGE = PAGE.replace("__REASONS__",
                    "".join(f'<option>{r}</option>' for r in FAIL_REASONS))


if __name__ == "__main__":
    print(f"Query bench on http://127.0.0.1:5000  (mode={AGENT_MODE})")
    app.run(port=5000, debug=False)
