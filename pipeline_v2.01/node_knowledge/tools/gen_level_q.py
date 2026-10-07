# -*- coding: utf-8 -*-
"""③ 出层级/规则题（树无关）：attached_tree.json → 题 jsonl
- L1 系列正向：{node}的{relation}是什么？ → value
- L2 命名规则：{代/子节点}会有{排除后缀}版吗？ → 不会（规则）
- L3 继承(全称)：{成员}的{relation}是什么？ → value（仅 semantics=全称 才继承；典型跳过）
"""
import json, sys, argparse
sys.stdout.reconfigure(encoding="utf-8", errors="replace")
ap = argparse.ArgumentParser(); ap.add_argument("--tree", required=True); ap.add_argument("--out", required=True); a = ap.parse_args()
tree = json.load(open(a.tree, encoding="utf-8"))
rows = []
def descendants(node, acc):
    for c in node.get("children", []):
        acc.append(c); descendants(c, acc)
    return acc
def walk(node):
    facts = node.get("facts")
    if facts:
        name = node["name"]
        # L1 系列正向（命名排除不出正向题）
        for f in facts:
            if f["relation"] == "命名排除": continue
            rows.append({"type": "L1-系列正向", "q": f"{name}的{f['relation']}是什么？", "a": f["value"], "sem": f.get("semantics")})
        # L2 命名规则：对每个"代"层子节点问"会有X版吗"
        excl = [f["value"] for f in facts if f["relation"] == "命名排除"]
        gens = [c for c in descendants(node, []) if c.get("type") in ("代",)]
        for g in gens:
            for x in excl:
                rows.append({"type": "L2-命名规则", "q": f"{g['name']}会有 {x} 版吗？",
                             "a": f"不会（{name}命名规则不含 {x}）", "sem": "规则"})
        # L3 继承：仅全称
        for f in facts:
            if f.get("semantics") != "全称": continue
            for m in descendants(node, []):
                if m.get("type") == "SPU":
                    rows.append({"type": "L3-继承(全称)", "q": f"{m['name']}的{f['relation']}是什么？", "a": f["value"], "sem": "全称"})
    for c in node.get("children", []): walk(c)
walk(tree)
import os
os.makedirs(os.path.dirname(os.path.abspath(a.out)), exist_ok=True)
with open(a.out, "w", encoding="utf-8") as f:
    for r in rows: f.write(json.dumps(r, ensure_ascii=False) + "\n")
from collections import Counter
print("写出", a.out, len(rows), dict(Counter(r["type"] for r in rows)))
for r in rows: print("  ", r["type"], "|", r["q"], "->", r["a"])
