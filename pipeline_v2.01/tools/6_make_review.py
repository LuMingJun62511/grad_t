# -*- coding: utf-8 -*-
"""审阅页 v2（3 页）：① 起点(schema 表 + 所有产品) ② SCPT ③ 出题
用法：python 6_make_review.py --pkg <pkg> --title <品类> [--data 数据.jsonl] [--schema schema_<产线>.csv] [--nodes nodes.jsonl]
  --data/--nodes 缺省会在 <pkg>/_meta/ 里找（数据.jsonl / nodes.jsonl）。
"""
import json, os, sys, glob, csv, argparse
from collections import Counter
sys.stdout.reconfigure(encoding="utf-8", errors="replace")
ap = argparse.ArgumentParser()
ap.add_argument("--pkg", required=True); ap.add_argument("--title", default="产品")
ap.add_argument("--out", default=""); ap.add_argument("--data", default="")
ap.add_argument("--schema", default=""); ap.add_argument("--nodes", default="")
ap.add_argument("--product-table", default=""); ap.add_argument("--series-table", default="")
a = ap.parse_args()
PKG = a.pkg; T = a.title

def find(*cands):
    for c in cands:
        if c and os.path.exists(c): return c
    return ""

DATA_P = a.data or find(os.path.join(PKG, "_meta", "数据.jsonl"), os.path.join(PKG, "数据.jsonl"))
NODE_P = a.nodes or find(os.path.join(PKG, "_meta", "nodes.jsonl"))
SCHEMA_P = a.schema or find(os.path.join(PKG, "_meta", "schema.csv"),
                            os.path.join(PKG, "schema_%s.csv" % T),
                            os.path.join(os.path.dirname(os.path.abspath(PKG)), "input", T, "schema_%s.csv" % T))

# ---- ① 起点：schema 表（列=谓语，行=产品）----
def load_schema_cols(p):
    if not p: return []
    with open(p, encoding="utf-8-sig", newline="") as f:
        return [r["关系"] for r in csv.DictReader(f) if r.get("关系")]
def build_start():
    if a.product_table and os.path.exists(a.product_table):
        pr = [r for r in csv.DictReader(open(a.product_table, encoding="utf-8-sig", newline=""))]
        cols = [c for c in pr[0].keys() if c not in ("产品", "归属")] if pr else []
        prows = [{"name": r["产品"], "tree_path": r.get("归属", ""), "cells": {c: r.get(c, "") for c in cols}} for r in pr]
        scols, srows = [], []
        if a.series_table and os.path.exists(a.series_table):
            sr = [r for r in csv.DictReader(open(a.series_table, encoding="utf-8-sig", newline=""))]
            scols = [c for c in sr[0].keys() if c not in ("系列", "路径")] if sr else []
            srows = [{"name": r["系列"], "path": r.get("路径", ""), "cells": {c: r.get(c, "") for c in scols}} for r in sr]
        return {"cols": cols, "rows": prows, "series_cols": scols, "series": srows,
                "node_facts": [], "note": "", "schema_file": os.path.basename(a.product_table)}
    if not DATA_P: return {"cols": [], "rows": [], "series_cols": [], "series": [], "node_facts": [], "note": "未提供数据（--data）"}
    rows = [json.loads(l) for l in open(DATA_P, encoding="utf-8") if l.strip()]
    freq = Counter()
    for r in rows:
        for t in r.get("triples", []): freq[t["relation"]] += 1
    scol = load_schema_cols(SCHEMA_P)
    cols = [c for c in scol if c in freq] + [c for c, _ in freq.most_common() if c not in scol]
    outrows = []
    for r in rows:
        cells = {}
        for t in r.get("triples", []):
            cells.setdefault(t["relation"], [])
            if t["value"] not in cells[t["relation"]]: cells[t["relation"]].append(t["value"])
        outrows.append({"name": r["entity"], "tree_path": r.get("tree_path", ""),
                        "cells": {k: " ｜ ".join(v) for k, v in cells.items()}})
    outrows.sort(key=lambda x: (x["tree_path"], x["name"]))
    node_facts = []
    if NODE_P:
        for l in open(NODE_P, encoding="utf-8"):
            if not l.strip(): continue
            n = json.loads(l)
            for f in n.get("facts", []):
                node_facts.append({"path": n.get("path", ""), "relation": f.get("relation", ""),
                                   "value": f.get("value", ""), "semantics": f.get("semantics", "")})
    return {"cols": cols, "rows": outrows, "series_cols": [], "series": [], "node_facts": node_facts,
            "note": "", "schema_file": os.path.basename(SCHEMA_P) if SCHEMA_P else "（无 schema 文件，列由数据推导）"}

# ---- ③ 出题 + ② SCPT ----
qs = {}
for p in sorted(glob.glob(os.path.join(PKG, "*.jsonl"))):
    t = os.path.basename(p)[:-6]
    qs[t] = [json.loads(l) for l in open(p, encoding="utf-8") if l.strip()]
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
data = {"title": T, "start": build_start(), "items": items,
        "counts": {t: len(v) for t, v in qs.items()}, "scpt": scpt}

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
main{padding:12px 14px;margin:0 auto}
.card{background:var(--card);border:1px solid var(--line);border-radius:10px;padding:10px 12px;margin:8px 0}
.tag{display:inline-block;font-size:11px;color:#fff;background:#33507a;border-radius:4px;padding:1px 7px;margin-right:8px}
.tag.src{background:#1f6f45}.tag.syn{background:#7a5a20}
.q{font-weight:600}.a{color:var(--ok)}
details{margin-top:6px}summary{cursor:pointer;color:var(--acc)}
.pre{white-space:pre-wrap;word-break:break-word;background:#0b0d11;border:1px solid var(--line);border-radius:8px;padding:8px;font:12px/1.5 Consolas,"Cascadia Mono",monospace;color:#cfd6e4;max-height:320px;overflow:auto}
.out{color:#dfe7f5;background:#10231a;border:1px solid #1f6f45;border-radius:8px;padding:8px;margin-top:6px;white-space:pre-wrap}
.wrap{overflow:auto;max-width:100%;border:1px solid var(--line);border-radius:8px}
table.sx{border-collapse:collapse;font-size:12px;min-width:100%}
table.sx th,table.sx td{border:1px solid var(--line);padding:4px 7px;vertical-align:top;white-space:nowrap}
table.sx th{position:sticky;top:0;background:#20242e;z-index:2}
td.empty{background:#141720;color:#3f4656}
td.pname{font-weight:600;background:#171b23;position:sticky;left:0}
</style></head><body>
<header>
  <h1 id="ttl">__T__ · 审阅 <span class="muted" id="stat"></span></h1>
  <div class="bar"><button class="big on" id="tabStart">① 起点</button><button class="big" id="tabS">② SCPT</button><button class="big" id="tabQ">③ 出题</button></div>
  <div class="bar" id="filters"></div>
  <div class="bar"><input id="s" placeholder="搜索…"><button id="rand">随机抽 20 条</button><button id="clear">显示全部</button></div>
</header><main id="main"></main><script>
const DATA=__DATA__; let tab='start', filter='all', smode='llm', search='';
function esc(s){return (s||'').replace(/[&<>]/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;'}[c]))}
function renderStart(){
  const S=DATA.start||{}; const main=document.getElementById('main'); main.innerHTML='';
  document.getElementById('stat').textContent=`schema 列 ${(S.cols||[]).length}｜产品 ${(S.rows||[]).length}｜来源 ${S.schema_file||''}`;
  if(!S.rows||!S.rows.length){ main.innerHTML='<div class="card muted">'+esc(S.note||'无数据')+'</div>'; return; }
  let h='<div class="card"><div class="muted">schema 表：列 = 谓语/元属性，行 = 产品（空 = 该产品缺此项）</div><div class="wrap"><table class="sx"><thead><tr><th>产品</th>';
  S.cols.forEach(c=>h+=`<th>${esc(c)}</th>`); h+='</tr></thead><tbody>';
  S.rows.forEach(r=>{ h+=`<tr><td class="pname">${esc(r.name)}<div class="muted">${esc(r.tree_path)}</div></td>`;
    S.cols.forEach(c=>{ const v=r.cells[c]||''; h+=`<td class="${v?'':'empty'}">${esc(v)}</td>`; }); h+='</tr>'; });
  h+='</tbody></table></div></div>';
  if((S.series||[]).length){
    h+='<div class="card"><div class="muted">系列级大表（行 = 系列/代节点；命名后缀/别名/全称特性…）</div><div class="wrap"><table class="sx"><thead><tr><th>系列</th>';
    (S.series_cols||[]).forEach(c=>h+=`<th>${esc(c)}</th>`); h+='<th>路径</th></tr></thead><tbody>';
    S.series.forEach(r=>{ h+=`<tr><td class="pname">${esc(r.name)}</td>`;
      (S.series_cols||[]).forEach(c=>{ const v=(r.cells||{})[c]||''; h+=`<td class="${v?'':'empty'}">${esc(v)}</td>`; });
      h+=`<td class="muted">${esc(r.path)}</td></tr>`; });
    h+='</tbody></table></div></div>';
  }
  if((S.node_facts||[]).length){
    h+='<div class="card"><div class="muted">节点级知识（挂在系列/代等中间节点）</div><div class="wrap"><table class="sx"><thead><tr><th>路径</th><th>关系</th><th>值</th><th>语义</th></tr></thead><tbody>';
    S.node_facts.forEach(f=>h+=`<tr><td>${esc(f.path)}</td><td>${esc(f.relation)}</td><td>${esc(f.value)}</td><td>${esc(f.semantics||'')}</td></tr>`);
    h+='</tbody></table></div></div>';
  }
  main.innerHTML=h;
}
function curItems(){ return DATA.items.filter(x=>(filter==='all'||x.type===filter)&&(!search||(x.q+x.a).toLowerCase().includes(search))); }
function curScpt(){ return DATA.scpt[smode].filter(x=>!search||(x.label+x.output).toLowerCase().includes(search)); }
function render(){
  if(tab==='start'){ renderStart(); return; }
  const main=document.getElementById('main'); main.innerHTML='';
  if(tab==='q'){
    let items=curItems();
    document.getElementById('stat').textContent=`共 ${DATA.items.length} 题｜显示 ${items.length}`;
    items.forEach(x=>{ const d=document.createElement('div'); d.className='card';
      d.innerHTML=`<div><span class="tag">${x.type}</span></div><div class="q">Q: ${esc(x.q)}</div><div class="a">A: ${esc(x.a)}</div>`+
        (x.cot?`<details><summary>CoT</summary><pre class="pre">${esc(x.cot)}</pre></details>`:`<div class="muted">（无 CoT）</div>`);
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
  if(tab==='start'){ f.innerHTML='<span class="muted">起点：schema 表 + 所有产品</span>'; return; }
  if(tab==='q'){ ['all',...Object.keys(DATA.counts)].forEach(t=>{ const b=document.createElement('button');
    b.textContent=t==='all'?`全部(${DATA.items.length})`:`${t}(${DATA.counts[t]})`; b.className=(filter===t?'on':'');
    b.onclick=()=>{filter=t;render();bar();}; f.appendChild(b); }); }
  else { [['llm','LLM实体版'],['leaf','规则叶子版']].forEach(([k,lab])=>{ const b=document.createElement('button');
    b.textContent=`${lab}(${DATA.scpt[k].length})`; b.className=(smode===k?'on':'');
    b.onclick=()=>{smode=k;render();bar();}; f.appendChild(b); }); }
}
document.getElementById('s').oninput=e=>{search=e.target.value.trim();render();};
document.getElementById('rand').onclick=()=>{ if(tab==='q'){const old=DATA.items;DATA.items=DATA.items.slice().sort(()=>Math.random()-.5).slice(0,20);const of=filter,os=search;filter='all';search='';render();DATA.items=old;filter=of;search=os;}
  else if(tab==='s'){const old=DATA.scpt[smode];DATA.scpt[smode]=old.slice().sort(()=>Math.random()-.5).slice(0,20);const os=search;search='';render();DATA.scpt[smode]=old;search=os;} };
document.getElementById('clear').onclick=()=>{filter='all';search='';document.getElementById('s').value='';render();bar();};
function setTab(t){tab=t;['start','s','q'].forEach(k=>{});document.getElementById('tabStart').classList.toggle('on',t==='start');
  document.getElementById('tabS').classList.toggle('on',t==='s');document.getElementById('tabQ').classList.toggle('on',t==='q');filter='all';render();bar();}
document.getElementById('tabStart').onclick=()=>setTab('start');
document.getElementById('tabS').onclick=()=>setTab('s');
document.getElementById('tabQ').onclick=()=>setTab('q');
bar();render();
</script></body></html>"""
out = a.out or os.path.join(PKG, "review_all.html")
open(out, "w", encoding="utf-8").write(HTML.replace("__DATA__", json.dumps(data, ensure_ascii=False)).replace("__T__", T))
print(f"写出 {out} ｜题 {len(items)} ｜SCPT llm/leaf {len(scpt['llm'])}/{len(scpt['leaf'])} ｜起点 {len(data['start']['rows'])} 产品 / {len(data['start']['cols'])} 列")
