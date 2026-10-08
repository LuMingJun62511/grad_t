# -*- coding: utf-8 -*-
"""大表 → 三元组（反向）：填满的大表 = 数据；空表 = schema
用法：python 0_matrix_to_triples.py --product 大表_耳机_产品级.csv --series 大表_耳机_系列级.csv \
        --out-data input/耳机/数据.jsonl --out-nodes input/耳机/nodes.jsonl
"""
import json, os, sys, csv, re, argparse
sys.stdout.reconfigure(encoding="utf-8", errors="replace")
ap = argparse.ArgumentParser()
ap.add_argument("--product", required=True); ap.add_argument("--series", default="")
ap.add_argument("--out-data", required=True); ap.add_argument("--out-nodes", default="")
a = ap.parse_args()
def sem(r):
    if re.search(r"全称|共享", r): return "全称"
    if re.search(r"命名|别名|代际", r): return "规则"
    if re.search(r"定位", r): return "典型"
    return "事实"
prod = [r for r in csv.DictReader(open(a.product, encoding="utf-8-sig", newline=""))]
pcols = [c for c in prod[0].keys() if c not in ("产品", "归属")] if prod else []
os.makedirs(os.path.dirname(os.path.abspath(a.out_data)), exist_ok=True)
n = 0
with open(a.out_data, "w", encoding="utf-8") as f:
    for r in prod:
        trip = []
        for c in pcols:
            v = (r.get(c) or "").strip()
            if v:
                for one in v.split(" ｜ "):
                    if one.strip(): trip.append({"relation": c, "value": one.strip()})
        f.write(json.dumps({"entity": r["产品"], "tree_path": r.get("归属", ""), "triples": trip}, ensure_ascii=False) + "\n")
        n += 1
print(f"数据 → {a.out_data}（{n} 产品）")
if a.series and a.out_nodes:
    srows = [r for r in csv.DictReader(open(a.series, encoding="utf-8-sig", newline=""))]
    scols = [c for c in srows[0].keys() if c not in ("系列", "路径")] if srows else []
    os.makedirs(os.path.dirname(os.path.abspath(a.out_nodes)), exist_ok=True)
    m = 0
    with open(a.out_nodes, "w", encoding="utf-8") as f:
        for r in srows:
            facts = [{"relation": c, "value": r[c].strip(), "semantics": sem(c)} for c in scols if (r.get(c) or "").strip()]
            if facts:
                f.write(json.dumps({"path": r["路径"], "level": "系列", "facts": facts}, ensure_ascii=False) + "\n"); m += 1
    print(f"节点知识 → {a.out_nodes}（{m} 系列节点）")
