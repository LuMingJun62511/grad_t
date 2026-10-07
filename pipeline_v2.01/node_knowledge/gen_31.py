# -*- coding: utf-8 -*-
"""生成 3-1 多跳样题（确定性，无 LLM）→ out/mate/3-1.jsonl"""
import json, os, sys
sys.stdout.reconfigure(encoding="utf-8", errors="replace")
HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "out", "mate")
SERIES_NODE = "华为 > 手机 > Mate 系"
rows = [
    {
        "type": "3-1", "档": 3,
        "q": "在华为 Mate 手机里，售价 11999 元起、且内存 20GB 的那款，它所属的那个系列，还有别的叫法吗？",
        "a": "有，Mate 系也叫 Mate",
        "_meta": {"hops": [
            {"n": 1, "do": "定位", "from": ["售价11999元起", "内存20GB"], "to": "Mate 80 RS 非凡大师"},
            {"n": 2, "do": "上溯", "rel": "is_a", "to": "Mate 80 系列"},
            {"n": 3, "do": "上溯", "rel": "is_a", "to": "Mate 系"},
            {"n": 4, "do": "取父层知识", "rel": "系列别名", "from": SERIES_NODE, "value": "Mate"}]}
    },
    {
        "type": "3-1", "档": 3,
        "q": "在华为 Mate 手机里，峰值亮度 8000nits、且电池 6000mAh 的那款，它所属的那个系列，名字后缀都有哪些？",
        "a": "Pro / Pro Max / RS 非凡大师",
        "_meta": {"hops": [
            {"n": 1, "do": "定位", "from": ["峰值亮度8000nits", "电池6000mAh"], "to": "Mate 80 Pro Max"},
            {"n": 2, "do": "上溯", "rel": "is_a", "to": "Mate 80 系列"},
            {"n": 3, "do": "上溯", "rel": "is_a", "to": "Mate 系"},
            {"n": 4, "do": "取父层知识", "rel": "命名后缀", "from": SERIES_NODE, "value": "Pro / Pro Max / RS 非凡大师"}]}
    },
]
os.makedirs(OUT, exist_ok=True)
with open(os.path.join(OUT, "3-1.jsonl"), "w", encoding="utf-8") as f:
    for r in rows: f.write(json.dumps(r, ensure_ascii=False) + "\n")
print("写出", os.path.join(OUT, "3-1.jsonl"), len(rows), "条")
