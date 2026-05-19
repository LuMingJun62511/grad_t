#!/usr/bin/env python3
"""
Pure-Python 模块测试
====================
测试 eval_tool.py 中不依赖 NPU/昇腾环境的所有功能模块：
  - 数据加载 (load_data)
  - Prompt 构建 (build_prompt)
  - JSON 工具 (_try_parse_json, _json_deep_compare)
  - 全部内置指标 (6 个)
  - Meta 提取 (_extract_meta)

用法: python test_pure_python.py
"""

import json
import os
import sys
import tempfile

# 确保能 import 同目录下的 eval_tool
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from eval_tool import (
    load_data,
    build_prompt,
    register_metric,
    METRIC_REGISTRY,
    _try_parse_json,
    _json_deep_compare,
    _extract_meta,
    _normalize_refs,
)

PASS = 0
FAIL = 0

def check(condition, label):
    global PASS, FAIL
    if condition:
        PASS += 1
        print(f"  [PASS] {label}")
    else:
        FAIL += 1
        print(f"  [FAIL] {label}")

# ============================================================================
# 1. JSON 工具测试
# ============================================================================
print("=" * 60)
print("1. JSON Utilities")

def test_try_parse_json():
    # 字符串 JSON
    check(_try_parse_json('{"a": 1}') == {"a": 1}, "parse dict string")
    check(_try_parse_json("[1, 2, 3]") == [1, 2, 3], "parse list string")

    # 已经是 dict/list
    check(_try_parse_json({"a": 1}) == {"a": 1}, "pass-through dict")
    check(_try_parse_json([1, 2]) == [1, 2], "pass-through list")

    # 从文本中提取 JSON
    check(_try_parse_json('结果是 {"a": 1}，请注意') == {"a": 1},
          "extract JSON from surrounding text")
    check(_try_parse_json('前面废话{"level1": "A", "level2": "B"}后面废话')
          == {"level1": "A", "level2": "B"},
          "extract nested JSON from text")

    # 无法解析的，返回原字符串
    check(_try_parse_json("纯文本输出") == "纯文本输出", "fallback to string")
    check(_try_parse_json("") == "", "empty string")
    check(_try_parse_json(None) is None, "None passthrough")

    # int/float 类型直接返回
    check(_try_parse_json(42) == 42, "int passthrough")
    check(_try_parse_json(True) == True, "bool passthrough")

def test_json_deep_compare():
    # 相同值
    result = _json_deep_compare({"a": 1}, {"a": 1})
    check(result == {"a": 1.0}, f"simple equal dict: {result}")

    # 不同值
    result = _json_deep_compare({"a": 1}, {"a": 2})
    check(result == {"a": 0.0}, f"simple unequal dict: {result}")

    # 嵌套 dict
    result = _json_deep_compare(
        {"level1": "A", "level2": {"sub": "X"}},
        {"level1": "A", "level2": {"sub": "Y"}},
    )
    check(result == {"level1": 1.0, "level2.sub": 0.0},
          f"nested dict compare: {result}")

    # 多层级，部分对部分错
    result = _json_deep_compare(
        {"l1": "A", "l2": "B", "l3": "C"},
        {"l1": "A", "l2": "X", "l3": "C"},
    )
    check(result == {"l1": 1.0, "l2": 0.0, "l3": 1.0},
          f"multi-field compare: {result}")

    # 列表比较
    result = _json_deep_compare([1, 2, 3], [1, 2, 3])
    check(result == {"[0]": 1.0, "[1]": 1.0, "[2]": 1.0},
          f"equal lists: {result}")

    result = _json_deep_compare([1, 2, 3], [1, 0, 3])
    check(result == {"[0]": 1.0, "[1]": 0.0, "[2]": 1.0},
          f"unequal lists: {result}")

    # 一方多字段
    result = _json_deep_compare({"a": 1}, {"a": 1, "b": 2})
    check(result == {"a": 1.0, "b": 0.0}, f"extra field in ref: {result}")

    # 空对象
    result = _json_deep_compare({}, {})
    check(result == {"value": 1.0}, f"empty dicts: {result}")

    # 标量比较
    result = _json_deep_compare("hello", "hello")
    check(result == {"value": 1.0}, f"equal scalars: {result}")

    result = _json_deep_compare("hello", "world")
    check(result == {"value": 0.0}, f"unequal scalars: {result}")

test_try_parse_json()
test_json_deep_compare()

# ============================================================================
# 2. 数据加载测试
# ============================================================================
print("=" * 60)
print("2. Data Loading")

def test_load_data():
    # 标准 JSONL
    with tempfile.NamedTemporaryFile(mode="w", suffix=".jsonl", delete=False, encoding="utf-8") as f:
        f.write('{"instruction": "Q", "input": "X", "output": "Y"}\n')
        f.write('{"instruction": "Q2", "input": "X2", "output": "{\\"k\\": \\"v\\"}"}\n')
        tmp = f.name

    data = load_data(tmp)
    check(len(data) == 2, f"load 2 samples: got {len(data)}")
    check(data[0]["instruction"] == "Q", "first sample instruction")
    check(data[0]["output"] == "Y", "first sample output")
    check(data[1]["output"] == '{"k": "v"}', "second sample output (JSON string preserved)")
    os.unlink(tmp)

    # JSON 数组格式
    with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False, encoding="utf-8") as f:
        json.dump([{"instruction": "Q", "input": "X", "output": "A"},
                    {"instruction": "Q2", "input": "X2", "output": "B"}], f)
        tmp = f.name

    data = load_data(tmp)
    check(len(data) == 2, f"load JSON array: got {len(data)}")
    check(data[1]["output"] == "B", "JSON array second sample")
    os.unlink(tmp)

    # 空行和无效行
    with tempfile.NamedTemporaryFile(mode="w", suffix=".jsonl", delete=False, encoding="utf-8") as f:
        f.write('\n')
        f.write('{"instruction": "Q", "input": "X", "output": "Y"}\n')
        f.write('\n')
        f.write('not valid json\n')
        f.write('{"instruction": "Q2", "input": "X2", "output": "Y2"}\n')
        tmp = f.name

    data = load_data(tmp)
    check(len(data) == 2, f"skip blanks and bad lines: got {len(data)}")
    check(data[-1]["output"] == "Y2", "last valid sample intact")
    os.unlink(tmp)

    # 不存在的文件
    try:
        load_data("/nonexistent/path.jsonl")
        check(False, "should raise FileNotFoundError")
    except FileNotFoundError:
        check(True, "FileNotFoundError on missing file")

test_load_data()

# ============================================================================
# 3. Prompt 构建测试
# ============================================================================
print("=" * 60)
print("3. Prompt Building")

def test_build_prompt():
    # default template
    s = {"instruction": "翻译成英文", "input": "你好"}
    p = build_prompt(s, "default")
    check(p == "翻译成英文\n你好", f"default template: '{p}'")

    # 无 instruction
    s = {"instruction": "", "input": "你好"}
    p = build_prompt(s, "default")
    check(p == "你好", f"no instruction: '{p}'")

    # 无 input
    s = {"instruction": "翻译成英文", "input": ""}
    p = build_prompt(s, "default")
    check("翻译成英文" in p, f"no input: '{p}'")

    # chatml template
    s = {"instruction": "Q", "input": "X"}
    p = build_prompt(s, "chatml")
    check(p.startswith("<|im_start|>user"), f"chatml starts correctly")
    check(p.endswith("<|im_start|>assistant\n"), f"chatml ends correctly")

    # qwen template
    p = build_prompt(s, "qwen")
    check("<|im_start|>system" in p, f"qwen has system prompt")
    check("<|im_start|>assistant\n" in p, f"qwen ends with assistant marker")

    # custom template
    custom = "Human: {instruction}\n{input}\nAI:"
    s = {"instruction": "Q", "input": "X"}
    p = build_prompt(s, custom)
    check(p == "Human: Q\nX\nAI:", f"custom template: '{p}'")

    # 完全空
    s = {"instruction": "", "input": ""}
    p = build_prompt(s)
    check(p == "", f"empty instruction and input: '{p}'")

test_build_prompt()

# ============================================================================
# 4. Metrics 测试
# ============================================================================
print("=" * 60)
print("4. Metrics")

def test_metrics():
    # ---- exact_match ----
    fn = METRIC_REGISTRY["exact_match"]
    r = fn(["hello", "world", "你好"], ["hello", "earth", "你好"])
    check(r["score"] == 2 / 3, f"exact_match score: {r['score']}")
    check(r["per_sample"] == [1.0, 0.0, 1.0], f"exact_match per_sample: {r['per_sample']}")
    check(r["correct"] == 2, "exact_match correct count")
    check(r["total"] == 3, "exact_match total count")

    # 带空格
    r = fn(["  hello  "], ["hello"])
    check(r["score"] == 1.0, f"exact_match with whitespace: {r['score']}")

    # ---- contains ----
    fn = METRIC_REGISTRY["contains"]
    r = fn(["前面答案后面", "无关文本", "包含正确答案"],
           ["答案", "不匹配", "正确答案"])
    check(r["score"] == 2 / 3, f"contains score: {r['score']}")
    check(r["per_sample"] == [1.0, 0.0, 1.0], f"contains per_sample")

    # ---- json_accuracy (核心：层级分类) ----
    fn = METRIC_REGISTRY["json_accuracy"]

    # 场景1: 两方都是合法 JSON，部分字段对
    preds = ['{"level1": "A", "level2": "B"}', '{"level1": "A", "level2": "X"}']
    refs = ['{"level1": "A", "level2": "B"}', '{"level1": "A", "level2": "B"}']
    r = fn(preds, refs)
    check(r["score"] == 0.75, f"json_accuracy overall: {r['score']} "
         f"(sample1=1.0, sample2=0.5)")
    check(r["field_scores"]["level1"] == 1.0, f"level1 all correct")
    check(r["field_scores"]["level2"] == 0.5, f"level2 half correct")

    # 场景2: 答案带额外文字，但包含 JSON
    preds = ['分类结果：{"a": 1, "b": 2}', '{"a": 1}']
    refs = ['{"a": 1, "b": 2}', '{"a": 1}']
    r = fn(preds, refs)
    check(r["score"] == 1.0, f"extract JSON from text: {r['score']}")

    # 场景3: 一方是 JSON，一方是纯文本 → 退化为字符串匹配
    preds = ["纯文本"]
    refs = ["纯文本"]
    r = fn(preds, refs)
    check(r["score"] == 1.0, f"plain text fallback match: {r['score']}")

    preds = ["不同文本"]
    refs = ["纯文本"]
    r = fn(preds, refs)
    check(r["score"] == 0.0, f"plain text fallback mismatch: {r['score']}")

    # 场景4: reference 已经是 dict/list（数据加载时已解析）
    preds = ['{"level1": "A"}']
    refs = [{"level1": "A"}]
    r = fn(preds, refs)
    check(r["score"] == 1.0, f"reference is already dict: {r['score']}")

    # 场景5: 三层层级标签
    preds = ['{"l1": "A", "l2": {"l2a": "X", "l2b": "Y"}, "l3": "C"}']
    refs = ['{"l1": "A", "l2": {"l2a": "X", "l2b": "W"}, "l3": "C"}']
    r = fn(preds, refs)
    check(r["field_scores"]["l1"] == 1.0, "3-level: l1 correct")
    check(r["field_scores"]["l2.l2a"] == 1.0, "3-level: l2.l2a correct")
    check(r["field_scores"]["l2.l2b"] == 0.0, "3-level: l2.l2b wrong")
    check(r["field_scores"]["l3"] == 1.0, "3-level: l3 correct")
    # 4 fields, 3 correct → overall 0.75
    check(abs(r["score"] - 0.75) < 0.01, f"3-level overall: {r['score']}")

    # ---- json_exact_match ----
    fn = METRIC_REGISTRY["json_exact_match"]
    preds = ['{"a": 1, "b": 2}', '{"a": 1, "b": 3}']
    refs = ['{"a": 1, "b": 2}', '{"a": 1, "b": 2}']
    r = fn(preds, refs)
    check(r["score"] == 0.5, f"json_exact_match: {r['score']}")

    # ---- char_f1 ----
    fn = METRIC_REGISTRY["char_f1"]
    r = fn(["abc"], ["abc"])
    check(r["score"] == 1.0, f"char_f1 exact match: {r['score']}")

    r = fn(["abc"], ["xyz"])
    check(r["score"] == 0.0, f"char_f1 no overlap: {r['score']}")

    r = fn(["abcd"], ["ab"])
    # pred chars: {a,b,c,d}, ref chars: {a,b}
    # precision = 2/4 = 0.5, recall = 2/2 = 1.0, f1 = 2*0.5*1.0/1.5 = 0.667
    check(abs(r["score"] - 2/3) < 0.01, f"char_f1 partial overlap: {r['score']}")

    # 空字符串
    r = fn([""], [""])
    check(r["score"] == 1.0, f"char_f1 both empty: {r['score']}")

    # ---- bleu ----
    fn = METRIC_REGISTRY["bleu"]
    r = fn(["hello world"], ["hello world"])
    check(r["bleu1"] == 1.0, f"bleu1 exact: {r['bleu1']}")
    check(r["bleu2"] == 1.0, f"bleu2 exact: {r['bleu2']}")
    check(r["score"] == 1.0, f"bleu score exact: {r['score']}")

    r = fn(["abcdefgh"], ["abcdxxxx"])
    # pred: abcdefgh, ref: abcdxxxx, some overlap
    check(r["bleu1"] < 1.0 and r["bleu1"] > 0.0,
          f"bleu1 partial: {r['bleu1']:.4f}")
    check(r["score"] < 1.0 and r["score"] > 0.0,
          f"bleu score partial: {r['score']:.4f}")

    # 中文
    r = fn(["我爱自然语言处理"], ["我喜欢自然语言处理"])
    check(0.0 < r["score"] < 1.0, f"bleu chinese partial: {r['score']:.4f}")

test_metrics()

# ============================================================================
# 5. 自定义指标注册测试
# ============================================================================
print("=" * 60)
print("5. Custom Metric Registration")

def test_custom_metric():
    @register_metric("_test_custom")
    def _test_custom(predictions, references):
        per_sample = [1.0 if len(p) > 5 else 0.0 for p in predictions]
        return {"score": sum(per_sample) / len(per_sample), "per_sample": per_sample}

    check("_test_custom" in METRIC_REGISTRY, "custom metric registered")
    fn = METRIC_REGISTRY["_test_custom"]
    r = fn(["short", "long enough text", "also long enough"],
           ["x", "x", "x"])
    check(r["score"] == 2 / 3, f"custom metric score: {r['score']}")

test_custom_metric()

# ============================================================================
# 6. Meta 提取测试
# ============================================================================
print("=" * 60)
print("6. Meta Extraction")

def test_extract_meta():
    sample = {"instruction": "Q", "input": "X", "output": "Y",
              "category": "test", "labels": {"l1": "A"}}
    meta = _extract_meta(sample)
    check("instruction" not in meta, "instruction excluded from meta")
    check("input" not in meta, "input excluded from meta")
    check("output" not in meta, "output excluded from meta")
    check(meta["category"] == "test", "category preserved")
    check(meta["labels"] == {"l1": "A"}, "labels preserved")

test_extract_meta()

# ============================================================================
# 7. 端到端模拟测试
# ============================================================================
print("=" * 60)
print("7. End-to-End Simulation (no model)")

def test_e2e():
    """
    模拟一次完整的评测流程（不加载模型，手动构造推理结果）。
    验证数据加载 → prompt 构建 → 指标计算 → 结果保存链路。
    """
    # 构造测试数据
    data = [
        {"instruction": "判断情感", "input": "很好", "output": "正面", "category": "test"},
        {"instruction": "判断情感", "input": "无聊", "output": "负面", "category": "test"},
        {"instruction": "分类", "input": "...",
         "output": '{"level1": "A", "level2": "B"}', "category": "prod"},
        {"instruction": "分类", "input": "...",
         "output": '{"level1": "A", "level2": "C"}', "category": "prod"},
    ]

    # 写临时 JSONL
    with tempfile.NamedTemporaryFile(mode="w", suffix=".jsonl", delete=False, encoding="utf-8") as f:
        for d in data:
            f.write(json.dumps(d, ensure_ascii=False) + "\n")
        tmp = f.name

    # 加载
    loaded = load_data(tmp)
    check(len(loaded) == 4, f"e2e: loaded {len(loaded)} samples")

    # 构建 prompt
    prompts = [build_prompt(s, "default") for s in loaded]
    check(prompts[0] == "判断情感\n很好", f"e2e: prompt[0] = '{prompts[0]}'")
    check(prompts[2] == "分类\n...", f"e2e: prompt[2] = '{prompts[2]}'")

    # 模拟推理结果 (实际使用时由 InferEngine 产出)
    simulated_predictions = [
        "正面",       # 正确
        "正面",       # 错误（应该是"负面"）
        '{"level1": "A", "level2": "B"}',  # 正确
        '{"level1": "A", "level2": "D"}',  # level2 错误
    ]

    # 计算指标
    refs = [s["output"] for s in loaded]

    em = METRIC_REGISTRY["exact_match"](simulated_predictions, refs)
    check(em["correct"] == 2, f"e2e: exact_match correct = {em['correct']}/4")
    check(em["score"] == 0.5, f"e2e: exact_match score = {em['score']}")

    ja = METRIC_REGISTRY["json_accuracy"](simulated_predictions, refs)
    check("level1" in ja["field_scores"], "e2e: json_accuracy has level1 field")
    check(ja["field_scores"]["level1"] == 1.0,
          f"e2e: level1 accuracy = {ja['field_scores']['level1']}")

    # 模拟分组统计 (category)
    categories = [s["category"] for s in loaded]
    from collections import defaultdict
    groups = defaultdict(list)
    for i, cat in enumerate(categories):
        groups[cat].append(i)

    test_preds = [simulated_predictions[i] for i in groups["test"]]
    test_refs = [refs[i] for i in groups["test"]]
    em_test = METRIC_REGISTRY["exact_match"](test_preds, test_refs)
    check(em_test["correct"] == 1, f"e2e: test group exact_match = {em_test['correct']}/2")

    prod_preds = [simulated_predictions[i] for i in groups["prod"]]
    prod_refs = [refs[i] for i in groups["prod"]]
    ja_prod = METRIC_REGISTRY["json_accuracy"](prod_preds, prod_refs)
    check(ja_prod["score"] == 0.75, f"e2e: prod group json_accuracy = {ja_prod['score']}")

    os.unlink(tmp)
    print("  (end-to-end data→metric pipeline verified)")

test_e2e()

# ============================================================================
# Summary
# ============================================================================
print()
print("=" * 60)
print(f"  RESULTS: {PASS} passed, {FAIL} failed")
print("=" * 60)

if FAIL > 0:
    sys.exit(1)
else:
    print("All tests passed!")
    sys.exit(0)
