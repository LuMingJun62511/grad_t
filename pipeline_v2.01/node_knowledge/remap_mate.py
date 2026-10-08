# -*- coding: utf-8 -*-
"""把 Mate 原始数据映射到【手机规范化 schema】列（一次性迁移演示）
   - 拆：屏幕 → 屏幕尺寸 + 屏幕类型
   - 并：潜望长焦_*/微距长焦 → 长焦
   - 改：材质→后盖材质、中框→中框材质、传感器→主摄传感器、极限续航→续航
   - 兜底：个别款独有 → 特性
"""
import json, os, sys, csv, re
sys.stdout.reconfigure(encoding="utf-8", errors="replace")
HERE = os.path.dirname(os.path.abspath(__file__))
META = os.path.join(HERE, "out", "mate", "_meta")
IN = os.path.join(HERE, "..", "input", "手机")
SCHEMA = os.path.join(IN, "schema_手机.csv")
OUTDIR = os.path.join(IN, "大表"); os.makedirs(OUTDIR, exist_ok=True)
data = [json.loads(l) for l in open(os.path.join(META, "数据.jsonl"), encoding="utf-8") if l.strip()]
nodes = [json.loads(l) for l in open(os.path.join(META, "nodes.jsonl"), encoding="utf-8") if l.strip()]
schema = [r for r in csv.DictReader(open(SCHEMA, encoding="utf-8-sig"))]
spu_cols = [r["关系"] for r in schema if "系列" not in r["适用层级"] and "代" not in r["适用层级"]]
ser_cols = [r["关系"] for r in schema if "系列" in r["适用层级"] or "代" in r["适用层级"]]
DIRECT = {"材质": "后盖材质", "中框": "中框材质", "传感器": "主摄传感器", "极限续航": "续航",
          "潜望长焦_4X": "长焦", "潜望长焦_6.2X": "长焦", "微距长焦": "长焦"}
DROP = {"is_a", "机身", "机身设计", "微距长焦变焦"}
def cells_of(e):
    c = {}
    for t in e["triples"]:
        rel, val = t["relation"], t["value"]
        if rel == "屏幕":
            m = re.search(r"[\d.]+英寸", val)
            if m: c.setdefault("屏幕尺寸", []).append(m.group())
            rest = val.replace(m.group(), "") if m else val
            if rest: c.setdefault("屏幕类型", []).append(rest)
        elif rel == "特性":
            m = re.search(r"蓝牙([\d.]+)", val)
            if m: c.setdefault("蓝牙版本", []).append(m.group(1)); continue
            if val.startswith("WiFi"): c.setdefault("WiFi", []).append(val); continue
            if "LTPO" in val or "Hz" in val: c.setdefault("刷新率", []).append(val); continue
            if "IP" in val: c.setdefault("防水等级", []).append(val); continue
            if "卫星" in val or "北斗" in val: c.setdefault("卫星通信", []).append(val.replace("卫星通信", "").replace("双向", "")); continue
            c.setdefault("特性", []).append(val)
        elif rel in DROP: continue
        elif rel in DIRECT: c.setdefault(DIRECT[rel], []).append(val)
        else: c.setdefault(rel, []).append(val)
    return c
def w(path, header, rows, empty=False):
    with open(path, "w", encoding="utf-8-sig", newline="") as f:
        wr = csv.writer(f); wr.writerow(header)
        for r in rows: wr.writerow(["" if empty else v for v in r])
prows = sorted(data, key=lambda e: (e["tree_path"], e["entity"]))
w(os.path.join(OUTDIR, "大表_手机_产品级.csv"), ["产品", *spu_cols, "归属"],
  [[e["entity"], *[" ｜ ".join(cells_of(e).get(c, [])) for c in spu_cols], e["tree_path"]] for e in prows])
w(os.path.join(OUTDIR, "模板_手机_产品级.csv"), ["产品", *spu_cols, "归属"],
  [[e["entity"], *["" for _ in spu_cols], e["tree_path"]] for e in prows], empty=True)
nf = {n["path"]: {f["relation"]: f["value"] for f in n["facts"]} for n in nodes}
srows = sorted({e["tree_path"] for e in data})
w(os.path.join(OUTDIR, "大表_手机_系列级.csv"), ["系列", *ser_cols, "路径"],
  [[p.split(" > ")[-1], *[nf.get(p, {}).get(c, "") for c in ser_cols], p] for p in srows])
w(os.path.join(OUTDIR, "模板_手机_系列级.csv"), ["系列", *ser_cols, "路径"],
  [[p.split(" > ")[-1], *["" for _ in ser_cols], p] for p in srows], empty=True)
filled = sum(1 for e in prows for c in spu_cols if cells_of(e).get(c))
print(f"手机规范化：{len(prows)} 款 × {len(spu_cols)} 列（产品级）｜{len(srows)} 系列 × {len(ser_cols)} 列（系列级）｜已填 {filled} 格")
