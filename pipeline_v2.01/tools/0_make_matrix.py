# -*- coding: utf-8 -*-
"""大表生成 v2：按【产线 × 层级】出表。空表=schema，填满=三元组。
用法：python 0_make_matrix.py --title 耳机 --data input/耳机/数据.jsonl [--nodes nodes.jsonl] [--schema schema_耳机.csv] --outdir input/耳机/大表
产出：
  大表_<title>_产品级.csv   行=产品(SPU)，列=产品级谓语
  大表_<title>_系列级.csv   行=系列节点，列=系列级谓语(命名后缀/别名/全称特性…)
  模板_<title>_{产品级,系列级}.csv   同列同行的【空表 = schema】(只留表头/行名，留白待填)
"""
import json, os, sys, csv, argparse
from collections import Counter
sys.stdout.reconfigure(encoding="utf-8", errors="replace")
ap = argparse.ArgumentParser()
ap.add_argument("--title", required=True); ap.add_argument("--outdir", required=True)
ap.add_argument("--data", default=""); ap.add_argument("--nodes", default=""); ap.add_argument("--schema", default="")
ap.add_argument("--rename", default="", help="旧列=新列;旧列2=新列（分号分隔，同目标会合并）")
a = ap.parse_args()
RENAME = {}
for kv in (a.rename or "").split(";"):
    if "=" in kv:
        o, n = kv.split("=", 1); RENAME[o.strip()] = n.strip()
def rr(x): return RENAME.get(x, x)
NODE_DEFAULT = ["命名后缀", "命名排除", "系列别名", "系列定位", "全称特性", "代际命名规则", "共享平台/芯片"]
def is_node_rel(r): return any(k in r for k in ("命名", "别名", "系列", "全称", "代际", "共享"))

# schema（若有）：关系 -> 适用层级
schema_lvl = {}
if a.schema and os.path.exists(a.schema):
    with open(a.schema, encoding="utf-8-sig", newline="") as f:
        for r in csv.DictReader(f):
            if r.get("关系"): schema_lvl[r["关系"]] = r.get("适用层级", "")

rows = [json.loads(l) for l in open(a.data, encoding="utf-8") if l.strip()] if a.data else []
nodes = [json.loads(l) for l in open(a.nodes, encoding="utf-8") if l.strip()] if (a.nodes and os.path.exists(a.nodes)) else []
node_facts = {}
for n in nodes:
    node_facts[n["path"]] = {f["relation"]: f["value"] for f in n.get("facts", []) if f.get("relation")}

# 列拆分
freq = Counter()
for r in rows:
    for t in r.get("triples", []): freq[rr(t["relation"])] += 1
if schema_lvl:
    prod_cols = [c for c in schema_lvl if "系列" not in schema_lvl[c] and "代" not in schema_lvl[c]]
    for c, _ in freq.most_common():
        if c not in prod_cols and not is_node_rel(c): prod_cols.append(c)   # 数据里多出的（未进 schema）
    ser_cols = [c for c in schema_lvl if ("系列" in schema_lvl[c] or "代" in schema_lvl[c])] or NODE_DEFAULT
else:
    prod_cols = [c for c, _ in freq.most_common() if not is_node_rel(c)]
    ser_cols = NODE_DEFAULT
ser_cols = [c for c in ser_cols if c not in prod_cols]

# 产品级行
prows = []
for r in rows:
    cells = {}
    for t in r.get("triples", []):
        k = rr(t["relation"])
        cells.setdefault(k, [])
        if t["value"] not in cells[k]: cells[k].append(t["value"])
    prows.append({"name": r["entity"], "tp": r.get("tree_path", ""), "cells": {k: " ｜ ".join(v) for k, v in cells.items()}})
prows.sort(key=lambda x: (x["tp"], x["name"]))
# 系列级行 = 不同 tree_path（系列节点）
srows = []
seen = set()
for r in rows:
    tp = r.get("tree_path", "")
    if tp and tp not in seen:
        seen.add(tp); srows.append({"path": tp, "name": tp.split(" > ")[-1]})
srows.sort(key=lambda x: x["path"])

os.makedirs(a.outdir, exist_ok=True)
def write(path, header, data_rows, empty=False):
    with open(path, "w", encoding="utf-8-sig", newline="") as f:
        w = csv.writer(f); w.writerow(header)
        for row in data_rows: w.writerow(["" if empty else v for v in row])
P = os.path.join(a.outdir, f"大表_{a.title}_产品级.csv"); PT = os.path.join(a.outdir, f"模板_{a.title}_产品级.csv")
S = os.path.join(a.outdir, f"大表_{a.title}_系列级.csv"); ST = os.path.join(a.outdir, f"模板_{a.title}_系列级.csv")
write(P, ["产品", *prod_cols, "归属"], [[r["name"], *[r["cells"].get(c, "") for c in prod_cols], r["tp"]] for r in prows])
write(PT, ["产品", *prod_cols, "归属"], [[r["name"], *["" for _ in prod_cols], r["tp"]] for r in prows], empty=True)
write(S, ["系列", *ser_cols, "路径"], [[r["name"], *[node_facts.get(r["path"], {}).get(c, "") for c in ser_cols], r["path"]] for r in srows])
write(ST, ["系列", *ser_cols, "路径"], [[r["name"], *["" for _ in ser_cols], r["path"]] for r in srows], empty=True)
print(f"[{a.title}] 产品级 {len(prows)}行×{len(prod_cols)}列 | 系列级 {len(srows)}行×{len(ser_cols)}列 → {a.outdir}")
print(f"  列(产品级): {prod_cols}")
print(f"  列(系列级): {ser_cols}")
