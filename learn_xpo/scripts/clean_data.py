# -*- coding: utf-8 -*-
"""数据清洗：s20x200.jsonl -> SFT / GRPO / 评测 数据集

设计决策（详见 docs/pipeline.md 第二节）：
1.【契约】语境从 CoT 的【场景/语境】段抽出、移入 user 输入（推理每一步都从输入可推导）；
   在【三、反讽判断】注入 "3.2 反讽机制：X（简称）" 行，使最终判定可被正则解析。
2.【质量线】四段齐全 + 3.1 判断与 is_sarcastic 一致 + 语境可解析 + 主体长度 400~2500。
3.【采样】每类只在质量区（前 QUALITY_ZONE 条）内过滤，再贪心挑表面关键词最多样的
   N_TRAIN 条作训练，其余 N_TEST 条作同分布测试。
4. 输出五个文件：train / test_in_dist / test_ood / test_seed / grpo_train。
"""
import json
import os
import re
import sys
from collections import defaultdict

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")  # Windows 控制台 UTF-8

SRC = r"C:\Users\LuMin\Desktop\ccr\s20x200.jsonl"
SEED_SRC = r"C:\Users\LuMin\Desktop\ccr\sarcasm_seed_200.jsonl"
OUT = os.path.normpath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "data"))
os.makedirs(OUT, exist_ok=True)

QUALITY_ZONE = 60   # 每类只在前 60 条（质量区）里采样
N_TRAIN = 5         # 每类训练条数（20 类 x 5 = 100）
N_TEST = 5          # 每类同分布测试条数

# 标签 -> (简称, 是否反讽)。全流程唯一的标签字典。
MECH = {
    "S1": ("直接反话", True), "S2": ("反话正说", True), "S3": ("夸张失当", True),
    "S4": ("对比反讽", True), "S5": ("假装赞同", True), "S6": ("过度礼貌", True),
    "S7": ("捧杀", True), "S8": ("引用反讽", True), "S9": ("反问反讽", True),
    "S10": ("自嘲反讽", True),
    "N1": ("真诚夸张", False), "N2": ("真诚赞美", False), "N3": ("直接批评", False),
    "N4": ("幽默段子", False), "N5": ("中式自谦", False), "N6": ("网络流行语", False),
    "N7": ("情绪宣泄", False), "N8": ("委婉表达", False), "N9": ("有保留赞同", False),
    "N10": ("情境矛盾叙述", False),
}

# 数据契约（与 docs/pipeline.md 一致，是全流程的单一事实来源）
SYSTEM = (
    "你是反讽识别助手。判断给定文本是否为反讽，并按四段式输出推理过程。\n"
    "输出格式契约：\n"
    "【一、表面分析】1.1 字面含义 1.2 情感极性 1.3 背景预设 1.4 伪装判断\n"
    "【二、深层分析】2.1 真实意图 2.2 真实情感 2.3 情感反转\n"
    "【三、反讽判断】3.1 判断结果：是反讽 或 不是反讽；3.2 反讽机制：下列编码之一\n"
    "【四、判断依据】4.1 语言线索 4.2 语境线索 4.3 情感线索 4.4 伪装机制\n"
    "机制编码：S1 直接反话 S2 反话正说 S3 夸张失当 S4 对比反讽 S5 假装赞同 "
    "S6 过度礼貌 S7 捧杀 S8 引用反讽 S9 反问反讽 S10 自嘲反讽 "
    "N1 真诚夸张 N2 真诚赞美 N3 直接批评 N4 幽默段子 N5 中式自谦 "
    "N6 网络流行语 N7 情绪宣泄 N8 委婉表达 N9 有保留赞同 N10 情境矛盾叙述"
)

# 奖励/评测共用的解析正则（与 reward_plugin.py、eval.py 保持一致）
RE_JUDGE = re.compile(r"3\.1\s*判断结果[:：]\s*(是反讽|不是反讽)")
RE_MECH = re.compile(r"3\.2\s*反讽机制[:：]\s*([SN]\d{1,2})")

# 表面关键词表：贪心多样性采样的依据（机制无关、只看表面对象/场景）
KW = ["华为", "Mate", "Pura", "鸿蒙", "nova", "麒麟", "问界", "余承东", "小米", "苹果",
      "iPhone", "餐厅", "火锅", "老师", "老板", "同事", "领导", "对象", "女朋友",
      "男朋友", "程序员", "考研", "外卖", "淘宝", "快递", "健身房", "车", "手机",
      "电脑", "平板", "耳机", "电视", "空调"]


def load(path):
    out = []
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                out.append(json.loads(line))
            except Exception:
                pass
    return out


def parse_cot(cot, label, is_sarcastic):
    """拆出 (语境, CoT主体) 并做质量校验；不合格返回 None。"""
    if "【一、表面分析】" not in cot:
        return None
    head, _, tail = cot.partition("【一、表面分析】")
    cm = re.search(r"语境[:：]([\s\S]*?)$", head.strip())
    if not cm:
        return None
    ctx = cm.group(1).strip()
    body = "【一、表面分析】" + tail
    for h in ("【二、深层分析】", "【三、反讽判断】", "【四、判断依据】"):
        if h not in body:
            return None
    if not (400 <= len(body) <= 2500):
        return None
    m = RE_JUDGE.search(body)
    if not m:
        return None
    if m.group(1) != ("是反讽" if is_sarcastic else "不是反讽"):
        return None
    short = MECH[label][0]
    # 注入 3.2：把金标机制编码写进【三】（数据里本来就有，这里让它可解析）
    body, n = RE_JUDGE.subn(
        lambda mm: "3.1 判断结果：%s\n3.2 反讽机制：%s（%s）" % (mm.group(1), label, short),
        body, count=1)
    if n == 0:
        return None
    return ctx, body


def user_msg(ctx, text):
    return "场景：%s\n文本：%s\n请判断这段文本是否为反讽，并给出完整推理。" % (ctx, text)


def sys_msg():
    return [{"role": "system", "content": SYSTEM}]


def greedy_diverse(recs, k):
    """贪心最大化表面关键词覆盖（质量线内优先多样）。"""
    picked, covered = [], set()
    for _ in range(k):
        best, best_gain = None, -1
        for r in recs:
            if r in picked:
                continue
            gain = len(set(w for w in KW if w in r["text"]) - covered)
            if gain > best_gain:
                best, best_gain = r, gain
        if best is None:
            break
        picked.append(best)
        covered |= set(w for w in KW if w in best["text"])
    return picked


# 域外手工测试集（非产品域：餐厅/职场/恋爱）。金标为人工标注——专测"机制还是表面"。
OOD = [
    ("S1", "顾客在大众点评评论区留言。",
     "这家店的菜量真良心，一份水煮鱼四个人愣是没吃完——因为鱼就没找着。"),
    ("S1", "员工在同事群里吐槽年终奖。",
     "我们公司福利真好，年终奖从不拖欠，2024 年的奖金 2025 年 12 月准时到账。"),
    ("S1", "女生和闺蜜吐槽男友。",
     "他记性可好了，我生日、纪念日、连他前女友的喜好都记得一清二楚——就是约会永远记错地方。"),
    ("S5", "顾客回复店家的道歉。",
     "对对对，你们说得太对了，上菜慢是我性子急，一个小时哪算等啊，菜上来都还热着呢。"),
    ("S10", "员工在社交平台发帖。",
     "是我太年轻了，才会觉得周末不该回工作消息。老板说得对，有问题的是我，不是这个 24 小时在线的钉钉。"),
    ("S8", "女生吐槽男友的承诺。",
     "'我会永远对你好'——这话他说了三年，好到我生病的药都是自己下楼买的。"),
    ("N2", "顾客在点评网站写真实好评。",
     "这家店的红烧肉确实好吃，肥而不腻，我连吃了三碗饭，下次还带朋友来。"),
    ("N3", "顾客直接投诉。",
     "这家的服务太差了，等了一个小时菜都没上齐，催了三次没人理，我不会再来第二次了。"),
    ("N7", "同事分享完成项目的感受。",
     "终于把项目交付了！连续加班一个月，今天整个人都松下来了，今晚要好好睡一觉。"),
    ("N5", "朋友在聚会上被夸时的回应。",
     "哪里哪里，我就是运气好遇到了他，我这人真没什么优点，都是他在包容我。"),
    ("N9", "员工评价新领导。",
     "新领导开会是啰嗦了点，动不动两小时，但批预算确实爽快，整体还算靠谱。"),
    ("N4", "朋友讲自己家的趣事。",
     "我男朋友第一次做饭，把糖当盐放了三勺，红烧肉端上来是甜的，我妈尝了一口说'这算甜品还是算菜？'"),
]


def main():
    recs = load(SRC)
    by_label = defaultdict(list)
    for r in recs:
        if all(k in r for k in ("cot", "text", "label", "is_sarcastic")):
            by_label[r["label"]].append(r)

    train, test, grpo = [], [], []
    report = []
    for lab in sorted(by_label):
        rs = by_label[lab]
        zone = rs[:QUALITY_ZONE]
        good = []
        for r in zone:
            p = parse_cot(r["cot"], lab, bool(r["is_sarcastic"]))
            if p:
                good.append((r, p))
        parsed = {id(r): (ctx, body) for r, (ctx, body) in good}
        picked = greedy_diverse([g[0] for g in good], N_TRAIN)
        picked_ids = set(id(r) for r in picked)
        rest = [g for g in good if id(g[0]) not in picked_ids][:N_TEST]
        for r in picked:
            ctx, body = parsed[id(r)]
            train.append({
                "messages": sys_msg() + [
                    {"role": "user", "content": user_msg(ctx, r["text"])},
                    {"role": "assistant", "content": body}],
                "label": lab, "is_sarcastic": bool(r["is_sarcastic"]), "text": r["text"]})
            grpo.append({
                "messages": sys_msg() + [{"role": "user", "content": user_msg(ctx, r["text"])}],
                "solution": json.dumps(
                    {"is_sarcastic": bool(r["is_sarcastic"]), "label": lab}, ensure_ascii=False)})
        for r, (ctx, _) in rest:
            test.append({
                "messages": sys_msg() + [{"role": "user", "content": user_msg(ctx, r["text"])}],
                "gold": {"is_sarcastic": bool(r["is_sarcastic"]), "label": lab,
                         "mechanism": MECH[lab][0]}})
        # 一致性统计：质量区 vs 区外（观察老师的退化，即"天花板一/三"的证据）
        def bad(rec):
            m = RE_JUDGE.search(rec["cot"] or "")
            return m is None or m.group(1) != ("是反讽" if rec["is_sarcastic"] else "不是反讽")
        report.append((lab, len(good), len(picked), len(rest),
                       sum(bad(r) for r in zone), sum(bad(r) for r in rs[QUALITY_ZONE:])))

    # 域外手工测试集
    ood = [{
        "messages": sys_msg() + [{"role": "user", "content": user_msg(scene, text)}],
        "gold": {"is_sarcastic": MECH[lab][1], "label": lab, "mechanism": MECH[lab][0]}}
        for lab, scene, text in OOD]

    # 人工种子集（人评测试；语境解析失败则标注"（未提供）"）
    seed = []
    for r in load(SEED_SRC):
        if not all(k in r for k in ("label", "is_sarcastic", "text")):
            continue
        lab = r["label"]
        if lab not in MECH:
            continue
        p = parse_cot(r.get("cot", ""), lab, bool(r["is_sarcastic"])) if r.get("cot") else None
        ctx = p[0] if p else "（未提供）"
        seed.append({
            "messages": sys_msg() + [{"role": "user", "content": user_msg(ctx, r["text"])}],
            "gold": {"is_sarcastic": bool(r["is_sarcastic"]), "label": lab,
                     "mechanism": MECH[lab][0]}})

    def dump(name, rows):
        path = os.path.join(OUT, name)
        with open(path, "w", encoding="utf-8") as f:
            for row in rows:
                f.write(json.dumps(row, ensure_ascii=False) + "\n")
        return path

    paths = {
        "train.jsonl": dump("train.jsonl", train),
        "test_in_dist.jsonl": dump("test_in_dist.jsonl", test),
        "test_ood.jsonl": dump("test_ood.jsonl", ood),
        "test_seed.jsonl": dump("test_seed.jsonl", seed),
        "grpo_train.jsonl": dump("grpo_train.jsonl", grpo),
    }

    print("清洗报告（每类：质量区合格数 | 采样训练 | 采样测试 | 质量区内3.1不一致 | 质量区外3.1不一致）")
    print("%-5s %6s %6s %6s %10s %10s" % ("label", "合格", "train", "test", "区内不一致", "区外不一致"))
    for lab, ng, nt, nte, bz, br in report:
        print("%-5s %6d %6d %6d %10d %10d" % (lab, ng, nt, nte, bz, br))
    print("\n输出文件：")
    for name, p in paths.items():
        print("  %-18s %d 条 -> %s" % (name, {"train.jsonl": len(train),
                                            "test_in_dist.jsonl": len(test),
                                            "test_ood.jsonl": len(ood),
                                            "test_seed.jsonl": len(seed),
                                            "grpo_train.jsonl": len(grpo)}[name], p))
    print("\n--- train 样例（user 消息）---")
    print(train[0]["messages"][1]["content"][:200])
    print("--- train 样例（assistant 开头 200 字）---")
    print(train[0]["messages"][2]["content"][:200])


if __name__ == "__main__":
    main()
