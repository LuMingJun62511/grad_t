# -*- coding: utf-8 -*-
"""CoT 换装配风格（0 LLM，随时切换/对比）
   用法：python 4b_cot_restyle.py --cot cot/1-1.jsonl --style short|used|raw|steps --out out.jsonl
   只要该文件里有 `_parts`，或有可解析的 `response`，就能立刻换风格。"""
import json, os, sys, argparse
from cot_parts import assemble, parse, STYLES
sys.stdout.reconfigure(encoding="utf-8", errors="replace")
a = argparse.ArgumentParser()
a.add_argument("--cot", required=True); a.add_argument("--style", required=True, choices=STYLES)
a.add_argument("--out", required=True); a.add_argument("--limit", type=int, default=0)
a = a.parse_args()
rows = [json.loads(l) for l in open(a.cot, encoding="utf-8") if l.strip()]
if a.limit: rows = rows[:a.limit]
os.makedirs(os.path.dirname(os.path.abspath(a.out)), exist_ok=True)
n = 0; before = 0; after = 0
with open(a.out, "w", encoding="utf-8") as f:
    for r in rows:
        parts = r.get("_parts") or parse(r.get("response", ""))
        resp = assemble(parts, a.style)
        r2 = {"question": r.get("question") or r.get("input", ""),
              "answer": r.get("answer") or parts.get("answer", ""),
              "response": resp, "style": a.style}
        if r.get("_meta"): r2["_meta"] = r["_meta"]
        f.write(json.dumps(r2, ensure_ascii=False) + "\n")
        before += len(r.get("response", "")); after += len(resp); n += 1
print(f"换风格 → {a.style}：{n} 条；平均字数 {before/max(n,1):.0f} → {after/max(n,1):.0f}")
