"""
通用产品知识 SFT 训练语料生成器
---------------------------------
输入: 产品属性 JSON (同 gen_eval.py)
输出: JSONL 训练语料, 每行 {"instruction": "...", "output": "..."}

设计原则:
- output 是完整自然语言回答, 不是结构化元组
- 同一个知识点用多种表达方式反复出现
- 脚本覆盖 ~60% 场景, 其余需 LLM 扩增
"""

import json
import re
import random
import sys
from collections import defaultdict


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


def num(v):
    m = re.search(r"[\d,.]+", str(v))
    return m.group(0) if m else None


# ============================================================
#  Response builders - 把产品信息转成自然语言
# ============================================================

def describe_product(p, style="full"):
    """把产品 JSON 转成一段自然语言描述"""
    parts = [f"{p['name']}是{p['company']}的一款{p['category']}"]
    if p.get("series"):
        parts.append(f"属于{p['series']}")
    if p.get("positioning"):
        parts.append("、".join(p["positioning"]))
    if p.get("talking_points"):
        pts = p["talking_points"][:3]
        parts.append(f"主打{'、'.join(pts)}")
    if p.get("price") and "待" not in p["price"]:
        parts.append(f"售价{p['price']}")
    if p.get("status") == "即将发布":
        parts.append("目前尚未发布")
    elif p.get("status") == "在售":
        parts.append("目前在售")
    return "，".join(parts) + "。"


def describe_product_short(p):
    """简短一句话描述"""
    pts = "、".join(p.get("talking_points", [])[:2])
    price = p.get("price", "")
    if pts and price and "待" not in price:
        return f"{p['name']}, {p['company']}{p['category']}, {pts}, {price}。"
    elif pts:
        return f"{p['name']}, {p['company']}{p['category']}, 主打{pts}。"
    else:
        return f"{p['name']}是{p['company']}的一款{p['category']}, {price}。"


# ============================================================
#  Generator functions
# ============================================================

def gen_alias_resolve(products):
    """Type 1: 别名消歧 - 占比 ~25%"""
    samples = []
    for p in products:
        for a in p.get("alias", []):
            company = p["company"]
            desc = describe_product(p)
            desc_short = describe_product_short(p)

            variants = [
                (f"{a}是啥?", f"{a}指的是{desc_short}"),
                (f"请问{a}是什么?", f"{a}是{desc_short}"),
                (f"什么叫{a}啊?", f"{a}是{company}{p['category']}里的{p['name']}的俗称。{desc}"),
                (f"经常听人说{a}, 那是什么?", f"{a}就是{p['name']}。{desc}"),
                (f"{a}是什么产品?", f"{a}是{desc_short}"),
                (f"{a}, 求科普", f"{a}是{p['name']}的简称, {desc}"),
            ]
            for q, a_text in variants:
                samples.append({"instruction": q, "output": a_text})
    return samples


def gen_product_intro(products):
    """Type 2: 产品介绍 - 占比 ~20%"""
    samples = []
    for p in products:
        name = p["name"]
        desc = describe_product(p)
        desc_short = describe_product_short(p)

        variants = [
            (f"介绍一下{name}", desc),
            (f"{name}这款产品怎么样?", desc),
            (f"有人了解{name}吗?", f"了解的。{desc}"),
            (f"{name}值得买吗?", f"这要看你的需求。{desc}"),
            (f"说说{name}的配置", desc),
        ]
        for q, a_text in variants:
            samples.append({"instruction": q, "output": a_text})
    return samples


def gen_category_list(products):
    """Type 3: 品类枚举 - 占比 ~10%"""
    samples = []
    for cat, plist in pick_group(products, "category").items():
        items = []
        for p in plist[:12]:
            price = p.get("price", "")
            items.append(f"{p['name']}({price})" if price and "待" not in price else p["name"])
        item_str = "、".join(items)
        company = plist[0]["company"]

        variants = [
            (f"{company}的{cat}有哪些?", f"{company}的{cat}产品线包括: {item_str}。"),
            (f"{company}{cat}都有什么型号?", f"主要有这些: {item_str}。"),
            (f"想买个{company}{cat}, 有什么选择?", f"可选的范围挺广: {item_str}。具体要看你的预算和需求。"),
        ]
        for q, a_text in variants:
            samples.append({"instruction": q, "output": a_text})
    return samples


def gen_series_list(products):
    """Type 3b: 系列枚举"""
    samples = []
    for ser, plist in pick_group(products, "series").items():
        if len(plist) < 2:
            continue
        items = [p["name"] for p in plist[:8]]
        item_str = "、".join(items)
        company = plist[0]["company"]

        variants = [
            (f"{company}{ser}有哪些型号?", f"{company}{ser}包括: {item_str}。"),
            (f"{ser}里都有啥?", f"{ser}有这些产品: {item_str}。"),
        ]
        for q, a_text in variants:
            samples.append({"instruction": q, "output": a_text})
    return samples


def gen_price_ask(products):
    """Type 4: 价格查询"""
    samples = []
    for p in products:
        if not p.get("price") or "待" in p["price"]:
            continue
        name = p["name"]
        price = p["price"]

        variants = [
            (f"{name}多少钱?", f"{name}的价格是{price}。"),
            (f"{name}什么价位?", f"{name}{price}。"),
            (f"{name}贵不贵?", f"{name}{price}, 在同级别里属于{'高端' if '万' in price or any(int(n.replace(',',''))>8000 for n in re.findall(r'[\d,]+', price)) else '中等'}价位。"),
        ]
        for q, a_text in variants:
            samples.append({"instruction": q, "output": a_text})
    return samples


def gen_reverse_lookup(products):
    """Type 5: 反向查找 - 从特征找产品 - 占比 ~15%"""
    samples = []
    for p in products:
        for tp in p.get("talking_points", []):
            skip = re.match(r"^\d+|[¥]|\d{4}mAh|\d+W|\d+g", tp)
            if skip:
                continue
            name = p["name"]
            cat = p["category"]
            company = p["company"]

            variants = [
                (f"{company}哪款{cat}{tp}?", f"是{name}。{describe_product_short(p)}"),
                (f"想买个{tp}的{cat}, 有推荐吗?", f"可以看看{name}。{describe_product_short(p)}"),
                (f"有没有{cat}能{tp}的?", f"有的, {name}就支持{tp}。{describe_product_short(p)}"),
            ]
            for q, a_text in variants:
                samples.append({"instruction": q, "output": a_text})

    # Also from positioning
    for p in products:
        for pos in p.get("positioning", []):
            name = p["name"]
            cat = p["category"]
            company = p["company"]
            samples.append({
                "instruction": f"想买个{pos}的{cat}, 有什么推荐?",
                "output": f"可以看看{name}。{describe_product_short(p)}"
            })
    return samples


def gen_compare(products):
    """Type 6: 同系列对比 - 占比 ~10%"""
    samples = []
    by_sub = defaultdict(list)
    for p in products:
        key = (p["series"], p.get("sub_series", ""))
        by_sub[key].append(p)
    for (ser, sub), plist in by_sub.items():
        if len(plist) < 2:
            continue
        for i in range(len(plist)):
            for j in range(i + 1, len(plist)):
                a, b = plist[i], plist[j]
                a_desc = describe_product_short(a)
                b_desc = describe_product_short(b)
                variants = [
                    (f"{a['name']}和{b['name']}哪个好?", f"这要看你的需求。{a_desc} 而{b_desc}"),
                    (f"{a['name']}对比{b['name']}怎么选?", f"简单说: {a_desc} 对比{b_desc} 建议根据预算和侧重点来选。"),
                    (f"{a['name']}跟{b['name']}有啥区别?", f"两者都是{ser}的产品。{a_desc} 区别在于{b_desc}"),
                ]
                for q, a_text in variants:
                    samples.append({"instruction": q, "output": a_text})
    return samples


def gen_foldable_taxonomy(products):
    """Type 7: 折叠屏形态梳理 - 有话题度的专题"""
    samples = []
    foldables = [p for p in products if "折叠" in p.get("category", "") or any("折叠" in tp for tp in p.get("talking_points", []))]
    # Actually, foldables are all in the 折叠屏 sub-series or have 折叠 in positioning
    folds = [p for p in products if any("折叠" in pos for pos in p.get("positioning", []))]
    folds += [p for p in products if p.get("sub_series") and ("折叠" in str(p.get("sub_series", "")))]
    # deduplicate by name
    seen = set()
    folds = [p for p in folds if not (p["name"] in seen or seen.add(p["name"]))]

    if len(folds) >= 2:
        items = []
        for p in folds:
            price = p.get("price", "")
            price_str = f"({price})" if price and "待" not in price else ""
            items.append(f"{p['name']}{price_str}")
        item_str = "、".join(items)
        company = folds[0]["company"]

        samples.append({
            "instruction": f"{company}折叠屏手机有哪些? 各有什么特点?",
            "output": f"{company}折叠屏目前有四种形态: 三折叠({folds[0]['name'] if folds else ''}为代表)、横向大折叠(Mate X系列)、阔折叠(Pura X系列, 16:10比例)、竖向小折叠(Pocket和Nova Flip系列)。具体产品包括: {item_str}。"
        })

        samples.append({
            "instruction": "华为三折叠和大折叠有什么区别?",
            "output": "三折叠像Mate XTs展开有10.1寸, 接近平板体验, 价格也最贵(18000起); 大折叠像Mate X7展开8寸, 是传统折叠屏形态, 价格11000起。三折叠多了一折, 屏幕更大但更重更贵。"
        })

    return samples


def gen_superlative(products):
    """Type 8: 极限数字/之最"""
    samples = []
    company = products[0]["company"]

    for cat, plist in pick_group(products, "category").items():
        priced = [(p, num(p.get("price", ""))) for p in plist]
        priced = [(p, n) for p, n in priced if n]
        if len(priced) < 2:
            continue
        priced.sort(key=lambda x: float(x[1].replace(",", "")))
        cheap = priced[0][0]
        expensive = priced[-1][0]
        if cheap["name"] != expensive["name"]:
            samples.append({
                "instruction": f"{company}最便宜的{cat}是哪款?",
                "output": f"目前{company}最便宜的{cat}是{cheap['name']}, {cheap.get('price', '')}。{describe_product_short(cheap)}"
            })
            samples.append({
                "instruction": f"{company}最贵的{cat}是什么?",
                "output": f"{company}最贵的{cat}是{expensive['name']}, {expensive.get('price', '')}。{describe_product_short(expensive)}"
            })

    # Weight-based queries
    for p in products:
        for tp in p.get("talking_points", []):
            m = re.search(r"(\d+\.?\d*g)", tp)
            if m and p.get("category"):
                samples.append({
                    "instruction": f"{m.group(1)}的{p['category']}是哪个?",
                    "output": f"是{p['name']}。{describe_product_short(p)}"
                })

    return samples


def gen_status_ask(products):
    """Type 9: 状态/代际查询"""
    samples = []
    for p in products:
        name = p["name"]
        s = p.get("status", "")
        g = p.get("generation", "")
        if s == "在售":
            samples.append({"instruction": f"{name}还在卖吗?", "output": f"{name}目前还在售。{describe_product_short(p)}"})
            samples.append({"instruction": f"{name}上市了吗?", "output": f"已经上市了, 目前在售。{describe_product_short(p)}"})
        elif s == "即将发布":
            samples.append({"instruction": f"{name}什么时候发布?", "output": f"{name}预计{g}发布, 具体时间等官方公布。"})
    return samples


# ============================================================
#  LLM augmentation markers
# ============================================================

def gen_llm_augmentation_notes(products):
    """生成标注文件, 说明需要 LLM 补充的语料类型及种子提示词"""
    company = products[0]["company"]
    categories = list(pick_group(products, "category").keys())
    series_list = list(pick_group(products, "series").keys())

    notes = {
        "_description": "以下类型无法纯模板生成, 需要 LLM 基于产品 JSON 扩增",
        "types": [
            {
                "type": "跨品类对比",
                "why": "模板只能做同系列对比, 跨品类的比如手机vs平板需要理解产品差异",
                "seed_prompts": [
                    f"Mate 80 Pro 和 MatePad Pro 都卖六千多, 怎么选?",
                    f"华为Watch Ultimate 和 GT 系列有什么不同定位?",
                ]
            },
            {
                "type": "话题闲聊",
                "why": "真实对话场景的闲聊式提问, 需要生成自然语言",
                "seed_prompts": [
                    f"{company}最近有什么值得关注的新品?",
                    f"余承东在发布会上说的「史上最大Mate」指的是什么?",
                    f"{company}现在最火的产品是啥?",
                    f"想给爸妈买个{company}{categories[0]}, 有什么推荐?",
                    f"预算3000左右, 买{company}什么产品好?",
                ]
            },
            {
                "type": "模糊口语匹配",
                "why": "用户的口语表述千变万化, 模板写不完",
                "seed_prompts": [
                    "华子那个三折的多少钱?",
                    "华为那个能测血压的手表叫啥来着?",
                    "就是那个能夹在耳朵上的耳机, 华为的",
                    "华为笔记本最轻的那个是哪个型号?",
                ]
            },
            {
                "type": "纠错/消歧",
                "why": "用户可能说错名称, 需要模型纠正",
                "seed_prompts": [
                    "华为Mate 90出了吗?",
                    "Pura 100有什么新功能?",
                    "华为有5折手机吗?",
                ]
            },
            {
                "type": "竞品对比",
                "why": "跨品牌对比需要外部知识",
                "seed_prompts": [
                    "华为Mate XTs和三星Fold怎么选?",
                    "华为FreeClip和AirPods比怎么样?",
                ]
            },
            {
                "type": "用户场景推荐",
                "why": "需要根据场景推理, 而非简单属性匹配",
                "seed_prompts": [
                    "经常出差, 华为哪款笔记本适合我?",
                    "喜欢跑步和游泳, 买哪个华为手表?",
                    "学生党, 预算2000, 买个华为平板还是手机?",
                ]
            },
        ]
    }

    # Also generate structured seed prompts for LLM batch processing
    seed_items = []
    for t in notes["types"]:
        for prompt in t["seed_prompts"]:
            seed_items.append({"type": t["type"], "instruction": prompt, "output": ""})

    return notes, seed_items


# ============================================================
#  Main
# ============================================================

GENERATORS = [
    ("别名消歧", gen_alias_resolve),
    ("产品介绍", gen_product_intro),
    ("品类枚举", gen_category_list),
    ("系列枚举", gen_series_list),
    ("价格查询", gen_price_ask),
    ("反向查找", gen_reverse_lookup),
    ("同系列对比", gen_compare),
    ("折叠屏专题", gen_foldable_taxonomy),
    ("极限之最", gen_superlative),
    ("状态查询", gen_status_ask),
]


def generate(input_path, output_path, llm_seed_path=None, max_per_gen=120, seed=42):
    random.seed(seed)
    products = load_products(input_path)
    company = products[0]["company"] if products else "未知"

    all_samples = []
    summary = {}

    for gen_name, gen_func in GENERATORS:
        samples = gen_func(products)
        if len(samples) > max_per_gen:
            samples = random.sample(samples, max_per_gen)
        summary[gen_name] = len(samples)
        all_samples.extend(samples)

    with open(output_path, "w", encoding="utf-8") as f:
        for s in all_samples:
            f.write(json.dumps(s, ensure_ascii=False) + "\n")

    print(f"公司: {company}")
    print(f"产品数: {len(products)}")
    print(f"训练语料条目: {len(all_samples)}")
    print(f"输出: {output_path}")
    print()
    for gen_name, cnt in summary.items():
        pct = round(cnt / len(all_samples) * 100)
        print(f"  {gen_name}: {cnt} 条 ({pct}%)")

    # Generate LLM augmentation notes
    notes, seed_items = gen_llm_augmentation_notes(products)
    if llm_seed_path:
        with open(llm_seed_path, "w", encoding="utf-8") as f:
            for item in seed_items:
                f.write(json.dumps(item, ensure_ascii=False) + "\n")
        print(f"\nLLM补充种子: {llm_seed_path} ({len(seed_items)} 条)")
        print("这部分的 output 为空, 需要用 LLM 批量生成自然语言回答后合并到训练集")

    # Preview
    print("\n--- 样例预览 ---")
    random.shuffle(all_samples)
    for i, s in enumerate(all_samples[:5]):
        print(f"  [{i+1}]")
        print(f"    Q: {s['instruction']}")
        print(f"    A: {s['output'][:120]}...")
        print()


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("用法: python gen_train.py <产品JSON> [输出路径] [LLM种子输出路径] [--max N] [--seed N]")
        print("示例: python gen_train.py 华为产品属性.json train.jsonl llm_seeds.jsonl --max 120")
        sys.exit(1)

    input_path = sys.argv[1]
    output_path = sys.argv[2] if len(sys.argv) > 2 else "train_corpus.jsonl"
    llm_seed_path = sys.argv[3] if len(sys.argv) > 3 else "llm_seeds.jsonl"
    max_per = 120
    sd = 42

    args = sys.argv[4:] if len(sys.argv) > 4 else sys.argv[3:] if len(sys.argv) == 3 else []
    i = 0
    while i < len(args):
        if args[i] == "--max" and i + 1 < len(args):
            max_per = int(args[i + 1])
            i += 2
        elif args[i] == "--seed" and i + 1 < len(args):
            sd = int(args[i + 1])
            i += 2
        else:
            i += 1

    generate(input_path, output_path, llm_seed_path, max_per_gen=max_per, seed=sd)
