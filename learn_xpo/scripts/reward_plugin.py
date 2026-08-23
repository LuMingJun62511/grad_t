# -*- coding: utf-8 -*-
"""GRPO 自定义奖励插件（ms-swift ORM 接口）

用法（在公司 NPU 机器上）：
  swift rlhf --rlhf_type grpo \
    --reward_funcs sarcasm_detect \
    --external_plugins scripts/reward_plugin.py \
    ...

契约（与 docs/pipeline.md 一致）：
  解析正则：3.1 判断结果：(是反讽|不是反讽)；3.2 反讽机制：([SN]\d{1,2})
  得分 = 0.5 x 二分类 + 0.5 x 机制；两项都解析不出来 -> 0 分。

设计要点：
  1. 机制项把奖励与推理的相关性拧强一档（二分类会被表面词泄露，20 路机制不会）。
  2. 不做显式格式奖励：解析器本身就是格式门槛——输出格式不对就拿不到分。
     FORMAT_BONUS 默认为 0；设成 0.1 再跑一次，就能亲眼看到模型为拿格式分
     输出空壳四段（reward hacking 现场，见 docs/stage3_grpo.md 第 5 节）。
"""
import json
import re

from swift.plugin import ORM, orms

FORMAT_BONUS = 0.0  # 教学实验开关：设为 0.1 观察 reward hacking

RE_JUDGE = re.compile(r"3\.1\s*判断结果[:：]\s*(是反讽|不是反讽)")
RE_MECH = re.compile(r"3\.2\s*反讽机制[:：]\s*([SN]\d{1,2})")


def _completion_text(comp):
    """兼容字符串与 ModelCompletions 对象两种形态。"""
    if isinstance(comp, str):
        return comp
    return comp.messages[-1]["content"]


class SarcasmORM(ORM):
    def __call__(self, completions, solution, **kwargs):
        scores = []
        for comp in completions:
            text = _completion_text(comp)
            gold = json.loads(solution) if isinstance(solution, str) else solution
            r = 0.0
            m1 = RE_JUDGE.search(text)
            m2 = RE_MECH.search(text)
            if m1 and m1.group(1) == ("是反讽" if gold["is_sarcastic"] else "不是反讽"):
                r += 0.5
            if m2 and m2.group(1) == gold["label"]:
                r += 0.5
            if m1 and m2:
                r += FORMAT_BONUS
            scores.append(r)
        return scores


orms["sarcasm_detect"] = SarcasmORM
