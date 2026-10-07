# -*- coding: utf-8 -*-
"""D-6 长度实验：C = 短版（仍按题型路径，但压成一句话）；并统计 A/B/C 长度"""
import json, os, sys, time, urllib.request
sys.stdout.reconfigure(encoding="utf-8", errors="replace")
BASE = os.environ.get("ANTHROPIC_BASE_URL", "").rstrip("/")
KEY = os.environ.get("ANTHROPIC_AUTH_TOKEN", ""); MODEL = os.environ.get("DS_MODEL", "deepseek-v4-flash")
HERE = os.path.dirname(os.path.abspath(__file__))
MATE = os.path.join(HERE, "out", "mate"); META = os.path.join(MATE, "_meta")
OUTD = os.path.join(HERE, "out", "d6")

def call(p, max_tokens=300):
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
                return "".join(b.get("text", "") for b in json.loads(r.read().decode()).get("content", [])).strip()
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
def ents_in(t0):
    t = t0; out = []
    for n in ENT_NAMES:
        if n in t: out.append(n); t = t.replace(n, " ")
    return out
def rel_in_q(name, q):
    for r in ent[name]["facts"]:
        if r in q: return r
    return ""
def struct_for(es, node_paths):
    lines = []
    for e in es:
        lines.append(f"- {e}：apt " + "; ".join(f"{r}={'/'.join(v)}" for r, v in ent[e]["facts"].items()))
    for path in node_paths:
        for n in nodes:
            if n["path"] == path:
                lines.append("- 〔系列节点〕" + n["path"].split(" > ")[-1] + "：" + "; ".join(f"{f['relation']}={f['value']}" for f in n["facts"]))
    return "\n".join(lines)
def hint_for(typ, q, a, hops):
    es = ents_in(q)
    if typ == "1-1": return f"定位「{es[0] if es else '机型'}」→ 取关系「{rel_in_q(es[0],q) if es else '?'}」的值 → 结论"
    if typ == "1-2": return f"定位「{es[0] if es else '机型'}」→ 读 is_a 归属 → 结论"
    if typ == "2-3": return "分别定位两个机型 → 各取同一关系值 → 比较差异 → 结论"
    if typ == "L2": return "找到系列规则（命名后缀/命名排除）→ 判归属适用 → 否定/肯定 → 结论"
    if typ == "3-1": return "按特征定位唯一机型 → is_a 上溯到系列 → 取父层知识 → 结论"
    return "定位 → 取值 → 结论"

def load(typ): return [json.loads(l) for l in open(os.path.join(MATE, f"{typ}.jsonl"), encoding="utf-8") if l.strip()]
TYPES = ["1-1", "1-2", "2-3", "L2", "3-1"]
qs = []
for t in TYPES:
    rr = load(t); [x.__setitem__("type", x.get("type") or t) for x in rr]; qs += rr[:2]

rows = []
for q in qs:
    typ = q["type"]; qq = q["q"]; aa = q["a"]; hops = (q.get("_meta") or {}).get("hops")
    es = list(ent.keys()) if typ == "3-1" else ents_in(qq)
    np_ = ["华为 > 手机 > Mate 系"] if typ in ("L2", "L1", "3-1") else []
    struct = struct_for(es, np_)
    hint = hint_for(typ, qq, aa, hops)
    pC = (f"【问题】{qq}\n【已知答案】{aa}\n【知识结构】\n{struct}\n"
          f"请用**一句话**（不超过 60 字）写推理，按这个思路：{hint}。"
          f"只输出这一句话，不要分点、不要复述知识结构、不要重复答案原文。")
    rC = call(pC)
    rows.append({"type": typ, "question": qq, "answer": aa, "reason_c": rC})
    print(f"[{typ}] {rC[:60]}")

with open(os.path.join(OUTD, "cot_c.jsonl"), "w", encoding="utf-8") as f:
    for r in rows:
        f.write(json.dumps({"question": r["question"], "answer": r["answer"],
                            "response": f"【推理】\n{r['reason_c']}\n【答案】\n{r['answer']}", "_meta": {"type": r["type"]}}, ensure_ascii=False) + "\n")

A = [json.loads(l) for l in open(os.path.join(OUTD, "cot_a.jsonl"), encoding="utf-8")]
B = [json.loads(l) for l in open(os.path.join(OUTD, "cot_b.jsonl"), encoding="utf-8")]
def reason_len(resp):
    try:
        seg = resp.split("【推理】")[-1].split("【答案】")[0]
        if "分步）】" in resp: seg = resp.split("分步）】")[-1].split("【答案】")[0]
        return len(seg.strip())
    except Exception:
        return len(resp)
print("\n题型 | A(通用)字数 | B(分步)字数 | C(短版)字数")
for i in range(len(rows)):
    a = reason_len(A[i]["response"]); b = reason_len(B[i]["response"]); c = len(rows[i]["reason_c"])
    print(f"{rows[i]['type']} | {a} | {b} | {c}")
la = sum(reason_len(A[i]["response"]) for i in range(len(rows)))/len(rows)
lb = sum(reason_len(B[i]["response"]) for i in range(len(rows)))/len(rows)
lc = sum(len(rows[i]["reason_c"]) for i in range(len(rows)))/len(rows)
print(f"\n平均：A={la:.0f} 字  B={lb:.0f} 字  C={lc:.0f} 字")
print("A/B 平均压缩比：B/A=", round(lb/la, 2), " C/A=", round(lc/la, 2))
