# -*- coding: utf-8 -*-
"""
阶段0 · 建"出题建议表"（人类可编辑，每品类一份）。
用法：python 0_make_suggest.py --data <数据.jsonl> --out <出题建议.csv>
默认用启发式给"出对比/权重"，之后人工在 CSV 里改。
"""
import json, os, sys, csv, argparse, re
from collections import Counter
sys.stdout.reconfigure(encoding="utf-8", errors="replace")
ap = argparse.ArgumentParser(); ap.add_argument("--data", required=True); ap.add_argument("--out", required=True); a = ap.parse_args()
data = [json.loads(l) for l in open(a.data, encoding="utf-8") if l.strip()]
relc = Counter()
for e in data:
    for t in e["triples"]: relc[t["relation"]] += 1
HOT = re.compile(r"处理器|芯片|内存|存储|重量|屏幕类型|续航|降噪深度|单耳重量|屏幕尺寸|充电功率|系统|操作系统|形态|售价|防水|佩戴|材质")
MID = re.compile(r"尺寸|充电|功率|材质|颜色|配色|接口|键盘|分辨率|刷新率|亮度|电池")
def grade(r, n):
    if HOT.search(r): return "高"
    if MID.search(r): return "中"
    return "低"
rows = []
for r, n in relc.most_common():
    if r == "特性": continue
    w = grade(r, n)
    rows.append({"关系": r, "出现次数": n, "出对比": 1 if w in ("高", "中") else 0, "权重": w, "备注": ""})
os.makedirs(os.path.dirname(os.path.abspath(a.out)), exist_ok=True)
with open(a.out, "w", encoding="utf-8-sig", newline="") as f:
    wr = csv.DictWriter(f, fieldnames=["关系", "出现次数", "出对比", "权重", "备注"]); wr.writeheader()
    for x in rows: wr.writerow(x)
print("写出", a.out, len(rows), "行")
