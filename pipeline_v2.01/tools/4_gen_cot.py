# -*- coding: utf-8 -*-
"""
CoT 生成器 v3（通用：给任意品类补 CoT）
改进：★ 收紧（只高亮 本题实体 + 用到的关系；系列不再打★）
用法：python gen_cot3.py --questions Q --data D --scpt S --out O [--limit N] [--raw RAW]
  --raw: 可选，真实语料 jsonl(每行 {entity,text})，优先于 scpt 作为"相关原文"来源
"""
import os, json, re, sys, time, argparse, urllib.request
from cot_parts import assemble, parse
sys.stdout.reconfigure(encoding="utf-8", errors="replace")
BASE = os.environ.get("ANTHROPIC_BASE_URL", "").rstrip("/"); KEY = os.environ.get("ANTHROPIC_AUTH_TOKEN", "")
MODEL = os.environ.get("DS_MODEL", "deepseek-v4-flash")
B, L, SP = "├─ ", "└─ ", "   "
def call(p, retries=3):
    for i in range(retries):
        try:
            req = urllib.request.Request(BASE + "/v1/messages",
                data=json.dumps({"model": MODEL, "max_tokens": 500, "temperature": 0.3,
                                 "thinking": {"type": "disabled"},
                                 "system": "你是华为产品领域专家，只依据给定结构与原文写一小段推理，不引入外部信息。",
                                 "messages": [{"role": "user", "content": p}]}).encode(),
                headers={"Content-Type": "application/json", "x-api-key": KEY,
                         "Authorization": "Bearer " + KEY, "anthropic-version": "2023-06-01"})
            with urllib.request.urlopen(req, timeout=90) as r:
                d = json.loads(r.read().decode())
            return "".join(b.get("text", "") for b in d.get("content", [])).strip()
        except Exception:
            if i < retries - 1: time.sleep(2*(i+1)); continue
            return ""
def build_tree(data):
    """按完整 tree_path 建树；实体节点下挂 facts。"""
    root = {}
    for e in data:
        segs = [s for s in e["tree_path"].split(" > ") if s]
        if not segs or segs[-1] != e["entity"]: segs = segs + [e["entity"]]
        node = root
        for s in segs: node = node.setdefault(s, {})
        node.update({t["relation"]: t["value"] for t in e["triples"]})
    return root
def render(node, prefix="", hl_entities=frozenset(), hl_rels=frozenset()):
    """展开 hl_entities 到 fact；兄弟只列名；用到实体/关系打 ★。支持多实体。"""
    lines = []
    items = list(node.items())
    for i, (name, child) in enumerate(items):
        last = i == len(items) - 1
        conn = L if last else B
        nxt = prefix + (SP if last else "│  ")
        if isinstance(child, dict) and any(isinstance(v, dict) for v in child.values()):   # 中间层
            lines.append(prefix + conn + name)
            lines.extend(render(child, prefix=nxt, hl_entities=hl_entities, hl_rels=hl_rels))
        elif isinstance(child, dict):                                                      # 实体层
            lines.append(prefix + conn + (("★ " + name) if name in hl_entities else name))
            if name in hl_entities:
                facts = list(child.items())
                for j, (r, v) in enumerate(facts):
                    lines.append(nxt + (L if j == len(facts)-1 else B) + (("★ " if r in hl_rels else "") + f"{r}: {v}"))
        else:
            lines.append(prefix + conn + name)
    return lines

def struct_used(involved, ents):
    """紧凑版结构：只列本题涉及的实体与其全部事实（不含整棵树）"""
    lines = []
    for e in involved:
        fs = ents[e]
        lines.append("- " + e + "：" + "; ".join(f"{r}={v}" for r, v in fs.items()))
    return "\n".join(lines)

ap = argparse.ArgumentParser()
ap.add_argument("--questions", required=True); ap.add_argument("--data", required=True)
ap.add_argument("--scpt", default=""); ap.add_argument("--out", required=True)
ap.add_argument("--limit", type=int, default=0); ap.add_argument("--raw", default="")
ap.add_argument("--top", default="华为"); ap.add_argument("--second", default="")
ap.add_argument("--style", default="raw", choices=["raw", "used", "short", "steps"])
ap.add_argument("--reasonings", default="both", choices=["both", "normal", "short"])
a = ap.parse_args()
data = [json.loads(l) for l in open(a.data, encoding="utf-8") if l.strip()]
ents = {e["entity"]: {t["relation"]: t["value"] for t in e["triples"]} for e in data}
tree = build_tree(data)
from collections import defaultdict
series_of = {e["entity"]: [s for s in e["tree_path"].split(">") if s.strip()][-1] for e in data}
by_series = defaultdict(list)
for e in data: by_series[series_of[e["entity"]]].append(e["entity"])
corpus = {}
for path in [a.raw, a.scpt]:
    if path and os.path.exists(path):
        for l in open(path, encoding="utf-8"):
            r = json.loads(l)
            ent = r.get("entity") or r.get("_meta", {}).get("entity")
            txt = r.get("text") or r.get("output")
            if ent and txt and ent not in corpus: corpus[ent] = txt
qs = [json.loads(l) for l in open(a.questions, encoding="utf-8") if l.strip()]
if a.limit: qs = qs[:a.limit]
os.makedirs(os.path.dirname(os.path.abspath(a.out)), exist_ok=True)
rows = []
for q in qs:
    qq = q.get("q") or q.get("question"); aa = q.get("a") or q.get("answer"); typ = q.get("type", "")
    # 涉及实体：题面出现的 + 答案里出现的（2-1/2-2 是实体列表）
    involved = [e for e in ents if e in qq] + [e for e in ents if e in aa]
    for ser, mem in by_series.items():          # 题面出现"系列名" → 展开整系列成员（2-5）
        if ser in qq: involved += mem
    involved = list(dict.fromkeys(involved))
    if not involved: continue
    # 用到的关系：题面出现的关系名
    rels = set(r for e in involved for r in ents[e] if r in qq)
    struct = "\n".join(render(tree, hl_entities=frozenset(involved), hl_rels=frozenset(rels)))
    srcs = [corpus.get(e, "") for e in involved if corpus.get(e)]
    sent = srcs[0] if srcs else ""
    for e in involved:                              # 优先取含"用到值"的句子
        for r in rels:
            if r in ents[e]:
                v = ents[e][r].replace(" ", "")
                for s in re.split(r"[。！？]", corpus.get(e, "")):
                    if v and v in s.replace(" ", ""): sent = s.strip() + "。"; break
    reason = call(f"【问题】{qq}\n【已知答案】{aa}\n【相关原文】{sent}\n请一两句话给出推理：先定位结构分支，再引用原文要点，得出结论。只输出推理文字。")
    reason_short = ""
    if a.reasonings in ("both", "short"):
        reason_short = call(f"【问题】{qq}\n【已知答案】{aa}\n【相关原文】{sent}\n请用**一句话**（不超过 60 字）给出推理，只输出这一句，不要分点、不要重复答案原文。")
    parts = {"struct_full": struct, "struct_used": struct_used(involved, ents), "corpus": sent,
             "reasoning": reason, "reasoning_short": reason_short, "answer": aa}
    resp = assemble(parts, a.style)
    rows.append({"question": qq, "answer": aa, "response": resp, "style": a.style, "_parts": parts,
                 "_meta": {"type": typ, "entities": involved, "relations": sorted(rels)}})
    print(f"[{len(rows)}] {typ} {qq[:26]}...", flush=True)
with open(a.out, "w", encoding="utf-8") as f:
    for r in rows: f.write(json.dumps(r, ensure_ascii=False) + "\n")
print("写出", a.out, len(rows))
