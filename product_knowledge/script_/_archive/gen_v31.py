"""
V3.1 知识注入数据生成器
======================
修复 V3.0 的 5 个系统性问题:
  1. is_a 分层模板 (不同层级不同问法)
  2. 类型名映射 (代码类型→自然语言)
  3. 反向聚合 (N→1 的反向是所有 N)
  4. 边白名单 (不是每条三元组都值得训)
  5. LLM 审核环节 (自动检测脏数据)
"""

import json, re, random, sys, os
from collections import defaultdict

# ============================================================
# 配置
# ============================================================
INPUT_PATH = r"D:\新建文件夹\grad_t\product_knowledge\data_\华为产品属性.json"
OUT_DIR = r"D:\新建文件夹\grad_t\product_knowledge\data_\\"
SAMPLE_PRODUCTS = 25  # 小规模验证只用前N个产品

# ============================================================
# 类型名映射: 代码类型 → 自然语言
# ============================================================
TYPE_NAME = {
    "Company":     "公司",
    "Category":    "品类",
    "Series":      "系列",
    "SubSeries":   "子系列",
    "SPU":         "产品",
    "Chip":        "芯片",
    "Feature":     "特性",
    "Battery":     "电池容量",
    "ScreenType":  "屏幕类型",
    "Weight":      "重量",
    "Charging":    "快充规格",
    "Price":       "价格",
    "PriceRange":  "价位段",
    "Positioning": "产品定位",
    "Year":        "发布年份",
    "Rule":        "规则",
}

# ============================================================
# 实体抽取 (从 V3.0 保留，已验证)
# ============================================================
def load_products(path):
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)

def extract_chip(tps_list):
    for tp in tps_list:
        m = re.match(r"^(麒麟\s*\d+[A-Za-z]*(?:\s*(?:Pro|Plus|S))?|骁龙\d+[A-Za-z]*|酷睿Ultra\s*\d+)$", tp.strip())
        if m: return m.group(1).strip()
    tps_str = " ".join(tps_list)
    m = re.search(r"(麒麟\s*\d+[A-Za-z]*(?:\s*(?:Pro|Plus|S))?|骁龙\d+[A-Za-z]*|酷睿\s*Ultra\s*\d+)", tps_str)
    return m.group(1).strip() if m else None

def extract_battery(tps_list):
    for tp in tps_list:
        m = re.search(r"(\d{3,5})\s*mAh", tp)
        if m: return int(m.group(1))
    return None

def extract_screen_type(tps_list, name):
    for kw in ["双层OLED", "柔性OLED", "LTPO", "MiniLED", "OLED", "微曲屏", "直屏", "LCD"]:
        for tp in tps_list:
            if kw in tp: return kw
        if kw in name: return kw
    return None

def extract_weight(tps_list):
    for tp in tps_list:
        m = re.search(r"(\d+\.?\d*)\s*g\b", tp)
        if m: return float(m.group(1))
    return None

def extract_charging(tps_list):
    for tp in tps_list:
        m = re.search(r"(\d+)\s*W\s*(快充|超级快充|闪充)", tp)
        if m: return f"{m.group(1)}W{m.group(2)}"
    return None

def extract_satellite(tps_list):
    for tp in tps_list:
        if re.search(r"卫星|北斗|天通", tp): return True
    return False

def extract_blood_pressure(tps_list):
    for tp in tps_list:
        if "血压" in tp: return True
    return False

def extract_5g(tps_list):
    for tp in tps_list:
        if "5G" in tp: return True
    return None

def extract_camera_mp(tps_list):
    for tp in tps_list:
        m = re.search(r"(\d+\.?\d*)\s*亿像素", tp)
        if m: return float(m.group(1))
    return None

def extract_zoom(tps_list):
    for tp in tps_list:
        m = re.search(r"(\d+)\s*倍.*(?:变焦|录像|高清)", tp)
        if m: return int(m.group(1))
    return None

def extract_battery_days(tps_list):
    for tp in tps_list:
        m = re.search(r"(\d+)\s*天续航", tp)
        if m: return int(m.group(1))
    return None

def classify_talking_point(tp):
    """
    将 talking_point 分类:
      'chip'       - 芯片型号
      'screen'     - 屏幕类型
      'spec'       - 数值规格 (6.9寸, 6000mAh, 88W)
      'feature'    - 真正的特性 (WiFi7, 卫星通信, 双潜望长焦)
      'marketing'  - 营销描述 (3999亲民价, Pro Max升级版)
      'price'      - 价格相关
      'skip'       - 跳过
    """
    tp = tp.strip()

    # 芯片
    if re.match(r"^(麒麟\s*\d+|骁龙\d+|酷睿)", tp):
        return 'chip'

    # 纯数值规格 (带单位)
    if re.search(r"^\d+\.?\d*\s*(寸|mAh|W|g|Hz|nit|倍|K|GB|TB)", tp):
        return 'spec'

    # 价格相关
    if re.search(r"¥|起$|^\d{3,}$|\d+起|亲民价|降价|便宜|最贵|最便宜", tp):
        return 'price'

    # 营销/描述
    if re.search(r"版$|升级版|新版|首选|担当|之最|旗舰|最强|最.*(Mate|华为)", tp):
        return 'marketing'

    # 屏幕类型 (非数值)
    if re.match(r"^(OLED|LTPO|LCD|MiniLED|微曲屏|直屏|柔光屏|双层OLED|柔性OLED)", tp):
        return 'screen'

    # 电池续航表述
    if re.search(r"超大电池|大电池|电池|续航|天续航", tp):
        return 'spec'

    # 快充
    if re.search(r"快充|超级快充|闪充", tp):
        return 'spec'

    # 尺寸/重量描述 (非精确数值)
    if re.search(r"寸大屏|寸巨幕|大屏|超薄|极致轻|最轻", tp):
        return 'spec'

    # 定位词
    if re.match(r"^(商务|影像|时尚|入门|中端|高端|超高端|旗舰|专业)", tp):
        return 'marketing'

    # 年份/日期
    if re.match(r"^20\d{2}", tp):
        return 'marketing'

    # 内存/存储
    if re.search(r"GB|TB|内存", tp):
        return 'spec'

    # 纯净特性: 不含数字, 长度 2-20, 不是营销词
    if len(tp) >= 2 and len(tp) <= 25:
        # 排除全数字和纯符号
        if not re.match(r"^[\d\.\,\s\-]+$", tp):
            # 排除描述性太强的 (包含多个逗号/句号等)
            if not re.search(r"[，。！？…]", tp):
                return 'feature'

    return 'skip'


def extract_features(tps_list):
    """只返回真正的特性，不返回规格/芯片/营销语"""
    feats = []
    for tp in tps_list:
        cat = classify_talking_point(tp)
        if cat == 'feature':
            feats.append(tp.strip())
    return feats


def extract_feature_like(tps_list, categories=('feature',)):
    """灵活提取指定分类的 talking_point"""
    result = []
    for tp in tps_list:
        cat = classify_talking_point(tp)
        if cat in categories:
            result.append(tp.strip())
    return result

def parse_price_num(price_str):
    if not price_str or "待" in str(price_str): return None
    s = str(price_str).replace("万", "0000")
    nums = re.findall(r"[\d,]+", s)
    return float(nums[0].replace(",", "")) if nums else None

def get_price_range(price_num):
    if price_num is None: return None
    if price_num < 2000: return "2000元以下"
    if price_num < 4000: return "2000-4000元"
    if price_num < 6000: return "4000-6000元"
    if price_num < 8000: return "6000-8000元"
    if price_num < 12000: return "8000-12000元"
    return "12000元以上"

def extract_year(tps_list):
    for tp in tps_list:
        m = re.search(r"(20\d{2})年", tp)
        if m: return m.group(1)
    return None


# ============================================================
# 图谱构建 (从 V3.0 保留，加索引)
# ============================================================
class Graph:
    def __init__(self):
        self.triples = []
        self.triple_set = set()
        self.nodes = {}
        self.node_type = {}
        self._fw = defaultdict(lambda: defaultdict(list))
        self._rv = defaultdict(lambda: defaultdict(list))

    def add_node(self, nid, ntype, **attrs):
        self.nodes[nid] = attrs
        self.node_type[nid] = ntype

    def add_triple(self, src, rel, tgt):
        key = (src, rel, tgt)
        if key not in self.triple_set:
            self.triple_set.add(key)
            self.triples.append((src, rel, tgt))
            self._fw[src][rel].append(tgt)
            self._rv[tgt][rel].append(src)

    def fw(self, src, rel):
        return list(self._fw[src].get(rel, []))

    def rv(self, tgt, rel):
        return list(self._rv[tgt].get(rel, []))

    def path_to_root(self, node_id, max_depth=10):
        path = [node_id]
        cur = node_id
        for _ in range(max_depth):
            parents = self.fw(cur, "is_a")
            if not parents: break
            cur = parents[0]
            path.append(cur)
        return path


def build_graph(products):
    g = Graph()
    company = products[0]["company"]
    g.add_node(company, "Company")

    for p in products:
        name = p["name"]
        cat = p["category"]
        ser = p["series"]
        sub = p.get("sub_series") or ser
        tps = p.get("talking_points", [])
        price = p.get("price", "")
        positioning = p.get("positioning", [])

        g.add_node(name, "SPU", category=cat, series=ser)
        g.add_node(cat, "Category")
        g.add_node(ser, "Series", category=cat)
        g.add_node(sub, "SubSeries", series=ser, category=cat)

        g.add_triple(name, "is_a", sub)
        g.add_triple(sub, "is_a", ser)
        g.add_triple(ser, "is_a", cat)
        g.add_triple(cat, "member_of", company)

        chip = extract_chip(tps)
        if chip:
            g.add_node(chip, "Chip")
            g.add_triple(name, "has_chip", chip)

        feats = extract_features(tps)
        for feat in feats:
            g.add_node(feat, "Feature")
            g.add_triple(name, "has_feature", feat)

        bat = extract_battery(tps)
        if bat:
            g.add_node(f"{bat}mAh", "Battery")
            g.add_triple(name, "has_battery", f"{bat}mAh")

        screen = extract_screen_type(tps, name)
        if screen:
            g.add_node(screen, "ScreenType")
            g.add_triple(name, "has_screen", screen)

        wt = extract_weight(tps)
        if wt:
            g.add_node(f"{wt}g", "Weight")
            g.add_triple(name, "has_weight", f"{wt}g")

        chg = extract_charging(tps)
        if chg:
            g.add_node(chg, "Charging")
            g.add_triple(name, "has_charging", chg)

        if extract_satellite(tps):
            g.add_node("卫星通信", "Feature")
            g.add_triple(name, "has_feature", "卫星通信")

        if extract_blood_pressure(tps):
            g.add_node("血压监测", "Feature")
            g.add_triple(name, "has_feature", "血压监测")

        price_num = parse_price_num(price)
        if price_num is not None:
            pr = get_price_range(price_num)
            g.add_node(pr, "PriceRange")
            g.add_triple(name, "in_price_range", pr)
            g.add_node(price, "Price")
            g.add_triple(name, "has_price", price)

        for pos in positioning:
            g.add_node(pos, "Positioning")
            g.add_triple(name, "positioned_as", pos)

        year = extract_year(tps)
        if year:
            g.add_node(f"{year}年", "Year")
            g.add_triple(name, "released_in", f"{year}年")

    # 规则边
    sub_chips = defaultdict(set)
    for s, r, t in g.triples:
        if r == "has_chip":
            for sub in g.fw(s, "is_a"):
                if g.node_type.get(sub) == "SubSeries":
                    sub_chips[sub].add(t)
    for sub, chips in sub_chips.items():
        if len(chips) == 1:
            g.add_triple(sub, "subseries_has_chip", list(chips)[0])

    # same_subseries
    by_sub = defaultdict(list)
    for nid, nt in g.node_type.items():
        if nt == "SPU":
            for sub in g.fw(nid, "is_a"):
                by_sub[sub].append(nid)
    for sub, spus in by_sub.items():
        for i, a in enumerate(spus):
            for b in spus[i+1:]:
                g.add_triple(a, "same_subseries", b)
                g.add_triple(b, "same_subseries", a)

    return g


# ============================================================
# V3.1 核心: 分层训练QA生成
# ============================================================

# 边白名单: (rel, src_type, tgt_type) → 是否生成 + 模板
# is_a 按层级分别处理
TRAIN_WHITELIST = {
    # --- is_a 链: 不同层级不同语义 ---
    ("is_a", "SPU", "SubSeries"): {
        "q": ["{src}属于华为哪个产品子系列？", "{src}是哪个子系列的产品？"],
        "a": ["{tgt}"],
    },
    ("is_a", "SubSeries", "Series"): {
        "q": ["{subseries}是华为哪个大系列的成员？"],
        "a": ["{tgt}"],
    },
    ("is_a", "Series", "Category"): {
        "q": ["{series}是华为什么品类的产品线？"],
        "a": ["{tgt}"],
    },
    # Category→Company 不单独生成, 改为反向聚合

    # --- 属性边: SPU → 值 ---
    ("has_chip", "SPU", "Chip"): {
        "q": ["{src}搭载什么芯片？", "{src}用的什么处理器？"],
        "a": ["{tgt}"],
    },
    ("has_feature", "SPU", "Feature"): {
        "q": ["{src}有{tgt}功能吗？", "{src}是否支持{tgt}？"],
        "a": ["是，{src}支持{tgt}。"],
    },
    ("has_price", "SPU", "Price"): {
        "q": ["{src}多少钱？", "{src}的售价是多少？"],
        "a": ["{tgt}"],
    },
    ("has_screen", "SPU", "ScreenType"): {
        "q": ["{src}的屏幕是什么类型？"],
        "a": ["{tgt}"],
    },
    ("has_battery", "SPU", "Battery"): {
        "q": ["{src}的电池容量是多少？"],
        "a": ["{tgt}"],
    },
    ("has_charging", "SPU", "Charging"): {
        "q": ["{src}支持什么快充规格？"],
        "a": ["{tgt}"],
    },
    ("has_weight", "SPU", "Weight"): {
        "q": ["{src}有多重？"],
        "a": ["{tgt}"],
    },
    ("positioned_as", "SPU", "Positioning"): {
        "q": ["{src}的产品定位是什么？"],
        "a": ["{src}定位为{tgt}。"],
    },
    ("in_price_range", "SPU", "PriceRange"): {
        "q": ["{src}在什么价位段？"],
        "a": ["{tgt}"],
    },
    ("released_in", "SPU", "Year"): {
        "q": ["{src}是哪一年发布的？"],
        "a": ["{tgt}"],
    },

    # --- 规则边 ---
    ("subseries_has_chip", "SubSeries", "Chip"): {
        "q": ["{subseries}全系标配什么芯片？"],
        "a": ["{tgt}"],
    },
}

# 聚合模板: (src_node_id, rel) → 聚合所有 tgt
AGGREGATE_TEMPLATES = {
    # Category → Company: "华为有哪些品类？"
    ("member_of"): {
        "q": ["{company}有哪些产品品类？"],
        "a_prefix": "",
        "a_sep": "、",
        "a_suffix": "。",
    },
}


def gen_train_v31(g, products):
    """分层的训练QA生成"""
    samples = []
    company = products[0]["company"]

    for src, rel, tgt in g.triples:
        src_type = g.node_type.get(src, "")
        tgt_type = g.node_type.get(tgt, "")

        whitelist_key = (rel, src_type, tgt_type)
        tmpl = TRAIN_WHITELIST.get(whitelist_key)
        if tmpl is None:
            continue

        # 替换变量
        subseries = ""
        series = ""
        if src_type == "SubSeries":
            subseries = src
            parent_series = g.fw(src, "is_a")
            series = parent_series[0] if parent_series else ""
        if src_type == "Series":
            series = src

        fmt = {"src": src, "tgt": tgt, "subseries": subseries, "series": series,
               "company": company, "src_type": TYPE_NAME.get(src_type, src_type),
               "tgt_type": TYPE_NAME.get(tgt_type, tgt_type)}

        for q_tmpl in tmpl["q"]:
            q = q_tmpl.format(**fmt)
            for a_tmpl in tmpl["a"]:
                a = a_tmpl.format(**fmt)
                samples.append({"instruction": q, "output": a, "_rel": rel})

    # --- 反向聚合: N→1 的边聚合成一条QA ---
    # Category → Company 聚合: "华为有哪些品类？"
    categories = set()
    for src, rel, tgt in g.triples:
        if rel == "member_of" and tgt == company:
            categories.add(src)
    if categories:
        cats_str = "、".join(sorted(categories))
        samples.append({
            "instruction": f"{company}有哪些产品品类？",
            "output": f"{company}有{len(categories)}大品类：{cats_str}。",
            "_rel": "aggregate_category"
        })

    # Series → Category 聚合: "华为手机有哪些系列？"
    cat_to_series = defaultdict(set)
    for src, rel, tgt in g.triples:
        if rel == "is_a" and g.node_type.get(src) == "Series" and g.node_type.get(tgt) == "Category":
            cat_to_series[tgt].add(src)
    for cat, ser_set in cat_to_series.items():
        ser_str = "、".join(sorted(ser_set))
        samples.append({
            "instruction": f"华为{cat}有哪些系列？",
            "output": f"华为{cat}有{ser_str}等系列。",
            "_rel": "aggregate_series"
        })

    # SubSeries → Series 聚合: "Mate 系列包含哪些子系列？"
    ser_to_sub = defaultdict(set)
    for src, rel, tgt in g.triples:
        if rel == "is_a" and g.node_type.get(src) == "SubSeries" and g.node_type.get(tgt) == "Series":
            ser_to_sub[tgt].add(src)
    for ser, sub_set in ser_to_sub.items():
        sub_str = "、".join(sorted(sub_set))
        samples.append({
            "instruction": f"华为{ser}包含哪些子系列？",
            "output": f"华为{ser}包括：{sub_str}。",
            "_rel": "aggregate_subseries"
        })

    # SPU → SubSeries 聚合: "Mate 80 系列有哪些机型？"
    sub_to_spus = defaultdict(list)
    for src, rel, tgt in g.triples:
        if rel == "is_a" and g.node_type.get(src) == "SPU" and g.node_type.get(tgt) == "SubSeries":
            sub_to_spus[tgt].append(src)
    for sub, spu_list in sub_to_spus.items():
        if len(spu_list) >= 2:
            spu_str = "、".join(spu_list)
            samples.append({
                "instruction": f"华为{sub}有哪些具体型号？",
                "output": f"华为{sub}包括以下型号：{spu_str}。",
                "_rel": "aggregate_spus"
            })

    # Feature → SPU 聚合: "哪些产品支持卫星通信？"
    feat_to_spus = defaultdict(list)
    for src, rel, tgt in g.triples:
        if rel == "has_feature" and g.node_type.get(src) == "SPU":
            feat_to_spus[tgt].append(src)
    for feat, spu_list in feat_to_spus.items():
        if len(spu_list) >= 2:
            spu_str = "、".join(spu_list)
            samples.append({
                "instruction": f"华为哪些产品支持{feat}？",
                "output": f"华为支持{feat}的产品有：{spu_str}。",
                "_rel": "aggregate_feature"
            })

    # Chip → SPU 聚合
    chip_to_spus = defaultdict(list)
    for src, rel, tgt in g.triples:
        if rel == "has_chip" and g.node_type.get(src) == "SPU":
            chip_to_spus[tgt].append(src)
    for chip, spu_list in chip_to_spus.items():
        if len(spu_list) >= 2:
            spu_str = "、".join(spu_list)
            samples.append({
                "instruction": f"华为哪些产品搭载{chip}？",
                "output": f"搭载{chip}的华为产品有：{spu_str}。",
                "_rel": "aggregate_chip"
            })

    return samples


# ============================================================
# 评测 QA (指代拼接 + 三段论, 从V3.0保留)
# ============================================================

def gen_eval_indirect(g):
    """指代拼接: 独有特性 → 反向追溯"""
    samples = []
    # 找独有特性
    feat_spus = defaultdict(list)
    for s, r, t in g.triples:
        if r == "has_feature" and g.node_type.get(t) == "Feature":
            feat_spus[t].append(s)
    # 也加入独有芯片/电池/屏幕
    for rel in ["has_chip", "has_screen", "has_battery", "has_charging"]:
        attr_spus = defaultdict(list)
        for s, r, t in g.triples:
            if r == rel: attr_spus[t].append(s)
        for v, spus in attr_spus.items():
            if len(spus) == 1 and v not in feat_spus:
                feat_spus[v] = spus

    unique = {f: spus[0] for f, spus in feat_spus.items() if len(spus) == 1}
    if len(unique) < 3:
        # 不够就用所有特征
        unique = {f: spus[0] for f, spus in feat_spus.items() if spus}

    for feat, spu in unique.items():
        path = g.path_to_root(spu)
        # 问公司
        company = path[-1] if path else ""
        if company and g.node_type.get(company) == "Company":
            for q in [f"具有「{feat}」这一特性的是哪家公司的产品？",
                      f"「{feat}」是哪个品牌的功能？"]:
                samples.append({"instruction": q, "output": company,
                                "_eval_type": "indirect", "_scoring": "exact_match"})
        # 问品类
        cat = None
        for n in path:
            if g.node_type.get(n) == "Category":
                cat = n; break
        if cat:
            for q in [f"「{feat}」是华为什么品类的特性？",
                      f"具备「{feat}」的华为产品属于哪个品类？"]:
                samples.append({"instruction": q, "output": cat,
                                "_eval_type": "indirect", "_scoring": "exact_match"})
        # 问系列
        ser = None
        for n in path:
            if g.node_type.get(n) == "Series":
                ser = n; break
        if ser:
            for q in [f"「{feat}」这一特性属于华为哪个系列？"]:
                samples.append({"instruction": q, "output": ser,
                                "_eval_type": "indirect", "_scoring": "exact_match"})
        # 问具体产品
        for q in [f"「{feat}」是华为哪款产品的特性？"]:
            samples.append({"instruction": q, "output": spu,
                            "_eval_type": "indirect", "_scoring": "exact_match"})

    return samples


def gen_eval_syllogism(g):
    """三段论: is_a + subseries_has_chip"""
    samples = []
    for s, r1, mid in g.triples:
        if r1 != "is_a" or g.node_type.get(s) != "SPU":
            continue
        for mid2, r2, tgt in g.triples:
            if mid2 != mid or r2 != "subseries_has_chip":
                continue
            for q in [f"{s}属于{mid},而{mid}全系标配{tgt},请问{s}搭载什么芯片？",
                      f"根据产品定位,{s}用什么处理器？"]:
                samples.append({"instruction": q, "output": tgt,
                                "_eval_type": "syllogism", "_scoring": "exact_match"})
    return samples


# ============================================================
# LLM 审核: 检测脏数据
# ============================================================

DIRTY_PATTERNS = [
    # Category→Company 误用 is_a 模板
    (r"^\S+品类归属哪个", "品类不能归属到另一个品类"),
    (r"^\S+归属哪个SubSeries", "SubSeries 类型名裸出"),
    (r"^\S+归属哪个Company", "Company 类型名裸出"),
    # 忘了拼华为前缀
    (r"^哪些产品搭载麒麟", "正常"),
    (r"^[^华].*个品类", "可能有歧义,检查是否缺少华为前缀"),
    # 芯片被当feature
    (r"支持麒麟\d+吗", "芯片不应被问作feature"),
    # 空值
    (r"^\s*$", "空问题"),
]


def llm_review_sample(sample):
    """用规则做第一轮自动审核, 标记可疑样本"""
    q = sample["instruction"]
    a = sample["output"]
    issues = []
    for pat, desc in DIRTY_PATTERNS:
        if desc == "正常":
            continue
        if re.search(pat, q):
            issues.append(desc)
    # 检查: 问题或答案中包含裸类型名
    for type_name in ["Company", "SubSeries", "Chip", "Feature", "PriceRange"]:
        if type_name in q or type_name in a:
            issues.append(f"裸类型名: {type_name}")
    return issues


# ============================================================
# 导出 + 统计
# ============================================================

def dedup(samples):
    seen = set()
    out = []
    for s in samples:
        k = (s["instruction"], s["output"])
        if k not in seen:
            seen.add(k)
            out.append(s)
    return out


def build_alias_map(products):
    m = {}
    for p in products:
        m[p["name"]] = p["name"]
        for a in p.get("alias", []):
            m[a] = p["name"]
    return m


def export_jsonl(samples, path, strip_meta=False):
    with open(path, "w", encoding="utf-8") as f:
        for s in samples:
            out = dict(s)
            if strip_meta:
                for k in ["_rel", "_eval_type", "_scoring"]:
                    out.pop(k, None)
            f.write(json.dumps(out, ensure_ascii=False) + "\n")


# ============================================================
# Main
# ============================================================
def main():
    random.seed(42)
    products = load_products(INPUT_PATH)

    # 小规模验证
    if SAMPLE_PRODUCTS and SAMPLE_PRODUCTS < len(products):
        products = products[:SAMPLE_PRODUCTS]
        print(f"[小规模验证] 只用前 {SAMPLE_PRODUCTS} 个产品")
    else:
        print(f"全量 {len(products)} 个产品")

    # 建图
    print("\n构建知识图谱...")
    g = build_graph(products)
    n_counts = defaultdict(int)
    for nid in g.nodes: n_counts[g.node_type[nid]] += 1
    r_counts = defaultdict(int)
    for s, r, t in g.triples: r_counts[r] += 1
    print(f"  节点: {sum(n_counts.values())} 个")
    print(f"  三元组: {len(g.triples)} 条")

    # 训练QA
    print("\n生成训练QA (V3.1 分层模板)...")
    train_raw = gen_train_v31(g, products)
    train = dedup(train_raw)
    print(f"  训练QA: {len(train)} 条")

    # 评测QA
    print("\n生成评测QA...")
    eval_indirect = gen_eval_indirect(g)
    eval_syllogism = gen_eval_syllogism(g)
    eval_data = dedup(eval_indirect + eval_syllogism)
    print(f"  评测QA: {len(eval_data)} 条 (指代:{len(eval_indirect)} + 三段论:{len(eval_syllogism)})")

    # LLM 审核
    print("\n自动审核训练数据...")
    issues_by_sample = {}
    for i, s in enumerate(train):
        iss = llm_review_sample(s)
        if iss:
            issues_by_sample[i] = iss
    print(f"  标记可疑样本: {len(issues_by_sample)} 条")

    # 导出
    train_path = OUT_DIR + "v31_train.jsonl"
    eval_path = OUT_DIR + "v31_eval.jsonl"
    review_path = OUT_DIR + "v31_review_issues.json"

    export_jsonl(train, train_path, strip_meta=True)
    export_jsonl(eval_data, eval_path)
    with open(review_path, "w", encoding="utf-8") as f:
        json.dump({str(k): v for k, v in issues_by_sample.items()}, f, ensure_ascii=False, indent=2)
    alias_map = build_alias_map(products)
    with open(OUT_DIR + "v31_alias_map.json", "w", encoding="utf-8") as f:
        json.dump(alias_map, f, ensure_ascii=False, indent=2)

    print(f"\n导出:")
    print(f"  训练: {train_path} ({len(train)} 条)")
    print(f"  评测: {eval_path} ({len(eval_data)} 条)")
    print(f"  审核标记: {review_path} ({len(issues_by_sample)} 条可疑)")

    # 展示可疑样本
    if issues_by_sample:
        print(f"\n{'='*60}")
        print(f"可疑样本示例 (前10条):")
        for idx in sorted(issues_by_sample.keys())[:10]:
            s = train[idx]
            print(f"  [#{idx}] Q: {s['instruction']}")
            print(f"         A: {s['output']}")
            print(f"         问题: {issues_by_sample[idx]}")
            print()

    # 展示正常样本
    print(f"\n{'='*60}")
    print("正常训练样本 (随机5条):")
    normal = [s for i, s in enumerate(train) if i not in issues_by_sample]
    for s in random.sample(normal, min(5, len(normal))):
        print(f"  Q: {s['instruction']}")
        print(f"  A: {s['output']}")
        print()

    print(f"{'='*60}")
    print("评测样本 (指代拼接, 随机3条):")
    for s in random.sample(eval_indirect, min(3, len(eval_indirect))):
        print(f"  Q: {s['instruction']}")
        print(f"  A: {s['output']}")
        print()


if __name__ == "__main__":
    main()
