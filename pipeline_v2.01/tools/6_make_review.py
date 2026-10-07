# -*- coding: utf-8 -*-
"""
通用审阅页生成器（一张页：出题 / SCPT 两大块）
用法：python make_review_all.py --pkg <交付包目录> --title <品类名> [--out <html>]
包目录约定：
  <pkg>/*.jsonl            → 各题型出题（文件名=题型）
  <pkg>/cot/*.jsonl        → 对应 CoT（可选）
  <pkg>/scpt/*.jsonl       → SCPT（读取 *_llm* / *_leaf* 归两类）
"""
import json, os, sys, glob, argparse
sys.stdout.reconfigure(encoding="utf-8")
ap = argparse.ArgumentParser()
ap.add_argument("--pkg", required=True); ap.add_argument("--title", default="产品")
ap.add_argument("--out", default=""); a = ap.parse_args()
PKG = a.pkg; T = a.title
qs = {}
for p in sorted(glob.glob(os.path.join(PKG, "*.jsonl"))):
    t = os.path.basename(p)[:-6]; qs[t] = [json.loads(l) for l in open(p, encoding="utf-8") if l.strip()]
cot = {}
for p in glob.glob(os.path.join(PKG, "cot", "*.jsonl")):
    cot[os.path.basename(p)[:-6]] = [json.loads(l) for l in open(p, encoding="utf-8") if l.strip()]
items = []
for t in qs:
    cmap = {c.get("question", ""): c.get("response", "") for c in cot.get(t, [])}
    for q in qs[t]:
        items.append({"type": t, "q": q.get("q", ""), "a": q.get("a", ""), "cot": cmap.get(q.get("q", ""), "")})
scpt = {"llm": [], "leaf": []}
for p in glob.glob(os.path.join(PKG, "scpt", "*.jsonl")):
    nm = os.path.basename(p)
    key = "llm" if "llm" in nm else ("leaf" if "leaf" in nm else None)
    if not key: continue
    for l in open(p, encoding="utf-8"):
        r = json.loads(l); m = r.get("_meta", {})
        scpt[key].append({"label": m.get("entity", "") + (f" · {m['relation']}" if m.get("relation") else ""),
                          "input": r.get("input", ""), "output": r.get("output", ""),
                          "prov": m.get("provenance", ""), "fb": m.get("fallback", False)})
data = {"title": T, "items": items, "counts": {t: len(v) for t, v in qs.items()}, "scpt": scpt}

HTML = r"""<!doctype html><html lang="zh"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>__T__ · 审阅</title><style>
:root{--bg:#0f1115;--card:#1a1d24;--line:#2a2f3a;--fg:#e6e9ef;--mut:#8b93a3;--acc:#4f9cff;--ok:#37c37a}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--fg);font:14px/1.6 -apple-system,Segoe UI,Roboto,"Microsoft YaHei",sans-serif}
header{position:sticky;top:0;background:#12151b;border-bottom:1px solid var(--line);padding:10px 14px;z-index:9}
h1{font-size:16px;margin:0 0 6px}.bar{display:flex;flex-wrap:wrap;gap:6px;align-items:center;margin-top:6px}
button{background:#20242e;color:var(--fg);border:1px solid var(--line);border-radius:6px;padding:4px 10px;cursor:pointer;font-size:13px}
button.on{background:var(--acc);border-color:var(--acc);color:#fff}
button.big{padding:6px 14px;font-weight:600}
input{background:#0b0d11;border:1px solid var(--line);color:var(--fg);border-radius:6px;padding:5px 9px;min-width:220px}
.muted{color:var(--mut);font-size:12px}
main{padding:12px 14px;max-width:1100px;margin:0 auto}
.card{background:var(--card);border:1px solid var(--line);border-radius:10px;padding:10px 12px;margin:8px 0}
.tag{display:inline-block;font-size:11px;color:#fff;background:#33507a;border-radius:4px;padding:1px 7px;margin-right:8px}
.tag.src{background:#1f6f45}.tag.syn{background:#7a5a20}
.q{font-weight:600}.a{color:var(--ok)}
details{margin-top:6px}summary{cursor:pointer;color:var(--acc)}
.pre{white-space:pre-wrap;word-break:break-word;background:#0b0d11;border:1px solid var(--line);border-radius:8px;padding:8px;font:12px/1.5 Consolas,"Cascadia Mono",monospace;color:#cfd6e4;max-height:320px;overflow:auto}
.out{color:#dfe7f5;background:#10231a;border:1px solid #1f6f45;border-radius:8px;padding:8px;margin-top:6px;white-space:pre-wrap}
</style></head><body>
<header>
  <h1 id="ttl">__T__ · 审阅 <span class="muted" id="stat"></span></h1>
  <div class="bar"><button class="big on" id="tabQ">出题</button><button class="big" id="tabS">SCPT</button></div>
  <div class="bar" id="filters"></div>
  <div class="bar"><input id="s" placeholder="搜索…"><button id="rand">随机抽 20 条</button><button id="clear">显示全部</button></div>
</header><main id="main"></main><script>
const DATA=__DATA__; let tab='q', filter='all', smode='llm', search='';
function esc(s){return (s||'').replace(/[&<>]/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;'}[c]))}
function curItems(){ return DATA.items.filter(x=>(filter==='all'||x.type===filter)&&(!search||(x.q+x.a).toLowerCase().includes(search))); }
function curScpt(){ return DATA.scpt[smode].filter(x=>!search||(x.label+x.output).toLowerCase().includes(search)); }
function render(){
  const main=document.getElementById('main'); main.innerHTML='';
  if(tab==='q'){
    let items=curItems();
    document.getElementById('stat').textContent=`共 ${DATA.items.length} 题｜显示 ${items.length}`;
    items.forEach(x=>{ const d=document.createElement('div'); d.className='card';
      d.innerHTML=`<div><span class="tag">${x.type}</span></div><div class="q">Q: ${esc(x.q)}</div><div class="a">A: ${esc(x.a)}</div>`+
        (x.cot?`<details><summary>CoT（结构召回+原文+推理+答案）</summary><pre class="pre">${esc(x.cot)}</pre></details>`:`<div class="muted">（无 CoT）</div>`);
      main.appendChild(d); });
  } else {
    let rows=curScpt();
    document.getElementById('stat').textContent=`SCPT ${smode==='llm'?'LLM实体版':'规则叶子版'}：${DATA.scpt[smode].length} 条｜显示 ${rows.length}`;
    rows.forEach(x=>{ const d=document.createElement('div'); d.className='card';
      const tag=x.prov==='source'?'<span class="tag src">source</span>':(x.prov?`<span class="tag syn">${x.prov}</span>`:'');
      d.innerHTML=`<div><span class="tag">${esc(x.label)}</span>${tag}${x.fb?'<span class="tag syn">补句</span>':''}</div>`+
        `<div class="muted" style="margin:4px 0">input（结构前缀）</div><div class="pre">${esc(x.input)}</div>`+
        `<div class="muted" style="margin:6px 0 0">output（正文）</div><div class="out">${esc(x.output)}</div>`;
      main.appendChild(d); });
  }
}
function bar(){
  const f=document.getElementById('filters'); f.innerHTML='';
  if(tab==='q'){ ['all',...Object.keys(DATA.counts)].forEach(t=>{ const b=document.createElement('button');
    b.textContent=t==='all'?`全部(${DATA.items.length})`:`${t}(${DATA.counts[t]})`; b.className=(filter===t?'on':'');
    b.onclick=()=>{filter=t;render();bar();}; f.appendChild(b); }); }
  else { [['llm','LLM实体版'],['leaf','规则叶子版']].forEach(([k,lab])=>{ const b=document.createElement('button');
    b.textContent=`${lab}(${DATA.scpt[k].length})`; b.className=(smode===k?'on':'');
    b.onclick=()=>{smode=k;render();bar();}; f.appendChild(b); }); }
}
document.getElementById('s').oninput=e=>{search=e.target.value.trim();render();};
document.getElementById('rand').onclick=()=>{ if(tab==='q'){const old=DATA.items;DATA.items=DATA.items.slice().sort(()=>Math.random()-.5).slice(0,20);const of=filter,os=search;filter='all';search='';render();DATA.items=old;filter=of;search=os;}
  else {const old=DATA.scpt[smode];DATA.scpt[smode]=old.slice().sort(()=>Math.random()-.5).slice(0,20);const os=search;search='';render();DATA.scpt[smode]=old;search=os;} };
document.getElementById('clear').onclick=()=>{filter='all';search='';document.getElementById('s').value='';render();bar();};
document.getElementById('tabQ').onclick=()=>{tab='q';filter='all';document.getElementById('tabQ').classList.add('on');document.getElementById('tabS').classList.remove('on');render();bar();};
document.getElementById('tabS').onclick=()=>{tab='s';smode='llm';document.getElementById('tabS').classList.add('on');document.getElementById('tabQ').classList.remove('on');render();bar();};
bar();render();
</script></body></html>"""
out = a.out or os.path.join(PKG, "review_all.html")
open(out, "w", encoding="utf-8").write(HTML.replace("__DATA__", json.dumps(data, ensure_ascii=False)).replace("__T__", T))
print("写出", out, "｜题", len(items), "｜SCPT llm/leaf", len(scpt["llm"]), len(scpt["leaf"]))
