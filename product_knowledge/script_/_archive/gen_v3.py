"""
V3 知识注入数据生成器
=====================
全量 89 产品 → 知识图谱 → 训练QA + 评测QA

评测策略:
  主力 (~80%): 指代拼接 — 独有特性→反向追溯公司/品类/系列
  辅助 (~20%): 可靠三段论 — is_a链 + subseries_has_* 全称规则

修复:
  - 芯片提取: 不再把 WiFi/特性名混入芯片名
  - 充电提取: 修复误匹配
  - 独有特性自动检测
"""

import json
import re
import random
import sys
from collections import defaultdict

# ============================================================
# 配置
# ============================================================

INPUT_PATH = r"D:\新建文件夹\grad_t\product_knowledge\data_\华为产品属性.json"
OUT_DIR = r"D:\新建文件夹\grad_t\product_knowledge\data_\\"

# ============================================================
# Step 1: 加载 + 实体抽取 (修复版)
# ============================================================

def load_products(path):
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def extract_chip(tps_list):
    """只提取芯片代号，不混入其他特性"""
    tps_str = " ".join(tps_list)
    # 先匹配独立的芯片 talking_point
    for tp in tps_list:
        m = re.match(r"^(麒麟\s*\d+[A-Za-z]*(?:\s*(?:Pro|Plus|S))?|骁龙\d+[A-Za-z]*|酷睿Ultra\s*\d+)$", tp.strip())
        if m:
            return m.group(1).strip()
    # fallback: 从整个字符串匹配
    m = re.search(r"(麒麟\s*\d+[A-Za-z]*(?:\s*(?:Pro|Plus|S))?|骁龙\d+[A-Za-z]*|酷睿\s*Ultra\s*\d+)", tps_str)
    return m.group(1).strip() if m else None


def extract_battery(tps_list):
    for tp in tps_list:
        m = re.search(r"(\d{3,5})\s*mAh", tp)
        if m:
            return int(m.group(1))
    return None


def extract_screen_type(tps_list, name):
    for kw in ["双层OLED", "柔性OLED", "LTPO", "MiniLED", "OLED", "微曲屏", "直屏", "LCD"]:
        for tp in tps_list:
            if kw in tp:
                return kw
        if kw in name:
            return kw
    return None


def extract_screen_size(tps_list):
    for tp in tps_list:
        m = re.search(r"(\d+\.?\d*)\s*寸", tp)
        if m:
            return float(m.group(1))
    return None


def extract_weight(tps_list):
    for tp in tps_list:
        m = re.search(r"(\d+\.?\d*)\s*g\b", tp)
        if m:
            return float(m.group(1))
    return None


def extract_charging(tps_list):
    """只提取真正的快充规格,不误匹配数字"""
    for tp in tps_list:
        m = re.search(r"(\d+)\s*W\s*(快充|超级快充|闪充)", tp)
        if m:
            return f"{m.group(1)}W{m.group(2)}"
    return None


def extract_satellite(tps_list):
    for tp in tps_list:
        if re.search(r"卫星|北斗|天通", tp):
            return True
    return False


def extract_blood_pressure(tps_list):
    for tp in tps_list:
        if "血压" in tp:
            return True
    return False


def extract_ecg(tps_list):
    for tp in tps_list:
        if "ECG" in tp:
            return True
    return False


def extract_5g(tps_list):
    for tp in tps_list:
        if "5G" in tp:
            return True
        if "4G" in tp:
            return False
    return None


def extract_water_resist(tps_list):
    for tp in tps_list:
        m = re.search(r"IP(\d+)", tp)
        if m:
            return f"IP{m.group(1)}"
    return None


def extract_refresh_rate(tps_list):
    for tp in tps_list:
        m = re.search(r"(\d+)\s*Hz", tp)
        if m:
            return int(m.group(1))
    return None


def extract_camera_mp(tps_list):
    for tp in tps_list:
        m = re.search(r"(\d+\.?\d*)\s*亿像素", tp)
        if m:
            return float(m.group(1))
    return None


def extract_zoom(tps_list):
    for tp in tps_list:
        m = re.search(r"(\d+)\s*倍.*(?:变焦|录像|高清)", tp)
        if m:
            return int(m.group(1))
    return None


def extract_battery_days(tps_list):
    for tp in tps_list:
        m = re.search(r"(\d+)\s*天续航", tp)
        if m:
            return int(m.group(1))
    return None


def extract_brightness(tps_list):
    for tp in tps_list:
        m = re.search(r"(\d+)\s*nit", tp)
        if m:
            return int(m.group(1))
    return None


def extract_features(tps_list):
    """从talking_points提取纯粹的「特性」标签(非数值类)"""
    skip_patterns = [
        r"^\d+$", r"^[¥¥]\d", r"^20\d{2}年", r"^\d{4}mAh", r"^\d+[Ww]$",
        r"^\d+[Ww](快充|超级快充|闪充)?$", r"^\d+\.?\d*g$",
        r"^\d+\.?\d*寸$", r"^\d+\.?\d*[Kk]$", r"^\d+Hz$", r"^\d+nit$",
        r"^\d{4,}$", r"^\d+倍", r"^\d+\.?\d*亿像素",
        r"\d+起$", r"最便宜", r"最贵", r"比.*便宜",
        r"^\d+-\d+价位", r"^\d+-\d+元",
        r"^\d+\.?\d*天续航",
        # 芯片类已单独提取
        r"^麒麟\s*\d+", r"^骁龙\d+", r"^酷睿",
        r"^麒麟XE\d+",
    ]
    features = []
    for tp in tps_list:
        tp_clean = tp.strip()
        if len(tp_clean) < 2:
            continue
        if any(re.match(pat, tp_clean) for pat in skip_patterns):
            continue
        # 排除纯数字结尾的（价格、数值）
        if re.match(r"^.*\d{3,}$", tp_clean) and not any(
            kw in tp_clean for kw in ["WiFi", "USB", "PC", "AI", "HiFi", "RGB", "BT"]
        ):
            continue
        features.append(tp_clean)
    return features


def parse_price_num(price_str):
    if not price_str or "待" in str(price_str):
        return None
    s = str(price_str).replace("万", "0000")
    nums = re.findall(r"[\d,]+", s)
    return float(nums[0].replace(",", "")) if nums else None


def get_price_range(price_num):
    if price_num is None:
        return None
    if price_num < 2000: return "2000元以下"
    if price_num < 4000: return "2000-4000元"
    if price_num < 6000: return "4000-6000元"
    if price_num < 8000: return "6000-8000元"
    if price_num < 12000: return "8000-12000元"
    return "12000元以上"


def extract_year(tps_list):
    for tp in tps_list:
        m = re.search(r"(20\d{2})年", tp)
        if m:
            return m.group(1)
    return None


# ============================================================
# Step 2: 图谱构建
# ============================================================

class Graph:
    def __init__(self):
        self.triples = []              # [(src, rel, tgt), ...]
        self.triple_set = set()
        self.nodes = {}                # id -> {"type": ..., ...}
        self.node_type = {}            # id -> type string
        # 索引: 快速查询
        self._fw_index = defaultdict(lambda: defaultdict(list))  # src -> rel -> [tgt]
        self._rv_index = defaultdict(lambda: defaultdict(list))  # tgt -> rel -> [src]

    def add_node(self, nid, ntype, **attrs):
        self.nodes[nid] = attrs
        self.node_type[nid] = ntype

    def add_triple(self, src, rel, tgt):
        key = (src, rel, tgt)
        if key not in self.triple_set:
            self.triple_set.add(key)
            self.triples.append((src, rel, tgt))
            self._fw_index[src][rel].append(tgt)
            self._rv_index[tgt][rel].append(src)

    # ---- 反向查询 (使用索引) ----
    def find_by_rel(self, src, rel):
        """src --rel--> [tgts]"""
        return list(self._fw_index[src].get(rel, []))

    def find_reverse(self, tgt, rel):
        """src --rel--> tgt, return [srcs]"""
        return list(self._rv_index[tgt].get(rel, []))

    def path_to_root(self, node_id, stop_types=None, max_depth=10):
        """沿 is_a 链走到根节点(Company),返回路径上的节点列表"""
        path = [node_id]
        current = node_id
        for _ in range(max_depth):
            parents = self.find_by_rel(current, "is_a")
            if not parents:
                break
            current = parents[0]
            path.append(current)
            if stop_types and self.node_type.get(current) in stop_types:
                break
        return path

    def get_stats(self):
        node_counts = defaultdict(int)
        for nid in self.nodes:
            node_counts[self.node_type.get(nid, "?")] += 1
        rel_counts = defaultdict(int)
        for s, r, t in self.triples:
            rel_counts[r] += 1
        return dict(node_counts), dict(rel_counts)


def build_graph(products):
    g = Graph()
    company = products[0]["company"]
    g.add_node(company, "Company")

    for p in products:
        name = p["name"]
        cat = p["category"]
        ser = p["series"]
        sub = p.get("sub_series") or ser
        tps_list = p.get("talking_points", [])
        price = p.get("price", "")
        status = p.get("status", "")
        gen = p.get("generation", "")
        positioning = p.get("positioning", [])

        # --- 实体节点 ---
        g.add_node(name, "SPU", category=cat, series=ser)
        g.add_node(cat, "Category")
        g.add_node(ser, "Series", category=cat)
        g.add_node(sub, "SubSeries", series=ser, category=cat)

        # --- is_a 链 ---
        g.add_triple(name, "is_a", sub)
        g.add_triple(sub, "is_a", ser)
        g.add_triple(ser, "is_a", cat)
        g.add_triple(cat, "is_a", company)

        # --- 芯片 ---
        chip = extract_chip(tps_list)
        if chip:
            g.add_node(chip, "Chip")
            g.add_triple(name, "has_chip", chip)

        # --- 特性 ---
        feats = extract_features(tps_list)
        for feat in feats:
            g.add_node(feat, "Feature")
            g.add_triple(name, "has_feature", feat)

        # --- 电池 ---
        bat = extract_battery(tps_list)
        if bat:
            bat_str = f"{bat}mAh"
            g.add_node(bat_str, "Battery")
            g.add_triple(name, "has_battery", bat_str)

        # --- 屏幕 ---
        screen = extract_screen_type(tps_list, name)
        if screen:
            g.add_node(screen, "ScreenType")
            g.add_triple(name, "has_screen", screen)

        # --- 重量 ---
        wt = extract_weight(tps_list)
        if wt:
            wt_str = f"{wt}g"
            g.add_node(wt_str, "Weight")
            g.add_triple(name, "has_weight", wt_str)

        # --- 快充 ---
        chg = extract_charging(tps_list)
        if chg:
            g.add_node(chg, "Charging")
            g.add_triple(name, "has_charging", chg)

        # --- 卫星 ---
        if extract_satellite(tps_list):
            g.add_node("卫星通信", "Feature")
            g.add_triple(name, "has_feature", "卫星通信")

        # --- 血压 ---
        if extract_blood_pressure(tps_list):
            g.add_node("血压监测", "Feature")
            g.add_triple(name, "has_feature", "血压监测")

        # --- 价格 ---
        price_num = parse_price_num(price)
        if price_num is not None:
            price_range = get_price_range(price_num)
            g.add_node(price_range, "PriceRange")
            g.add_triple(name, "in_price_range", price_range)
            g.add_node(price, "Price")
            g.add_triple(name, "has_price", price)

        # --- 定位 ---
        for pos in positioning:
            g.add_node(pos, "Positioning")
            g.add_triple(name, "positioned_as", pos)

        # --- 年份 ---
        year = extract_year(tps_list)
        if year:
            year_node = year + "年"
            g.add_node(year_node, "Year")
            g.add_triple(name, "released_in", year_node)

    # --- 规则边: subseries_has_chip ---
    subseries_chips = defaultdict(set)
    for s, r, t in g.triples:
        if r == "has_chip":
            spu = s
            subs = g.find_by_rel(spu, "is_a")
            for sub in subs:
                if g.node_type.get(sub) == "SubSeries":
                    subseries_chips[sub].add(t)
    for sub, chips in subseries_chips.items():
        if len(chips) == 1:  # 全系列统一芯片才算规则
            chip = list(chips)[0]
            g.add_node(f"{sub}_chip_rule", "Rule")
            g.add_triple(sub, "subseries_has_chip", chip)

    # --- 横向边: same_subseries ---
    by_sub = defaultdict(list)
    for nid, ntype in g.node_type.items():
        if ntype == "SPU":
            subs = g.find_by_rel(nid, "is_a")
            for sub in subs:
                by_sub[sub].append(nid)
    for sub, spus in by_sub.items():
        for i, a in enumerate(spus):
            for b in spus[i+1:]:
                g.add_triple(a, "same_subseries", b)
                g.add_triple(b, "same_subseries", a)

    # --- 横向边: shares_chip ---
    chip_to_spus = defaultdict(list)
    for s, r, t in g.triples:
        if r == "has_chip":
            chip_to_spus[t].append(s)
    for chip, spus in chip_to_spus.items():
        for i, a in enumerate(spus):
            for b in spus[i+1:]:
                g.add_triple(a, "shares_chip", b)
                g.add_triple(b, "shares_chip", a)

    # --- 横向边: same_tier (同品类同定位级别) ---
    tiers = defaultdict(list)
    for nid, ntype in g.node_type.items():
        if ntype == "SPU":
            # 简单规则: Pro Max级 / Pro级 / 标准/入门
            if "Pro Max" in nid or "Ultra" in nid or "RS" in nid or "Ultimate" in nid:
                tier = "旗舰+"
            elif "Pro" in nid and "Pro Max" not in nid:
                tier = "旗舰"
            elif "SE" in nid or "畅享" in nid:
                tier = "入门"
            else:
                tier = "标准"
            cat = g.nodes.get(nid, {}).get("category", "")
            tiers[(cat, tier)].append(nid)
    for (cat, tier), spus in tiers.items():
        if len(spus) > 15:  # 跳过太大的分组,避免O(N^2)爆炸
            continue
        for i, a in enumerate(spus):
            for b in spus[i+1:]:
                g.add_triple(a, "same_tier", b)
                g.add_triple(b, "same_tier", a)

    return g


# ============================================================
# Step 3: 训练 QA 生成 (从所有三元组)
# ============================================================

# 关系 → QA 模板 (正问 + 反问)
TRAIN_TEMPLATES = {
    "is_a": {
        "forward": [
            "{src}属于什么分类？",
            "{src}归属哪个{tgt_type}？",
        ],
        "reverse": [
            "{tgt}包含哪些产品？",
            "{tgt}下面有什么？",
        ],
    },
    "has_chip": {
        "forward": [
            "{src}搭载什么芯片？",
            "{src}用的什么处理器？",
        ],
        "reverse": [
            "哪些产品搭载{tgt}？",
            "{tgt}用于哪些产品？",
        ],
    },
    "has_feature": {
        "forward": [
            "{src}支持{tgt}吗？",
            "{src}有{tgt}功能吗？",
        ],
        "reverse": [
            "哪些产品支持{tgt}？",
            "哪些产品有{tgt}功能？",
        ],
    },
    "has_price": {
        "forward": [
            "{src}的售价是多少？",
            "{src}多少钱？",
        ],
    },
    "has_screen": {
        "forward": [
            "{src}的屏幕是什么类型？",
            "{src}用的什么屏幕？",
        ],
    },
    "has_battery": {
        "forward": [
            "{src}的电池容量是多少？",
        ],
    },
    "has_charging": {
        "forward": [
            "{src}支持什么快充？",
        ],
    },
    "has_weight": {
        "forward": [
            "{src}有多重？",
        ],
    },
    "positioned_as": {
        "forward": [
            "{src}的产品定位是什么？",
            "{src}主打什么定位？",
        ],
        "reverse": [
            "华为{tgt}定位的产品有哪些？",
            "哪些产品定位为{tgt}？",
        ],
    },
    "in_price_range": {
        "forward": [
            "{src}在什么价位段？",
        ],
        "reverse": [
            "华为{tgt}价位有哪些产品？",
        ],
    },
    "released_in": {
        "forward": [
            "{src}是哪一年发布的？",
        ],
    },
    "subseries_has_chip": {
        "forward": [
            "{src}全系搭载什么芯片？",
            "{src}标配什么处理器？",
        ],
    },
    "same_subseries": {},   # 不生成训练QA，太冗余
    "same_tier": {},        # 不生成训练QA
    "shares_chip": {},      # 不生成训练QA
}


def gen_train(g):
    samples = []
    company = list(g.node_type.keys())[0]  # 第一个通常是公司

    for src, rel, tgt in g.triples:
        tmpl = TRAIN_TEMPLATES.get(rel, {})
        if not tmpl:
            continue

        src_type = g.node_type.get(src, "?")
        tgt_type = g.node_type.get(tgt, "?")

        # 正向 QA
        for q_tmpl in tmpl.get("forward", []):
            q = q_tmpl.format(src=src, tgt=tgt, src_type=src_type, tgt_type=tgt_type)
            a = str(tgt)
            samples.append({"instruction": q, "output": a, "_rel": rel, "_dir": "forward"})

        # 反向 QA
        for q_tmpl in tmpl.get("reverse", []):
            q = q_tmpl.format(src=src, tgt=tgt, src_type=src_type, tgt_type=tgt_type)
            a = str(src)
            samples.append({"instruction": q, "output": a, "_rel": rel, "_dir": "reverse"})

    return samples


# ============================================================
# Step 4: 评测 QA 生成
# ============================================================

def gen_eval_indirect_reference(g):
    """
    策略B [主力]: 指代拼接
    从独有特性出发,反向追溯公司/品类/系列/SPU

    独有特性 = 只有一个 SPU 拥有的 Feature
    评测问法 = 用特性指代产品,问上层归属
    """
    samples = []

    # 找独有特性 (feature 只属于1个 SPU)
    feature_spus = defaultdict(list)
    for s, r, t in g.triples:
        if r == "has_feature" and g.node_type.get(t) == "Feature":
            feature_spus[t].append(s)

    unique_features = {f: spus[0] for f, spus in feature_spus.items() if len(spus) == 1}

    # 同样找独有芯片/电池/屏幕等
    for rel in ["has_chip", "has_screen", "has_battery", "has_charging"]:
        attr_spus = defaultdict(list)
        for s, r, t in g.triples:
            if r == rel:
                attr_spus[t].append(s)
        for attr_val, spus in attr_spus.items():
            if len(spus) == 1 and attr_val not in unique_features:
                unique_features[attr_val] = spus[0]

    if not unique_features:
        print("  [WARN] 没有找到独有特性,回退到所有特性")
        for f, spus in feature_spus.items():
            if spus:
                unique_features[f] = spus[0]

    for feat, spu in unique_features.items():
        path = g.path_to_root(spu)
        # path: [SPU, SubSeries, Series, Category, Company]
        # 跳过 SubSeries (太细)

        # 问公司
        if len(path) >= 5:
            company = path[-1]
            qs = [
                f"具有「{feat}」这一特性的是哪家公司的产品？",
                f"「{feat}」是哪个品牌的功能？",
            ]
            for q in qs:
                samples.append({
                    "instruction": q, "output": company,
                    "_eval_type": "indirect", "_scoring": "exact_match",
                    "_path": f"{feat} -> {spu} -> ... -> {company}",
                })

        # 问品类
        if len(path) >= 4:
            category = path[-2] if path[-1] == path[-1] else None
            # find category in path
            cat_node = None
            for node in path:
                if g.node_type.get(node) == "Category":
                    cat_node = node
                    break
            if cat_node:
                qs = [
                    f"「{feat}」是华为什么品类的特性？",
                    f"具备「{feat}」的华为产品属于哪个品类？",
                ]
                for q in qs:
                    samples.append({
                        "instruction": q, "output": cat_node,
                        "_eval_type": "indirect", "_scoring": "exact_match",
                        "_path": f"{feat} -> {spu} -> ... -> {cat_node}",
                    })

        # 问系列
        series_node = None
        for node in path:
            if g.node_type.get(node) == "Series":
                series_node = node
                break
        if series_node:
            qs = [
                f"「{feat}」这一特性属于华为哪个系列？",
                f"华为哪个系列的产品有「{feat}」？",
            ]
            for q in qs:
                samples.append({
                    "instruction": q, "output": series_node,
                    "_eval_type": "indirect", "_scoring": "exact_match",
                    "_path": f"{feat} -> {spu} -> ... -> {series_node}",
                })

        # 问具体产品
        qs = [
            f"「{feat}」是华为哪款产品的特性？",
            f"哪款华为产品有「{feat}」？",
        ]
        for q in qs:
            samples.append({
                "instruction": q, "output": spu,
                "_eval_type": "indirect", "_scoring": "exact_match",
                "_path": f"{feat} -> {spu}",
            })

    return samples


def gen_eval_syllogism(g):
    """
    策略A [辅助]: 可靠三段论
    只用 is_a + subseries_has_chip 这种已验证的全称规则
    """
    samples = []

    for s, r1, mid in g.triples:
        if r1 != "is_a":
            continue
        if g.node_type.get(s) != "SPU":
            continue

        # 找 mid 出发的全称规则
        for mid2, r2, tgt in g.triples:
            if mid2 != mid:
                continue
            if r2 not in ("subseries_has_chip",):
                continue

            # 生成结论 QA
            if r2 == "subseries_has_chip":
                qs = [
                    f"{s}属于{mid},而{mid}全系搭载{tgt},请问{s}搭载什么芯片？",
                    f"根据产品定位,{s}用什么处理器？",
                ]
                for q in qs:
                    samples.append({
                        "instruction": q, "output": tgt,
                        "_eval_type": "syllogism", "_scoring": "exact_match",
                        "_path": f"{s} --is_a--> {mid} --{r2}--> {tgt}",
                    })

    return samples


# ============================================================
# Step 5: 去重 + 导出
# ============================================================

def dedup_and_sample(samples, max_per_type=None):
    seen = set()
    result = []
    for s in samples:
        key = (s["instruction"], s["output"])
        if key not in seen:
            seen.add(key)
            result.append(s)
    if max_per_type and len(result) > max_per_type:
        result = random.sample(result, max_per_type)
    return result


def export_jsonl(samples, path, strip_meta=False):
    with open(path, "w", encoding="utf-8") as f:
        for s in samples:
            out = dict(s)
            if strip_meta:
                out.pop("_rel", None)
                out.pop("_dir", None)
                out.pop("_eval_type", None)
                out.pop("_scoring", None)
                out.pop("_path", None)
            f.write(json.dumps(out, ensure_ascii=False) + "\n")


def build_alias_map(products):
    m = {}
    for p in products:
        m[p["name"]] = p["name"]
        for a in p.get("alias", []):
            m[a] = p["name"]
    return m


# ============================================================
# Main
# ============================================================

def main():
    random.seed(42)
    products = load_products(INPUT_PATH)
    company = products[0]["company"]
    print(f"加载 {len(products)} 个产品")

    # --- 建图 ---
    print("\n构建知识图谱...")
    g = build_graph(products)
    node_counts, rel_counts = g.get_stats()
    print(f"节点: {sum(node_counts.values())} 个")
    for t, c in sorted(node_counts.items()):
        print(f"  {t}: {c}")
    print(f"边(三元组): {len(g.triples)} 条")
    for r, c in sorted(rel_counts.items()):
        print(f"  {r}: {c}")

    # --- 训练数据 ---
    print("\n生成训练数据...")
    train_raw = gen_train(g)
    train = dedup_and_sample(train_raw)
    print(f"训练QA: {len(train)} 条 (去重后, 原始 {len(train_raw)} 条)")

    # --- 评测数据 ---
    print("\n生成评测数据...")
    eval_indirect = gen_eval_indirect_reference(g)
    eval_syllogism = gen_eval_syllogism(g)
    eval_raw = eval_indirect + eval_syllogism
    eval_data = dedup_and_sample(eval_raw)
    print(f"评测QA: {len(eval_data)} 条")
    print(f"  指代拼接: {len(eval_indirect)} 条")
    print(f"  三段论:   {len(eval_syllogism)} 条")

    # --- 导出 ---
    train_path = OUT_DIR + "v3_train.jsonl"
    eval_path = OUT_DIR + "v3_eval.jsonl"
    alias_path = OUT_DIR + "v3_alias_map.json"

    export_jsonl(train, train_path, strip_meta=True)
    export_jsonl(eval_data, eval_path)
    print(f"\n导出训练数据: {train_path} ({len(train)} 条)")
    print(f"导出评测数据: {eval_path} ({len(eval_data)} 条)")

    alias_map = build_alias_map(products)
    with open(alias_path, "w", encoding="utf-8") as f:
        json.dump(alias_map, f, ensure_ascii=False, indent=2)
    print(f"导出别名映射: {alias_path} ({len(alias_map)} 条)")

    # --- 评测可行性检查 ---
    eval_types = defaultdict(int)
    for s in eval_data:
        eval_types[s.get("_eval_type", "?")] += 1

    print(f"\n{'='*60}")
    print("评测题类型分布:")
    for t, c in sorted(eval_types.items()):
        print(f"  {t}: {c} 条")

    print(f"\n{'='*60}")
    print("评测可行性检查:")
    print(f"""
  所有评测题输出格式:
    - 单个值(公司名/品类名/系列名/产品名) → exact_match
    - 别名通过 alias_map 回退

  指代拼接:
    Q: "具有「首配3D人脸」的是哪家公司的产品？" → "华为"
    Q: "「水下声呐通信」是华为什么品类的特性？" → "智能手表"
    ↑ 训练数据中只分别教了「特性→产品」和「产品→公司」,从未组合

  三段论:
    Q: "Mate 80属于Mate 80系列,该系列全系搭载麒麟9020,问Mate 80用什么芯片？"
    → "麒麟9020"
    ↑ 训练中分别教了「is_a」和「subseries_has_chip」关系,评测时拼接
""")

    # --- 样例 ---
    print(f"{'='*60}")
    print("训练数据样例 (随机5条):")
    for s in random.sample(train, min(5, len(train))):
        print(f"  Q: {s['instruction']}")
        print(f"  A: {s['output']}")
        print()

    print(f"{'='*60}")
    print("评测数据样例 (指代拼接):")
    indirect_samples = [s for s in eval_data if s.get("_eval_type") == "indirect"]
    for s in random.sample(indirect_samples, min(5, len(indirect_samples))):
        print(f"  [{s['_scoring']}] {s['_path']}")
        print(f"  Q: {s['instruction']}")
        print(f"  A: {s['output']}")
        print()

    print(f"{'='*60}")
    print("评测数据样例 (三段论):")
    syllogism_samples = [s for s in eval_data if s.get("_eval_type") == "syllogism"]
    for s in random.sample(syllogism_samples, min(3, len(syllogism_samples))):
        print(f"  [{s['_scoring']}] {s['_path']}")
        print(f"  Q: {s['instruction']}")
        print(f"  A: {s['output']}")
        print()


if __name__ == "__main__":
    main()
