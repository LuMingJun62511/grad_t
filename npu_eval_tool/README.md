# NPU Eval Tool

单文件、数据并行的昇腾 NPU 模型评测工具。不绑定 MindSpeed 版本，只依赖 `torch` + `torch_npu` + `transformers`。

## 设计

```
JSONL 数据  →  [Rank 0..N 分片]  →  InferEngine 推理  →  all_gather 汇聚
                                                         ↓
                                            Metrics (exact_match / json_accuracy / bleu ...)
                                                         ↓
                                          results.json  +  summary.json  +  report.txt
```

- **DataLoader** — 纯函数，读 JSONL，产出 `(prompt, reference)` pair
- **InferEngine** — 只负责加载 HF 模型、批量生成，不关心评测逻辑
- **Metrics** — 注册式，`@register_metric("name")` 装饰即用，纯函数 `(preds, refs) -> dict`
- **Evaluator** — 编排器，分布式协调、容错、分组统计、输出报告

数据并行策略：每张卡加载完整模型副本，各自推理不同数据分片，最后 `all_gather_object` 汇聚到 rank 0 计算指标。

## 快速开始

```bash
# 单卡
python eval_tool.py -m /path/to/hf_model -d data.jsonl -o ./results

# 8 卡数据并行
torchrun --nproc_per_node=8 eval_tool.py -m /path/to/hf_model -d data.jsonl -o ./results

# 多指标 + 分组统计
python eval_tool.py -m ./hf_model -d data.jsonl \
    --metrics exact_match json_accuracy bleu \
    --group_by category \
    --batch_size 16
```

## 数据格式

JSONL，每行一个 JSON 对象：

```jsonl
{"instruction": "判断情感倾向", "input": "这部电影真好看", "output": "正面"}

{"instruction": "分类", "input": "...", "output": "{\"level1\": \"A\", \"level2\": \"B\"}", "category": "test"}

{"instruction": "", "input": "直接输入无指令", "output": "预期输出"}
```

- `instruction` + `input` → 拼成 prompt
- `output` → 参考答案，可以是字符串或 JSON 字符串（用于层级标签）
- 其他字段（如 `category`）可通过 `--group_by` 做分组统计

## 内置指标

| 指标 | 说明 |
|------|------|
| `exact_match` | strip 后全等匹配 |
| `contains` | 参考答案是否在预测文本中 |
| `json_accuracy` | 解析 JSON 后逐字段比对，输出 per-field 准确率 |
| `json_exact_match` | JSON 结构化全等比较 |
| `char_f1` | 字符集合 F1 |
| `bleu` | 字符级 BLEU-1/2/4（不依赖 nltk） |

## 扩展新指标

```python
from eval_tool import register_metric

@register_metric("my_metric")
def my_metric(predictions, references):
    """predictions: List[str]  模型生成文本
       references:  List[Any]  参考答案（字符串或已解析的 JSON）
       returns:     dict      必须包含 "score" 和 "per_sample"，可选其他统计"""
    per_sample = [1.0 if p == str(r) else 0.0 for p, r in zip(predictions, references)]
    return {"score": sum(per_sample) / len(per_sample), "per_sample": per_sample}
```

注册后即可通过 `--metrics my_metric` 调用。

## 输出

```
./results/
├── results.json   # 逐条结果 [{"prompt", "reference", "prediction", "error", "meta"}]
├── summary.json   # {"num_samples": N, "scores": {"exact_match": {"score": 0.82, ...}}}
└── report.txt     # 人类可读报告
```

## 依赖

- Python ≥ 3.8
- `torch` + `torch_npu`（昇腾环境自带）
- `transformers`

不依赖 nltk、MindSpeed、或其他第三方评测库。
