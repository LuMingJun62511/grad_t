# -*- coding: utf-8 -*-
"""大表整理分析：给出 核心/同义候选/单品独有 三类清单，辅助"整理 schema"
用法：python 0_analyze_matrix.py --data <数据.jsonl> --out <整理建议.md> --title 耳机"""
import json, os, sys, csv, argparse
from collections import Counter
sys.stdout.reconfigure(encoding="utf-8", errors="replace")
ap = argparse.ArgumentParser()
ap.add_argument("--data", required=True); ap.add_argument("--out", required=True); ap.add_argument("--title", default="")
a = ap.parse_args()
rows = [json.loads(l) for l in open(a.data, encoding="utf-8") if l.strip()]
N = len(rows)
freq = Counter()
for r in rows:
    for t in r.get("triples", []): freq[t["relation"]] += 1
cols = [c for c, _ in freq.most_common()]
core = [c for c in cols if freq[c] >= 0.8 * N]
mid = [c for c in cols if 0.4 * N <= freq[c] < 0.8 * N]
sparse = [c for c in cols if 1 < freq[c] < 0.4 * N]
uniq = [c for c in cols if freq[c] == 1]
KEYS = ["续航", "降噪", "电池", "重量", "充电", "连接", "蓝牙", "查找", "音频", "麦克风", "屏幕", "芯片",
        "内存", "存储", "尺寸", "材质", "散热", "定位", "防水", "通话", "编解码", "延迟", "空间", "佩戴", "价格", "发布"]
groups = {k: [c for c in cols if k in c] for k in KEYS}
groups = {k: v for k, v in groups.items() if len(v) > 1}
L = [f"# 大表整理建议 · {a.title}", "",
     f"- 产品 **{N}** 款，列 **{len(cols)}** 个。", "",
     "## 原则",
     "- **列 = 跨产品可比的元属性**；只有个别款有的东西 → 进 `特性`（多值），**不单开列**。",
     "- **一列一概念、一口径**（口径写进 schema 的「口径」列）。",
     "- **核心列应对所有款有值**（缺的 = 待补）。", "",
     f"## ① 核心列（≥80%，应保持必填）  {len(core)} 个"]
for c in core: L.append(f"- {c}  ({freq[c]}/{N})")
L += ["", f"## ② 同义候选组（**同概念拆成多列 → 需合并/统一口径**）  {len(groups)} 组"]
for k, v in groups.items():
    L.append(f"- **{k}**：" + " ｜ ".join(f"{c}({freq[c]}/{N})" for c in v))
L += ["", f"## ③ 单品独有列（=1/N，**多半应移入 `特性` 或判为不可得**）  {len(uniq)} 个"]
for c in uniq: L.append(f"- {c}")
L += ["", f"## ④ 中间列（40%~80%，**考虑补齐**）  {len(mid)} 个"]
for c in mid: L.append(f"- {c}  ({freq[c]}/{N})")
L += ["", f"## ⑤ 稀疏列（>1 且 <40%）  {len(sparse)} 个"]
for c in sparse: L.append(f"- {c}  ({freq[c]}/{N})")
os.makedirs(os.path.dirname(os.path.abspath(a.out)), exist_ok=True)
open(a.out, "w", encoding="utf-8").write("\n".join(L))
print(f"[{a.title}] 核心{len(core)} 同义组{len(groups)} 独有{len(uniq)} 中间{len(mid)} 稀疏{len(sparse)} → {a.out}")
