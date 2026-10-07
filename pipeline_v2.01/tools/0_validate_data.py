# -*- coding: utf-8 -*-
"""校验数据是否对齐树：python 0_validate_data.py --data <数据.jsonl> --tree <tree.json>"""
import json, sys, argparse
sys.stdout.reconfigure(encoding="utf-8", errors="replace")
ap = argparse.ArgumentParser(); ap.add_argument("--data", required=True); ap.add_argument("--tree", required=True); a = ap.parse_args()
tree = json.load(open(a.tree, encoding="utf-8"))
paths, children = set(), {}
def walk(n, prefix):
    path = (prefix + " > " + n["name"]) if prefix else n["name"]; paths.add(path)
    children[path] = {c["name"] for c in n.get("children", [])}
    for c in n.get("children", []): walk(c, path)
walk(tree, "")
rows = [json.loads(l) for l in open(a.data, encoding="utf-8") if l.strip()]
errs = []
for r in rows:
    e, tp = r.get("entity", ""), r.get("tree_path", "")
    if not e or e != e.strip(): errs.append(f"entity 空/带空格: 『{e}』")
    if tp not in paths: errs.append(f"[{e}] tree_path 不在树里: {tp}")
    elif e not in children.get(tp, set()): errs.append(f"[{e}] entity 不是 tree_path 的子节点: {tp} > {e}")
    if not r.get("triples"): errs.append(f"[{e}] triples 为空")
    for t in r.get("triples", []):
        if not t.get("relation") or t.get("value") in (None, ""): errs.append(f"[{e}] triple 缺 relation/value")
print(f"校验数据 {len(rows)} 条：错误 {len(errs)}")
for x in errs[:50]: print("  ✗", x)
if not errs: print("  ✅ 数据与树对齐")
