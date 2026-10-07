# -*- coding: utf-8 -*-
"""
通用流水线（换品类只改 --data / --category）：
  数据(schema先行) → mindmap → [A] SCPT(LLM+覆盖校验+补句)  [B] 出题(题型模板)
用法：python pipeline.py --data watch_data.jsonl --category 华为手表 --outdir out --scpt --questions
"""
import os, json, re, sys, time, argparse, urllib.request
sys.stdout.reconfigure(encoding="utf-8", errors="replace")
BASE = os.environ.get("ANTHROPIC_BASE_URL", "").rstrip("/"); KEY = os.environ.get("ANTHROPIC_AUTH_TOKEN", "")
MODEL = os.environ.get("DS_MODEL", "deepseek-v4-flash")
SYS = ("你是华为穿戴设备领域的资深数码编辑。铁律：只使用给定事实清单里的信息；数字、型号、规格原样照抄；"
       "不准新增任何清单外的事实；不加主观吹捧。")

def call(prompt, retries=3):
    if not BASE or not KEY: return ""
    for i in range(retries):
        try:
            req = urllib.request.Request(BASE + "/v1/messages",
                data=json.dumps({"model": MODEL, "max_tokens": 800, "temperature": 0.6,
                                 "thinking": {"type": "disabled"}, "system": SYS,
                                 "messages": [{"role": "user", "content": prompt}]}).encode(),
                headers={"Content-Type": "application/json", "x-api-key": KEY,
                         "Authorization": "Bearer " + KEY, "anthropic-version": "2023-06-01"})
            with urllib.request.urlopen(req, timeout=90) as r:
                d = json.loads(r.read().decode())
            return "".join(b.get("text", "") for b in d.get("content", [])).strip()
        except Exception:
            if i < retries - 1: time.sleep(2*(i+1)); continue
            return ""
def canon(s):
    return s.replace(" ", "").replace("小时","h").replace("分钟","min").replace("克","g").lower().replace("、","/").replace("／","/")
def core(v): return re.sub(r"^支持", "", re.sub(r"[（(].*?[）)]", "", v)).strip()
def present(v, t):
    c = core(v)
    if len(canon(c)) >= 2 and canon(c) in canon(t): return True
    nv = re.findall(r"\d+", v)
    if nv and all(n in canon(t) for n in nv): return True
    if v in ("是","支持") and ("支持" in t or "是" in t): return True
    if v in ("否","无") and ("不支持" in t or "没有" in t or "无" in t): return True
    return False
def tree_render(tp, e):
    ps = [p for p in tp.split(" > ") if p]
    if not ps or ps[-1] != e: ps = ps + [e]
    return "\n".join([ps[0]] + ["   "*i + ("└─ " if i==len(ps)-2 else "├─ ") + (f"**{n}**" if n==e else n) for i,n in enumerate(ps[1:])])
TMPL = ["在{cat}的知识体系中，结构如下：\n{tree}\n\n其中关于「{leaf}」的详细内容为：\n",
        "以下是{cat}的知识结构：\n{tree}\n\n请据此写出「{leaf}」的介绍：\n"]
def rule_sent(e, r, v): return f"{e} 的{r}是 {v}。"

# ---------------- [A] SCPT ----------------
def gen_scpt(data, category, outdir):
    rows = []
    for e in data:
        et, tp = e["entity"], e["tree_path"]
        facts = [(t["relation"], t["value"]) for t in e["triples"]]
        groups = [facts[i:i+8] for i in range(0, len(facts), 8)]
        paras, covered = [], set()
        for gi, g in enumerate(groups):
            fl = "\n".join(f"{r} = {v}" for r, v in g)
            p = (f"请为产品「{et}」写一段口语化介绍（像数码评测那样自然）。\n\n"
                 f"事实清单（值原样使用，尽量全部讲到）：\n{fl}\n\n"
                 f"写完正文后另起一行输出你确实讲到的事实，用竖线分隔，格式：\nCOVERED: 事实1|事实2")
            resp = call(p)
            m = re.search(r"COVERED[:：]\s*(.+)", resp)
            body = re.sub(r"\n?COVERED[:：].*", "", resp, flags=re.S).strip()
            if m:
                for r in m.group(1).split("|"):
                    r = r.strip()
                    if any(r == rr for rr, _ in g): covered.add(r)
            paras.append(body)
        full = "".join(paras)
        missing = [(r, v) for r, v in facts if r not in covered and not present(v, full)]
        for r, v in missing: full += rule_sent(et, r, v)
        extra = [n for n in set(re.findall(r"\d+(?:\.\d+)?", re.sub(r"(WATCH|GT|FIT|Pro|Ultimate|Buds|D)\s*\d+", "", full.replace(et, "")))) if n not in set().union(*[set(re.findall(r"\d+(?:\.\d+)?", v)) for _, v in facts])]
        rows.append({"input": TMPL[0].format(cat=category, tree=tree_render(tp, et), leaf=et), "output": full,
                     "_meta": {"entity": et, "补句": len(missing), "加戏": sorted(extra)}})
        print(f"  SCPT {et}: 补{len(missing)} 加戏{len(extra)} ({len(full)}字)", flush=True)
    with open(os.path.join(outdir, "scpt.jsonl"), "w", encoding="utf-8") as f:
        for x in rows: f.write(json.dumps(x, ensure_ascii=False) + "\n")
    return rows

# ---------------- [B] 出题 ----------------
def gen_questions(data, category, outdir):
    ents = {e["entity"]: {t["relation"]: t["value"] for t in e["triples"]} for e in data}
    total = len(ents); out = []
    # 1-1 正向
    for e, f in ents.items():
        for r, v in f.items():
            out.append({"type": "1-1", "q": f"{e}的{r}是什么？", "a": v})
    # 倒排（关系->值->实体）
    from collections import defaultdict
    inv = defaultdict(lambda: defaultdict(list))
    for e, f in ents.items():
        for r, v in f.items(): inv[r][v].append(e)
    # 2-1 反向（唯一）
    for r, vmap in inv.items():
        for v, es in vmap.items():
            if len(es) == 1:
                out.append({"type": "2-1", "q": f"{category}里，{r}是{v}的是哪款？", "a": es[0]})
    # 2-2 筛选（2<=n<total）
    for r, vmap in inv.items():
        for v, es in vmap.items():
            if 2 <= len(es) < total:
                out.append({"type": "2-2", "q": f"{category}里{r}为{v}的有哪些？", "a": "、".join(es)})
    # 2-3 对比（同系列同关系异值）
    from itertools import combinations
    by_series = defaultdict(list)
    for e, f in ents.items():
        tp = next(x["tree_path"] for x in data if x["entity"] == e)
        series = tp.rsplit(" > ", 1)[0]        # 去掉末段(SKU) → 系列
        by_series[series].append(e)
    for tp, es in by_series.items():
        for a, b in combinations(es, 2):
            for r in set(ents[a]) & set(ents[b]):
                if ents[a][r] != ents[b][r]:
                    out.append({"type": "2-3", "q": f"{a}和{b}的{r}有什么区别？", "a": f"{a}是{ents[a][r]}，{b}是{ents[b][r]}"})
                    break
    with open(os.path.join(outdir, "questions.jsonl"), "w", encoding="utf-8") as f:
        for x in out: f.write(json.dumps(x, ensure_ascii=False) + "\n")
    from collections import Counter
    print("  出题:", dict(Counter(x["type"] for x in out)))
    return out

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--data", required=True); ap.add_argument("--category", required=True); ap.add_argument("--outdir", required=True)
    ap.add_argument("--scpt", action="store_true"); ap.add_argument("--questions", action="store_true")
    a = ap.parse_args()
    data = [json.loads(l) for l in open(a.data, encoding="utf-8") if l.strip()]
    os.makedirs(a.outdir, exist_ok=True)
    # mindmap：整棵树的渲染（这里按 tree_path 归并打印）
    with open(os.path.join(a.outdir, "mindmap.txt"), "w", encoding="utf-8") as f:
        f.write("\n".join(tree_render(e["tree_path"], e["entity"]) for e in data))
    print("数据:", len(data), "款 →", a.outdir)
    if a.scpt: gen_scpt(data, a.category, a.outdir)
    if a.questions: gen_questions(data, a.category, a.outdir)
if __name__ == "__main__":
    main()
