# -*- coding: utf-8 -*-
"""
阶段1 · 建 mindmap：把 schema 数据（entity + tree_path）渲染成结构树。
用法：python 1_make_mindmap.py --data <数据.jsonl> --out <mindmap.txt> [--with-facts]
输出：<mindmap.txt>（ASCII 树；--with-facts 时在实体下挂 facts）
"""
import json, os, sys, argparse
sys.stdout.reconfigure(encoding="utf-8", errors="replace")
B, L, SP = "├─ ", "└─ ", "   "
def build(data):
    root = {}
    for e in data:
        segs = [s for s in e["tree_path"].split(">") if s.strip()]
        if not segs or segs[-1] != e["entity"]: segs = segs + [e["entity"]]
        node = root
        for s in segs: node = node.setdefault(s, {})
        node.update({t["relation"]: t["value"] for t in e["triples"]})
    return root
def render(node, with_facts, prefix=""):
    lines = []; items = list(node.items())
    for i, (name, child) in enumerate(items):
        last = i == len(items) - 1; conn = L if last else B; nxt = prefix + (SP if last else "│  ")
        is_ent = isinstance(child, dict) and any(not isinstance(v, dict) for v in child.values())
        lines.append(prefix + conn + name)
        if isinstance(child, dict):
            if is_ent and with_facts:
                facts = list(child.items())
                for j, (r, v) in enumerate(facts):
                    lines.append(nxt + (L if j == len(facts) - 1 else B) + f"{r}: {v}")
            elif not is_ent or with_facts:
                lines.extend(render(child, with_facts, nxt))
    return lines
ap = argparse.ArgumentParser(); ap.add_argument("--data", required=True); ap.add_argument("--out", required=True)
ap.add_argument("--with-facts", action="store_true"); a = ap.parse_args()
data = [json.loads(l) for l in open(a.data, encoding="utf-8") if l.strip()]
tree = build(data)
txt = "\n".join(render(tree, a.with_facts))
os.makedirs(os.path.dirname(os.path.abspath(a.out)), exist_ok=True)
open(a.out, "w", encoding="utf-8").write(txt)
print("写出", a.out, "｜实体", len(data))
print(txt[:600])
