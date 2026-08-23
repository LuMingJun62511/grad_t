# 反讽识别训练全流程（教学版 v0.1）

规模：训练集 **100 条**（20 类 × 5）。目的不是效果，是走通"数据 → SFT → DPO → GRPO → 评测"的全链，
并让每一步的输入/输出/契约都预先设计好、可检查。

## 一、项目结构

```
D:\learn_xpo\
├── data\                      # 数据（脚本生成，勿手改）
│   ├── train.jsonl            # SFT 训练集 100 条（messages 含 assistant）
│   ├── test_in_dist.jsonl     # 同分布测试 100 条（messages + gold）
│   ├── test_ood.jsonl         # 域外手工测试 12 条（餐厅/职场/恋爱）
│   ├── test_seed.jsonl        # 人工种子测试 ~152 条（人评集）
│   ├── grpo_train.jsonl       # GRPO 训练集 100 条（messages 无 assistant + solution）
│   └── dpo_train.jsonl        # DPO 偏好对 300 对（messages 末条=chosen + rejected_response）
├── scripts\
│   ├── clean_data.py          # 清洗 + 采样 + 生成上述五个文件
│   ├── build_dpo.py           # DPO 三变体偏好对构造
│   ├── reward_plugin.py       # GRPO 自定义奖励插件（ORM）
│   └── eval.py                # 评测统计
└── docs\                      # 本目录
    ├── pipeline.md            # 总览 + 契约 + 决策日志
    ├── stage1_sft.md          # 阶段1 五件套
    ├── stage2_dpo.md          # 阶段2 五件套
    ├── stage3_grpo.md         # 阶段3 五件套
    └── stage4_eval.md         # 阶段4 五件套
```

## 二、数据契约（全流程的单一事实来源）

所有阶段共享同一套契约；改契约必须同步改 `clean_data.py`、`reward_plugin.py`、`eval.py` 三处。

**System prompt**（见 `scripts/clean_data.py` 的 `SYSTEM` 常量）：

```
你是反讽识别助手。判断给定文本是否为反讽，并按四段式输出推理过程。
输出格式契约：
【一、表面分析】1.1 字面含义 1.2 情感极性 1.3 背景预设 1.4 伪装判断
【二、深层分析】2.1 真实意图 2.2 真实情感 2.3 情感反转
【三、反讽判断】3.1 判断结果：是反讽 或 不是反讽；3.2 反讽机制：下列编码之一
【四、判断依据】4.1 语言线索 4.2 语境线索 4.3 情感线索 4.4 伪装机制
机制编码：S1 直接反话 S2 反话正说 S3 夸张失当 S4 对比反讽 S5 假装赞同
S6 过度礼貌 S7 捧杀 S8 引用反讽 S9 反问反讽 S10 自嘲反讽
N1 真诚夸张 N2 真诚赞美 N3 直接批评 N4 幽默段子 N5 中式自谦
N6 网络流行语 N7 情绪宣泄 N8 委婉表达 N9 有保留赞同 N10 情境矛盾叙述
```

**User 模板**：`场景：{语境}\n文本：{文本}\n请判断这段文本是否为反讽，并给出完整推理。`

**解析正则**（奖励与评测共用）：
```python
RE_JUDGE = re.compile(r"3\.1\s*判断结果[:：]\s*(是反讽|不是反讽)")
RE_MECH  = re.compile(r"3\.2\s*反讽机制[:：]\s*([SN]\d{1,2})")
```

**标签字典**：S1~S10 → 是反讽；N1~N10 → 不是反讽（见 `clean_data.py` 的 `MECH`）。

## 三、设计决策日志

| # | 决策 | 理由 |
|---|---|---|
| D1 | 语境从 CoT 移入 user 输入 | 推理每一步必须从输入可推导，否则训的是幻觉 |
| D2 | 质量线（前 60 条）+ 关键词贪心多样采样 | 数量天花板：5 条/类时尽量覆盖表面特征，降低"华为→S1"式捷径 |
| D3 | 【三】注入 `3.2 反讽机制` 行 | 把 20 路机制变成可解析输出，奖励与推理的相关性拧强一档 |
| D4 | 不设 val 集、不调超参 | 教学项目，避免用测试集信息污染；阶段间用 test_in_dist 对比即可 |
| D5 | 全参微调，不用 LoRA | 0.6B 全参在单卡上毫无压力；少一个合并步骤，少一个变量 |
| D6 | GRPO 奖励 = 0.5×二分类 + 0.5×机制 | 二分类保底、机制逼推理；无显式格式奖励（解析器即格式门槛） |
| D7 | DPO 三变体（矛盾/裸答/空壳） | DPO 的价值在注入规则表达不了的偏好（证据一致 > 空壳 > 裸答） |

## 四、命令速查（公司 NPU 机器上执行）

```bash
# 阶段1 SFT
swift sft --model Qwen/Qwen3-0.6B --dataset data/train.jsonl \
  --train_type full --num_train_epochs 5 --per_device_train_batch_size 4 \
  --gradient_accumulation_steps 2 --learning_rate 1e-5 --warmup_ratio 0.1 \
  --lr_scheduler_type cosine --max_length 2048 --save_steps 20 --logging_steps 5 \
  --output_dir output/stage1_sft

# 阶段2 DPO（ckpt 号以实际为准）
swift rlhf --rlhf_type dpo \
  --model output/stage1_sft/checkpoint-XX --ref_model output/stage1_sft/checkpoint-XX \
  --dataset data/dpo_train.jsonl --beta 0.1 --learning_rate 5e-7 \
  --num_train_epochs 2 --per_device_train_batch_size 2 --gradient_accumulation_steps 4 \
  --max_length 2048 --output_dir output/stage2_dpo

# 阶段3 GRPO
swift rlhf --rlhf_type grpo \
  --model output/stage2_dpo/checkpoint-XX \
  --dataset data/grpo_train.jsonl \
  --reward_funcs sarcasm_detect --external_plugins scripts/reward_plugin.py \
  --num_generations 4 --temperature 1.0 --beta 0.04 --learning_rate 1e-6 \
  --per_device_train_batch_size 4 --max_completion_length 1024 \
  --use_vllm true --vllm_gpu_memory_utilization 0.5 --sleep_level 1 \
  --output_dir output/stage3_grpo

# 阶段4 推理 + 评测（每个 checkpoint 跑一遍，得四档对比）
swift infer --model <ckpt> --dataset data/test_in_dist.jsonl --result_dir preds/stage1
python scripts/eval.py --preds preds/stage1/<结果文件名>.jsonl --gold data/test_in_dist.jsonl
python scripts/eval.py --preds preds/stage1/<结果文件名>.jsonl --gold data/test_ood.jsonl
```

## 五、验收标准（每阶段跑完对照）

| 阶段 | 通过线 |
|---|---|
| SFT | test_in_dist 二分类 Acc ≥ 60%（base 0-shot 约 50%）；解析率 ≥ 90% |
| DPO | 相对 SFT 不退化；解析率不掉 |
| GRPO | 相对 DPO 持平或提升；平均输出长度不爆炸；机制分布不坍缩 |
| 复盘 | 能把每个指标变化映射回文档里的天花板概念 |

## 六、版本与兼容声明

- ms-swift **v4.x**（2026-07 时点 v4.4.0）。命令 flag 以官方文档为准，个别名称可能随版本微调。
- 昇腾 NPU：SFT/DPO 无压力；GRPO 的推理后端在 NPU 上是 vllm-ascend / MindIE，
  到公司按实际环境调整 `--use_vllm` / 引擎参数（ms-swift v4.4.0 含 NPU GRPO 修复）。
- vLLM 版本敏感：官方曾报告 0.8.3 卡死问题、推荐 0.7.3；v4.5 线要求 ≥0.17.0。装之前查对应版本文档。
