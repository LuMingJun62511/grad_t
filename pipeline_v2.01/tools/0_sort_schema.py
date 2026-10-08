# -*- coding: utf-8 -*-
"""按"价值 + 可否对比"给 schema 排序（行序 = 大表列序 = 优先级）
用法：python 0_sort_schema.py --schema input/手机/schema_手机.csv [--out 覆盖]
规则：同层级内按 价值(高>中>低) → 可否对比(1>0) → 原有顺序（稳定）。
价值从「备注」里的 [价值:高/中/低] 读取（缺省=中）。
"""
import csv, re, sys, argparse
sys.stdout.reconfigure(encoding="utf-8", errors="replace")
COLS = ["关系", "值域", "口径", "适用层级", "语义", "可否对比", "备注"]
LORDER = {"SPU": 0, "代": 1, "系列": 2, "产线": 3}
VAL = {"顶": 0, "高": 1, "中": 2, "低": 3}
ap = argparse.ArgumentParser(); ap.add_argument("--schema", required=True); ap.add_argument("--out", default=""); a = ap.parse_args()
rows = list(csv.DictReader(open(a.schema, encoding="utf-8-sig", newline="")))
def val(r):
    m = re.search(r"\[价值:([顶高中低])\]", r.get("备注", "") or "")
    return VAL[m.group(1)] if m else 2
rows.sort(key=lambda r: (LORDER.get(r.get("适用层级", ""), 9), val(r), 0 if r.get("可否对比") == "1" else 1))
out = a.out or a.schema
with open(out, "w", encoding="utf-8-sig", newline="") as f:
    w = csv.DictWriter(f, fieldnames=COLS); w.writeheader(); w.writerows(rows)
order = [r["关系"] for r in rows]
print(f"排序完成 → {out}")
print("列序：", " | ".join(order))
