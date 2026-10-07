# -*- coding: utf-8 -*-
"""② 渲染 mindmap（路径 + 祖先 facts，防臃肿）：attached_tree.json [--target 节点名] → ASCII"""
import json, sys, argparse
sys.stdout.reconfigure(encoding="utf-8", errors="replace")
ap = argparse.ArgumentParser(); ap.add_argument("--tree", required=True); ap.add_argument("--target", default=""); a = ap.parse_args()
tree = json.load(open(a.tree, encoding="utf-8"))
B, L, SP = "├─ ", "└─ ", "   "
def is_ancestor_or_self(node, target):
    """target 是否在该节点子树里"""
    if not target: return True
    if node["name"] == target: return True
    return any(is_ancestor_or_self(c, target) for c in node.get("children", []))
def render(node, prefix="", is_root=True, target=""):
    lines = []
    if is_root: lines.append(node["name"])
    kids = node.get("children", [])
    # 非根节点：先打自己（+ facts，若在 target 路径上）
    if not is_root:
        pass
    for i, c in enumerate(kids):
        last = i == len(kids) - 1; conn = L if last else B; nxt = prefix + (SP if last else "│  ")
        mark = ""
        if not target or is_ancestor_or_self(c, target):
            lines.append(prefix + conn + c["name"] + mark)
            if c.get("facts") and (not target or is_ancestor_or_self(c, target)):
                fi = c["facts"]
                for j, f in enumerate(fi):
                    sem = {"全称": "★全称", "典型": "○典型", "规则": "◇规则"}.get(f.get("semantics", ""), "")
                    lines.append(nxt + (L if j == len(fi) - 1 else B) + f"{f['relation']}: {f['value']}  {sem}")
            if c.get("children"):
                lines.extend(render(c, nxt, is_root=False, target=target))
        else:
            lines.append(prefix + conn + c["name"] + "  …")   # 与目标无关的分支：只列名
    return lines
print("\n".join(render(tree, target=a.target)))
