"""
V2 训练+评测数据生成器
======================
训练(T1-T5): 单实体查找，自然语言输出
评测(E1-E4): 跨实体组合推理，结构化输出 → 全自动评分

核心约束: 评测问法在训练中从未出现，但所需知识全在训练数据中
"""

import json
import re
import random
import sys
from collections import defaultdict

# ============================================================
#  Utility
# ============================================================

def load_products(path):
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)

def pick_group(products, key):
    g = defaultdict(list)
    for p in products:
        v = p.get(key)
        if v:
            g[v].append(p)
    return dict(g)

def parse_price_num(p):
    """Extract min numeric price from string like '¥7499起' or '¥4000-5000'"""
    if not p or "待" in str(p):
        return None
    nums = re.findall(r"[\d,]+", str(p).replace("万", "0000"))
    if not nums:
        return None
    return float(nums[0].replace(",", ""))

def extract_attrs(product):
    """从 talking_points + 其他字段提取结构化属性"""
    tps = " ".join(product.get("talking_points", []))
    name = product["name"]
    attrs = {}

    # 芯片
    chip_m = re.search(r"(麒麟\s*\d+\s*[A-Za-z]*(?:\s*Pro|\s*Plus)?|骁龙\d+[A-Za-z]*|酷睿Ultra\d+)", tps)
    if chip_m:
        attrs["chip"] = chip_m.group(1).strip()

    # 电池
    bat_m = re.search(r"(\d{3,5})\s*mAh", tps)
    if bat_m:
        attrs["battery_mah"] = int(bat_m.group(1))

    # 屏幕类型
    for kw in ["双层OLED", "OLED", "LTPO", "MiniLED", "LCD"]:
        if kw in tps or kw in name:
            attrs["screen_type"] = kw
            break

    # 屏幕尺寸
    scr_m = re.search(r"(\d+\.?\d*)\s*寸", tps)
    if scr_m:
        attrs["screen_size"] = float(scr_m.group(1))

    # 重量
    wt_m = re.search(r"(\d+\.?\d*)\s*g", tps)
    if wt_m:
        attrs["weight_g"] = float(wt_m.group(1))

    # 快充功率
    chg_m = re.search(r"(\d+)\s*W\s*(快充|超级快充|闪充)", tps)
    if chg_m:
        attrs["charging_w"] = int(chg_m.group(1))

    # 卫星
    attrs["has_satellite"] = bool(re.search(r"卫星|北斗|天通", tps))

    # 折叠
    attrs["has_foldable"] = bool(re.search(r"折叠|Fold|Flip", tps + name))

    # 防水
    ip_m = re.search(r"IP(\d+)", tps)
    if ip_m:
        attrs["water_resist"] = f"IP{ip_m.group(1)}"

    # 血压
    attrs["has_blood_pressure"] = bool(re.search(r"血压", tps))

    # 降噪
    attrs["has_anc"] = bool(re.search(r"降噪", tps))

    # 5G
    attrs["has_5g"] = bool(re.search(r"5G", tps))
    if "4G" in tps:
        attrs["has_5g"] = False

    # 价格数值
    price_num = parse_price_num(product.get("price", ""))
    if price_num:
        attrs["price_num"] = price_num

    # 摄像头
    cam_m = re.search(r"(\d+\.?\d*)\s*亿像素", tps)
    if cam_m:
        attrs["camera_mp"] = float(cam_m.group(1))

    # 变焦
    zoom_m = re.search(r"(\d+)\s*倍.*变焦|变焦.*(\d+)\s*倍", tps)
    if zoom_m:
        attrs["zoom"] = int(zoom_m.group(1) or zoom_m.group(2))

    # 续航天数
    bat_day = re.search(r"(\d+)\s*天续航", tps)
    if bat_day:
        attrs["battery_days"] = int(bat_day.group(1))

    # 心率/ECG
    attrs["has_ecg"] = bool(re.search(r"ECG|心率", tps))

    # 刷新率
    hz_m = re.search(r"(\d+)\s*Hz", tps)
    if hz_m:
        attrs["refresh_hz"] = int(hz_m.group(1))

    # 亮度
    nit_m = re.search(r"(\d+)\s*nit", tps)
    if nit_m:
        attrs["brightness_nit"] = int(nit_m.group(1))

    # 分辨率
    res_m = re.search(r"(\d+\.?\d*)\s*K", tps)
    if res_m:
        attrs["resolution_k"] = float(res_m.group(1))

    # 内存
    ram_m = re.search(r"(\d+)\s*GB.*内存|(\d+)\s*GB(?!\s*p)", tps)
    # just capture first memory mention

    # WiFi
    attrs["has_wifi7"] = bool(re.search(r"WiFi\s*7|Wi-Fi\s*7", tps))

    # 从 price 字符串也提取数值
    if "price_num" not in attrs:
        price_num = parse_price_num(product.get("price", ""))
        if price_num:
            attrs["price_num"] = price_num

    return attrs


def build_alias_map(products):
    """别名 → 产品全称"""
    m = {}
    for p in products:
        m[p["name"]] = p["name"]
        for a in p.get("alias", []):
            m[a] = p["name"]
    return m


# ============================================================
#  Train / Eval Split
# ============================================================

HELD_OUT_NAMES = [
    # 手机 — 每个系列/子系列抽一个
    "Mate 80",                        # Mate 80 系列标准版
    "Mate 70 Pro 优享版",             # Mate 70 系列变体
    "Pura 80 Pro",                    # Pura 80 系列中杯
    "Mate X6",                        # 上代大折叠
    "Pocket 2",                       # 竖向小折叠旧款
    "nova 16 SE",                     # nova SE 入门
    "畅享 90 Plus",                   # 畅享中杯
    # 平板
    "MatePad Air 12 2025",            # Air 上代
    # 笔记本
    "MateBook 14 Linux 版",           # 数字系列 Linux 版
    # 手表
    "WATCH GT 7 41mm",               # GT 小尺寸
    # 耳机
    "FreeBuds 7i",                    # 海外版
    # 智慧屏
    "Vision 智慧屏 5 Pro",            # 上代智慧屏（不在89个里，用6代替）
    # 智能汽车
    "享界 S9 / S9T",                  # 享界轿车
]


def split_products(products):
    """分出训练集产品 + 留出产品"""
    held_out = []
    train = []
    held_set = set(HELD_OUT_NAMES)
    for p in products:
        if p["name"] in held_set:
            held_out.append(p)
        else:
            train.append(p)
    return train, held_out


# ============================================================
#  T1: product → series + category（上溯）
# ============================================================

def gen_t1(train_products):
    samples = []
    for p in train_products:
        company = p["company"]
        cat = p["category"]
        ser = p["series"]
        name = p["name"]

        variants = [
            (f"{name}属于华为什么产品线？", f"{name}属于{company}的{cat}品类，{ser}。"),
            (f"{name}是{company}的什么品类和系列？", f"{name}是{company}{cat}品类，属于{ser}。"),
            (f"{name}在华为产品体系里是什么定位？", f"{name}是{company}{cat}品类下的{ser}。"),
            (f"请问{name}是哪个系列的产品？", f"{name}属于{company}的{ser}，是{cat}品类。"),
            (f"{name}的品类和系列是什么？", f"{name}是{company}的{cat}，系列是{ser}。"),
        ]
        for q, a in variants:
            samples.append({"instruction": q, "output": a, "_task": "T1"})
    return samples


# ============================================================
#  T2: series → SPU 列表（下钻）
# ============================================================

def gen_t2(train_products):
    samples = []
    # 按 series 分组
    by_series = defaultdict(list)
    for p in train_products:
        by_series[p["series"]].append(p)

    for ser, plist in by_series.items():
        if len(plist) < 2:
            continue
        company = plist[0]["company"]
        cat = plist[0]["category"]

        # 按 sub_series 分组展示
        by_sub = defaultdict(list)
        for p in plist:
            sub = p.get("sub_series") or ser
            by_sub[sub].append(p["name"])

        # 扁平列表
        all_names = [p["name"] for p in plist]
        names_str = "、".join(all_names)

        variants = [
            (f"{company}{ser}有哪些具体型号？", f"{company}{ser}包括以下型号：{names_str}。"),
            (f"{ser}包含了哪些产品？", f"{ser}包含：{names_str}。"),
            (f"想了解{ser}的全部产品", f"{ser}目前有这些产品：{names_str}。"),
        ]

        # 如果有子系列，也生成分组版本
        if len(by_sub) > 1:
            sub_parts = []
            for sub_name, sub_names in by_sub.items():
                sub_parts.append(f"{sub_name}：{'、'.join(sub_names)}")
            grouped_str = "；".join(sub_parts)
            variants.append(
                (f"{company}{ser}有哪些产品线？", f"{company}{ser}分为{'、'.join(by_sub.keys())}，具体包括：{grouped_str}。")
            )

        for q, a in variants:
            samples.append({"instruction": q, "output": a, "_task": "T2"})

    return samples


# ============================================================
#  T3: product → specs（属性展开）
# ============================================================

def gen_t3(train_products):
    samples = []
    for p in train_products:
        name = p["name"]
        company = p["company"]
        cat = p["category"]
        ser = p["series"]
        tps = p.get("talking_points", [])
        positioning = "、".join(p.get("positioning", []))
        price = p.get("price", "")
        status = p.get("status", "")

        if not tps:
            continue

        specs = "、".join(tps[:5])
        spec_long = "、".join(tps)

        price_part = f"，售价{price}" if price and "待" not in price else ""
        status_part = "，目前在售" if status == "在售" else ("，即将发布" if "发布" in status else "")

        variants = [
            (f"{name}有什么核心配置？", f"{name}是{company}{cat}，属于{ser}。核心配置：{specs}{price_part}{status_part}。"),
            (f"{name}的详细参数是什么？", f"{name}（{positioning}）的详细参数包括：{spec_long}{price_part}{status_part}。"),
            (f"介绍一下{name}的配置和特点", f"{name}是{company}的{cat}（{ser}），主打{specs}{price_part}{status_part}。"),
            (f"{name}有哪些卖点？", f"{name}的主要卖点：{specs}。{price_part}{status_part}"),
        ]
        for q, a in variants:
            samples.append({"instruction": q, "output": a, "_task": "T3"})

    return samples


# ============================================================
#  T4: feature → products（反向索引）
# ============================================================

def gen_t4(train_products):
    samples = []
    # 收集所有有意义的 talking_point
    feature_products = defaultdict(list)
    skip_pats = [
        r"^\d+$", r"^[¥]\d", r"^20\d{2}年", r"^\d{4}mAh", r"^\d+W", r"^\d+g",
        r"^\d+\.?\d*寸", r"^\d+\.?\d*K", r"^\d+Hz", r"^\d+nit",
        r"\d+起", r"\d+较", r"最便宜", r"最贵", r"\d+-\d+价位", r"比.*便宜",
        r"^\d{4,}",  # 纯数字价格
    ]
    for p in train_products:
        for tp in p.get("talking_points", []):
            if any(re.match(pat, tp) for pat in skip_pats):
                continue
            if len(tp) < 3:
                continue
            feature_products[tp].append(p["name"])

    for feat, names in feature_products.items():
        names_str = "、".join(names)
        company = train_products[0]["company"]

        variants = [
            (f"哪些{company}产品支持{feat}？", f"支持{feat}的{company}产品有：{names_str}。"),
            (f"{feat}的{company}产品有哪些？", f"具备{feat}的{company}产品包括：{names_str}。"),
            (f"想买{feat}的{company}产品，有什么选择？", f"有{feat}的{company}产品：{names_str}。"),
        ]

        # 限制每类feature最多3个变体，太多会爆炸
        for q, a in variants[:2]:
            samples.append({"instruction": q, "output": a, "_task": "T4"})

    # Also from positioning
    pos_products = defaultdict(list)
    for p in train_products:
        for pos in p.get("positioning", []):
            pos_products[pos].append(p["name"])
    for pos, names in pos_products.items():
        if len(names) < 2:
            continue
        names_str = "、".join(names[:6])
        company = train_products[0]["company"]
        samples.append({
            "instruction": f"{company}{pos}的产品有哪些？",
            "output": f"{company}{pos}的产品包括：{names_str}。",
            "_task": "T4"
        })

    return samples


# ============================================================
#  T5: company+category → series 列表（顶层枚举）
# ============================================================

def gen_t5(train_products):
    samples = []
    by_cat = defaultdict(set)
    for p in train_products:
        by_cat[p["category"]].add(p["series"])

    for cat, series_set in by_cat.items():
        series_list = sorted(series_set)
        ser_str = "、".join(series_list)
        company = train_products[0]["company"]

        variants = [
            (f"{company}{cat}有哪些系列？", f"{company}{cat}分为以下系列：{ser_str}。"),
            (f"{company}的{cat}产品线怎么划分的？", f"{company}{cat}产品线包括：{ser_str}。"),
            (f"想了解{company}{cat}的各个系列", f"{company}{cat}目前有{len(series_list)}个系列：{ser_str}。"),
        ]
        for q, a in variants:
            samples.append({"instruction": q, "output": a, "_task": "T5"})

    # 跨品类顶层枚举
    all_cats = sorted(by_cat.keys())
    cat_summary = "；".join([f"{c}（{'、'.join(sorted(by_cat[c]))}）" for c in all_cats])
    company = train_products[0]["company"]
    samples.append({
        "instruction": f"{company}有哪些产品品类？",
        "output": f"{company}消费者产品涵盖{len(all_cats)}大品类：{cat_summary}。",
        "_task": "T5"
    })

    return samples


# ============================================================
#  E1: 多条件筛选 → 列表输出, 评分 list_f1
# ============================================================

def gen_e1(train_products):
    """
    条件来源: price_range, category, status, generation, features (satellite, foldable, 5G, chip, OLED...)
    输出格式: 顿号分隔的产品全称列表
    """
    samples = []
    company = train_products[0]["company"]
    attrs_list = [(p, extract_attrs(p)) for p in train_products]

    # --- 条件模板 ---

    # 1) 价位 + 品类 + 特性
    conditions = [
        {
            "desc": "5000-8000元价位、支持卫星通信的手机",
            "filter": lambda p, a: (
                a.get("price_num") and 5000 <= a["price_num"] <= 8000
                and a.get("has_satellite")
                and p["category"] == "手机"
            ),
        },
        {
            "desc": "1000-2000元、5G手机",
            "filter": lambda p, a: (
                a.get("price_num") and 1000 <= a["price_num"] <= 2000
                and a.get("has_5g")
                and p["category"] == "手机"
            ),
        },
        {
            "desc": "3000元以下、电池7000mAh以上的手机",
            "filter": lambda p, a: (
                a.get("price_num") and a["price_num"] < 3000
                and a.get("battery_mah") and a["battery_mah"] >= 7000
                and p["category"] == "手机"
            ),
        },
        {
            "desc": "搭载麒麟9030或9030 Pro芯片的手机",
            "filter": lambda p, a: (
                a.get("chip") and ("9030" in str(a["chip"]))
                and p["category"] == "手机"
            ),
        },
        {
            "desc": "支持快充且电池10000mAh以上的平板",
            "filter": lambda p, a: (
                a.get("charging_w") and a["charging_w"] >= 50
                and a.get("battery_mah") and a["battery_mah"] >= 10000
                and p["category"] == "平板"
            ),
        },
        {
            "desc": "支持血压监测的华为手表",
            "filter": lambda p, a: (
                a.get("has_blood_pressure")
                and p["category"] == "智能手表"
            ),
        },
        {
            "desc": "折叠屏手机中10000元以上的",
            "filter": lambda p, a: (
                a.get("has_foldable")
                and a.get("price_num") and a["price_num"] >= 10000
                and p["category"] == "手机"
            ),
        },
        {
            "desc": "最新款、支持北斗卫星的华为产品",
            "filter": lambda p, a: (
                p.get("generation") == "最新款"
                and a.get("has_satellite")
            ),
        },
        {
            "desc": "2026年发布的华为手机",
            "filter": lambda p, a: (
                "2026" in " ".join(p.get("talking_points", []))
                and p["category"] == "手机"
            ),
        },
        {
            "desc": "华为在售的、OLED屏幕的平板",
            "filter": lambda p, a: (
                p.get("status") == "在售"
                and a.get("screen_type") in ("OLED", "双层OLED", "LTPO")
                and p["category"] == "平板"
            ),
        },
        {
            "desc": "8000元以上的华为折叠屏手机",
            "filter": lambda p, a: (
                a.get("price_num") and a["price_num"] >= 8000
                and a.get("has_foldable")
                and p["category"] == "手机"
            ),
        },
    ]

    for c in conditions:
        matched = [p["name"] for p, a in attrs_list if c["filter"](p, a)]
        if len(matched) < 2:
            continue  # 结果太少没意义
        if len(matched) > 8:
            continue  # 结果太多像枚举

        gold_str = "、".join(matched)
        gold_list = matched

        variants = [
            f"列出{c['desc']}",
            f"{company}的{c['desc']}有哪些？",
            f"哪些产品是{c['desc']}？",
        ]
        for q in variants:
            samples.append({
                "instruction": q,
                "output": gold_str,
                "_task": "E1",
                "_scoring": "list_f1",
                "_gold_list": gold_list,
            })

    return samples


# ============================================================
#  E2: 最值比较 → 单产品名, 评分 exact_match
# ============================================================

def gen_e2(train_products):
    samples = []
    company = train_products[0]["company"]
    attrs_list = [(p, extract_attrs(p)) for p in train_products]

    # 各品类的最值
    for cat, cat_name in [
        ("手机", "手机"), ("平板", "平板"), ("笔记本", "笔记本"),
        ("智能手表", "手表"), ("智能汽车", "车"), ("智慧屏", "智慧屏"),
    ]:
        cat_products = [(p, a) for p, a in attrs_list if p["category"] == cat]

        # 最便宜 / 最贵
        priced = [(p, a) for p, a in cat_products if a.get("price_num")]
        if len(priced) >= 2:
            priced.sort(key=lambda x: x[1]["price_num"])
            cheapest = priced[0][0]
            priciest = priced[-1][0]
            if cheapest["name"] != priciest["name"]:
                samples.append({
                    "instruction": f"{company}最便宜的{cat_name}是哪款？",
                    "output": cheapest["name"],
                    "_task": "E2", "_scoring": "exact_match",
                    "_gold": cheapest["name"],
                })
                samples.append({
                    "instruction": f"{company}最贵的在售{cat_name}是什么？",
                    "output": priciest["name"],
                    "_task": "E2", "_scoring": "exact_match",
                    "_gold": priciest["name"],
                })

        # 电池最大
        batt = [(p, a) for p, a in cat_products if a.get("battery_mah")]
        if len(batt) >= 2:
            batt.sort(key=lambda x: x[1]["battery_mah"], reverse=True)
            top = batt[0][0]
            samples.append({
                "instruction": f"{company}电池容量最大的{cat_name}是哪款？",
                "output": top["name"],
                "_task": "E2", "_scoring": "exact_match",
                "_gold": top["name"],
            })

        # 最轻
        light = [(p, a) for p, a in cat_products if a.get("weight_g")]
        if len(light) >= 2:
            light.sort(key=lambda x: x[1]["weight_g"])
            lightest = light[0][0]
            samples.append({
                "instruction": f"{company}最轻的{cat_name}是哪款？",
                "output": lightest["name"],
                "_task": "E2", "_scoring": "exact_match",
                "_gold": lightest["name"],
            })

    # 特殊最值（不分类别）
    # 最便宜折叠屏
    folds = [(p, a) for p, a in attrs_list
              if a.get("has_foldable") and a.get("price_num") and p["category"] == "手机"]
    if len(folds) >= 2:
        folds.sort(key=lambda x: x[1]["price_num"])
        cheapest_fold = folds[0][0]
        samples.append({
            "instruction": f"{company}最便宜的折叠屏手机是哪款？",
            "output": cheapest_fold["name"],
            "_task": "E2", "_scoring": "exact_match",
            "_gold": cheapest_fold["name"],
        })
        priciest_fold = folds[-1][0]
        samples.append({
            "instruction": f"{company}最贵的折叠屏手机是哪款？",
            "output": priciest_fold["name"],
            "_task": "E2", "_scoring": "exact_match",
            "_gold": priciest_fold["name"],
        })

    # 续航最长的手表
    watches = [(p, a) for p, a in attrs_list if p["category"] == "智能手表" and a.get("battery_days")]
    if len(watches) >= 2:
        watches.sort(key=lambda x: x[1]["battery_days"], reverse=True)
        samples.append({
            "instruction": f"{company}续航最长的手表是哪款？",
            "output": watches[0][0]["name"],
            "_task": "E2", "_scoring": "exact_match",
            "_gold": watches[0][0]["name"],
        })

    return samples


# ============================================================
#  E3: 跨品类关联 → 分组输出, 评分 per-key list_f1
# ============================================================

def gen_e3(train_products):
    samples = []
    company = train_products[0]["company"]
    attrs_list = [(p, extract_attrs(p)) for p in train_products]

    queries = [
        {
            "desc": "支持北斗卫星通信",
            "filter": lambda p, a: a.get("has_satellite"),
        },
        {
            "desc": "搭载麒麟芯片",
            "filter": lambda p, a: a.get("chip") and "麒麟" in str(a.get("chip", "")),
        },
        {
            "desc": "有OLED屏幕",
            "filter": lambda p, a: a.get("screen_type") in ("OLED", "双层OLED", "LTPO"),
        },
        {
            "desc": "有折叠形态",
            "filter": lambda p, a: a.get("has_foldable") or "折叠" in " ".join(p.get("talking_points", [])),
        },
        {
            "desc": "支持防水",
            "filter": lambda p, a: a.get("water_resist") is not None,
        },
    ]

    for qdef in queries:
        # 按品类分组
        by_cat = defaultdict(list)
        for p, a in attrs_list:
            if qdef["filter"](p, a):
                by_cat[p["category"]].append(p["name"])

        # 至少跨2个品类才有意义
        if len(by_cat) < 2:
            continue
        # 总产品数不超过15，否则太泛
        total = sum(len(v) for v in by_cat.values())
        if total > 15:
            continue

        # 构建分组输出
        lines = []
        gold_grouped = {}
        for cat in sorted(by_cat.keys()):
            names = by_cat[cat]
            lines.append(f"{cat}：{'、'.join(names)}")
            gold_grouped[cat] = names

        output_str = "\n".join(lines)
        gold_flat = [n for names in by_cat.values() for n in names]

        variants = [
            f"{company}哪些产品{qdef['desc']}？",
            f"{company}{qdef['desc']}的产品分布在哪些品类？",
        ]
        for q in variants:
            samples.append({
                "instruction": q,
                "output": output_str,
                "_task": "E3",
                "_scoring": "grouped_list_f1",
                "_gold_grouped": gold_grouped,
                "_gold_list": gold_flat,
            })

    return samples


# ============================================================
#  E4: 属性补全（留出产品）→ 单值, 评分 exact_match
# ============================================================

def gen_e4(held_out_products):
    """
    对留出的产品，问训练中没直接问过的属性维度。
    模型需要从产品树位置推断（同子系列的其他产品在训练中教过）。
    """
    samples = []
    company = held_out_products[0]["company"] if held_out_products else "华为"

    for p in held_out_products:
        name = p["name"]
        tps = p.get("talking_points", [])
        tps_str = " ".join(tps)

        # 从 talking_points 提取可问答的属性
        # 芯片
        chip_m = re.search(r"(麒麟\s*\d+\s*[A-Za-z]*(?:\s*Pro|\s*Plus)?|骁龙\d+[A-Za-z]*|酷睿Ultra\d+)", tps_str)
        if chip_m:
            chip = chip_m.group(1).strip()
            samples.append({
                "instruction": f"{name}用的是哪款芯片？",
                "output": chip,
                "_task": "E4", "_scoring": "exact_match",
                "_gold": chip, "_attr": "chip",
            })

        # 电池
        bat_m = re.search(r"(\d+)\s*mAh", tps_str)
        if bat_m:
            bat = f"{bat_m.group(1)}mAh"
            samples.append({
                "instruction": f"{name}的电池容量是多少？",
                "output": bat,
                "_task": "E4", "_scoring": "exact_match",
                "_gold": bat, "_attr": "battery",
            })

        # 价格
        price = p.get("price", "")
        if price and "待" not in price:
            samples.append({
                "instruction": f"{name}的售价是多少？",
                "output": price,
                "_task": "E4", "_scoring": "exact_match",
                "_gold": price, "_attr": "price",
            })

        # 特定特征
        if "卫星" in tps_str:
            samples.append({
                "instruction": f"{name}支持卫星通信吗？",
                "output": "支持",
                "_task": "E4", "_scoring": "exact_match",
                "_gold": "支持", "_attr": "satellite",
            })

        # 定位
        positioning = p.get("positioning", [])
        if positioning:
            pos_str = "、".join(positioning)
            samples.append({
                "instruction": f"{name}的产品定位是什么？",
                "output": pos_str,
                "_task": "E4", "_scoring": "exact_match",
                "_gold": pos_str, "_attr": "positioning",
            })

        # 系列归属
        ser = p.get("series", "")
        cat = p.get("category", "")
        if ser and cat:
            samples.append({
                "instruction": f"{name}属于华为什么品类和系列？",
                "output": f"{cat}品类，{ser}",
                "_task": "E4", "_scoring": "exact_match",
                "_gold": f"{cat}品类，{ser}", "_attr": "series_cat",
            })

    return samples


# ============================================================
#  Main
# ============================================================

def generate_all(input_path, out_dir, seed=42):
    random.seed(seed)
    products = load_products(input_path)
    train, held_out = split_products(products)
    company = products[0]["company"]

    print(f"=" * 60)
    print(f"公司: {company}")
    print(f"总产品数: {len(products)}")
    print(f"训练集产品数: {len(train)}")
    print(f"留出产品数: {len(held_out)}")
    print(f"留出产品: {[p['name'] for p in held_out]}")
    print()

    # --- 生成训练数据 ---
    all_train = []
    generators = [
        ("T1-产品上溯", gen_t1),
        ("T2-系列下钻", gen_t2),
        ("T3-属性展开", gen_t3),
        ("T4-反向索引", gen_t4),
        ("T5-品类枚举", gen_t5),
    ]

    for label, gen_func in generators:
        samples = gen_func(train)
        # 去重（相同 instruction → output）
        seen = set()
        deduped = []
        for s in samples:
            key = (s["instruction"], s["output"])
            if key not in seen:
                seen.add(key)
                deduped.append(s)
        # 限流
        if len(deduped) > 200:
            deduped = random.sample(deduped, 200)
        print(f"  {label}: {len(deduped)} 条")
        for s in deduped:
            s.pop("_task", None)  # 训练数据不需要 task 标签
        all_train.extend(deduped)

    random.shuffle(all_train)
    train_path = f"{out_dir}/v2_train.jsonl"
    with open(train_path, "w", encoding="utf-8") as f:
        for s in all_train:
            f.write(json.dumps(s, ensure_ascii=False) + "\n")
    print(f"\n训练数据: {train_path} ({len(all_train)} 条)")
    print()

    # --- 生成评测数据 ---
    all_eval = []
    eval_generators = [
        ("E1-多条件筛选", gen_e1),
        ("E2-最值比较", gen_e2),
        ("E3-跨品类关联", gen_e3),
    ]

    for label, gen_func in eval_generators:
        samples = gen_func(train)
        seen = set()
        deduped = []
        for s in samples:
            key = (s["instruction"], s["output"])
            if key not in seen:
                seen.add(key)
                deduped.append(s)
        print(f"  {label}: {len(deduped)} 条")
        all_eval.extend(deduped)

    # E4 用留出产品
    e4_samples = gen_e4(held_out)
    print(f"  E4-属性补全: {len(e4_samples)} 条")
    all_eval.extend(e4_samples)

    eval_path = f"{out_dir}/v2_eval.jsonl"
    with open(eval_path, "w", encoding="utf-8") as f:
        for s in all_eval:
            f.write(json.dumps(s, ensure_ascii=False) + "\n")
    print(f"\n评测数据: {eval_path} ({len(all_eval)} 条)")

    # --- 别名映射（给评分脚本用） ---
    alias_map = build_alias_map(products)
    alias_path = f"{out_dir}/v2_alias_map.json"
    with open(alias_path, "w", encoding="utf-8") as f:
        json.dump(alias_map, f, ensure_ascii=False, indent=2)
    print(f"别名映射: {alias_path} ({len(alias_map)} 条)")

    # --- 留出信息 ---
    split_info = {
        "held_out_names": HELD_OUT_NAMES,
        "held_out_products": [
            {"name": p["name"], "category": p["category"], "series": p["series"]}
            for p in held_out
        ],
        "train_count": len(train),
        "held_count": len(held_out),
    }
    split_path = f"{out_dir}/v2_split_info.json"
    with open(split_path, "w", encoding="utf-8") as f:
        json.dump(split_info, f, ensure_ascii=False, indent=2)
    print(f"分割信息: {split_path}")

    # --- 预览 ---
    print(f"\n{'=' * 60}")
    print("训练数据预览 (各任务抽1条):")
    print()
    for task_label in ["T1", "T2", "T3", "T4", "T5"]:
        task_samples = [s for s in all_train if s.get("_task") == task_label]
        if task_samples:
            s = random.choice(task_samples)
            print(f"  [{task_label}]")
            print(f"    Q: {s['instruction']}")
            print(f"    A: {s['output'][:150]}...")
            print()

    print(f"{'=' * 60}")
    print("评测数据预览 (各任务抽1条):")
    print()
    for task_label in ["E1", "E2", "E3", "E4"]:
        task_samples = [s for s in all_eval if s.get("_task") == task_label]
        if task_samples:
            s = random.choice(task_samples)
            print(f"  [{task_label}] scoring={s.get('_scoring')}")
            print(f"    Q: {s['instruction']}")
            print(f"    A: {s['output'][:200]}")
            print(f"    Gold: {s.get('_gold') or s.get('_gold_list', '')}")
            print()

    # --- SFT 评测可行性检查 ---
    print(f"{'=' * 60}")
    print("SFT 评测可行性检查:")
    print()

    checks = {
        "E1": {
            "输出格式": "顿号分隔的产品全称列表，例: 'Mate 70 Pro+、Pura 80 Pro+'",
            "解析规则": "split('、') → 去空白 → 得集合",
            "评分方式": "precision = |pred ∩ gold| / |pred|, recall = |pred ∩ gold| / |gold|, F1",
            "边缘情况": "口语前缀('还有''包括')→先strip；输出别名→alias_map查表",
            "可行性": "[OK] 全自动，一行 Python",
        },
        "E2": {
            "输出格式": "单个产品全称，例: '畅享 90 Pro Max'",
            "解析规则": "整段 strip，去引号",
            "评分方式": "exact_match → 失败则 contains(gold, pred) → 失败则 alias_match",
            "边缘情况": "输出'畅享90PM'别名→alias_map转换；输出'畅享 90 Pro Max，8500mAh'→contains回退",
            "可行性": "[OK] 全自动，含别名回退",
        },
        "E3": {
            "输出格式": "品类：产品1、产品2\\n品类：产品3，例: '手机：Mate 70 Pro+、Pura 80 Pro+\\n手表：WATCH Ultimate 2'",
            "解析规则": "按行 split → 每行按'：'拆 (品类, 产品列表) → 产品列表 split('、')",
            "评分方式": "每个品类独立算 list_f1 → 宏平均",
            "边缘情况": "品类名写法不一致 → 训练数据固化品类名；未按行输出 → 尝试按'。'分句",
            "可行性": "[OK] 自动，解析容错率略低于E1/E2",
        },
        "E4": {
            "输出格式": "单个属性值，例: '麒麟9030 Pro' 或 '¥12999起' 或 '6000mAh'",
            "解析规则": "整段 strip",
            "评分方式": "exact_match + contains 回退",
            "边缘情况": "芯片名有空格差异(麒麟 9030 vs 麒麟9030)→先归一化",
            "可行性": "[OK] 全自动",
        },
    }

    for task, check in checks.items():
        print(f"  ┌─ {task} ─────────────────────────────")
        for k, v in check.items():
            print(f"  │ {k}: {v}")
        print(f"  └{'─' * 40}")

    return all_train, all_eval, alias_map


if __name__ == "__main__":
    if len(sys.argv) < 2:
        # 默认路径
        input_path = r"D:\新建文件夹\grad_t\product_knowledge\data_\华为产品属性.json"
        out_dir = r"D:\新建文件夹\grad_t\product_knowledge\data_"
    else:
        input_path = sys.argv[1]
        out_dir = sys.argv[2] if len(sys.argv) > 2 else "."

    generate_all(input_path, out_dir)
