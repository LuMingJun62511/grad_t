# -*- coding: utf-8 -*-
"""按 发布时间 过滤数据（筛"某日之后的新品"）
用法：python 0_filter_since.py --data in.jsonl --since 2025-01-01 --out out.jsonl [--keep-undated]
  --keep-undated：无"发布时间"的行也保留（默认丢弃）
"""
import json, os, re, sys, argparse
sys.stdout.reconfigure(encoding="utf-8", errors="replace")
ap = argparse.ArgumentParser()
ap.add_argument("--data", required=True); ap.add_argument("--since", required=True)
ap.add_argument("--out", required=True); ap.add_argument("--keep-undated", action="store_true")
a = ap.parse_args()
sy, sm, sd = [int(x) for x in a.since.split("-")]
def date_of(r):
    for t in r.get("triples", []):
        if t["relation"] == "发布时间":
            m = re.search(r"(\d{4})年(\d{1,2})月(?:(\d{1,2})日)?", t["value"])
            if m: return (int(m.group(1)), int(m.group(2)), int(m.group(3) or 1))
    return None
rows = [json.loads(l) for l in open(a.data, encoding="utf-8") if l.strip()]
keep, und = [], 0
for r in rows:
    d = date_of(r)
    if d is None:
        if a.keep_undated: keep.append(r); und += 1
        continue
    if d >= (sy, sm, sd): keep.append(r)
os.makedirs(os.path.dirname(os.path.abspath(a.out)), exist_ok=True)
with open(a.out, "w", encoding="utf-8") as f:
    for r in keep: f.write(json.dumps(r, ensure_ascii=False) + "\n")
print(f"{a.data} → {a.out}：{len(rows)} → {len(keep)} 款（>={a.since}）｜无日期保留 {und}")
