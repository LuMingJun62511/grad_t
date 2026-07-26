# 桥接数据（Bridge Data）生成方案

## 一、问题背景

模型在第一阶段学习了反讽识别（S1-S10 反讽类 / N1-N10 非反讽类），能够判断一段文本是不是反讽。但这个能力是**独立存储**的——模型在下游任务（情感分析、意图识别等）中并不会自动调用反讽识别能力。结果就是：遇到反讽文本时，模型把表面含义当成真实含义，情感分析把"骂"判成"夸"，意图识别把"投诉"判成"炫耀"。

## 二、核心思路

造一批**桥接数据**，它的 CoT 中包含两个环节的连接：

```
文本输入
  → 【反讽感知】快速扫描有无反讽信号
  → 有信号 → 【反讽确认】正式判断
    → 是反讽 → 【语义翻转】 → 【下游任务】（基于深层含义）
    → 不是反讽 → 直接进入 → 【下游任务】（基于字面含义）
  → 无信号 → 跳过反讽分析 → 【下游任务】（基于字面含义）
```

关键是**条件激活**——不是每条数据都深度分析反讽，而是根据文本特征选择性激活。

## 三、三类桥接 CoT

### S 型：反讽激活路径

```
【一、反讽感知】
1.1 信号扫描：简述文本中观察到的反讽线索
1.2 感知结论：存在反讽信号，需进一步确认

【二、反讽确认】
2.1 表面-真实对照：字面说什么 vs 实际想说什么
2.2 情感反转确认：方向 + 强度 + 触发点
2.3 确认结论：是反讽 ✓

【三、语义还原】
3.1 翻转方式：如何去掉反讽包装
3.2 还原后的等价直白表达

【四、{下游任务}分析】（基于真实语义）
4.1 分析过程
4.2 任务输出
```

**适用**：文本确实有反讽，需要翻转后做下游任务。

### N 型：快速通过路径

```
【一、反讽感知】
1.1 信号扫描：一句话观察特征
1.2 感知结论：无明显反讽信号，按字面理解

【二、{下游任务}分析】（基于字面语义）
2.1 分析过程
2.2 任务输出
```

**适用**：文本明显不是反讽，轻量扫描后直接做下游任务。防止模型对所有输入都做深度反讽分析。

### C 型：混淆排除路径

```
【一、反讽感知】
1.1 信号扫描：发现疑似反讽特征
1.2 感知结论：存在疑似特征，需进一步判断

【二、反讽排除】
2.1 疑似反讽点：哪些表达看起来像反讽
2.2 排除分析：为什么不是反讽
2.3 关键区分依据
2.4 最终判定：不是反讽 ✗

【三、{下游任务}分析】（基于字面语义）
3.1 分析过程
3.2 任务输出
```

**适用**：文本看起来像反讽但实际不是（夸张修辞、幽默段子、真诚赞美等），教会模型区分边界。

## 四、桥接标签体系

标签格式：`BX-{分类标签}-{任务ID}-{桥接类型}`

| 组成 | 说明 | 可选值 |
|---|---|---|
| 分类标签 | 反讽/非反讽类别 | S1-S10, N1-N10 |
| 任务ID | 下游任务 | SA（情感分析）, IR（意图识别） |
| 桥接类型 | CoT 路径 | S（反讽激活）, N（快速通过）, C（混淆排除） |

示例：
- `BX-S1-SA-S`：S1 直接反话 × 情感分析 × 反讽激活
- `BX-N3-IR-C`：N3 直接批评 × 意图识别 × 混淆排除

## 五、下游任务

### SA — 情感分析

- 输出：`正面/积极` `负面/消极` `中性`
- 反讽影响：表面情感与真实情感相反。正话反说的文本表面正面、实际负面，必须先翻转。

### IR — 意图识别

- 输出：`投诉/抱怨` `询问/求助` `建议/推荐` `分享/讨论` `炫耀/展示` `吐槽/调侃`
- 反讽影响：反讽可能把投诉包装成赞美、把嘲讽包装成询问。

## 六、数量规划

| 桥接类型 | 覆盖分类 | 下游任务数 | 每类每条数 | 总计 |
|---|---|---|---|---|
| S 型（反讽激活） | S1-S10（10类） | 2 (SA+IR) | 50 | **1000** |
| N 型（快速通过） | N1-N10（10类） | 2 (SA+IR) | 30 | **600** |
| C 型（混淆排除） | N1-N10（10类） | 2 (SA+IR) | 30 | **600** |
| **合计** | | | | **~2200** |

## 七、使用方法

### 环境要求

- Python 3.8+
- `requests` 库
- 同目录下需有 `_sarcasm_constants.py`（或通过软链接/路径使其可导入）
- DeepSeek API Key

### 快速验证

```bash
# S型 × SA任务 × 2类 × 5条（~10条，约2分钟）
python generate_bridge_data.py \
  --bridge-type S --task SA --categories S1,S2 --count 5 \
  --api-key $ANTHROPIC_AUTH_TOKEN
```

### 分步生成

```bash
# Step 1: S型（反讽类10类 × 2任务 × 50条 = 1000条）
python generate_bridge_data.py \
  --bridge-type S --all-tasks --all-sarcasm \
  --samples-per-label 50 \
  --output bridge_s.jsonl \
  --api-key $ANTHROPIC_AUTH_TOKEN

# Step 2: N型（非反讽类10类 × 2任务 × 30条 = 600条）
python generate_bridge_data.py \
  --bridge-type N --all-tasks --all-non-sarcasm \
  --samples-per-label 30 \
  --output bridge_n.jsonl \
  --api-key $ANTHROPIC_AUTH_TOKEN

# Step 3: C型（非反讽类10类 × 2任务 × 30条 = 600条）
python generate_bridge_data.py \
  --bridge-type C --all-tasks --all-non-sarcasm \
  --samples-per-label 30 \
  --output bridge_c.jsonl \
  --api-key $ANTHROPIC_AUTH_TOKEN
```

### 一锅端全量

```bash
python generate_bridge_data.py \
  --all-bridge-types --all-tasks --all-categories \
  --s-samples 50 --n-samples 30 --c-samples 30 \
  --output bridge_data_full.jsonl \
  --api-key $ANTHROPIC_AUTH_TOKEN
```

### 断点续传

```bash
# 中途断了直接加 --resume，自动跳过已完成的桥接标签
python generate_bridge_data.py \
  --all-bridge-types --all-tasks --all-categories \
  --s-samples 50 --n-samples 30 --c-samples 30 \
  --output bridge_data_full.jsonl \
  --api-key $ANTHROPIC_AUTH_TOKEN \
  --resume
```

### 质量验证

```bash
# 生成完跑质量检查
python generate_bridge_data.py \
  ... \
  --validate
```

### 完整参数说明

| 参数 | 说明 | 默认值 |
|---|---|---|
| `--bridge-type S,N,C` | 桥接类型 | 必选 |
| `--all-bridge-types` | 全部三种桥接类型 | - |
| `--task SA,IR` | 下游任务 | 必选 |
| `--all-tasks` | 全部下游任务 | - |
| `--categories S1,S2,N1` | 分类标签 | 必选 |
| `--all-sarcasm` | 全部反讽类 S1-S10 | - |
| `--all-non-sarcasm` | 全部非反讽类 N1-N10 | - |
| `--all-categories` | 全部 20 类 | - |
| `--count N` | 每个桥接标签生成数量（单类型模式） | 10 |
| `--samples-per-label N` | 每标签数量（多类型模式） | 10 |
| `--s-samples N` | S 型每标签数量 | 50 |
| `--n-samples N` | N 型每标签数量 | 30 |
| `--c-samples N` | C 型每标签数量 | 30 |
| `--output PATH` | 输出 JSONL 路径 | `./bridge_data_output.jsonl` |
| `--resume` | 断点续传 | 否 |
| `--validate` | 生成后跑质量检查 | 否 |
| `--api-key KEY` | API Key | `$ANTHROPIC_AUTH_TOKEN` |
| `--model NAME` | 模型名 | `deepseek-v4-pro` |
| `--base-url URL` | API 端点 | `https://api.deepseek.com/anthropic` |
| `--batch-size N` | 每批生成条数 | 5 |
| `--temperature F` | 温度 | 0.9 |
| `--max-tokens N` | 最大 tokens | 16000 |
| `--timeout N` | API 超时秒数 | 180 |
| `--seed-file PATH` | 种子数据 JSONL | 无 |
| `--flush-every N` | 累积 N 条后落库 | 0（每批都落） |

## 八、输出格式

每条样本的 JSON 结构：

```json
{
  "text": "华为平板办公体验真好，多设备协同如泰山般稳定...",
  "bridge_label": "BX-S1-SA-S",
  "sarcasm_label": "S1",
  "task_id": "SA",
  "bridge_type": "S",
  "is_sarcastic": true,
  "cot": "【一、反讽感知】\n1.1 信号扫描：...\n...",
  "task_output": "负面/消极"
}
```

## 九、Phase 2 训练混合比例建议

| 数据类型 | 占比 | 作用 |
|---|---|---|
| 纯下游任务数据（无 CoT / 短 CoT） | 35% | 保持正常能力，不让模型对什么文本都激活反讽 |
| 桥接 S 型（反讽→激活→下游） | 25% | 核心：学会感知反讽 + 翻转语义 + 应用 |
| 桥接 N 型（无反讽→快速跳过） | 20% | 学会判断"不需要反讽分析"时直接做任务 |
| 桥接 C 型（混淆→排除→下游） | 10% | 学会区分"像反讽但不是"的边界 |
| 原反讽识别数据（S1-S10, N1-N10） | 10% | 保持反讽识别本身不退化 |

## 十、目录结构

```
bridge_data/
├── generate_bridge_data.py   # 桥接数据生成脚本
└── README.md                 # 本文件
```

脚本依赖同级目录（`..`）下的 `_sarcasm_constants.py`。
