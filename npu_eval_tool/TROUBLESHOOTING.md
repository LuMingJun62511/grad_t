# Troubleshooting Guide

常见问题诊断与修复，按发生阶段排列。

---

## 1. 环境与依赖

### `ModuleNotFoundError: No module named 'torch_npu'`

昇腾 NPU 环境未正确安装或加载。

```bash
# 检查 torch_npu 是否可用
python -c "import torch_npu; print(torch_npu.__version__)"
```

**修复方向**：
- 确认昇腾 CANN / torch_npu 已按 MindSpeed 文档安装
- 检查 `PYTHONPATH` 是否包含 `torch_npu` 的安装路径
- MindSpeed 容器环境内通常已配好，裸机环境需确认 `source set_env.sh`

### `ModuleNotFoundError: No module named 'transformers'`

```bash
pip install transformers
```

---

## 2. 模型加载阶段

### `OSError: Can't load tokenizer for ...`

模型路径下缺少 `tokenizer_config.json` 或 `tokenizer.model`。HF 格式模型应包含这些文件。

```bash
ls /path/to/model/tokenizer*
```

**修复方向**：
- 确认 Megatron→HF 转换时 tokenizer 文件是否一同复制
- 如果是自定义 tokenizer，需要 `--trust_remote_code`

### `ValueError: Cannot find a valid model architecture`

`config.json` 中的 `architectures` 字段不匹配或缺失。

**修复方向**：
- 检查 `config.json`：
  ```bash
  cat /path/to/model/config.json | grep architectures
  ```
- 正确范例：`"architectures": ["LlamaForCausalLM"]`
- 如果是 MindSpeed 转出来的非标准架构，加 `--trust_remote_code`

### 模型加载时 OOM（单卡装不下）

```
torch.cuda.OutOfMemoryError: NPU out of memory
```

这是**数据并行策略的固有限制**：每张卡需完整加载模型。

**修复方向**：
- 降低 `--torch_dtype float16`（已是默认）
- 减小 `--batch_size`（推理时进一步节省 peak memory）
- 如果 `bf16` 是伪量化方案可试试 `float32`（不推荐，会吃更多）
- **根本方案**：模型大于单卡时需要模型并行，当前工具不支持，需扩展 InferEngine 加入 device_map 或 Megatron 风格的分片加载

---

## 3. HCCL 分布式初始化

### `torch.distributed.DistNetworkError` / 初始化超时

HCCL 通信初始化失败，通常与网络配置或 NPU 可见性有关。

**症状**：
```
RuntimeError: HCCL init failed
```
或初始化卡在 `init_process_group` 超过 30 秒后超时。

**排查步骤**：
```bash
# 1. 确认 NPU 数量和可见性
npu-smi info
# 或
python -c "import torch; import torch_npu; print(torch.npu.device_count())"

# 2. 确认 torchrun 参数与 NPU 数量一致
# 错误示例：只有 4 张卡却写了 --nproc_per_node=8
torchrun --nproc_per_node=$(python -c "import torch; import torch_npu; print(torch.npu.device_count())") ...

# 3. 确认 HCCL 环境变量
echo $HCCL_CONNECT_TIMEOUT
echo $HCCL_EXEC_TIMEOUT
```

**修复方向**：
- `--nproc_per_node` 不能超过实际 NPU 数量
- 如果 NPU 之间有网络隔离（如 8 卡分成两个 4 卡组），可能需要设置 `HCCL_IF_IP` 等网络环境变量
- 尝试加超时容忍：`export HCCL_CONNECT_TIMEOUT=1800`

### 多卡 `all_gather_object` 卡死

**症状**：推理完成，但所有 rank 卡在汇聚阶段不继续。

**原因**：某个 rank 提前报错退出（如 OOM），导致其他 rank 在 `all_gather_object` 处等待。

**排查**：
- 检查所有 rank 的输出，是否有一个 rank 提前打印了 `[ERROR]`
- 如果数据量很大（>1 万条且每条带长文本），`all_gather_object` 对象过大可能触发通信超时

**修复方向**：
- 减小 `--max_new_tokens 128` → 减少生成文本长度
- 先用单卡验证（不通过 torchrun），确认单卡能跑通
- 如果是大数据量，考虑分片评测后手动合并 JSON（绕过 all_gather）

---

## 4. 推理阶段

### 单 batch OOM

```
[ERROR] Batch [0:8]: OOM: NPU out of memory
```

**修复方向**：
- 减小 `--batch_size 4` 或 `--batch_size 1`
- 减小 `--max_input_length 1024`
- 减小 `--max_new_tokens 128`

### 生成结果全是空字符串

**症状**：`results.json` 中所有 `prediction` 都是 `""`。

**可能原因**：
1. `tokenizer.pad_token` 未设置，导致 batch padding 异常
2. `max_new_tokens` 太小，生成了一个 token 就被截断
3. 模型本身的 `eos_token` 是句子开头第一个 token

**排查**：
```python
# 在 eval_tool.py 的 InferEngine.load() 中添加：
print(f"pad_token: {self.tokenizer.pad_token}, eos_token: {self.tokenizer.eos_token}")
```

**修复方向**：
- 代码已经处理了 `pad_token = eos_token`，但如果模型的 `eos_token` 为空则无效
- 手动指定：改 InferEngine.load() 中 `self.tokenizer.pad_token = "[PAD]"` 且添加对应 token

### 生成结果全是乱码 / 重复词

**症状**：预测文本是重复的字符或 token。

**修复方向**：
- 确认 `temperature=0.0` + `do_sample=False`（greedy decoding），这是默认值
- 确认 `eos_token_id` 设置正确
- 如果模型没训好停止 token，设置 `max_new_tokens` 为较小值

### `--prompt_template chatml` 不生效

确认你的模型实际用的是哪个模板。不同模型（Qwen, LLaMA, ChatGLM）的 chat template 不同：

| 模型系列 | 建议模板 |
|---------|---------|
| Qwen / Qwen2 | `qwen` |
| LLaMA 3 | `chatml`（近似，可能需要调整） |
| 通用 base model | `default`（`instruction\ninput`） |
| 自定义 | `"<your template with {instruction} and {input}>"` |

---

## 5. 数据与格式

### `ValueError: No valid data found`

**症状**：数据文件读取后为空。

**排查**：
```bash
head -3 data.jsonl          # 确认文件非空
python -c "import json; json.loads(open('data.jsonl').readline())"  # 确认每行合法
```

**修复方向**：
- 确认编码是 UTF-8
- 确认不是 BOM 头导致第一行解析失败
- 尝试 `dos2unix data.jsonl`（Windows 换行符问题）

### 某些样本 `output` 字段缺失

输出 `[WARN] N samples missing 'output' field`。

如果这不是预期情况，检查 JSONL 字段名是否一致（手误写了 `Output` / `label` / `answer` 等）。当前工具只认 `output`。

### JSON 类指标输出全是 0

`json_accuracy` 输出 `score: 0.0000`。

**常见原因**：模型输出了纯文本而非 JSON，而 `_try_parse_json()` 未能从文本中提取 JSON。

**排查**：
- 查看 `results.json` 中实际的 `prediction` 文本长什么样
- 如果模型输出类似 `{"l1": "A", "l2": "B"}` 但混在文本中（如 `分类结果是{"l1": "A", "l2": "B"}，请确认`），`_try_parse_json` 应该能提取
- 如果模型输出是 markdown code block（`` ```json ... ``` ``），当前版本不处理，需要扩展

**修复方向**：
- 在 `_try_parse_json` 中加 markdown code block 提取逻辑（去 `` ``` `` 标记）
- 调整 prompt 让模型直接输出纯 JSON，不加解释文字

---

## 6. 快速自检脚本

到新环境后，先跑这个确认基础组件正常：

```bash
# 1. 纯 Python 逻辑 (不需要 NPU)
cd npu_eval_tool
python test_pure_python.py

# 2. 确认 NPU 可见
python -c "import torch; import torch_npu; print(f'NPUs: {torch.npu.device_count()}')"

# 3. 确认模型可加载（单卡，不跑分布式）
python -c "
from eval_tool import InferEngine
e = InferEngine('/path/to/model').load()
print('Model loaded OK')
print(f'Vocab size: {e.tokenizer.vocab_size}')
e.unload()
"

# 4. 确认分布式通信
torchrun --nproc_per_node=2 -c "
import torch; import torch_npu
torch.distributed.init_process_group(backend='hccl')
print(f'Rank {torch.distributed.get_rank()}: OK')
torch.distributed.destroy_process_group()
"
```
