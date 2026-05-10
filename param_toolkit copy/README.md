# param_toolkit 使用文档

模型参数空间几何分析工具。核心思想源自 [Task Arithmetic (Ilharco et al., ICLR 2023)](https://arxiv.org/abs/2212.04089)：把微调后的参数变化 `τ = θ_finetuned − θ_base` 看作高维向量，度量任务的"移动距离"和"移动方向"，评估多任务之间的相性。

## 快速开始

```python
from param_toolkit import TaskVector, compute_distance, per_layer_distance

# 1. 构建任务向量
tv = TaskVector("checkpoints/v1/model.pt", "checkpoints/v2/model.pt")

# 2. 全局距离
dist = compute_distance(tv)
# {"l1": 19501, "l2": 2.05, "rms": 0.000075, "n_params": 751632384,
#  "increased_pct": 11.72, "decreased_pct": 11.72, "unchanged_pct": 76.56}

# 3. 逐层距离
for row in per_layer_distance(tv):
    print(f"{row['layer']}: l2={row['l2']:.4f}, rms={row['rms']:.6f}")
```

## API

### TaskVector

```python
TaskVector(base_ckpt, target_ckpt, filter_fn=None)
```

加载两个 state_dict（`.pt` / `.bin`），计算 `target - base` 的逐参数差值。

| 方法 | 说明 |
|------|------|
| `tv.keys()` | 参数名列表 |
| `tv["model.layers.0.self_attn.q_proj.weight"]` | 获取单个参数的差值 tensor |
| `tv.save("path.pt")` | 保存任务向量到磁盘 |
| `TaskVector.load("path.pt")` | 从磁盘加载已保存的任务向量 |
| `TaskVector.from_state_dicts(base_dict, target_dict)` | 从内存中的 state_dict 构建 |

**filter_fn** 方案：只分析特定参数，例如只看 attention 层：

```python
tv = TaskVector(v1, v2, filter_fn=lambda name: "attn" in name)
```

### distance — 距离度量

```python
compute_distance(tv) → dict
```

返回全局指标：

| Key | 含义 |
|-----|------|
| `l1` | L1 距离 = Σ\|τᵢ\| |
| `l2` | L2 距离 = √(Σ τᵢ²) |
| `rms` | 均方根 = L2 / √N，归一化后不同尺寸模型可比较 |
| `increased_pct` | 参数增大的比例 |
| `decreased_pct` | 参数减小的比例 |
| `unchanged_pct` | 参数未变的比例（全量微调接近 0%，LoRA 可能很高） |

```python
per_layer_distance(tv) → list[dict]
```

按层分组返回每层的 `l2`、`rms`、`n_params`。输出已按层号排序。

```python
cosine_similarity(tv_a, tv_b) → float
```

两个任务向量之间的余弦相似度。核心指标，用于判断任务相性。

### direction — 方向分析

```python
task_direction_summary(tv) → dict
```

单任务向量的方向统计：`overall_mean`、`overall_std`、`positive_frac`、`negative_frac`、`zero_frac`。

```python
sign_agreement(tv_a, tv_b) → dict
```

两个任务向量中，多少参数朝同一方向移动。返回 `agreement`（0~1）、`same_pos`、`same_neg`、`opposite`。

```python
top_directions(tv, top_k=10) → list[dict]
```

变化幅度最大的 top-k 个参数及其均值、标准差、方向。

### compatibility — 多任务相性

```python
compatibility_matrix(task_vectors, min_similarity=0.3) → dict
```

输入 `{"任务A": tv_a, "任务B": tv_b, "任务C": tv_c}`，返回：

| Key | 内容 |
|-----|------|
| `matrix` | N×N 余弦相似度矩阵 |
| `labels` | 任务名列表（对应矩阵行列） |
| `compatible` | cos ≥ 0.3 的任务对 |
| `conflicting` | cos < 0 的任务对 |
| `neutral` | 0 ≤ cos < 0.3 的任务对 |

```python
conflict_report(result) → str
```

把 `compatibility_matrix` 的结果格式化为可读文本。

## CLI

```bash
# 分析单个任务向量
python -m param_toolkit.cli v1/model.pt v2/model.pt

# 对比两个任务向量
python -m param_toolkit.cli v1/model.pt taskA/model.pt taskB/model.pt

# 直接加载已保存的任务向量
python -m param_toolkit.cli --tv saved_tv.pt

# 分析同时保存任务向量
python -m param_toolkit.cli v1/model.pt v2/model.pt --save-tv tau.pt
```

## 解读指南

### cos 值含义

| cos 范围 | 含义 | 建议 |
|----------|------|------|
| **> 0.7** | 高度兼容 | 可以合并训练，或 task addition 增强 |
| **0.3 ~ 0.7** | 中度相关 | 合并训练可能有效，但需验证 |
| **0 ~ 0.3** | 正交/无关 | 两个任务独立，互不干扰 |
| **< 0** | 冲突 | 合并训练会互相抵消，需要分开或用 task arithmetic 减法 |

### unchanged_pct 解读

- **> 70%**：LoRA/部分微调，只改了少量参数
- **10% ~ 70%**：参数高效的微调方法
- **< 5%**：全量微调，几乎所有参数都变了

### 逐层 rms 模式

- **均匀分布**：任务对各层影响均衡
- **深层 > 浅层**：常见模式，任务特异信息主要编码在高层
- **浅层 > 深层**：任务主要改变底层特征提取
- **某层异常高**：该层对任务特别关键

## 完整示例：评估两个微调任务的相性

```python
from param_toolkit import *

base = "checkpoints/base/model.pt"
math_ckpt = "checkpoints/math/model.pt"
code_ckpt = "checkpoints/code/model.pt"

tv_math = TaskVector(base, math_ckpt)
tv_code = TaskVector(base, code_ckpt)

# 各自走了多远
print("Math:", compute_distance(tv_math))
print("Code:", compute_distance(tv_code))

# 是否兼容
cos = cosine_similarity(tv_math, tv_code)
print(f"cos = {cos:.4f}")

# 符号一致性
sa = sign_agreement(tv_math, tv_code)
print(f"sign agreement = {sa['agreement']:.2%}")

# 完整相性报告
result = compatibility_matrix({"math": tv_math, "code": tv_code})
print(conflict_report(result))

# 保存任务向量供后续使用
tv_math.save("task_vectors/math_tau.pt")
tv_code.save("task_vectors/code_tau.pt")
```

## 依赖

- PyTorch
- 无其他额外依赖（不依赖 transformers，直接操作 state_dict）

## MindSpeed / Megatron 适配

`param_toolkit` 自动识别并加载 MindSpeed 训练的分布式 checkpoint。

### 支持的 checkpoint 格式

| 格式 | 目录结构 | 说明 |
|------|----------|------|
| `hf_single` | `model.pt` / `pytorch_model.bin` | 单文件 state_dict |
| `megatron` | `iter_XXX/mp_rank_YY/model_optim_rng.pt` | MindSpeed/Megatron 分布式 |

### 自动适配流程

```
MindSpeed ckpt                    param_toolkit
──────────────                    ─────────────
iter_0000100/
  mp_rank_00/                     1. detect_format() → "megatron"
    model_optim_rng.pt   ──→      2. 加载所有 rank shards
  mp_rank_01/                     3. 合并 TP 分片 (cat along dim 0/1)
    model_optim_rng.pt            4. 提取 model 字段 (跳过 optimizer/rng)
  ...                             5. megatron_to_hf_state_dict()
                                  6. 拆分 QKV → q_proj/k_proj/v_proj
                                          gate+up → gate_proj/up_proj
                                  7. 返回 HF 格式 state_dict
                                          ↓
                                  TaskVector 直接可用
```

### 用法

```python
from param_toolkit import TaskVector, detect_format, load_checkpoint

# 自动检测格式
fmt = detect_format("/path/to/mindspeed_output")
# → "megatron"

# 直接构建 TaskVector（内部自动适配）
tv = TaskVector(
    "/path/to/base_model.pt",           # HF 单文件
    "/path/to/mindspeed_output",        # MindSpeed 分布式
    model_type="qwen3",                 # 模型架构（决定 key 映射规则）
    tp_size=4,                          # Tensor Parallel 大小
)

# 或手动加载后操作
sd = load_checkpoint(
    "/path/to/mindspeed_output/iter_0000100",
    model_type="qwen3",
    tp_size=4,
)
```

### model_type 预设

| Key | 适用模型 |
|-----|----------|
| `qwen3` | Qwen3 系列（GQA, SwiGLU, RMSNorm） |
| `llama3` | Llama3 系列（GQA, SwiGLU, RMSNorm） |

新增模型类型：在 `key_mapping.py` 的 `MODEL_PRESETS` 中添加配置即可。

### HiGGS → Megatron 反向映射

如果需要把分析结果（任务向量）应用回 MindSpeed checkpoint：

```python
from param_toolkit import hf_to_megatron_state_dict

# 把 HF 格式的 task vector 转回 Megatron 格式
mg_sd = hf_to_megatron_state_dict(task_vector_as_dict, model_type="qwen3")
torch.save(mg_sd, "merged_megatron_weights.pt")
```

这会自动将 Q/K/V 合并回 QKV，gate/up 合并回 fc1。
