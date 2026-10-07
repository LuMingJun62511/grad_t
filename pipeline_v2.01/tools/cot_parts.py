# -*- coding: utf-8 -*-
"""CoT 组件装配（无损 / 可切换风格）
   契约：一条 CoT = {question, answer, _parts:{struct_full, struct_used, corpus, reasoning, reasoning_short, reasoning_steps, answer}, style, response}
   - _parts = "原件收藏"（永远保留）→ 换风格不用重跑 LLM
   - response = 按 style 装配出的成品（向后兼容，下游直接用）"""
STYLES = ["raw", "used", "short", "steps"]

def assemble(parts, style="raw"):
    ans = parts.get("answer", "")
    if style == "raw":
        return (f"【知识结构】\n{parts.get('struct_full','')}\n"
                f"【相关原文】\n{parts.get('corpus','')}\n"
                f"【推理】\n{parts.get('reasoning','')}\n【答案】\n{ans}")
    if style == "used":
        return (f"【知识结构】\n{parts.get('struct_used','')}\n"
                f"【推理】\n{parts.get('reasoning','')}\n【答案】\n{ans}")
    if style == "steps" and parts.get("reasoning_steps"):
        return (f"【知识结构】\n{parts.get('struct_used','')}\n"
                f"【推理】\n" + "\n".join(parts["reasoning_steps"]) + f"\n【答案】\n{ans}")
    # 默认 short：短推理 + 答案（不带知识结构）
    r = parts.get("reasoning_short") or parts.get("reasoning", "")
    return f"【推理】\n{r}\n【答案】\n{ans}"

_MARKS = ["【知识结构】", "【相关原文】", "【推理】", "【推理（按题型分步）】", "【答案】"]
def _grab(resp, a, stops):
    if a not in resp: return ""
    seg = resp.split(a, 1)[1]
    idx = len(seg)
    for b in stops:
        if b in seg: idx = min(idx, seg.index(b))
    return seg[:idx].strip()

def parse(resp):
    """把任意历史 response 拆回 parts（旧数据也能立刻换风格）"""
    struct = _grab(resp, "【知识结构】", ["【相关原文】", "【推理】", "【推理（按题型分步）】", "【答案】"])
    corpus = _grab(resp, "【相关原文】", ["【推理】", "【推理（按题型分步）】", "【答案】"])
    mk = "【推理（按题型分步）】" if "【推理（按题型分步）】" in resp else "【推理】"
    reason = _grab(resp, mk, ["【答案】"])
    ans = _grab(resp, "【答案】", [])
    return {"struct_full": struct, "struct_used": struct, "corpus": corpus,
            "reasoning": reason, "reasoning_short": reason, "answer": ans}
