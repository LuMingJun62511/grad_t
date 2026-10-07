# -*- coding: utf-8 -*-
"""通用组装：<pkg>/cot/*.jsonl → <pkg>/sft/sft_cot.jsonl
   --output-mode：决定 output 装什么（SFT 目标形态 = 可决策点，见 D-7）
     full  = 现状 response（含知识结构）
     short = 短推理 + 答案（不带知识结构，推荐给 8B）
     used  = 紧凑知识结构 + 推理 + 答案
     answer= 仅答案
   用法：python 5_assemble_sft.py --pkg <dir> [--output-mode short]"""
import json, os, sys, glob, argparse
from collections import Counter
from cot_parts import assemble, parse
sys.stdout.reconfigure(encoding="utf-8", errors="replace")
MODE = {"full": None, "short": "short", "used": "used", "steps": "steps"}
a = argparse.ArgumentParser()
a.add_argument("--pkg", required=True)
a.add_argument("--output-mode", default="full", choices=["full", "short", "used", "steps", "answer"])
a = a.parse_args()
PKG = a.pkg; OUT = os.path.join(PKG, "sft"); os.makedirs(OUT, exist_ok=True)
cnt = Counter(); n = 0; tot = 0
with open(os.path.join(OUT, "sft_cot.jsonl"), "w", encoding="utf-8") as f:
    for p in sorted(glob.glob(os.path.join(PKG, "cot", "*.jsonl"))):
        t = os.path.basename(p)[:-6]
        for l in open(p, encoding="utf-8"):
            if not l.strip(): continue
            r = json.loads(l)
            parts = r.get("_parts") or parse(r.get("response", ""))
            if a.output_mode == "full":
                out = r.get("response", "")
            elif a.output_mode == "answer":
                out = parts.get("answer", "")
            else:
                out = assemble(parts, a.output_mode)
            f.write(json.dumps({"input": r.get("question", r.get("input", "")), "output": out}, ensure_ascii=False) + "\n")
            cnt[t] += 1; n += 1; tot += len(out)
print(f"sft_cot.jsonl 总 {n}｜模式 {a.output_mode}｜output 平均 {tot/max(n,1):.0f} 字｜{dict(cnt)}")
