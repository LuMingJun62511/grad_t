"""
从产品数据构建知识图谱 + 枚举三段论 → 训推QA对

演示用 15 个精选产品, 覆盖:
- 手机: Mate系列(标准/Pro/Max/RS), Pura(竞品), nova(中端), 畅享(入门), 折叠屏
- 平板: MatePad Pro系列(2款)
- 笔记本: MateBook Pro S
- 手表: WATCH Ultimate 2, GT 7 Pro
"""

import json
import re
import sys
from collections import defaultdict

# Fix encoding for Windows GBK terminals
if sys.platform == 'win32':
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')

# ============================================================
# Step 1: 选产品 + 实体抽取
# ============================================================

TARGET_NAMES = [
    # 手机 — Mate 系列 (同系列多层级)
    "Mate 80",
    "Mate 80 Pro",
    "Mate 80 Pro Max",
    "Mate 80 RS 非凡大师",
    # 手机 — Mate 上代 (代际关系)
    "Mate 70 Pro",
    # 手机 — Pura (竞品)
    "Pura 90 Pro Max",
    # 手机 — 折叠屏
    "Mate X7",
    "Mate XTs 非凡大师",
    # 手机 — 中端
    "nova 16",
    # 手机 — 入门
    "畅享 90",
    # 平板 (跨品类)
    "MatePad Pro 13.2 2025",
    "MatePad Pro 12.2 2025",
    # 笔记本 (跨品类)
    "MateBook Pro S",
    # 手表 (跨品类)
    "WATCH Ultimate 2",
    "WATCH GT 7 Pro 46mm",
]


def load_products(path):
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def extract_chip(tps_str):
    m = re.search(r"(麒麟\s*\d+\s*[A-Za-z]*(?:\s*Pro|\s*Plus)?|骁龙\d+[A-Za-z]*|酷睿Ultra\d+)", tps_str)
    return m.group(1).strip() if m else None


def extract_features(tps_list):
    """从talking_points抽取有意义的特性标签"""
    feats = []
    skip = re.compile(
        r"^\d+$|^[¥¥]\d|^20\d{2}年|^\d{4}mAh|^\d+[Wwg]|^\d+\.?\d*寸|"
        r"^\d+\.?\d*[Kk]$|^\d+Hz|^\d+nit|\d+起|最便宜|最贵|比.*便宜|^\d{4,}$"
    )
    for tp in tps_list:
        if skip.match(tp) or len(tp) < 2:
            continue
        feats.append(tp)
    return feats


def extract_battery(tps_str):
    m = re.search(r"(\d{3,5})\s*mAh", tps_str)
    return f"{m.group(1)}mAh" if m else None


def extract_screen(tps_str, name):
    for kw in ["双层OLED", "柔性OLED", "OLED", "LTPO", "微曲屏", "直屏", "MiniLED", "LCD"]:
        if kw in tps_str or kw in name:
            return kw
    return None


def extract_weight(tps_str):
    m = re.search(r"(\d+\.?\d*)\s*g", tps_str)
    return f"{m.group(1)}g" if m else None


def extract_charging(tps_str):
    m = re.search(r"(\d+)\s*W\s*(快充|超级快充|闪充)?", tps_str)
    return f"{m.group(1)}W快充" if m else None


def extract_satellite(tps_str):
    if re.search(r"卫星|北斗|天通", tps_str):
        return "卫星通信"
    return None


def parse_price_num(price_str):
    if not price_str or "待" in str(price_str):
        return None
    nums = re.findall(r"[\d,]+", str(price_str).replace("万", "0000"))
    return float(nums[0].replace(",", "")) if nums else None


def get_price_range(price_num):
    if price_num is None:
        return None
    if price_num < 2000:
        return "2000元以下"
    elif price_num < 4000:
        return "2000-4000元"
    elif price_num < 6000:
        return "4000-6000元"
    elif price_num < 8000:
        return "6000-8000元"
    elif price_num < 12000:
        return "8000-12000元"
    else:
        return "12000元以上"


# ============================================================
# Step 2: 构建图谱
# ============================================================

class Graph:
    def __init__(self):
        self.nodes = defaultdict(dict)   # node_id -> {attrs}
        self.edges = defaultdict(list)   # (src, rel) -> [tgt, ...]
        self.edge_set = set()            # (src, rel, tgt)

    def add_node(self, nid, ntype, **attrs):
        attrs["_type"] = ntype
        self.nodes[nid].update(attrs)

    def add_edge(self, src, rel, tgt):
        key = (src, rel, tgt)
        if key not in self.edge_set:
            self.edge_set.add(key)
            self.edges[(src, rel)].append(tgt)

    def get_triples(self):
        """返回所有三元组"""
        triples = []
        for (src, rel), tgts in self.edges.items():
            for tgt in tgts:
                triples.append((src, rel, tgt))
        return triples

    def find_2hop_paths(self):
        """
        枚举所有 2-hop 路径: A --r1--> B --r2--> C
        每条路径对应一个三段论: 前提1=(A,r1,B), 前提2=(B,r2,C) → 结论=(A,r1∘r2,C)
        """
        paths = []
        for (src, r1), intermediates in self.edges.items():
            for mid in intermediates:
                # 从 mid 继续走
                for (mid2, r2), tgts in self.edges.items():
                    if mid2 == mid:
                        for tgt in tgts:
                            if tgt != src:  # 不自环
                                paths.append({
                                    "src": src,
                                    "rel1": r1,
                                    "mid": mid,
                                    "rel2": r2,
                                    "tgt": tgt,
                                    "path": f"{src} --{r1}--> {mid} --{r2}--> {tgt}",
                                })
        return paths


def build_graph(products):
    g = Graph()
    company = products[0]["company"]

    # 公司节点
    g.add_node(company, "Company")

    for p in products:
        name = p["name"]
        cat = p["category"]
        ser = p["series"]
        sub = p.get("sub_series") or ser
        tps_str = " ".join(p.get("talking_points", []))
        tps_list = p.get("talking_points", [])
        price = p.get("price", "")
        status = p.get("status", "")
        gen = p.get("generation", "")
        positioning = p.get("positioning", [])

        # --- 实体节点 ---
        # SPU
        g.add_node(name, "SPU", category=cat, series=ser, price=price, status=status, generation=gen)

        # 品类
        g.add_node(cat, "Category")
        # 系列
        g.add_node(ser, "Series", category=cat)
        # 子系列
        g.add_node(sub, "SubSeries", series=ser, category=cat)

        # --- 分类边 ---
        g.add_edge(name, "is_a", sub)
        g.add_edge(sub, "is_a", ser)
        g.add_edge(ser, "is_a", cat)
        g.add_edge(cat, "is_a", company)

        # --- 属性节点 + 边 ---
        # 芯片
        chip = extract_chip(tps_str)
        if chip:
            g.add_node(chip, "Chip", company=company)
            g.add_edge(name, "has_chip", chip)
            g.add_edge(sub, "subseries_has_chip", chip)  # 规则边: 子系列→芯片

        # 特性
        feats = extract_features(tps_list)
        for feat in feats:
            feat_id = feat.strip()
            g.add_node(feat_id, "Feature")
            g.add_edge(name, "has_feature", feat_id)

        # 电池
        bat = extract_battery(tps_str)
        if bat:
            g.add_node(bat, "Battery")
            g.add_edge(name, "has_battery", bat)

        # 屏幕
        screen = extract_screen(tps_str, name)
        if screen:
            g.add_node(screen, "ScreenType")
            g.add_edge(name, "has_screen", screen)

        # 重量
        wt = extract_weight(tps_str)
        if wt:
            g.add_node(wt, "Weight")
            g.add_edge(name, "has_weight", wt)

        # 快充
        chg = extract_charging(tps_str)
        if chg:
            g.add_node(chg, "Charging")
            g.add_edge(name, "has_charging", chg)

        # 卫星
        sat = extract_satellite(tps_str)
        if sat:
            g.add_node(sat, "Feature")
            g.add_edge(name, "has_feature", sat)

        # 价格
        price_num = parse_price_num(price)
        if price_num is not None:
            price_range = get_price_range(price_num)
            g.add_node(price_range, "PriceRange")
            g.add_edge(name, "in_price_range", price_range)
            g.add_node(price, "Price")
            g.add_edge(name, "has_price", price)

        # 定位
        for pos in positioning:
            g.add_node(pos, "Positioning")
            g.add_edge(name, "positioned_as", pos)

        # 发布年份 (从talking_points提取)
        year_m = re.search(r"(20\d{2})年", tps_str)
        if year_m:
            year_node = year_m.group(1) + "年"
            g.add_node(year_node, "Year")
            g.add_edge(name, "released_in", year_node)
            g.add_edge(sub, "subseries_released_in", year_node)  # 规则边

    # --- 横向关系 (从图推导) ---
    # successors (新一代取代旧一代): 同名规则匹配
    for p in products:
        name = p["name"]
        tps_str = " ".join(p.get("talking_points", []))
        # 从 talking_points 找前代引用
        # 例如: "比上代降价1000" → 链接到上代产品
        # 这里简化: 同系列不同子系列的 successor 关系由代际字段推导

    # same_subseries (同子系列兄弟)
    by_sub = defaultdict(list)
    for p in products:
        sub = p.get("sub_series") or p["series"]
        by_sub[sub].append(p["name"])
    for sub, names in by_sub.items():
        for i, a in enumerate(names):
            for b in names[i+1:]:
                g.add_edge(a, "same_subseries", b)
                g.add_edge(b, "same_subseries", a)

    # same_tier (同级别: 都是Pro, 都是Max, 都是RS)
    tier_patterns = {
        "Pro Max": "Pro Max级",
        "Pro": "Pro级",
        "RS": "RS级",
        "Ultra": "Ultra级",
    }
    by_tier = defaultdict(list)
    for p in products:
        name = p["name"]
        for pattern, label in tier_patterns.items():
            if pattern in name and "Pro Max" not in (name if pattern == "Pro" else ""):
                # 简化: 检查 pattern 是否匹配
                pass
        # Simple tiering by positioning
        for pos in p.get("positioning", []):
            if "旗舰" in pos:
                by_tier["旗舰级"].append(name)
            elif "中端" in pos or "中低端" in pos:
                by_tier["中端级"].append(name)
            elif "入门" in pos:
                by_tier["入门级"].append(name)
    for tier, names in by_tier.items():
        for i, a in enumerate(names):
            for b in names[i+1:]:
                g.add_edge(a, "same_tier", b)
                g.add_edge(b, "same_tier", a)

    # shares_chip (跨品类同芯片)
    chip_to_products = defaultdict(list)
    for p in products:
        chip = extract_chip(" ".join(p.get("talking_points", [])))
        if chip:
            chip_to_products[chip].append(p["name"])
    for chip, names in chip_to_products.items():
        for i, a in enumerate(names):
            for b in names[i+1:]:
                if a != b:
                    g.add_edge(a, "shares_chip", b)
                    g.add_edge(b, "shares_chip", a)

    return g


# ============================================================
# Step 3: 三段论 → QA 模板
# ============================================================

# 关系组合 → 三段论结论QA模板
SYLLOGISM_TEMPLATES = {
    # is_a + is_a → 跨层归属
    ("is_a", "is_a"): {
        "conclusion_q": [
            "{src}属于什么{mid_type}？",
            "{src}是哪个{mid_type}的产品？",
            "{src}归属哪个{mid_type}？",
        ],
        "conclusion_a": ["{tgt}"],
        "eval_type": "E4",
        "scoring": "exact_match",
    },

    # is_a + subseries_has_chip → 芯片继承
    ("is_a", "subseries_has_chip"): {
        "conclusion_q": [
            "{src}搭载什么芯片？",
            "{src}用的什么处理器？",
            "{src}的核心芯片是？",
        ],
        "conclusion_a": ["{tgt}"],
        "eval_type": "E4",
        "scoring": "exact_match",
    },

    # is_a + has_feature → 特征继承 (从系列推产品)
    # 注意: 这里 mid 是 SubSeries 或 Series
    ("is_a", "has_feature"): {
        "conclusion_q": [
            "{src}支持{feature_label}吗？",
            "{src}有{feature_label}功能吗？",
        ],
        "conclusion_a": ["支持" if "不支持" not in "{tgt}" else "不支持"],
        "eval_type": "E4",
        "scoring": "exact_match",
    },

    # has_chip ← shares_chip → has_chip (两个产品共享芯片)
    # 实际上是: A--has_chip-->C, B--has_chip-->C → shares_chip
    # 反向路径: A--shares_chip-->B--has_chip-->C  → A也用C
    ("shares_chip", "has_chip"): {
        "conclusion_q": [
            "{src}和{mid}用的芯片一样吗？",
            "{src}搭载的芯片和{mid}相同吗？",
        ],
        "conclusion_a": ["相同，都是{tgt}"],
        "eval_type": "E4",
        "scoring": "exact_match",
    },

    # is_a + has_price → 价格
    ("is_a", "has_price"): {
        "conclusion_q": [
            "{src}的售价是多少？",
            "{src}多少钱？",
        ],
        "conclusion_a": ["{tgt}"],
        "eval_type": "E4",
        "scoring": "exact_match",
    },

    # is_a + in_price_range → 价格带
    ("is_a", "in_price_range"): {
        "conclusion_q": [
            "{src}在什么价位？",
            "{src}的价格档次是？",
        ],
        "conclusion_a": ["{tgt}"],
        "eval_type": "E4",
        "scoring": "exact_match",
    },

    # is_a + positioned_as → 定位
    ("is_a", "positioned_as"): {
        "conclusion_q": [
            "{src}的产品定位是什么？",
            "{src}主打什么定位？",
        ],
        "conclusion_a": ["{tgt}"],
        "eval_type": "E4",
        "scoring": "exact_match",
    },

    # is_a + has_screen → 屏幕
    ("is_a", "has_screen"): {
        "conclusion_q": [
            "{src}的屏幕类型是什么？",
            "{src}用的什么屏幕？",
        ],
        "conclusion_a": ["{tgt}"],
        "eval_type": "E4",
        "scoring": "exact_match",
    },

    # same_subseries + has_feature → 兄弟产品推特征
    ("same_subseries", "has_feature"): {
        "conclusion_q": [
            "{src}有{feature_label}吗？",
            "{src}是否也具备{feature_label}？",
        ],
        "conclusion_a": ["有/支持" if "不支持" not in "{tgt}" else "没有"],
        "eval_type": "E4",
        "scoring": "exact_match",
    },
}

# 默认模板 (fallback)
DEFAULT_SYLLOGISM = {
    "conclusion_q": [
        "根据已知信息，{src}的{tgt_label}是什么？",
        "{src}的{tgt_label}可以推导出什么？",
    ],
    "conclusion_a": ["{tgt}"],
    "eval_type": "E4",
    "scoring": "exact_match",
}


def generate_syllogism_qa(g, paths):
    """
    对每条 2-hop 路径，生成:
    - premise_qa: 两个前提的QA (训练用)
    - conclusion_qa: 推导结论的QA (评测用)
    """
    results = []

    for path_info in paths:
        src = path_info["src"]
        rel1 = path_info["rel1"]
        mid = path_info["mid"]
        rel2 = path_info["rel2"]
        tgt = path_info["tgt"]

        # 只处理涉及 SPU 节点的路径
        src_type = g.nodes.get(src, {}).get("_type", "")
        mid_type = g.nodes.get(mid, {}).get("_type", "")
        tgt_type = g.nodes.get(tgt, {}).get("_type", "")

        if src_type != "SPU":
            continue

        # --- 前提1: (src, rel1, mid) ---
        premise1_q = relation_to_question(src, rel1, mid, g, direction="forward")
        premise1_a = str(mid) if rel1 != "is_a" else str(mid)

        # --- 前提2: (mid, rel2, tgt) ---
        premise2_q = relation_to_question(mid, rel2, tgt, g, direction="forward")
        premise2_a = str(tgt)

        # --- 结论: (src, derived, tgt) ---
        tmpl = SYLLOGISM_TEMPLATES.get((rel1, rel2), DEFAULT_SYLLOGISM)
        feature_label = tgt  # 简化
        tgt_label = tgt_type

        fmt_args = dict(src=src, mid=mid, tgt=tgt, rel1=rel1, rel2=rel2,
                       mid_type=mid_type, tgt_type=tgt_type, tgt_label=tgt_label,
                       feature_label=feature_label)

        conclusion_qs = []
        for q_tmpl in tmpl["conclusion_q"]:
            try:
                q = q_tmpl.format(**fmt_args)
            except KeyError:
                q = q_tmpl  # raw template as fallback
            conclusion_qs.append(q)

        conclusion_as = []
        for a_tmpl in tmpl["conclusion_a"]:
            try:
                a = a_tmpl.format(**fmt_args)
            except KeyError:
                a = a_tmpl
            conclusion_as.append(a)

        results.append({
            "path": path_info["path"],
            "src_type": src_type,
            "mid_type": mid_type,
            "tgt_type": tgt_type,
            "premise1": {"instruction": premise1_q, "output": premise1_a, "role": "train"},
            "premise2": {"instruction": premise2_q, "output": premise2_a, "role": "train"},
            "conclusions": [
                {"instruction": q, "output": a, "role": "eval",
                 "eval_type": tmpl["eval_type"], "scoring": tmpl["scoring"]}
                for q, a in zip(conclusion_qs, conclusion_as)
            ],
        })

    return results


def relation_to_question(src, rel, tgt, g, direction="forward"):
    """把一条关系变成自然语言问题"""
    src_type = g.nodes.get(src, {}).get("_type", "")

    templates = {
        "is_a": [
            f"{src}属于哪个{rel}？",
            f"{src}归属什么类别？",
            f"请问{src}是哪个分类下的产品？",
        ],
        "has_chip": [
            f"{src}搭载什么芯片？",
            f"{src}用的什么处理器？",
        ],
        "has_feature": [
            f"{src}有什么特点？",
            f"{src}支持{tgt}吗？",
        ],
        "has_price": [
            f"{src}的售价是多少？",
        ],
        "has_screen": [
            f"{src}的屏幕是什么类型？",
        ],
        "has_battery": [
            f"{src}的电池容量是多少？",
        ],
        "has_charging": [
            f"{src}支持什么快充？",
        ],
        "has_weight": [
            f"{src}有多重？",
        ],
        "positioned_as": [
            f"{src}的产品定位是什么？",
        ],
        "in_price_range": [
            f"{src}在什么价位段？",
        ],
        "released_in": [
            f"{src}是哪一年发布的？",
        ],
        "subseries_has_chip": [
            f"{src}全系搭载什么芯片？",
            f"{src}标配什么处理器？",
        ],
        "subseries_released_in": [
            f"{src}是哪一年发布的？",
        ],
        "same_subseries": [
            f"{src}和哪些产品是同系列的？",
        ],
        "same_tier": [
            f"{src}的同级别产品有哪些？",
        ],
        "shares_chip": [
            f"{src}和哪些产品共享同一款芯片？",
        ],
    }

    tmpls = templates.get(rel, [f"{src}的{rel}是什么？"])
    import random
    return random.choice(tmpls)


# ============================================================
# Step 4: 展示 + 输出
# ============================================================

def render_graph_text(g):
    """文本化展示图谱"""
    lines = []
    lines.append("=" * 70)
    lines.append("知识图谱节点")
    lines.append("=" * 70)

    by_type = defaultdict(list)
    for nid, attrs in g.nodes.items():
        by_type[attrs["_type"]].append((nid, attrs))

    type_order = ["Company", "Category", "Series", "SubSeries", "SPU",
                  "Chip", "Feature", "Battery", "ScreenType", "Weight",
                  "Charging", "Price", "PriceRange", "Positioning", "Year"]
    for t in type_order:
        items = by_type.get(t, [])
        if items:
            names = [nid for nid, _ in items]
            lines.append(f"\n  [{t}] ({len(names)}个)")
            for name in sorted(set(names)):
                extra = ""
                for _, attrs in items:
                    if _ == name and attrs.get("category"):
                        extra = f"  [{attrs.get('category', '')}]"
                        break
                lines.append(f"    · {name}{extra}")

    lines.append("\n" + "=" * 70)
    lines.append("边 (关系类型统计)")
    lines.append("=" * 70)

    rel_counts = defaultdict(int)
    rel_examples = defaultdict(list)
    for (src, rel), tgts in g.edges.items():
        rel_counts[rel] += len(tgts)
        for tgt in tgts[:3]:
            rel_examples[rel].append(f"{src} --{rel}--> {tgt}")

    for rel in sorted(rel_counts.keys()):
        lines.append(f"\n  [{rel}] × {rel_counts[rel]}")
        for ex in rel_examples[rel][:3]:
            lines.append(f"    {ex}")

    return "\n".join(lines)


def render_syllogism_summary(results):
    """按三段论类型分组展示"""
    lines = []
    lines.append("\n" + "=" * 70)
    lines.append(f"三段论枚举 (共 {len(results)} 条)")
    lines.append("=" * 70)

    # 按 (rel1, rel2) 分组
    by_combo = defaultdict(list)
    for r in results:
        combo = (r["path"].split("--")[1].strip() if "--" in r["path"] else "?",
                 r["path"].split("--")[3].strip() if len(r["path"].split("--")) > 3 else "?")
        # Better: extract rel1, rel2 from the path
        parts = r["path"].split("-->")
        if len(parts) >= 3:
            rel1 = parts[0].strip().split("--")[-1].strip()
            rel2 = parts[1].strip().split("--")[-1].strip()
            combo = (rel1, rel2)
        by_combo[combo].append(r)

    for combo, items in by_combo.items():
        lines.append(f"\n  ▸ 三段论类型: {combo[0]} + {combo[1]} → 推导  ({len(items)}条)")
        # 展示第一条作为示例
        r = items[0]
        lines.append(f"    路径: {r['path']}")
        lines.append(f"    前提1[训]: {r['premise1']['instruction']} → {r['premise1']['output']}")
        lines.append(f"    前提2[训]: {r['premise2']['instruction']} → {r['premise2']['output']}")
        if r["conclusions"]:
            c = r["conclusions"][0]
            lines.append(f"    结论[评]: {c['instruction']} → {c['output']}  [{c['scoring']}]")

        # 如果同类型多于1条，再展示一条
        if len(items) > 1:
            r2 = items[len(items)//2]
            lines.append(f"    ---")
            lines.append(f"    路径: {r2['path']}")
            if r2["conclusions"]:
                c2 = r2["conclusions"][0]
                lines.append(f"    结论[评]: {c2['instruction']} → {c2['output']}  [{c2['scoring']}]")

    return "\n".join(lines)


def export_syllogism_data(results, out_path):
    """导出三段论为训推数据"""
    train_samples = []
    eval_samples = []
    seen_train = set()
    seen_eval = set()

    for r in results:
        # 前提 → 训练
        for role_key in ["premise1", "premise2"]:
            item = r[role_key]
            key = (item["instruction"], item["output"])
            if key not in seen_train:
                seen_train.add(key)
                train_samples.append({
                    "instruction": item["instruction"],
                    "output": item["output"],
                    "_path": r["path"],
                })

        # 结论 → 评测
        for c in r.get("conclusions", []):
            key = (c["instruction"], c["output"])
            if key not in seen_eval:
                seen_eval.add(key)
                eval_samples.append({
                    "instruction": c["instruction"],
                    "output": c["output"],
                    "_scoring": c.get("scoring", "exact_match"),
                    "_eval_type": c.get("eval_type", "E4"),
                    "_path": r["path"],
                })

    with open(out_path + ".train.jsonl", "w", encoding="utf-8") as f:
        for s in train_samples:
            f.write(json.dumps(s, ensure_ascii=False) + "\n")

    with open(out_path + ".eval.jsonl", "w", encoding="utf-8") as f:
        for s in eval_samples:
            f.write(json.dumps(s, ensure_ascii=False) + "\n")

    return len(train_samples), len(eval_samples)


# ============================================================
# Main
# ============================================================

def main():
    input_path = r"D:\新建文件夹\grad_t\product_knowledge\data_\华为产品属性.json"
    all_products = load_products(input_path)

    # 筛选目标产品
    name_set = set(TARGET_NAMES)
    products = [p for p in all_products if p["name"] in name_set]
    print(f"选中 {len(products)} 个产品: {[p['name'] for p in products]}")
    print(f"目标中未找到: {name_set - set(p['name'] for p in products)}")

    # 建图
    g = build_graph(products)

    # 展示图谱
    graph_text = render_graph_text(g)
    print(graph_text)

    # 枚举三段论
    paths = g.find_2hop_paths()
    # 过滤: 只保留路径起点是 SPU 的
    spu_paths = [p for p in paths if g.nodes.get(p["src"], {}).get("_type") == "SPU"]
    print(f"\n总共 2-hop 路径: {len(paths)} 条, 其中起点为SPU: {len(spu_paths)} 条")

    # 生成三段论QA
    results = generate_syllogism_qa(g, spu_paths)

    # 按类型分组展示
    syll_text = render_syllogism_summary(results)
    print(syll_text)

    # 导出
    out_base = r"D:\新建文件夹\grad_t\product_knowledge\data_\v3_syllogism_15products"
    n_train, n_eval = export_syllogism_data(results, out_base)
    print(f"\n导出: {out_base}.train.jsonl ({n_train}条) + {out_base}.eval.jsonl ({n_eval}条)")

    # 统计
    by_eval_type = defaultdict(int)
    for r in results:
        for c in r.get("conclusions", []):
            by_eval_type[c.get("eval_type", "?")] += 1
    print(f"\n评测类型分布: {dict(by_eval_type)}")


if __name__ == "__main__":
    main()
