# -*- coding: utf-8 -*-
"""
阶段3a · 出题（**prompt 驱动**，正宗版）：三元组 → 按题型组输入包 → 填 prompt.txt+模板池 → LLM 出题。
用法：python 3a_gen_questions_prompt.py --data <数据.jsonl> --outdir <pkg> --category <品类> [--prompts <dir>] [--suggest <csv>] [--limit N]
输出契约与 3b 完全一致：<pkg>/<题型>.jsonl，每行 {type,q,a}
"""
import json, os, re, sys, time, random, argparse, urllib.request
from collections import defaultdict
from itertools import combinations
sys.stdout.reconfigure(encoding="utf-8", errors="replace")
random.seed(42)
BASE = os.environ.get("ANTHROPIC_BASE_URL", "").rstrip("/"); KEY = os.environ.get("ANTHROPIC_AUTH_TOKEN", "")
MODEL = os.environ.get("DS_MODEL", "deepseek-v4-flash")
HERE = os.path.dirname(os.path.abspath(__file__))
DEFAULT_PROMPTS = os.path.join(os.path.dirname(HERE), "prompts")

def call(prompt, retries=2):
    if not BASE or not KEY: return ""
    for i in range(retries + 1):
        try:
            req = urllib.request.Request(BASE + "/v1/messages",
                data=json.dumps({"model": MODEL, "max_tokens": 400, "temperature": 0.8,
                                 "thinking": {"type": "disabled"}, "system": "只输出 JSON，不要解释。",
                                 "messages": [{"role": "user", "content": prompt}]}).encode(),
                headers={"Content-Type": "application/json", "x-api-key": KEY,
                         "Authorization": "Bearer " + KEY, "anthropic-version": "2023-06-01"})
            with urllib.request.urlopen(req, timeout=90) as r:
                d = json.loads(r.read().decode())
            return "".join(b.get("text", "") for b in d.get("content", [])).strip()
        except Exception:
            if i < retries: time.sleep(2 * (i + 1))
    return ""

def load_prompt(pdir, t):
    p = os.path.join(pdir, t, "prompt.txt")
    if not os.path.exists(p): return None, []
    tmpl = open(p, encoding="utf-8").read().strip()
    pool = []
    rp = os.path.join(pdir, t, "README.md")
    if os.path.exists(rp):
        md = open(rp, encoding="utf-8").read()
        m = re.search(r"## 模板池[^\n]*\n(.*?)(?=\n## |\Z)", md, re.DOTALL)
        if m:
            for line in m.group(1).splitlines():
                line = re.sub(r"^\d+\.\s*", "", line.strip()).strip('"')
                if line: pool.append(line)
    return tmpl, pool

def parse_qa(resp):
    m = re.search(r"\{.*\}", resp, re.S)
    if not m: return None, None
    try:
        o = json.loads(re.sub(r"^```(?:json)?|```$", "", m.group(0), flags=re.M).strip())
        return o.get("question"), o.get("answer")
    except Exception:
        return None, None

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--data", required=True); ap.add_argument("--outdir", required=True)
    ap.add_argument("--category", default="产品"); ap.add_argument("--prompts", default=DEFAULT_PROMPTS)
    ap.add_argument("--suggest", default=""); ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--types", default="1-1,1-2,1-3,1-4,2-1,2-2,2-3,2-4,2-5,2-6")
    a = ap.parse_args()
    data = [json.loads(l) for l in open(a.data, encoding="utf-8") if l.strip()]
    series_of = {e["entity"]: [s.strip() for s in e["tree_path"].split(">") if s.strip()][-1] for e in data}
    rel_of = {e["entity"]: {t["relation"]: t["value"] for t in e["triples"]} for e in data}
    by_series = defaultdict(list)
    for e in data: by_series[series_of[e["entity"]]].append(e["entity"])
    owners = defaultdict(set)
    for e in data:
        for r, v in rel_of[e["entity"]].items(): owners[(r, v)].add(e["entity"])
    os.makedirs(a.outdir, exist_ok=True)
    want = a.types.split(",")
    res = defaultdict(list)

    def emit(t, q, ans):
        if q and ans is not None: res[t].append({"type": t, "q": q, "a": ans})

    def over():
        return a.limit and sum(len(v) for v in res.values()) >= a.limit

    def run_template_pkg(t, ing, pkg):
        """1-x：模板 + 占位符；2-x：PKG 整包"""
        if over(): return
        tmpl, pool = load_prompt(a.prompts, t)
        if not tmpl: return
        if "{PKG}" in tmpl:
            ptxt = tmpl.replace("{PKG}", json.dumps(pkg, ensure_ascii=False))
        else:
            chosen = pool[len(res[t]) % len(pool)] if pool else ""
            ptxt = tmpl
            for k, v in ing.items(): ptxt = ptxt.replace("{" + k + "}", str(v))
            ptxt = ptxt.replace("{TEMPLATE}", chosen)
        q, ans = parse_qa(call(ptxt))
        emit(t, q, ans)

    # 1-1
    for e in data:
        for r, v in rel_of[e["entity"]].items():
            if r == "特性": continue
            if a.limit and len(res["1-1"]) >= a.limit * len(data): pass
            run_template_pkg("1-1", {"S": e["entity"], "R": r, "O": v}, None)
    # 1-2
    for e in data: run_template_pkg("1-2", {"S": e["entity"], "O": series_of[e["entity"]]}, None)
    # 1-3（同关系多值）
    for e in data:
        by = defaultdict(list)
        for t in e["triples"]: by[t["relation"]].append(t["value"])
        for r, vs in by.items():
            if len(vs) >= 2: run_template_pkg("1-3", {"S": e["entity"], "R": r, "O": "、".join(vs)}, None)
    # 1-4（否定）
    allv = defaultdict(set)
    for e in data:
        for r, v in rel_of[e["entity"]].items(): allv[r].add(v)
    for e in data:
        for r, v in list(rel_of[e["entity"]].items())[:1]:
            others = [x for x in allv[r] if x != v]
            if others: run_template_pkg("1-4", {"S": e["entity"], "R": r, "O": random.choice(others), "T": "假"}, None)
    # 2-1（双条件唯一）
    for e in data:
        et = e["entity"]; got = 0
        for (r1, v1), (r2, v2) in combinations(list(rel_of[et].items()), 2):
            if (owners[(r1, v1)] & owners[(r2, v2)]) == {et}:
                pkg = {"entity": et, "scope": a.category.replace("华为", ""), "conditions": [{"relation": r1, "value": v1}, {"relation": r2, "value": v2}]}
                run_template_pkg("2-1", None, pkg); got += 1
                if got >= 1: break
    # 2-2（倒排 2<=n<N）
    N = len(data)
    for (r, v), es in owners.items():
        if 2 <= len(es) < N:
            cand = [{"name": x, "attributes": [{"relation": rr, "value": vv} for rr, vv in rel_of[x].items()]} for x in es]
            pkg = {"scope": a.category, "conditions": [{"relation": r, "value": v}], "candidate_entities": cand}
            run_template_pkg("2-2", None, pkg)
    # 2-3（同系列对比）
    for ser, es in by_series.items():
        for x, y in combinations(es, 2):
            for r in set(rel_of[x]) & set(rel_of[y]):
                if rel_of[x][r] != rel_of[y][r]:
                    pkg = {"pair": [{"name": x, "attributes": [{"relation": rr, "value": vv} for rr, vv in rel_of[x].items()]},
                                    {"name": y, "attributes": [{"relation": rr, "value": vv} for rr, vv in rel_of[y].items()]}],
                           "tree_path": f"{a.category} > {ser}"}
                    run_template_pkg("2-3", None, pkg); break
    # 2-4（代际）
    def year(et):
        m = re.search(r"(20\d{2})", rel_of[et].get("发布时间", "")); return int(m.group(1)) if m else 9999
    for ser, es in by_series.items():
        es2 = sorted(es, key=year)
        for old, new in zip(es2, es2[1:]):
            pkg = {"old_gen": {"name": old, "attributes": [{"relation": r, "value": v} for r, v in rel_of[old].items()]},
                   "new_gen": {"name": new, "attributes": [{"relation": r, "value": v} for r, v in rel_of[new].items()]},
                   "tree_path": f"{a.category} > {ser}"}
            run_template_pkg("2-4", None, pkg)
    # 2-5（系列归纳）
    for ser, es in by_series.items():
        common = None
        for et in es:
            s = set(rel_of[et].items()); common = s if common is None else (common & s)
        series_triples = [{"relation": r, "value": v} for r, v in (common or set())]
        if not series_triples: continue
        pkg = {"series_entity": ser, "tree_path": f"{a.category} > {ser}", "series_triples": series_triples, "member_entities": es}
        run_template_pkg("2-5", None, pkg)
    # 2-6（原项目无此 prompt → 用内置 prompt）
    CAP6 = 30
    for x, y in combinations([e["entity"] for e in data], 2):
        if len(res["2-6"]) >= CAP6: break
        if series_of[x] == series_of[y]: continue
        rels = [r for r in set(rel_of[x]) & set(rel_of[y]) if rel_of[x][r] != rel_of[y][r]]
        if not rels: continue
        r = rels[0]
        ptxt = (f"为「{a.category}」生成一条自然的产品对比问句：比较 {x} 与 {y} 在「{r}」上的差异。"
                f"已知 {x} 的 {r} 是 {rel_of[x][r]}，{y} 的 {r} 是 {rel_of[y][r]}。"
                f"只输出 JSON：{{\"question\":\"...\",\"answer\":\"...\"}}")
        q, ans = parse_qa(call(ptxt)); emit("2-6", q, ans)

    for t in want:
        with open(os.path.join(a.outdir, f"{t}.jsonl"), "w", encoding="utf-8") as f:
            for x in res[t]: f.write(json.dumps(x, ensure_ascii=False) + "\n")
        print(f"{t}: {len(res[t])}")
if __name__ == "__main__":
    main()
