# -*- coding: utf-8 -*-
"""① 挂知识到节点（树无关）：tree.json + nodes.jsonl(按 path) → attached_tree.json"""
import json, os, sys, argparse
sys.stdout.reconfigure(encoding="utf-8", errors="replace")
ap = argparse.ArgumentParser(); ap.add_argument("--tree", required=True); ap.add_argument("--nodes", required=True); ap.add_argument("--out", required=True); a = ap.parse_args()
tree = json.load(open(a.tree, encoding="utf-8"))
nodes = {}
for l in open(a.nodes, encoding="utf-8"):
    if l.strip():
        n = json.loads(l); nodes[n["path"]] = n
def walk(node, prefix):
    path = (prefix + " > " + node["name"]) if prefix else node["name"]
    node["_path"] = path
    if path in nodes:
        node["facts"] = nodes[path]["facts"]; node["level"] = nodes[path].get("level", node.get("type"))
        print(f"  挂载 {path} ← {len(node['facts'])} facts")
    for c in node.get("children", []): walk(c, path)
walk(tree, "")
os.makedirs(os.path.dirname(os.path.abspath(a.out)), exist_ok=True)
json.dump(tree, open(a.out, "w", encoding="utf-8"), ensure_ascii=False, indent=2)
print("写出", a.out)
