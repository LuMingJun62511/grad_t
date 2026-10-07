# -*- coding: utf-8 -*-
"""C 实验 v2：真 Mate 数据 → 叶子题 + 层级/规则题 + 分层档 + 审阅页（meta 与题分离）"""
import json, os, sys, subprocess
sys.stdout.reconfigure(encoding="utf-8", errors="replace")
HERE = os.path.dirname(os.path.abspath(__file__))
TOOLS = os.path.join(HERE, "tools")
V2 = os.path.join(os.path.dirname(HERE), "tools")          # 主链工具在上一级 pipeline_v2.01\tools
SRC = os.path.join(os.path.dirname(HERE), "_依赖", "mate80_tuples.json")  # 已随包内置，换机器可用
OUT = os.path.join(HERE, "out", "mate"); META = os.path.join(OUT, "_meta")
os.makedirs(META, exist_ok=True)

raw = json.load(open(SRC, encoding="utf-8"))
base = raw["tree_path"].strip()
series_path = " > ".join([s.strip() for s in base.split(">")][:3])
rows = []
for e in raw["entities"]:
    tp = series_path if e["level"] == "代" else base
    rows.append({"entity": e["entity"], "tree_path": tp,
                 "triples": [{"relation": t["relation"], "value": t["value"]} for t in e["triples"] if t.get("bucket", "A") == "A"]})
DATA = os.path.join(META, "数据.jsonl")
with open(DATA, "w", encoding="utf-8") as f:
    for r in rows: f.write(json.dumps(r, ensure_ascii=False) + "\n")
print("数据:", len(rows), "实体")

def build_tree(rows):
    root = {"name": "华为", "type": "公司", "children": []}; idx = {"华为": root}
    for r in rows:
        segs = [s.strip() for s in r["tree_path"].split(">") if s.strip()] + [r["entity"]]
        parent = root; pref = "华为"
        for s in segs[1:]:
            key = pref + " > " + s; node = idx.get(key)
            if node is None:
                typ = "产线" if s == "手机" else ("系列" if s == "Mate 系" else ("代" if s.endswith("系列") else "SPU"))
                node = {"name": s, "type": typ, "children": []}; parent["children"].append(node); idx[key] = node
            parent = node; pref = key
    return root
tree = build_tree(rows)
json.dump(tree, open(os.path.join(META, "tree.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=2)
NODES = os.path.join(META, "nodes.jsonl")
with open(NODES, "w", encoding="utf-8") as f:
    f.write(json.dumps({"path": series_path, "level": "系列", "facts": [
        {"relation": "命名后缀", "value": "Pro / Pro Max / RS 非凡大师", "semantics": "规则"},
        {"relation": "命名排除", "value": "Ultra", "semantics": "规则"}]}, ensure_ascii=False) + "\n")
print("series_path =", series_path)
def run(*a): subprocess.run([sys.executable, *a], check=False)
# 叶子题
run(os.path.join(V2, "0_make_suggest.py"), "--data", DATA, "--out", os.path.join(META, "出题建议.csv"))
run(os.path.join(V2, "3b_gen_questions_template.py"), "--data", DATA, "--outdir", OUT,
    "--suggest", os.path.join(META, "出题建议.csv"), "--category", "华为Mate手机")
# 层级/规则题
run(os.path.join(TOOLS, "attach.py"), "--tree", os.path.join(META, "tree.json"), "--nodes", NODES, "--out", os.path.join(META, "attached_tree.json"))
run(os.path.join(TOOLS, "gen_level_q.py"), "--tree", os.path.join(META, "attached_tree.json"), "--out", os.path.join(META, "level_q.jsonl"))
lq = [json.loads(l) for l in open(os.path.join(META, "level_q.jsonl"), encoding="utf-8")] if os.path.exists(os.path.join(META, "level_q.jsonl")) else []
for r in lq:
    t = "L1" if r["type"].startswith("L1") else ("L2" if r["type"].startswith("L2") else "L3"); r["type"] = t
for t in ("L1", "L2", "L3"):
    with open(os.path.join(OUT, f"{t}.jsonl"), "w", encoding="utf-8") as f:
        for r in lq:
            if r["type"] == t: f.write(json.dumps({"type": t, "q": r["q"], "a": r["a"]}, ensure_ascii=False) + "\n")
# 打档（D-2）
LEVEL = {"1-1": 0, "1-2": 1, "1-3": 0, "1-4": 0, "2-1": 1, "2-2": 1, "2-3": 1, "2-4": 1, "2-5": 1, "2-6": 1, "L1": 1, "L2": 2, "L3": 3}
from collections import Counter
cnt = Counter()
for fn in os.listdir(OUT):
    if not fn.endswith(".jsonl"): continue
    t = fn[:-6]; p = os.path.join(OUT, fn); rr = [json.loads(l) for l in open(p, encoding="utf-8") if l.strip()]
    with open(p, "w", encoding="utf-8") as f:
        for r in rr: r["档"] = LEVEL.get(t, 1); f.write(json.dumps(r, ensure_ascii=False) + "\n")
    cnt[t] = len(rr)
print("题型分布:", dict(cnt))
run(os.path.join(V2, "6_make_review.py"), "--pkg", OUT, "--title", "Mate手机")
print("done")
