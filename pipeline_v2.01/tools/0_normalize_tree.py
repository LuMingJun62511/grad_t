# -*- coding: utf-8 -*-
"""
树归一：把"不伦不类"的连续 <X>系列><Y>系列 合并为 <X Y>系列。
例：华为 > 耳机 > FreeBuds 系列 > Pro 系列  →  华为 > 耳机 > FreeBuds Pro 系列
用法：python normalize_tree.py --data <jsonl> [--inplace] [--out <jsonl>]
"""
import json, sys, argparse
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

def norm_tree(segs):
    out = []
    for s in segs:
        if out and out[-1].endswith("系列") and s.endswith("系列"):
            parent = out[-1][:-2].strip()          # 去掉父的"系列"
            out[-1] = f"{parent} {s}".strip()
        else:
            out.append(s)
    return out

ap = argparse.ArgumentParser(); ap.add_argument("--data", required=True)
ap.add_argument("--inplace", action="store_true"); ap.add_argument("--out", default="")
a = ap.parse_args()
rows, changed = [], 0
for l in open(a.data, encoding="utf-8"):
    if not l.strip(): continue
    r = json.loads(l)
    segs = [s.strip() for s in r["tree_path"].split(">") if s.strip()]
    orig = segs[:]
    if segs and segs[-1] == r.get("entity"):     # 去掉末尾实体名
        segs = segs[:-1]
    nsegs = norm_tree(segs)
    if nsegs != orig:
        changed += 1
        print("  ", " > ".join(orig), " → ", " > ".join(nsegs))
        r["tree_path"] = " > ".join(nsegs)
    rows.append(r)
dst = a.data if a.inplace else (a.out or a.data.replace(".jsonl", "_norm.jsonl"))
with open(dst, "w", encoding="utf-8") as f:
    for r in rows: f.write(json.dumps(r, ensure_ascii=False) + "\n")
print(f"归一 {changed}/{len(rows)} 条 → {dst}")
