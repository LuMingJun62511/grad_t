# 阶段2：DPO —— 五件套

**学什么**：离线偏好优化的机制与局限——DPO 不生成、不探索，只在已有回答风格里"选边"；
偏好对编码的是**你的价值观**，这是它相对 GRPO 规则奖励的独特价值。

## 1. 数据 I/O

**输入** `data/dpo_train.jsonl`（300 对，由 `scripts/build_dpo.py` 生成）。
ms-swift 格式：**messages 的最后一条 assistant 是 chosen**，被拒答案在 `rejected_response` 字段
（注意：没有 `chosen_response` 这个字段名）。

三个变体各教一件事：

| 变体 | rejected 长什么样 | 教的偏好 |
|---|---|---|
| V1 矛盾结论 | 四段保留，仅 3.1/3.2 换成反方向 | 结论必须与证据一致 |
| V2 裸答案 | "判断结果：是反讽，反讽机制：S1（直接反话）" | 这个任务上，有推理 > 裸答 |
| V3 糊弄推理 | 四段齐全但全是套话（空壳 CoT） | 扎实 > 空壳（对抗天花板三） |

```json
{
  "messages": [{"role":"system",…},{"role":"user",…},{"role":"assistant","content":"【一、表面分析】…（金标 CoT 全文）"}],
  "rejected_response": "判断结果：不是反讽，反讽机制：N3（直接批评）",
  "variant": "V1矛盾结论"
}
```

**输出**：`output/stage2_dpo/checkpoint-*`。

## 2. 配置

| 参数 | 值 | 理由 |
|---|---|---|
| `--model` / `--ref_model` | SFT checkpoint | 策略模型从 SFT 初始化；参考模型必须是同一个冻结的 SFT 权重，DPO 本质是"别离参考模型太远" |
| `--beta 0.1` | — | 偏好强度 vs 偏离惩罚的权衡。0.1 是常用档：偏好对可信（程序化构造，噪声低），可以稍小；若对噪声大有疑虑就调大 |
| `--learning_rate 5e-7` | — | 比 SFT 低一个量级：DPO 是在已经会格式的模型上微调偏好，大 lr 会把 SFT 学的格式冲掉 |
| `--num_train_epochs 2` | — | 300 对 × 2 epoch / 有效 batch 8 = 75 步，够学偏好；再多有拟合到"专门背这三类 rejected"的风险 |

## 3. 契约

与 SFT 完全相同（system/user 模板、3.1/3.2 正则）。DPO 阶段**不引入**任何新格式——
这是"三阶段共享一套数据契约"原则的第一次检验：如果 DPO 后解析率掉了，就是 beta/lr 太大把契约冲了。

## 4. 预期失败模式

| 症状 | 可能原因 | 看哪个指标 |
|---|---|---|
| 训练后输出变短、甚至变裸答 | beta 太小 / lr 太大，模型学到了"短就行"（V2 对没起到作用反而被模仿） | 平均输出长度 |
| 解析率下降、格式错乱 | DPO 把 SFT 的格式记忆冲掉了 | 解析率 |
| 完全没变化 | 偏好对太弱（chosen/rejected 差异不够大，logp 差趋零） | 训练日志的 chosen/rejected logp 差 |
| 输出全带"存在情感上的变化"这类套话 | V3 的空壳句被当成模板学走了（DPO 只学了 V3 的表面） | 人工抽检 |

## 5. 命令与验收

```bash
swift rlhf --rlhf_type dpo \
  --model output/stage1_sft/checkpoint-XX --ref_model output/stage1_sft/checkpoint-XX \
  --dataset data/dpo_train.jsonl --beta 0.1 --learning_rate 5e-7 \
  --num_train_epochs 2 --per_device_train_batch_size 2 --gradient_accumulation_steps 4 \
  --max_length 2048 --output_dir output/stage2_dpo
```

**验收**：test_in_dist 二分类 Acc 相对 SFT 不退化、解析率 ≥ 90%。
如果"完全没变化"也不要慌——这就是 DPO 的诚实：它只能在你给的数据里选边。
记录下这个现象，它和阶段 3 的 GRPO 形成对照。
