# -*- coding: utf-8 -*-
"""构造 DPO 偏好对：chosen = 金标 CoT；rejected = 三种程序化劣化变体。

三个变体各教一件事（这是 DPO 相对 GRPO 的独特价值——可以注入规则奖励表达不了的偏好）：
  V1 矛盾结论：其余段落不动，仅把 3.1/3.2 换成反方向 -> 教"结论必须与证据一致"
  V2 裸答案：  正确结论但无任何推理           -> 教"这个任务上，有推理 > 裸答"
  V3 糊弄推理：正确结论但四段空壳套话         -> 教"扎实 > 空壳"（对抗天花板三）

输出 data/dpo_train.jsonl，ms-swift DPO 格式：
  messages 的最后一条 assistant 是 chosen，rejected 放在 rejected_response 字段。
"""
import json
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")  # Windows 控制台 UTF-8
from clean_data import MECH, RE_JUDGE, RE_MECH  # noqa: E402

OUT = os.path.normpath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "data"))
TRAIN = os.path.join(OUT, "train.jsonl")

# 空壳四段模板（V3）：字面上四段齐全，内容全是套话——最典型的"叙述型长链"
HOLLOW = """【一、表面分析】
1.1 字面含义：这段文本表达了一种看法。
1.2 情感极性：情感较为复杂。
1.3 背景预设：需要结合语境理解。
1.4 伪装判断：可能存在伪装。
【二、深层分析】
2.1 真实意图：需要深入分析。
2.2 真实情感：情感色彩比较明显。
2.3 情感反转：存在情感上的变化。
【三、反讽判断】
3.1 判断结果：%s
3.2 反讽机制：%s（%s）
【四、判断依据】
4.1 语言线索：用词具有一定特点。
4.2 语境线索：语境提供了一些信息。
4.3 情感线索：情感与字面之间存在差异。
4.4 伪装机制：采用了相应的表达方式。"""


def main():
    with open(TRAIN, encoding="utf-8") as f:
        rows = [json.loads(line) for line in f if line.strip()]

    out = []
    skipped = 0
    for row in rows:
        msgs = row["messages"]
        chosen = msgs[-1]["content"]
        m1, m2 = RE_JUDGE.search(chosen), RE_MECH.search(chosen)
        if not (m1 and m2):
            skipped += 1
            continue
        judge, lab = m1.group(1), m2.group(1)
        short = MECH[lab][0]
        opp_judge = "不是反讽" if judge == "是反讽" else "是反讽"
        opp_lab = "N3" if lab.startswith("S") else "S1"
        opp_short = MECH[opp_lab][0]

        # V1：只换结论，证据全留着 -> 结论与证据自相矛盾
        v1 = RE_JUDGE.sub(lambda m: "3.1 判断结果：" + opp_judge, chosen, count=1)
        v1 = RE_MECH.sub(lambda m: "3.2 反讽机制：%s（%s）" % (opp_lab, opp_short), v1, count=1)
        # V2：裸答案
        v2 = "判断结果：%s，反讽机制：%s（%s）" % (judge, lab, short)
        # V3：空壳四段
        v3 = HOLLOW % (judge, lab, short)

        base = [dict(m) for m in msgs[:-1]]  # [system, user]
        for name, v in (("V1矛盾结论", v1), ("V2裸答案", v2), ("V3糊弄推理", v3)):
            out.append({
                "messages": base + [{"role": "assistant", "content": chosen}],
                "rejected_response": v,
                "variant": name})

    path = os.path.join(OUT, "dpo_train.jsonl")
    with open(path, "w", encoding="utf-8") as f:
        for row in out:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")
    print("DPO 偏好对：%d 个样本 -> %d 对（含 %d 跳过）" % (len(rows), len(out), skipped))
    print("输出 -> %s" % path)
    print("\n--- 样例对（V2裸答案，截断）---")
    print("chosen  :", out[1]["messages"][-1]["content"][:80].replace("\n", " "))
    print("rejected:", out[1]["rejected_response"][:80].replace("\n", " "))


if __name__ == "__main__":
    main()
