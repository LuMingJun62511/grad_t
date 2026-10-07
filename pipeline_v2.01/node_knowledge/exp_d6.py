# -*- coding: utf-8 -*-
"""D-6 A/B 实验：同一知识结构，只变【推理】段写法
   A 通用（现状 4_gen_cot 的问法）  vs  B 按题型分步（D-6）
   产物：out/d6/cot_a.jsonl、cot_b.jsonl、compare.html"""
import json, os, sys, re, time, urllib.request
sys.stdout.reconfigure(encoding="utf-8", errors="replace")
BASE = os.environ.get("ANTHROPIC_BASE_URL", "").rstrip("/")
KEY = os.environ.get("ANTHROPIC_AUTH_TOKEN", "")
MODEL = os.environ.get("DS_MODEL", "deepseek-v4-flash")
HERE = os.path.dirname(os.path.abspath(__file__))
MATE = os.path.join(HERE, "out", "mate"); META = os.path.join(MATE, "_meta")
OUTD = os.path.join(HERE, "out", "d6"); os.makedirs(OUTD, exist_ok=True)

def call(p, max_tokens=600):
    for i in range(3):
        try:
            req = urllib.request.Request(BASE + "/v1/messages",
                data=json.dumps({"model": MODEL, "max_tokens": max_tokens, "temperature": 0.3,
                                 "thinking": {"type": "disabled"},
                                 "system": "你是华为产品领域专家，只依据给定知识写推理，不引入外部信息。",
                                 "messages": [{"role": "user", "content": p}]}).encode(),
                headers={"Content-Type": "application/json", "x-api-key": KEY,
                         "Authorization": "Bearer " + KEY, "anthropic-version": "2023-06-01"})
            with urllib.request.urlopen(req, timeout=90) as r:
                d = json.loads(r.read().decode())
            return "".join(b.get("text", "") for b in d.get("content", [])).strip()
        except Exception:
            if i < 2: time.sleep(2*(i+1)); continue
            return ""

data = [json.loads(l) for l in open(os.path.join(META, "数据.jsonl"), encoding="utf-8") if l.strip()]
ent = {}
for e in data:
    fs = {}
    for t in e["triples"]: fs.setdefault(t["relation"], []).append(t["value"])
    ent[e["entity"]] = {"tp": e["tree_path"], "facts": fs}
nodes = [json.loads(l) for l in open(os.path.join(META, "nodes_d6.jsonl"), encoding="utf-8") if l.strip()]
ENT_NAMES = sorted(ent.keys(), key=len, reverse=True)

def ents_in(text):
    t = text; out = []
    for n in ENT_NAMES:            # 长名优先，命中后从文本移除，避免"Mate 80 Pro"误带"Mate 80"
        if n in t:
            out.append(n); t = t.replace(n, " ")
    return out

def rel_in_q(name, q):
    for r in ent[name]["facts"]:
        if r in q: return r
    return ""

def struct_for(es, node_paths):
    lines = []
    for e in es:
        s = "; ".join(f"{r}={'/'.join(v)}" for r, v in ent[e]["facts"].items())
        lines.append(f"- {e}（{ent[e]['tp']}）：{s}")
    for path in node_paths:
        for n in nodes:
            if n["path"] == path:
                s = "; ".join(f"{f['relation']}={f['value']}" for f in n["facts"])
                lines.append(f"- 〔系列节点〕{n['path'].split(' > ')[-1]}：{s}（语义：规则）")
    return "\n".join(lines)

def steps_for(typ, q, a, hops):
    es = ents_in(q)
    if typ == "1-1":
        e = es[0] if es else "（目标机型）"; r = rel_in_q(e, q) if es else "（题目关系）"
        return [f"1) 定位：在知识结构中找到「{e}»", f"2) 取值：读取其关系「{r}」的值", f"3) 结论：答案为「{a}」"]
    if typ == "1-2":
        e = es[0] if es else "（目标机型）"
        return [f"1) 定位：找到「{e}」", f"2) 归属：读 is_a，确定它属于「{a}」", "3) 结论：由此得答案"]
    if typ == "2-3":
        e1 = es[0] if es else "A"; e2 = es[1] if len(es) > 1 else "B"
        r = rel_in_q(e1, q) or rel_in_q(e2, q) or "（题目关系）"
        return [f"1) 分别定位「{e1}」与「{e2}」", f"2) 各取关系「{r}」的值", f"3) 比较两者差异 → 「{a}」"]
    if typ == "L2":
        return ["1) 定位：找到系列节点的规则知识（命名后缀 / 命名排除）", "2) 判定：用该规则判断题目所述情况", f"3) 结论：{a}"]
    if typ == "3-1":
        feas = []
        to = ""; rel = "节点知识"
        for h in (hops or []):
            if h.get("do") == "定位": feas = h.get("from", []); to = h.get("to", "")
            if h.get("do") == "取父层知识": rel = h.get("rel", rel)
        ft = "、".join(feas) if isinstance(feas, list) else str(feas)
        return [f"1) 定位：按特征「{ft}」在候选中锁定唯一机型「{to}」",
                "2) 上溯：由 is_a 逐层上溯到它所属的系列「Mate 系」",
                f"3) 取父层知识：读取系列的「{rel}」",
                f"4) 结论：「{a}」"]
    return ["1) 定位相关分支", "2) 读取相关值", f"3) 结论：{a}"]

TYPES = ["1-1", "1-2", "2-3", "L2", "3-1"]
qs = []
for t in TYPES:
    p = os.path.join(MATE, f"{t}.jsonl")
    if not os.path.exists(p): continue
    rr = [json.loads(l) for l in open(p, encoding="utf-8") if l.strip()]
    for x in rr: x["type"] = x.get("type") or t
    qs += rr[:2]
print("样本", len(qs), "题：", [q["type"] for q in qs])

rows = []
for k, q in enumerate(qs, 1):
    typ = q.get("type", ""); qq = q.get("q"); aa = q.get("a"); hops = (q.get("_meta") or {}).get("hops")
    es = ents_in(qq) + ents_in(aa)
    node_paths = []
    if typ in ("L2", "L1", "3-1") or (typ == "3-1"): node_paths = ["华为 > 手机 > Mate 系"]
    if typ == "3-1": es_all = list(ent.keys())
    else: es_all = list(dict.fromkeys(es))
    struct = struct_for(es_all, node_paths)
    steps = steps_for(typ, qq, aa, hops)
    pA = f"【问题】{qq}\n【已知答案】{aa}\n【知识结构】\n{struct}\n请用一两句话给出推理：先定位结构分支，再引用要点，得出结论。只输出推理文字。"
    pB = (f"【问题】{qq}\n【已知答案】{aa}\n【知识结构】\n{struct}\n"
          f"请**严格按下列步骤**写推理，每步单独一行、以「1) 2) 3)」开头，只依据给定知识，不引入外部信息：\n" + "\n".join(steps))
    rA = call(pA); rB = call(pB) or "\n".join(steps)
    respA = f"【知识结构】\n{struct}\n【推理】\n{rA}\n【答案】\n{aa}"
    respB = f"【知识结构】\n{struct}\n【推理（按题型分步）】\n{rB}\n【答案】\n{aa}"
    rows.append({"type": typ, "question": qq, "answer": aa, "struct": struct,
                 "reason_a": rA, "reason_b": rB, "steps": steps,
                 "response_a": respA, "response_b": respB})
    print(f"[{k}] {typ} 完成")

with open(os.path.join(OUTD, "cot_a.jsonl"), "w", encoding="utf-8") as f:
    for r in rows: f.write(json.dumps({"question": r["question"], "answer": r["answer"], "response": r["response_a"], "_meta": {"type": r["type"]}}, ensure_ascii=False) + "\n")
with open(os.path.join(OUTD, "cot_b.jsonl"), "w", encoding="utf-8") as f:
    for r in rows: f.write(json.dumps({"question": r["question"], "answer": r["answer"], "response": r["response_b"], "_meta": {"type": r["type"]}}, ensure_ascii=False) + "\n")

def esc(s): return (s or "").replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;").replace("\n", "<br>")
h = ["<!doctype html><meta charset='utf-8'><title>D-6 CoT A/B 对比</title>",
     "<style>body{font-family:system-ui,'Segoe UI',sans-serif;margin:16px}table{border-collapse:collapse;width:100%}",
     "th,td{border:1px solid #ccc;padding:8px;vertical-align:top;font-size:13px}th{background:#f2f2f2;position:sticky;top:0}",
     "td.q{width:22%}td.a{width:39%}td.b{width:39%}h1{font-size:18px}.t{color:#888;font-size:12px}</style>",
     "<h1>D-6 · CoT「通用写法」 vs 「按题型分步」</h1>",
     "<p class='t'>同一【知识结构】；A=现在的通用推理（4_gen_cot 的问法），B=按题型推理路径分步。</p>",
     "<table><tr><th>题型 / 问题</th><th>A · 通用推理</th><th>B · 按题型分步推理</th></tr>"]
for r in rows:
    h.append(f"<tr><td class='q'><b>{esc(r['type'])}</b><br>{esc(r['question'])}<div class='t'>答案：{esc(r['answer'])}</div></td>"
             f"<td class='a'>{esc(r['reason_a'])}</td><td class='b'>{esc(r['reason_b'])}</td></tr>")
h.append("</table>")
open(os.path.join(OUTD, "compare.html"), "w", encoding="utf-8").write("\n".join(h))
print("写出", os.path.join(OUTD, "compare.html"))
