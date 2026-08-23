# 阶段1：SFT 冷启动 —— 五件套

**学什么**：SFT 训进去的是什么（P(推理轨迹|任务) 的条件分布）；CoT 数据质量为何决定上限；
数据格式怎么决定"训进去什么"。

## 1. 数据 I/O

**输入** `data/train.jsonl`（100 条，messages 含 assistant）：

```json
{
  "messages": [
    {"role": "system", "content": "你是反讽识别助手。…（契约全文）"},
    {"role": "user", "content": "场景：一个中年用户在微信群聊里吐槽新买的MateBook笔记本…\n文本：华为笔记本品控真是绝了，用一周自动重启三次，太省心了。\n请判断这段文本是否为反讽，并给出完整推理。"},
    {"role": "assistant", "content": "【一、表面分析】\n1.1 字面含义：…\n…\n【三、反讽判断】\n3.1 判断结果：是反讽\n3.2 反讽机制：S1（直接反话）\n…【四、判断依据】…"}
  ],
  "label": "S1", "is_sarcastic": true, "text": "华为笔记本品控真是绝了…"
}
```

**输出**：`output/stage1_sft/checkpoint-*`（全参 checkpoint）。

注意：assistant 内容**不含**【场景/语境】段（已移入 user 输入，D1）；【三】多了一行 `3.2 反讽机制`（D3）。
这就是"数据形态决定天花板"在格式层的落地：模型的每一句推理都必须有输入来源。

## 2. 配置（每个值为什么这么取）

| 参数 | 值 | 理由 |
|---|---|---|
| `--train_type full` | — | 0.6B 全参无压力；少一个 LoRA 合并变量（D5） |
| `--num_train_epochs 5` | — | 100 条 × 5 epoch / 有效 batch 8 ≈ 62 步，足够小模型收敛到模板 |
| `--per_device_train_batch_size 4` | — | 序列 2048，0.6B 单卡显存绰绰有余 |
| `--gradient_accumulation_steps 2` | — | 有效 batch = 8：太小噪声大，太大这数据量没意义 |
| `--learning_rate 1e-5` | — | 全参小模型标准起步值；SFT 阶段 lr 是三个阶段里最高的 |
| `--warmup_ratio 0.1 --lr_scheduler_type cosine` | — | 前 10% 步线性热身，防开局发散；cosine 收尾稳定 |
| `--max_length 2048` | — | CoT 平均 1259 字 + prompt ≈ 1600，留余量 |
| `--save_steps 20` | — | 全程 ~62 步，多存几个点方便挑 |

## 3. 契约

- 解析正则、标签字典、语境位置：见 `docs/pipeline.md` 第二节。
- 训练数据已经过质量线（四段齐全、3.1 与 is_sarcastic 一致、语境可解析、长度 400~2500）——
  清洗报告里"区内不一致"列是零，说明老师在这些样本上没胡说（天花板三的初步防线）。

## 4. 预期失败模式

| 症状 | 可能原因 | 看哪个指标 |
|---|---|---|
| loss 不降 / 波动巨大 | lr 太高；数据格式错（assistant 为空等） | 训练日志前 10 步 |
| 输出没有【三】 | 数据契约没学进去；epoch 太少 | 评测解析率 |
| 全部输出 S1 / 全答"是反讽" | 类别坍缩（数量天花板二的典型表现） | 机制分布、分极性召回 |
| 1.1 整段复述输入凑字数 | 老师自己就爱复述（天花板三）被学到了 | 人工抽检输出 |

## 5. 命令与验收

```bash
swift sft --model Qwen/Qwen3-0.6B --dataset data/train.jsonl \
  --train_type full --num_train_epochs 5 --per_device_train_batch_size 4 \
  --gradient_accumulation_steps 2 --learning_rate 1e-5 --warmup_ratio 0.1 \
  --lr_scheduler_type cosine --max_length 2048 --save_steps 20 --logging_steps 5 \
  --output_dir output/stage1_sft
```

**验收**：`swift infer` + `python scripts/eval.py` 跑 test_in_dist：
二分类 Acc ≥ 60%、解析率 ≥ 90%。同时人工读 5 条输出，检查有没有"复述凑字"。
达不到先回第 4 节对症状，不要直接改数据。
