# -*- coding: utf-8 -*-
"""④ 校验节点知识：path 是否在树里 / semantics 是否填：tree.json + nodes.jsonl"""
import json, sys, argparse
sys.stdout.reconfigure(encoding="utf-8", errors="replace")
ap = argparse.ArgumentParser(); ap.add_argument("--tree", required=True); ap.add_argument("--nodes", required=True); a = ap.parse_args()
tree = json.load(open(a.tree, encoding="utf-8"))
paths = set()
def walk(n, p):
    path = (p + " > " + n["name"]) if p else n["name"]; paths.add(path)
    for c in n.get("children", []): walk(c, path)
walk(tree, "")
errs = 0
for l in open(a.nodes, encoding="utf-8"):
    if not l.strip(): continue
    n = json.loads(l); p = n["path"]
    if p not in paths: print("✗ path 不在树里:", p); errs += 1
    for f in n.get("facts", []):
        if f.get("semantics") not in ("全称", "典型", "规则"): print("✗ semantics 非法:", p, f); errs += 1
print(f"校验 {a.nodes}：{'OK' if not errs else str(errs) + ' 个问题'}")
