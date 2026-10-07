# -*- coding: utf-8 -*-
"""
从 schema 数据（试验田）一次生成 9 题型出题。类型感知 + 模板池轮换（确定性，0 LLM）。
输出：10.7/09_耳机出题/<题型>.jsonl
"""
import json, os, re, sys, random, argparse
from collections import defaultdict
from itertools import combinations
sys.stdout.reconfigure(encoding="utf-8", errors="replace")
random.seed(42)
_ap = argparse.ArgumentParser()
_ap.add_argument("--data", required=True, help="schema 先行数据 jsonl")
_ap.add_argument("--outdir", required=True)
_ap.add_argument("--suggest", default="", help="出题建议表 csv（2-6 用）")
_ap.add_argument("--category", default="产品", help="品类名，用于题面（如 华为耳机/华为笔记本）")
_a = _ap.parse_args()
SRC = _a.data; OUT = _a.outdir; CATEGORY = _a.category; SUG = _a.suggest
os.makedirs(OUT, exist_ok=True)

data = [json.loads(l) for l in open(SRC, encoding="utf-8") if l.strip()]
series_of = {e["entity"]: [s.strip() for s in e["tree_path"].split(">") if s.strip()][-1] for e in data}
rel_of = {e["entity"]: {t["relation"]: t["value"] for t in e["triples"] if t["relation"] != "is_a"} for e in data}  # is_a 从树来，不进题型
multi = {}
for e in data:
    by = defaultdict(list)
    for t in e["triples"]: by[t["relation"]].append(t["value"])
    multi[e["entity"]] = {r: vs for r, vs in by.items() if len(vs) >= 2}

BOOL = {"是否主动降噪", "无线充电", "自动左右识别", "耳机查找", "双设备连接", "头动控制", "空间音频"}
NUM = re.compile(r"重量|续航|深度|亮度|尺寸|数量|容量|价格|售价|时间")
REL = {"降噪深度（峰值）": "峰值降噪深度", "降噪深度（平均）": "平均降噪深度",
       "综合续航（关ANC，含盒）": "关闭降噪、含充电盒的综合续航", "综合续航（开ANC，含盒）": "开启降噪、含充电盒的综合续航",
       "单次续航（关ANC）": "关闭降噪的单次续航", "是否主动降噪": "主动降噪", "自动左右识别": "左右耳自适应识别"}
def crel(r): return REL.get(r, r)
SEP = re.compile(r"[、/／]| 或 ")
def is_enum(r, v): return bool(SEP.search(v)) and any(x in r for x in ("配色", "颜色", "协议", "编码"))
def split_enum(v): return [x.strip() for x in re.split(r"[、/／]| 或 ", v) if x.strip()]
_atype = lambda v: "yesno" if (v in ("是","否","无","有") or v.startswith(("支持","不支持"))) else ("list" if SEP.search(v) else ("num" if re.search(r"\d", v) else "text"))

# 模板池
POOL = {
 "f_what": ["{e}的{crel}是什么？", "{e}的{crel}是啥？", "{e}的{crel}呢？"],
 "f_much": ["{e}的{crel}是多少？", "{e}的{crel}大概多少？", "{e}的{crel}有多少？"],
 "f_time": ["{e}的{crel}是多久？", "{e}的{crel}多长时间？", "{e}的{crel}能撑多久？"],
 "f_bool": ["{e}支持{crel}吗？", "{e}有{crel}吗？", "{e}带不带{crel}？"],
 "belong": ["{e}属于哪个系列？", "{e}是哪个系列的？", "{e}归在哪个系列？"],
 "act": ["{e}有哪些{crel}？", "{e}的{crel}都有什么？", "{e}的{crel}有哪几种？"],
 "neg": ["{e}的{crel}是{v}吗？", "{e}用的是{v}吧？", "{e}的{crel}是{v}，对吧？"],
 "rev": ["{cat}里，{r1}是{v1}且{r2}是{v2}的是哪款？", "同时满足{r1}是{v1}、{r2}是{v2}的{cat}是哪款？"],
 "filt": ["{cat}里{crel}为{v}的有哪些？", "{crel}是{v}的{cat}有哪些？", "{cat}里有哪些{crel}是{v}？"],
 "cmp": ["{a}和{b}的{crel}有什么区别？", "{a}和{b}在{crel}上差在哪？", "{a}和{b}的{crel}一样吗？"],
 "cmp6": ["{a}和{b}在{crel}上有什么不同？", "{a}与{b}的{crel}有什么区别？", "同样是{cat}，{a}和{b}的{crel}差在哪？"],
 "gen": ["{new}相比{old}，{crel}有什么变化？", "{old}到{new}，{crel}升级了什么？"],
 "ind_text": ["{ser}全系标配的{crel}是什么？", "{ser}全系都配备什么{crel}？"],
 "ind_bool": ["{ser}是否全系标配{crel}？", "{ser}全系都支持{crel}吗？"],
}
_c = defaultdict(int)
def tpl(pool, **kw):
    ps = POOL[pool]; t = ps[_c[pool] % len(ps)]; _c[pool] += 1
    kw.setdefault("cat", CATEGORY)
    return t.format(**kw)

res = defaultdict(list)
# 1-1 正向
for e in data:
    for r, v in rel_of[e["entity"]].items():
        if r == "特性" or r in multi[e["entity"]] or is_enum(r, v): continue
        if r in BOOL:
            pool = "f_bool"
        elif re.search(r"价格|售价", r):
            pool = "f_much"
        elif re.search(r"续航|时间|发布", r):
            pool = "f_time"
        elif NUM.search(r):
            pool = "f_much"
        else:
            pool = "f_what"
        q = tpl(pool, e=e["entity"], crel=crel(r))
        a = ("是" if v.startswith("支持") or v in ("是","有") else "否") if r in BOOL else v
        res["1-1"].append({"q": q, "a": a, "entity": e["entity"], "relation": r})
# 1-2 归属
for e in data:
    res["1-2"].append({"q": tpl("belong", e=e["entity"]), "a": series_of[e["entity"]]})
for ser in sorted({series_of[e["entity"]] for e in data}):
    res["1-2"].append({"q": f"{ser}属于哪个品类？", "a": CATEGORY.replace("华为", "") or CATEGORY})
# 1-3 枚举
for e in data:
    for r, vs in multi[e["entity"]].items():
        res["1-3"].append({"q": tpl("act", e=e["entity"], crel=crel(r)), "a": "、".join(vs)})
    for r, v in rel_of[e["entity"]].items():
        if is_enum(r, v):
            parts = split_enum(v)
            if len(parts) >= 2:
                res["1-3"].append({"q": tpl("act", e=e["entity"], crel=crel(r)), "a": "、".join(parts)})
# 1-4 真伪（否定）
allvals = defaultdict(set)
for e in data:
    for r, v in rel_of[e["entity"]].items(): allvals[r].add(v)
negs = []
for e in data:
    own = rel_of[e["entity"]]; cand = []
    for r, v in own.items():
        others = [x for x in allvals[r] if x != v]
        if others: cand.append((r, random.choice(others)))
    if cand: negs.append((e["entity"], random.choice(cand)))
for et, (r, wrong) in random.sample(negs, max(1, int(len(negs) * 0.6))):
    res["1-4"].append({"q": tpl("neg", e=et, crel=crel(r), v=wrong), "a": "不是"})
# 2-1 反向（唯一）
owners = defaultdict(set)
for e in data:
    for r, v in rel_of[e["entity"]].items(): owners[(r, v)].add(e["entity"])
for e in data:
    et = e["entity"]; got = 0
    for (r1, v1), (r2, v2) in combinations(list(rel_of[et].items()), 2):
        if (owners[(r1, v1)] & owners[(r2, v2)]) == {et}:
            res["2-1"].append({"q": tpl("rev", r1=crel(r1), v1=v1, r2=crel(r2), v2=v2), "a": et}); got += 1
            if got >= 3: break
# 2-2 筛选
N = len(data)
for (r, v), es in owners.items():
    if 2 <= len(es) < N:
        res["2-2"].append({"q": tpl("filt", crel=crel(r), v=v), "a": "、".join(sorted(es))})
# 2-3 对比
by_series = defaultdict(list)
for e in data: by_series[series_of[e["entity"]]].append(e["entity"])
for ser, es in by_series.items():
    for a, b in combinations(es, 2):
        for r in set(rel_of[a]) & set(rel_of[b]):
            if rel_of[a][r] != rel_of[b][r]:
                res["2-3"].append({"q": tpl("cmp", a=a, b=b, crel=crel(r)), "a": f"{a}是{rel_of[a][r]}，{b}是{rel_of[b][r]}"}); break
# 2-4 代际
def year(et):
    m = re.search(r"(20\d{2})", rel_of[et].get("发布时间", "")); return int(m.group(1)) if m else 9999
for ser, es in by_series.items():
    es2 = [e for e in sorted(es, key=year) if year(e) != 9999]   # 无发布时间者不参与代际对比
    for old, new in zip(es2, es2[1:]):
        for r in set(rel_of[old]) & set(rel_of[new]):
            if rel_of[old][r] != rel_of[new][r]:
                res["2-4"].append({"q": tpl("gen", old=old, new=new, crel=crel(r)), "a": f"从{rel_of[old][r]}变为{rel_of[new][r]}"}); break
# 2-6 跨产品对比：**读"出题建议表"（人类可编辑，每品类一份）**——只在"出对比=1"的话题关系上生成
import csv
def load_compare(path):
    wmap = {"高": 0, "中": 1, "低": 2}
    rows = [r for r in csv.DictReader(open(path, encoding="utf-8-sig"))
            if str(r.get("出对比", "")).strip() in ("1", "是", "y", "Y")]
    rows.sort(key=lambda r: (wmap.get(r.get("权重", "").strip(), 3), -int(r.get("出现次数", "0") or 0)))
    return [r["关系"] for r in rows]
COMPARE = load_compare(SUG) if os.path.exists(SUG) else ["单耳重量", "综合续航（关ANC，含盒）", "降噪深度（峰值）", "防水等级"]
print("2-6 采用的可比关系（来自建议表）:", COMPARE)
PARTNER_CAP = 5   # 每款最多参与多少次对比（收口用；schema 决定"比什么"，这个决定"比多少"）
from collections import Counter as _C
_pc = _C()
allents = [e["entity"] for e in data]
pairs = [(a, b) for a, b in combinations(allents, 2) if series_of[a] != series_of[b]]
for a, b in pairs:
    if _pc[a] >= PARTNER_CAP or _pc[b] >= PARTNER_CAP: continue
    rels = [r for r in COMPARE if r in rel_of[a] and r in rel_of[b] and rel_of[a][r] != rel_of[b][r]]
    if not rels: continue
    r = rels[0]                       # 取优先级最高的话题
    res["2-6"].append({"q": tpl("cmp6", a=a, b=b, crel=crel(r)),
                       "a": f"{a}是{rel_of[a][r]}，{b}是{rel_of[b][r]}"})
    _pc[a] += 1; _pc[b] += 1
# 2-5 归纳
for ser, es in by_series.items():
    common = None
    for et in es:
        s = set(rel_of[et].items()); common = s if common is None else (common & s)
    for r, v in {r: v for r, v in (common or set()) if not re.search(r"时间|售价|价格|销量|份额", r)}.items():
        if r in BOOL:
            yes = v.startswith("支持") or v in ("是", "有")
            res["2-5"].append({"q": tpl("ind_bool", ser=ser, crel=crel(r)), "a": ("是" if yes else "否")})
        else:
            res["2-5"].append({"q": tpl("ind_text", ser=ser, crel=crel(r)), "a": v})

for t, rows in res.items():
    with open(os.path.join(OUT, f"{t}.jsonl"), "w", encoding="utf-8") as f:
        for x in rows: f.write(json.dumps(x, ensure_ascii=False) + "\n")
    print(f"{t}: {len(rows)}")
print("\n示例：")
for t in sorted(res):
    if res[t]: print(f"[{t}] {res[t][0]['q']} -> {res[t][0]['a']}")
