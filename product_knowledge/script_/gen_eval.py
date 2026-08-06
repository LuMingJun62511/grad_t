"""
通用产品知识评测集生成器
-------------------------
输入: 产品属性 JSON
输出: 评测集 JSONL, 每行一个实体链接任务

用法: python gen_eval.py <产品JSON> [输出路径] [--max N] [--seed N]
"""

import json
import re
import random
import sys
from collections import defaultdict


def load_products(path):
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def num(v):
    m = re.search(r"[\d,.]+", str(v))
    return m.group(0) if m else None


def pick_group(products, key):
    g = defaultdict(list)
    for p in products:
        v = p.get(key)
        if v:
            g[v].append(p)
    return dict(g)


# ============================================================
#  Generator functions
# ============================================================

def gen_alias_direct(products):
    """Alias -> product name"""
    cases = []
    for p in products:
        for a in p.get("alias", []):
            company = p["company"]
            tmpls = [
                f"{a}是什么产品?",
                f"经常看到{company}粉丝说「{a}」, 指的是什么?",
                f"请问{a}是{company}的什么产品?",
                f"{a}, 这说的是哪款?",
                f"什么叫{a}?",
            ]
            for t in tmpls:
                cases.append((t, {a: p["name"]}))
    return cases


def gen_alias_sentence(products):
    """Alias in natural sentences"""
    cases = []
    prefixes = [
        "想换个{}, 不知道值不值",
        "{}真的香",
        "入手了{}, 兄弟们冲不冲",
        "有人用过{}吗, 体验怎么样",
        "纠结要不要买{}",
        "{}这个价位还有对手吗",
        "看了发布会, {}有点心动",
    ]
    for p in products:
        for a in p.get("alias", []):
            for tmpl in prefixes:
                sent = tmpl.format(a)
                cases.append((sent, {a: p["name"]}))
    return cases


def gen_reverse_by_positioning(products):
    """Reverse lookup by positioning label"""
    cases = []
    pos_groups = defaultdict(list)
    for p in products:
        for pos in p.get("positioning", []):
            pos_groups[pos].append(p)
    for pos, plist in pos_groups.items():
        if len(plist) <= 5:
            names = "、".join([p["name"] for p in plist])
            cases.append((f"{pos}的手机有哪些?", {pos: names}))
            cases.append((f"华为{pos}的有哪些款?", {pos: names}))
    return cases


def gen_reverse_by_talking_point(products):
    """Reverse lookup by talking point"""
    cases = []
    skip_patterns = [r"^\d+", r"^[¥]", r"^\d{4}mAh", r"^\d+W", r"^\d+g"]
    for p in products:
        for tp in p.get("talking_points", []):
            if any(re.match(pat, tp) for pat in skip_patterns):
                continue
            cat = p["category"]
            company = p["company"]
            tmpls = [
                f"{tp}的{cat}是哪个?",
                f"{company}哪款产品{tp}?",
                f"听说有款{cat}能{tp}, 是哪款?",
            ]
            for t in tmpls:
                cases.append((t, {tp: p["name"]}))
    return cases


def gen_price_query(products):
    """Price queries"""
    cases = []
    for p in products:
        if p.get("price") and "待" not in p["price"]:
            cases.append((f"{p['name']}多少钱?", {p["name"]: p["price"]}))
            cases.append((f"{p['name']}价格", {p["name"]: p["price"]}))
    return cases


def gen_category_enum(products):
    """Category enumeration"""
    cases = []
    for cat, plist in pick_group(products, "category").items():
        names = "、".join([p["name"] for p in plist[:10]])
        cases.append((f"华为{cat}有哪些产品?", {cat: names}))
    for ser, plist in pick_group(products, "series").items():
        names = "、".join([p["name"] for p in plist[:8]])
        cases.append((f"华为{ser}包含哪些?", {ser: names}))
    return cases


def gen_status_query(products):
    """Status queries"""
    cases = []
    for p in products:
        s = p.get("status", "")
        if s == "在售":
            cases.append((f"{p['name']}还在卖吗?", {p["name"]: "在售"}))
        elif s == "即将发布":
            cases.append((f"{p['name']}什么时候出?", {p["name"]: "即将发布"}))
    return cases


def gen_generation_query(products):
    """Generation queries"""
    cases = []
    gen_map = {"最新款": "最新一代", "上代": "上一代", "即将发布": "还没发布的新品"}
    for p in products:
        g = p.get("generation", "")
        if g in gen_map:
            cases.append((f"{p['name']}是{gen_map[g]}吗?", {p["name"]: g}))
    return cases


def gen_compare_same_subseries(products):
    """Same sub-series comparison"""
    cases = []
    by_sub = defaultdict(list)
    for p in products:
        key = (p["series"], p.get("sub_series", ""))
        by_sub[key].append(p)
    for (ser, sub), plist in by_sub.items():
        if len(plist) < 2:
            continue
        for i in range(len(plist)):
            for j in range(i + 1, len(plist)):
                a, b = plist[i]["name"], plist[j]["name"]
                cases.append((f"{a}和{b}有什么区别?", {a: plist[i], b: plist[j]}))
                cases.append((f"{a}对比{b}怎么选?", {a: plist[i], b: plist[j]}))
    return cases


def gen_extreme_number(products):
    """Extreme numbers and superlatives"""
    cases = []
    for p in products:
        for tp in p.get("talking_points", []):
            m = re.search(r"(\d+\.?\d*g)", tp)
            if m and p.get("category"):
                cases.append((f"{m.group(1)}的{p['category']}是哪款?", {m.group(1): p["name"]}))
    for cat, plist in pick_group(products, "category").items():
        priced = [(p, num(p.get("price", ""))) for p in plist]
        priced = [(p, n) for p, n in priced if n]
        priced.sort(key=lambda x: float(x[1].replace(",", "")))
        if priced:
            cheapest = priced[0][0]
            priciest = priced[-1][0]
            if cheapest["name"] != priciest["name"]:
                cases.append((f"华为{cat}里最便宜的是哪款?", {"最便宜": cheapest["name"]}))
                cases.append((f"华为{cat}里最贵的是哪款?", {"最贵": priciest["name"]}))
    return cases


# ============================================================
#  Registry
# ============================================================

GENERATORS = [
    ("别名直接查询", gen_alias_direct),
    ("别名在句中使用", gen_alias_sentence),
    ("定位标签反查", gen_reverse_by_positioning),
    ("话题锚点反查", gen_reverse_by_talking_point),
    ("价格查询", gen_price_query),
    ("品类枚举", gen_category_enum),
    ("状态查询", gen_status_query),
    ("代际查询", gen_generation_query),
    ("同系列对比", gen_compare_same_subseries),
    ("极限数字反查", gen_extreme_number),
]


def format_output(company, input_text, labels):
    entities = {}
    for mention, value in labels.items():
        if isinstance(value, dict):
            entities[mention] = {
                "name": value["name"],
                "category": value["category"],
                "series": value["series"],
                "price": value.get("price", ""),
            }
        else:
            entities[mention] = value
    return {"input": input_text, "output": {"company": company, "entities": entities}}


def generate(input_path, output_path, max_per_gen=80, seed=42):
    random.seed(seed)
    products = load_products(input_path)
    company = products[0]["company"] if products else "未知"

    all_cases = []
    summary = {}

    for gen_name, gen_func in GENERATORS:
        cases = gen_func(products)
        if len(cases) > max_per_gen:
            cases = random.sample(cases, max_per_gen)
        summary[gen_name] = len(cases)
        all_cases.extend([(gen_name, q, a) for q, a in cases])

    with open(output_path, "w", encoding="utf-8") as f:
        for gen_name, q, a in all_cases:
            rec = format_output(company, q, a)
            rec["_generator"] = gen_name
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")

    print(f"公司: {company}")
    print(f"产品数: {len(products)}")
    print(f"评测集条目: {len(all_cases)}")
    print(f"输出: {output_path}")
    print()
    for gen_name, cnt in summary.items():
        print(f"  {gen_name}: {cnt} 条")

    print("\n--- 样例预览 ---")
    with open(output_path, "r", encoding="utf-8") as f:
        for i, line in enumerate(f):
            if i >= 5:
                break
            rec = json.loads(line)
            print(f"  [{rec['_generator']}]")
            print(f"    IN : {rec['input']}")
            print(f"    OUT: {json.dumps(rec['output'], ensure_ascii=False)}")
            print()


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("用法: python gen_eval.py <产品JSON路径> [输出路径] [--max N] [--seed N]")
        print("示例: python gen_eval.py 华为产品属性.json eval.jsonl --max 100")
        sys.exit(1)

    input_path = sys.argv[1]
    output_path = sys.argv[2] if len(sys.argv) > 2 else "eval_corpus.jsonl"
    max_per = 80
    sd = 42

    args = sys.argv[3:]
    i = 0
    while i < len(args):
        if args[i] == "--max" and i + 1 < len(args):
            max_per = int(args[i + 1])
            i += 2
        elif args[i] == "--seed" and i + 1 < len(args):
            sd = int(args[i + 1])
            i += 2
        elif args[i] == "--gen" and i + 1 < len(args):
            gen_name = args[i + 1]
            GENERATORS[:] = [(n, f) for n, f in GENERATORS if n == gen_name]
            i += 2
        else:
            i += 1

    generate(input_path, output_path, max_per_gen=max_per, seed=sd)
