# -*- coding: utf-8 -*-
"""
校验数据是否符合 tree_spec（自解释：报错即给修法）。
用法：python validate.py --data <jsonl>
"""
import json, sys, argparse
sys.stdout.reconfigure(encoding="utf-8", errors="replace")
ap = argparse.ArgumentParser(); ap.add_argument("--data", required=True); a = ap.parse_args()
rows = [json.loads(l) for l in open(a.data, encoding="utf-8") if l.strip()]
errs, warns = [], []
series2skus = {}
for r in rows:
    e, tp = r.get("entity", ""), r.get("tree_path", "")
    segs = [s.strip() for s in tp.split(">") if s.strip()]
    if not segs or segs[0] != "华为":
        errs.append(f"[{e}] tree_path 不以'华为'开头 → {tp}")
    if segs and segs[-1] == e:
        errs.append(f"[{e}] tree_path 末尾就是实体名（应去掉）→ 改：tree_path 到'系列'为止，entity 单独给")
    for i in range(len(segs) - 1):
        if segs[i].endswith("系列") and segs[i+1].endswith("系列"):
            errs.append(f"[{e}] 相邻两层都'系列'（{segs[i]} > {segs[i+1]}）→ 跑 normalize_tree.py 合并")
    if len(segs) < 3:
        warns.append(f"[{e}] 层数偏少（{len(segs)}）：{tp}")
    series2skus.setdefault(tp, []).append(e)
# 同系列一致性（tree_path 相同即同系列，天然一致；这里查"实体重名/多树")
from collections import Counter
dupe = [x for x, c in Counter(r.get("entity") for r in rows).items() if c > 1]
if dupe: errs.append(f"实体重名（同一 SKU 出现多次）：{dupe[:5]}")
print(f"校验 {len(rows)} 条：错误 {len(errs)}，警告 {len(warns)}，系列数 {len(series2skus)}")
for x in errs[:40]: print("  ✗", x)
for x in warns[:40]: print("  ⚠", x)
if not errs: print("  ✅ 全部符合 tree_spec")
