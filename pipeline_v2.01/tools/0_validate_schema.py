# -*- coding: utf-8 -*-
"""校验元特性表制式：python 0_validate_schema.py --schema <schema_产线.csv>
支持 v1（旧版，缺 适用层级/语义）——认得旧版，给提示不报错；v2 全列校验。"""
import csv, sys, argparse
sys.stdout.reconfigure(encoding="utf-8", errors="replace")
COLS = ["关系", "值域", "口径", "适用层级", "语义", "可否对比", "备注"]
SEM = {"事实", "全称", "典型", "规则"}
LEVELS = {"SPU", "代", "系列", "产线"}
ap = argparse.ArgumentParser(); ap.add_argument("--schema", required=True); a = ap.parse_args()
with open(a.schema, encoding="utf-8-sig", newline="") as f:
    rd = csv.DictReader(f); rows = list(rd); header = list(rd.fieldnames or [])
missing = [c for c in COLS if c not in header]
extra = [c for c in header if c not in COLS]
errs, warns = [], []
if extra: errs.append(f"未知列：{extra} → 只能 {COLS}")
v1 = set(missing) <= {"适用层级", "语义"} and bool(missing)
if v1:
    warns.append(f"检出 **v1 旧版**（缺 {missing}）→ 建议 `0_migrate_schema.py` 升级；旧版仍被认识，继续校验可用列")
elif missing:
    errs.append(f"缺列：{missing} → 期望 7 列 {COLS}")
elif header != COLS:
    warns.append(f"列序不符（期望 {COLS}，实际 {header}）→ 建议按序排列")
for i, r in enumerate(rows, 2):
    rel = (r.get("关系") or "").strip()
    if not rel: errs.append(f"第{i}行：关系为空")
    if not v1:
        sem = (r.get("语义") or "").strip()
        if sem not in SEM: errs.append(f"第{i}行[{rel}]：语义 『{sem}』 非法 → 只能 {sorted(SEM)}")
        lv = (r.get("适用层级") or "").strip()
        toks = [t.strip() for t in lv.split("|") if t.strip()]
        if not toks: errs.append(f"第{i}行[{rel}]：适用层级为空")
        for t in toks:
            if t not in LEVELS: errs.append(f"第{i}行[{rel}]：适用层级 『{t}』 非法 → 只能 {sorted(LEVELS)}")
        if sem in ("全称", "典型") and not ({"系列", "代"} & set(toks)):
            warns.append(f"第{i}行[{rel}]：语义={sem} 但适用层级={lv}（全称/典型通常在系列/代层）")
    cmp = (r.get("可否对比") or "").strip()
    if cmp not in ("0", "1"): errs.append(f"第{i}行[{rel}]：可否对比 『{cmp}』 非法 → 0/1")
    if not (r.get("值域") or "").strip(): warns.append(f"第{i}行[{rel}]：值域为空（建议列出可选范围）")
print(f"校验元特性表 {a.schema}：{len(rows)} 行，{'v1' if v1 else 'v2'}，错误 {len(errs)}，警告 {len(warns)}")
for x in errs[:50]: print("  ✗", x)
for x in warns[:50]: print("  ⚠", x)
if not errs: print("  ✅ 通过（旧版被认识 / 新版合规）")
