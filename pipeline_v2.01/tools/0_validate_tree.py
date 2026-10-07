# -*- coding: utf-8 -*-
"""校验树是否符合唯一制式：python 0_validate_tree.py --tree <tree.json>"""
import json, sys, argparse
sys.stdout.reconfigure(encoding="utf-8", errors="replace")
ap = argparse.ArgumentParser(); ap.add_argument("--tree", required=True); a = ap.parse_args()
ORDER = {"公司": 0, "产线": 1, "系列": 2, "代": 3, "SPU": 4}
tree = json.load(open(a.tree, encoding="utf-8"))
errs, warns = [], []
def walk(node, parent_type, prefix):
    name = node.get("name"); typ = node.get("type")
    path = (prefix + " > " + name) if prefix else name
    if not isinstance(name, str) or not name: errs.append(f"空名 @ {prefix}")
    if isinstance(name, str) and name != name.strip(): errs.append(f"名字有首尾空格: 『{name}』 @ {prefix} → 去空格")
    if isinstance(name, str) and ">" in name: errs.append(f"名字含 '>': 『{name}』 @ {prefix}")
    if typ not in ORDER: errs.append(f"type 非法: 『{typ}』 @ {path} → 用 {list(ORDER)}")
    if parent_type in ORDER and typ in ORDER and ORDER[typ] <= ORDER[parent_type]:
        warns.append(f"层级未严格下钻: {parent_type} > {typ} @ {path}")
    kids = node.get("children", [])
    if kids and not isinstance(kids, list): errs.append(f"children 非数组 @ {path}")
    seen = set()
    for c in kids or []:
        ck = c.get("name")
        if ck in seen: errs.append(f"同级重名: 『{ck}』 @ {path}")
        seen.add(ck)
        walk(c, typ, path)
walk(tree, None, "")
print(f"校验树 {a.tree}：错误 {len(errs)}，警告 {len(warns)}")
for x in errs[:50]: print("  ✗", x)
for x in warns[:50]: print("  ⚠", x)
if not errs: print("  ✅ 符合唯一树制式")
