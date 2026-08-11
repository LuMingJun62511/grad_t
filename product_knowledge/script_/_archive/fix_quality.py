"""
数据质量修复:
  1. generation 统一: 最新款/上代/旧代/即将发布
  2. 干掉 price 字段
  3. nova 7-12 芯片核实
  4. 畅享跳号说明
  5. 统一层级
"""
import json, re, sys

PATH = r"D:\新建文件夹\grad_t\product_knowledge\data_\华为产品属性.json"

with open(PATH, "r", encoding="utf-8") as f:
    data = json.load(f)

# ================================================================
# 代际映射表: 已知发布年份 → 相对 Mate 80/Pura 90 (2025-2026) 的代际
# ================================================================
SUB_SERIES_GEN = {
    # Mate 系列
    "Mate 80 系列": "最新款",
    "Mate 70 系列": "上代",
    "Mate 60 系列": "旧代",
    "Mate 50 系列": "旧代",
    "Mate 40 系列": "旧代",
    "Mate 系列即将发布": "即将发布",
    # Pura 系列 (以Pura 90为最新款)
    "Pura 90 系列": "最新款",
    "Pura 80 系列": "上代",
    "Pura 70 系列": "旧代",
    "P60 系列": "旧代",
    # 折叠屏
    "横向大折叠": None,  # 混合代际, 不统一标
    "三折叠": None,
    "阔折叠": None,
    "竖向小折叠": None,
    # nova
    "nova 16 系列": "最新款",
    "nova 15 系列": "上代",
    "nova 14 系列": "旧代",
    "nova 13 系列": "旧代",
    "nova 12 系列": "旧代",
    "nova 11 系列": "旧代",
    "nova 10 系列": "旧代",
    # 畅享
    "畅享 90 系列": "最新款",
    "畅享 80 系列": "上代",
    "畅享 70 系列": "旧代",
    "畅享 60 系列": "旧代",
    "畅享 50 系列": "旧代",
    "畅享 20 系列": "旧代",
}

# 已知真实芯片 (逐个核实)
KNOWN_CHIPS = {
    # Mate 40 系列
    "Mate 40 Pro+": "麒麟9000 5G",
    "Mate 40 Pro": "麒麟9000 5G",
    "Mate 40 RS 保时捷设计": "麒麟9000 5G",
    "Mate 40": "麒麟9000E 5G",
    # Mate 50 系列
    "Mate 50": "骁龙8+ Gen1 4G",
    "Mate 50 Pro": "骁龙8+ Gen1 4G",
    "Mate 50 RS 保时捷设计": "骁龙8+ Gen1 4G",
    # Mate 60 系列
    "Mate 60": "麒麟9000S",
    "Mate 60 Pro": "麒麟9000S",
    "Mate 60 Pro+": "麒麟9000S",
    "Mate 60 RS 非凡大师": "麒麟9000S",
    # Mate 70 系列
    "Mate 70": "麒麟9020",
    "Mate 70 Pro": "麒麟9020",
    "Mate 70 Pro 优享版": "麒麟9020A",
    "Mate 70 Pro+": "麒麟9020",
    "Mate 70 RS 非凡大师": "麒麟9020",
    "Mate 70 Air": "麒麟9020",
    # Mate 80 系列
    "Mate 80": "麒麟9020",
    "Mate 80 Pro": "麒麟9030",
    "Mate 80 Pro Max": "麒麟9030 Pro",
    "Mate 80 Pro Max 风驰版": "麒麟9030 Pro",
    "Mate 80 RS 非凡大师": "麒麟9030 Pro",
    # nova 已知芯片
    "nova 12": "麒麟9000S降频版",
    "nova 12 Pro": "麒麟9000S降频版",
    "nova 12 Ultra": "麒麟9000S降频版",
    "nova 11": "骁龙778G 4G",
    "nova 11 Pro": "骁龙778G 4G",
    "nova 11 Ultra": "骁龙778G 4G",
    "nova 10": "骁龙778G 4G",
    "nova 10 Pro": "骁龙778G 4G",
}

# ================================================================
# 修复逻辑
# ================================================================
changes = {"gen_fixed": 0, "price_removed": 0, "chip_fixed": 0, "gen_cleared": 0}
sub_gen_fixed = set()

for p in data:
    name = p["name"]
    sub = p.get("sub_series", "")

    # --- 1. 修复 generation ---
    # 折叠屏按 sub_series 类型 + SPU 名推断
    if p["series"] == "折叠屏":
        fold_gen = {
            "Mate X7": "最新款", "Mate X8": "即将发布", "Mate XT2": "即将发布",
            "Mate XTs 非凡大师": "最新款", "Pura X Max": "最新款", "Pura X": "最新款",
            "Nova Flip 2": "最新款", "Pocket 2": "上代",
            "Mate X6": "上代", "Mate X5": "旧代", "Mate X3": "旧代",
            "Mate X2": "旧代", "Mate Xs 2": "旧代",
            "Pocket S": "旧代", "Nova Flip S": "旧代",
        }
        new_gen = fold_gen.get(name)
        if new_gen and p.get("generation") != new_gen:
            p["generation"] = new_gen
            changes["gen_fixed"] += 1
    else:
        new_gen = SUB_SERIES_GEN.get(sub) if sub else None
        if new_gen and p.get("generation") != new_gen:
            p["generation"] = new_gen
            changes["gen_fixed"] += 1

    # 手动处理没有 sub_series 的产品
    if not sub or not SUB_SERIES_GEN.get(sub):
        # 看年份
        tps_str = " ".join(p.get("talking_points", []))
        name_lower = name
        if "2026" in name_lower or "2026" in tps_str:
            p["generation"] = "最新款"
            changes["gen_fixed"] += 1
        elif "2025" in name_lower:
            p["generation"] = "最新款"
            changes["gen_fixed"] += 1
        elif "2024" in name_lower:
            p["generation"] = "上代"
            changes["gen_fixed"] += 1
        elif "2023" in name_lower or "2022" in name_lower or "2021" in name_lower:
            p["generation"] = "旧代"
            changes["gen_fixed"] += 1
        # 其他情况保持旧值不动

    if p.get("generation") not in ("最新款", "上代", "旧代", "即将发布"):
        sub_gen_fixed.add(p["generation"])
        changes["gen_cleared"] += 1

    # --- 2. 干掉 price ---
    if "price" in p:
        del p["price"]
        changes["price_removed"] += 1

    # --- 3. 修复芯片 ---
    if name in KNOWN_CHIPS:
        correct_chip = KNOWN_CHIPS[name]
        tps = p.get("talking_points", [])
        # 替换或新增正确的芯片
        new_tps = []
        chip_replaced = False
        for tp in tps:
            if re.match(r"^(麒麟|骁龙|酷睿)", tp):
                if tp != correct_chip:
                    new_tps.append(correct_chip)
                    changes["chip_fixed"] += 1
                    chip_replaced = True
                else:
                    new_tps.append(tp)
                    chip_replaced = True  # 已有正确芯片, 不需补
            else:
                new_tps.append(tp)
        if not chip_replaced:
            # talking_point里没有芯片, 补一个
            new_tps.insert(0, correct_chip)
            changes["chip_fixed"] += 1
        p["talking_points"] = new_tps

    # nova 7-12 芯片: 去掉明显编造的, 保留已知信息
    if sub and any(sub.startswith(f"nova {n}") for n in ["7","8","9","10","11","12"]):
        tps = p.get("talking_points", [])
        new_tps = []
        for tp in tps:
            # 去掉模板生成的假芯片
            if re.match(r"^(骁龙680|骁龙778G|麒麟985|麒麟820)", tp) and name not in KNOWN_CHIPS:
                changes["chip_fixed"] += 1
                continue  # 丢弃不确定的芯片
            new_tps.append(tp)
        # 如果芯片被删光了, 补一个占位
        has_chip = any(re.match(r"^(麒麟|骁龙|酷睿)", tp) for tp in new_tps)
        if not has_chip and name not in ("nova 7 SE", "nova 8 SE", "nova 9 SE"):
            new_tps.insert(0, "芯片信息待核实")
            changes["chip_fixed"] += 1
        p["talking_points"] = new_tps

# ================================================================
# 最后清理: 非标准 generation 统一为 "旧代"
# ================================================================
for p in data:
    g = p.get("generation", "")
    if g not in ("最新款", "上代", "旧代", "即将发布"):
        # "上上代", "上上上代", "中间代", "在售" 全部 → "旧代"
        p["generation"] = "旧代"
        changes["gen_cleared"] += 1

# ================================================================
# 统计
# ================================================================
print(f"修复完成:")
print(f"  generation 修正: {changes['gen_fixed']} 个")
print(f"  generation 清理(非标准→旧代): {changes['gen_cleared']} 个")
print(f"  price 移除: {changes['price_removed']} 个")
print(f"  芯片修正: {changes['chip_fixed']} 个")

# 验证
from collections import Counter
gens = Counter(p.get("generation","?") for p in data)
print(f"\n修复后 generation 分布: {dict(gens)}")

# 写回
with open(PATH, "w", encoding="utf-8") as f:
    json.dump(data, f, ensure_ascii=False, indent=2)
print(f"已保存: {PATH} ({len(data)} 个产品)")
