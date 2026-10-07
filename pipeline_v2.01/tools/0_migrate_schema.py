# -*- coding: utf-8 -*-
"""schema v1 → v2 迁移（留痕）：python 0_migrate_schema.py --schema in.csv [--out out.csv] [--log out.migrate.md]"""
import csv, os, re, sys, argparse, datetime
sys.stdout.reconfigure(encoding="utf-8", errors="replace")
COLS = ["关系", "值域", "口径", "适用层级", "语义", "可否对比", "备注"]
NODE_RELS = {"命名后缀", "命名排除", "系列别名", "系列定位", "代际命名规则", "共享平台/芯片", "共享平台", "共享芯片", "全称特性"}
ap = argparse.ArgumentParser()
ap.add_argument("--schema", required=True)
ap.add_argument("--out", default="")
ap.add_argument("--log", default="")
a = ap.parse_args()
out = a.out or a.schema
log = a.log or (os.path.splitext(out)[0] + ".migrate.md")
with open(a.schema, encoding="utf-8-sig", newline="") as f:
    rd = csv.DictReader(f); rows = list(rd); header = list(rd.fieldnames or [])
ver = "v2" if all(c in header for c in COLS) else "v1"
print(f"读入 {a.schema} → 判定版本 {ver}（{len(rows)} 行）")
actions = []
def level_of(rel):  # 适用层级 缺省
    if rel in NODE_RELS or "系列" in rel: return "系列"
    return "SPU"
def sem_of(rel):    # 语义 缺省
    if rel in ("全称特性", "共享平台/芯片", "共享平台", "共享芯片"): return "全称"
    if rel in ("命名后缀", "命名排除", "系列别名", "代际命名规则"): return "规则"
    if rel == "系列定位": return "典型"
    return "事实"
for r in rows:
    rel = (r.get("关系") or "").strip()
    if ver == "v1" or not (r.get("适用层级") or "").strip():
        r["适用层级"] = level_of(rel)
        actions.append(f"`{rel}`：补 `适用层级={r['适用层级']}`")
    if ver == "v1" or not (r.get("语义") or "").strip():
        r["语义"] = sem_of(rel)
        actions.append(f"`{rel}`：补 `语义={r['语义']}`")
    if not (r.get("可否对比") or "").strip(): r["可否对比"] = "0"
os.makedirs(os.path.dirname(os.path.abspath(out)), exist_ok=True)
with open(out, "w", encoding="utf-8-sig", newline="") as f:
    w = csv.DictWriter(f, fieldnames=COLS); w.writeheader()
    for r in rows: w.writerow({c: (r.get(c) or "") for c in COLS})
stamp = datetime.date.today().isoformat()
with open(log, "w", encoding="utf-8") as f:
    f.write(f"# 迁移留痕：{os.path.basename(a.schema)} ({ver} → v2) · {stamp}\n\n")
    f.write(f"- 源：`{a.schema}`（{ver}，{len(rows)} 行）\n- 目标：`{out}`（v2，7 列）\n\n## 逐行动作\n")
    for x in actions: f.write(f"- {x}\n")
print(f"写出 {out}（v2，7 列）；动作 {len(actions)} 条 → 留痕 {log}")
