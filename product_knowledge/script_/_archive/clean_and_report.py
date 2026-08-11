"""
1. 清理: 去麦芒, nova10以前, P50以前
2. 生成 product_tree_insight.md
"""
import json
from collections import defaultdict

PATH = r"D:\新建文件夹\grad_t\product_knowledge\data_\华为产品属性_扩展.json"
OUT_JSON = r"D:\新建文件夹\grad_t\product_knowledge\data_\华为产品属性.json"
OUT_MD = r"D:\新建文件夹\grad_t\product_knowledge\data_\product_tree_insight.md"

with open(PATH, "r", encoding="utf-8") as f:
    products = json.load(f)

original = len(products)

# 过滤规则
def keep(p):
    # 去麦芒
    if p["series"] == "麦芒系列":
        return False
    # nova 10以前
    if p["series"] == "nova 系列":
        sub = p.get("sub_series", "")
        for old in ["nova 7", "nova 8", "nova 9"]:
            if old in sub:
                return False
    # P50及以前
    if p["series"] == "Pura 系列":
        sub = p.get("sub_series", "")
        for old in ["P40", "P50"]:
            if old in sub:
                return False
    return True

filtered = [p for p in products if keep(p)]
removed = original - len(filtered)

# ================================================================
# 生成 insight 文档
# ================================================================

# 统计
cat_series = defaultdict(lambda: defaultdict(list))
cat_count = defaultdict(int)
for p in filtered:
    cat = p["category"]
    ser = p["series"]
    cat_count[cat] += 1
    cat_series[cat][ser].append(p)

lines = []
lines.append("# 华为产品树 Insight")
lines.append("")
lines.append(f"> 数据截至 2026 年 8 月 | {len(filtered)} 个产品 | {len(cat_series)} 个品类 | {sum(len(s) for s in cat_series.values())} 个系列")
lines.append(f"> 清理: 去除麦芒系列 ({sum(1 for p in products if p['series']=='麦芒系列')}个)、nova 10以前、P50以前 (共移除 {removed} 个)")
lines.append("")
lines.append("---")
lines.append("")
lines.append("## 品类总览")
lines.append("")
lines.append("| 品类 | 产品数 | 系列数 | 系列列表 |")
lines.append("|------|--------|--------|----------|")
for cat in sorted(cat_count.keys(), key=lambda c: cat_count[c], reverse=True):
    sers = list(cat_series[cat].keys())
    lines.append(f"| {cat} | {cat_count[cat]} | {len(sers)} | {', '.join(sers)} |")
lines.append("")

lines.append("---")
lines.append("")
lines.append("## 各品类详情")
lines.append("")

for cat in sorted(cat_count.keys(), key=lambda c: cat_count[c], reverse=True):
    lines.append(f"### {cat} ({cat_count[cat]} 个产品)")
    lines.append("")

    for ser in sorted(cat_series[cat].keys()):
        spus = cat_series[cat][ser]
        # 按 sub_series 分组
        by_sub = defaultdict(list)
        for p in spus:
            sub = p.get("sub_series") or "(无子系列)"
            by_sub[sub].append(p)

        lines.append(f"#### {ser} ({len(spus)} 个)")
        lines.append("")

        if len(by_sub) == 1 and "(无子系列)" in by_sub:
            # 无子系列, 直接列产品
            lines.append("| 产品名 | 价格 | 代际 | 核心卖点 |")
            lines.append("|--------|------|------|----------|")
            for p in spus:
                price = p.get("price", "-")
                gen = p.get("generation", "-")
                tps = "、".join(p.get("talking_points", [])[:3])
                lines.append(f"| {p['name']} | {price} | {gen} | {tps} |")
            lines.append("")
        else:
            # 有子系列, 按子系列分组
            for sub in sorted(by_sub.keys()):
                sub_spus = by_sub[sub]
                lines.append(f"**{sub}** ({len(sub_spus)} 个)")
                lines.append("")
                lines.append("| 产品名 | 价格 | 代际 | 定位 |")
                lines.append("|--------|------|------|------|")
                for p in sub_spus:
                    price = p.get("price", "-")
                    gen = p.get("generation", "-")
                    pos = "、".join(p.get("positioning", [])[:2])
                    lines.append(f"| {p['name']} | {price} | {gen} | {pos} |")
                lines.append("")
    lines.append("---")
    lines.append("")

# 代际时间线
lines.append("## 代际时间线 (2020-2026)")
lines.append("")
lines.append("```")
# 按品类和系列整理时间线
phone_series = cat_series.get("手机", {})
for ser_name in ["Mate 系列", "Pura 系列", "折叠屏", "nova 系列", "畅享系列"]:
    if ser_name in phone_series:
        spus = phone_series[ser_name]
        by_sub = defaultdict(list)
        for p in spus:
            by_sub[p.get("sub_series", "")].append(p)
        lines.append(f"\n{ser_name}:")
        for sub in sorted(by_sub.keys()):
            count = len(by_sub[sub])
            lines.append(f"  {sub} ({count} SPU)")
lines.append("```")

lines.append("")
lines.append("---")
lines.append("")
lines.append("## 数据统计")
lines.append("")
lines.append(f"- 总产品数: {len(filtered)}")
lines.append(f"- 品类数: {len(cat_series)}")
lines.append(f"- 系列数: {sum(len(s) for s in cat_series.values())}")
lines.append(f"- 包含价格的产品: {sum(1 for p in filtered if p.get('price') and '待' not in str(p['price']))}")

# 写文件
with open(OUT_JSON, "w", encoding="utf-8") as f:
    json.dump(filtered, f, ensure_ascii=False, indent=2)

with open(OUT_MD, "w", encoding="utf-8") as f:
    f.write("\n".join(lines))

print(f"原始: {original} 个")
print(f"移除: {removed} 个 (麦芒 + nova10以前 + P50以前)")
print(f"保留: {len(filtered)} 个")
print(f"\n产品JSON → {OUT_JSON}")
print(f"Insight文档 → {OUT_MD}")

# 简要统计
for cat in sorted(cat_count.keys(), key=lambda c: cat_count[c], reverse=True):
    sers = list(cat_series[cat].keys())
    print(f"  {cat}: {cat_count[cat]} 个, {len(sers)} 系列")
