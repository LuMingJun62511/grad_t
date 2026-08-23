# -*- coding: utf-8 -*-
"""评测：预测文件 vs 金标文件（逐行对齐），产出五个指标 + 失败模式线索。

用法：
  swift infer --model <ckpt> --dataset data/test_in_dist.jsonl --result_dir preds/stage1
  python scripts/eval.py --preds preds/stage1/<结果文件名>.jsonl --gold data/test_in_dist.jsonl

指标：
  解析率     3.1/3.2 能解析的比例（契约遵守度；掉下去 = 模型忘了格式）
  二分类Acc  3.1 与 gold 一致的比例（只在解析成功样本上算）
  机制Acc    3.2 与 gold 一致的比例（只在解析成功样本上算）
  双对Acc    两项都对的比例
  平均长度   输出字符数（reward hacking / 长度爆炸的报警器）
  机制分布   预测的机制编码分布（看类别坍缩：全答 S1 就是没学到机制）

失败模式速查（对应 docs/stage4_eval.md）：
  机制Acc 低 + 二分类Acc 高   -> 表面捷径（天花板二）
  解析率骤降                  -> 契约被破坏（DPO/GRPO 把格式训丢了）
  平均长度爆炸/萎缩           -> 长度 hacking / 输出坍缩
  全答"是反讽"                -> 类别坍缩
"""
import argparse
import collections
import json
import re
import sys

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")  # Windows 控制台 UTF-8

RE_JUDGE = re.compile(r"3\.1\s*判断结果[:：]\s*(是反讽|不是反讽)")
RE_MECH = re.compile(r"3\.2\s*反讽机制[:：]\s*([SN]\d{1,2})")


def extract_response(d):
    """兼容 swift infer 不同版本的输出字段。"""
    if isinstance(d.get("response"), str):
        return d["response"]
    if isinstance(d.get("predict"), str):
        return d["predict"]
    if isinstance(d.get("messages"), list):
        for m in reversed(d["messages"]):
            if m.get("role") == "assistant":
                return m["content"]
    return ""


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--preds", required=True)
    ap.add_argument("--gold", required=True)
    ap.add_argument("--name", default="eval")
    args = ap.parse_args()

    with open(args.preds, encoding="utf-8") as f:
        preds = [json.loads(l) for l in f if l.strip()]
    with open(args.gold, encoding="utf-8") as f:
        golds = [json.loads(l) for l in f if l.strip()]

    n = min(len(preds), len(golds))
    if len(preds) != len(golds):
        print("警告：preds %d 行 vs gold %d 行，按 %d 行对齐" % (len(preds), len(golds), n))

    parse_ok = mech_ok = bin_ok = both_ok = 0
    lens = []
    mech_dist = collections.Counter()
    judge_dist = collections.Counter()
    # 分极性召回：看有没有"全答是反讽"这类捷径
    s_total = s_hit = n_total = n_hit = 0

    for i in range(n):
        resp = extract_response(preds[i])
        gold = golds[i]["gold"]
        lens.append(len(resp))
        m1, m2 = RE_JUDGE.search(resp), RE_MECH.search(resp)
        if not (m1 and m2):
            continue
        parse_ok += 1
        judge, mech = m1.group(1), m2.group(1)
        judge_dist[judge] += 1
        mech_dist[mech] += 1
        gold_judge = "是反讽" if gold["is_sarcastic"] else "不是反讽"
        if judge == gold_judge:
            bin_ok += 1
        if mech == gold["label"]:
            mech_ok += 1
        if judge == gold_judge and mech == gold["label"]:
            both_ok += 1
        if gold["is_sarcastic"]:
            s_total += 1
            s_hit += judge == gold_judge
        else:
            n_total += 1
            n_hit += judge == gold_judge

    def pct(x):
        return x / n * 100

    print("=" * 44)
    print("评测：%s（%d 条，gold=%s）" % (args.name, n, args.gold))
    print("-" * 44)
    print("解析率     %5.1f%%   (%d/%d)" % (pct(parse_ok), parse_ok, n))
    print("二分类Acc  %5.1f%%   (%d/%d 解析样本)" % (pct(bin_ok), bin_ok, n))
    print("机制Acc    %5.1f%%   (%d/%d 解析样本)" % (pct(mech_ok), mech_ok, n))
    print("双对Acc    %5.1f%%" % pct(both_ok))
    if s_total:
        print("是反讽召回 %5.1f%%   (%d/%d)" % (s_hit / s_total * 100, s_hit, s_total))
    if n_total:
        print("非反讽召回 %5.1f%%   (%d/%d)" % (n_hit / n_total * 100, n_hit, n_total))
    print("平均输出长度 %6.1f 字符（min %d / max %d）" %
          (sum(lens) / max(1, len(lens)), min(lens) if lens else 0, max(lens) if lens else 0))
    print("判断分布：%s" % dict(judge_dist.most_common()))
    print("机制分布 top8：%s" % dict(mech_dist.most_common(8)))


if __name__ == "__main__":
    main()
