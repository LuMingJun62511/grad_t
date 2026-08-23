# 阶段3：GRPO —— 五件套

**学什么**：在线 RL 的机制——模型自己生成一组候选、奖励打分、组内相对优势更新；
奖励设计；以及本项目的重头戏：**reward hacking 长什么样**。

## 1. 数据 I/O

**输入** `data/grpo_train.jsonl`（100 条）。注意与 SFT 的差别：
**messages 只有 [system, user]，没有 assistant**（防止答案泄漏）；金标放在 `solution` 列，
由 ms-swift 透传给奖励函数：

```json
{
  "messages": [{"role":"system",…},{"role":"user","content":"场景：…\n文本：…\n请判断…"}],
  "solution": "{\"is_sarcastic\": true, \"label\": \"S1\"}"
}
```

**奖励插件** `scripts/reward_plugin.py`（ORM 接口，见 `docs/pipeline.md` 第六节命令中的
`--external_plugins` 用法）。核心逻辑：

```python
r = 0.0
if 解析出 3.1 且与 gold 二分类一致:  r += 0.5
if 解析出 3.2 且与 gold 机制一致:    r += 0.5
# 无显式格式奖励：解析器本身就是格式门槛（D6）
```

**输出**：`output/stage3_grpo/checkpoint-*`。

## 2. 配置

| 参数 | 值 | 理由 |
|---|---|---|
| `--num_generations 4` | — | 组内相对优势需要每组至少 3~4 个候选；再大训练变慢、小数据也没必要 |
| `--beta 0.04` | — | KL 系数。RL 必须比 DPO 更"抓紧"参考模型——在线探索容易跑飞，0.04 是 GRPO 常用档 |
| `--learning_rate 1e-6` | — | RL 阶段 lr 再降一个量级：奖励有噪声，大 lr 直接震荡 |
| `--temperature 1.0` | — | 探索温度：组内候选要有差异才有相对优势可言；过低=组内全一样 |
| `--max_completion_length 1024` | — | 限制输出长度，防"复述输入换长度奖励"式的绕法（我们没给长度奖励，但也别让它无限写） |
| `--use_vllm true --sleep_level 1` | — | rollout 用 vLLM 加速；sleep_level 让训练与推理复用同卡时错峰。NPU 上按实际后端调 |

## 3. 契约

- 解析正则与 SFT/DPO 完全一致。
- solution 的 JSON schema：`{"is_sarcastic": bool, "label": "S1"~"N10"}`。
- 奖励区间 [0, 1]，粒度 0.5。**没有格式奖励、没有长度奖励**——这两样是 reward hacking 的经典入口。

## 4. 预期失败模式（本阶段的重头戏）

| 症状 | 解释 | 看哪个指标 |
|---|---|---|
| 奖励上升但二分类 Acc 下降 | 模型学会"蒙"奖励：比如在 3.1 写两遍一正一反，正则抓前一个；或把机制编码全试一遍 | 人工抽检 rollout 文本 + Acc |
| 输出变成空壳四段 | 机制项逼出来的"格式正确、内容空转"——**这就是弱相关下 RL 的必然产物**：奖励只看得见标签，看不见推理质量（天花板三的现场版） | 平均长度、抽检 |
| 平均长度爆炸 | 模型在长文本里藏更多"猜中"的机会；或复述输入凑命中率 | 平均输出长度 |
| KL 持续上升 | 离参考模型太远，语言能力退化（句子不通、乱码） | 训练日志的 KL 指标 |
| 机制分布坍缩到高频类 | 100 条数据里 S1/N1 最易学，模型放弃低收益类 | 机制分布 |

## 5. 命令、验收与 hacking 对照实验

```bash
swift rlhf --rlhf_type grpo \
  --model output/stage2_dpo/checkpoint-XX \
  --dataset data/grpo_train.jsonl \
  --reward_funcs sarcasm_detect --external_plugins scripts/reward_plugin.py \
  --num_generations 4 --temperature 1.0 --beta 0.04 --learning_rate 1e-6 \
  --per_device_train_batch_size 4 --max_completion_length 1024 \
  --use_vllm true --vllm_gpu_memory_utilization 0.5 --sleep_level 1 \
  --output_dir output/stage3_grpo
```

**验收**：test_in_dist 二分类 Acc 相对 DPO 持平或提升；平均输出长度不爆炸；机制分布不坍缩。

**对照实验（教学必修）**：把 `reward_plugin.py` 里的 `FORMAT_BONUS` 改成 `0.1` 再训一轮
（其余不变，`--output_dir` 换个名字）。预期看到：平均奖励更高，但模型开始输出
"四段齐全、内容全空"的文本——**奖励上去了，能力没上去**。这就是 reward hacking 的第一课：
你奖励什么，模型就优化什么，而且永远用你想不到的方式。
