# 白盒化复杂 Prompt：从屎山到可测试的系统

> 建立日期：2026-11-18  
> 用途：复杂 prompt 梳理 / 评测 / 蒸馏 / 面试案例  
> 核心：**Prompt 不是 code，是 policy；模型不是 compiler，是 stochastic interpreter；eval 不是单元测试，是统计验收。**

---

## 0. 一句话

> **让模型做“取证”，让规则做“判决”；把例外从主干拆出去，把稳定行为蒸馏进模型。**

---

## 1. 屎山 prompt 的本质

不是“写得烂”，是**一个 prompt 干了五个系统的活**：

| 职责 | 表现 | 应该交给谁 |
|---|---|---|
| **Parser** | 解析多源输入、格式清洗 | code |
| **Classifier** | 打标、分类、加权 | 小模型 / 规则 |
| **FSM** | 状态机转移、流程分支 | 显式 FSM / code |
| **Knowledge** | 政策、话术、长尾知识 | retrieval |
| **Formatter** | JSON、字段、格式 | schema / constrained decoding |
| **Judge** | 例外、模糊、判断 | LLM prompt |
| **Safety** | 合规、敏感、越权 | guardrails |

补丁式迭代（来一个 case 加一条规则）→ **prompt debt / prompt spaghetti**。

---

## 2. 心智模型：policy, not code

| | Code | Prompt |
|---|---|---|
| 语义 | 确定性 | 概率性 |
| 同一输入 | 同一输出 | 分布 |
| 执行 | compiler | stochastic interpreter |
| 验证 | unit test | statistical acceptance |
| 解释 | 真实 | post-hoc rationalization |

**结论**：

- Prompt 是 **policy**，不是 function。
- 模型是 **interpreter**，不是 compiler。
- 强模型是 **test generator + critic**；小模型才是 **compiled artifact**。

---

## 3. 重构：拆系统，不是压提示词

```
Raw inputs
  → 输入规范化（code）
  → 证据抽取（LLM，结构化 JSON）
  → 规则 / 判决层（code / decision table）
  → 例外 override（priority rules）
  → 置信度检查
      → 高：自动出标
      → 低 / 例外：强模型 / 人工
  → 输出 + 审计轨迹
```

**关键**：LLM 负责“看见”，系统负责“裁定”。

---

## 4. 方法：TDD for prompts

1. **Extract spec**：让强模型通读 prompt，产出结构化 spec（输入、变量、规则、例外、输出）。当作 hypothesis，不是 truth。
2. **Build behavior graph**：生成多样输入，跑强模型 + 自述，聚类轨迹，找主路径 / 例外路径。
3. **Ablate rules**：逐条删规则，在人标集上看行为变化；分类为 essential / redundant / harmful。
4. **Refactor**：主路径留 prompt；例外拆到 tools / retrieval / guardrails / fallback。
5. **Distill**：主路径数据训小模型；难例 fallback 强模型。
6. **Regression**：golden set + property tests + drift monitoring。
7. **Route**：按 cluster / confidence 路由；低置信 abstain。

---

## 5. 已知技术映射

| 你的做法 | 对应技术 |
|---|---|
| 路径遍历 | CFG / branch coverage / trace clustering |
| 主干 vs 特殊 | happy path vs exception handling |
| 路径稳定性 | determinism / self-consistency / uncertainty |
| 规则消融 | delta debugging / ablation |
| 强模型自述 | chain-of-thought / self-explanation（需验证） |
| 训小模型 | distillation / behavioral cloning |
| 两个独立信号 | differential testing / ensemble disagreement |
| 按类拆 | routing / mixture of experts |

---

## 6. 三个风险

1. **白盒自述是事后合理化**：模型说的原因不等于真实计算。用消融验证。
2. **路径覆盖 ≠ 语义覆盖**：case 可能不覆盖生产分布。用人标 golden set + 生产采样。
3. **非确定性**：一次路径不是真相。每类跑 N 次，看分布；用 confidence / abstain。

---

## 7. 三个严谨性

- **统计**：重复采样、置信区间、P99。
- **分布**：人标 golden set、生产采样、难例覆盖。
- **因果**：消融、对照、反事实；规则可能互相补偿。

---

## 8. 可以更多利用的 LLM-native 特征

- **In-context examples > 堆规则**：示例传递边界感。
- **Tools / code**：确定性逻辑不要交给 prompt。
- **Constrained decoding**：格式用 schema / grammar。
- **Retrieval**：长尾知识放外面。
- **Instruction hierarchy**：system / user / tool 优先级。
- **Self-consistency**：多次采样投票。
- **DSPy 式优化**：signature + metric + optimizer。
- **Distillation + routing**：稳定行为进小模型，难例 fallback。

---

## 9. 复杂二分类：LLM 取证，规则判决

> 二分类不代表任务简单。复杂度在**取证**和**例外**，不在“输出一个 0/1”。

### 9.1 三层架构

| 层 | 做什么 | 谁来做 |
|---|---|---|
| **L0 硬规则** | 缺失、越权、政策硬约束 | code |
| **L1 主路径** | 证据抽取 + 常规判断 | 小模型 / LLM |
| **L2 难例** | 例外、模糊、低置信 | 强模型 |
| **L3 人工** | 高风险、争议、审计 | human |

### 9.2 取证 prompt 的骨架

```json
{
  "case_id": "...",
  "evidence": {
    "dimension_a": {"value": "...", "span": "...", "confidence": 0.0},
    "dimension_b": {"value": "...", "span": "...", "confidence": 0.0}
  },
  "exception_flags": ["..."],
  "missing_info": ["..."]
}
```

**不要让它直接出标**；让它出证据。判决交给规则 / 小模型。

### 9.3 判决层

- **Decision table**：优先级 × 条件 × 动作 × 例外。
- 硬约束先判；例外 override；默认兜底。
- **三向决策**：label 0 / label 1 / abstain（转人工）。

### 9.4 例外怎么放

| 例外类型 | 放哪 |
|---|---|
| 硬约束 / 合规 | guardrail / code |
| 长尾知识 | retrieval |
| 罕见 case | fallback prompt / 强模型 |
| 争议 case | human review |
| 格式 / 字段 | schema |

---

## 10. 验收指标

| 维度 | 指标 |
|---|---|
| 分类质量 | accuracy / precision / recall / F1 / AUC |
| 覆盖率 | auto-label coverage vs accuracy on covered |
| 校准 | ECE / Brier |
| 例外 | exception recall |
| 成本 | cost per case（小 / 强 / 人工） |
| 延迟 | P50 / P95 / P99 TTFT / TPOT |
| 漂移 | 分布变化、bad case 率 |

**风险-覆盖曲线**：覆盖率越高，准确率越低；找业务可接受的点。

---

## 11. 一句话

> **Prompt 不是代码，是 policy；模型不是编译器，是 stochastic interpreter；eval 不是单元测试，是统计验收。**
>
> **让模型做“取证”，让规则做“判决”。**

---

## 12. 三句话的深解：policy / interpreter / eval

### 12.1 一条链

```
Prompt 是 policy
  → 因为模型是 stochastic interpreter
    → 所以输出是分布
      → 所以 eval 必须是统计验收
```

### 12.2 Prompt 是 policy

**Policy 不是玄学词。** 公司的报销政策、退款政策、请假政策，都是 policy：

- 给原则：“7 天内、未使用，可以退”；
- 给边界：“定制商品、恶意退货，不退”；
- 给例外：“特殊情况，经理审批”；
- 具体 case 怎么判，由执行人解释。

**Prompt 就是写给模型的 policy。**

| | Code | Prompt |
|---|---|---|
| 语义 | 形式语义 | 自然语言语义 |
| 行为 | 确定 | 分布 |
| 完备性 | 封闭世界 | 开放世界，模型补全 |
| 组合 | 函数组合 | 规则交互，非线性 |
| 验证 | 证明 / 测试 | 统计评估 |

**含义**：

- 你写的是目标、约束、优先级、例子、兜底，不是每一步。
- 规则会互相影响；加一条可能改变另一条的解释。
- 模型会带入先验；它知道“定制商品通常不退”，哪怕你没写。

### 12.3 模型是 stochastic interpreter

| | Compiler | Stochastic interpreter |
|---|---|---|
| 输入 | 形式语言 | 自然语言 |
| 语义 | 形式语义 | 学习到的语义 |
| 输出 | 确定 | 分布 |
| 错误 | 可复现 | 随机、上下文相关 |
| 先验 | 无 | 有（预训练知识、偏见） |
| 验证 | 形式证明 | 经验评估 |

**精确说法**：

```
p(y | x, prompt) = ∏ p(y_t | y_<t, x, prompt)
```

- prompt 是条件变量，不是完整程序；
- 输出是采样，不是求值；
- “程序” = 模型权重 + prompt + decoding + context。

**含义**：

- 不能“编译一次，永远运行”；要持续评估。
- 不能假设组合性；加规则可能改变其他规则。
- 不能证明正确；只能测量。
- 要测的是 interpreter 的行为，不是 prompt 的语法。

### 12.4 Eval 是统计验收

| | Unit test | Statistical acceptance |
|---|---|---|
| 对象 | 一个函数 | 一个分布 |
| 输入 | 手工 case | 分层采样 |
| 结果 | pass / fail | 指标 + 置信区间 |
| 失败 | 1 个失败 = bug | 1 个失败 = 数据点 |
| 覆盖 | 代码路径 | 输入分布 |
| 结论 | 正确性 | 风险 / 收益 |

**临床 trial 类比**：

- 不会用一个病人证明药有效；要样本、对照、终点、显著性。
- 不会用一条 case 证明 prompt 有效；要 golden set、baseline、指标、置信区间。
- 临床看 subgroup analysis；eval 看 per-subclass metrics。
- 临床看 adverse events；eval 看 failure modes / exception recall。
- 临床看长期随访；eval 看 drift monitoring。

### 12.5 四个误解

1. **“写清楚就会确定。”** 清楚降低方差，不消除方差。
2. **“过了我的测试就是对的。”** 测试是样本，不是证明。
3. **“模型忽略规则，所以 prompt 坏了。”** 可能规则冲突、先验覆盖、解释歧义；要消融。
4. **“换个更大模型就好了。”** 更强但仍非确定，且可能更会“合理化”错误。

### 12.6 冲突的五种类型

“冲突”不是一种病，是五种病。共同点：模型必须在两个不能同时满足的信号之间做隐式仲裁；但坏处和修法不同。

| 冲突类型 | 例子 | 主要坏处 | 怎么修 |
|---|---|---|---|
| **Prompt 内部** | “简洁” vs “逐步解释”；规则 A vs B 无优先级 | **方差**：摇摆、边界翻转、顺序敏感 | 优先级、decision table、分区 |
| **Prompt vs 训练先验** | 提示说“都通过”，SFT 数据说“定制拒绝” | **偏差**：指令被先验覆盖，自信地错 | 示例、对齐数据、改措辞 |
| **训练数据内部** | 同一 case 两个标注员标了 0 和 1 | **天花板**：标签噪声，校准差 | 标注审计、仲裁、清洗 |
| **Prompt vs 上下文/工具** | 文档说 A，指令说 B；工具返回冲突 | **grounding 失败 / 注入**：幻觉、越权 | 指令层级、引用、工具校验 |
| **目标冲突** | 准确率 vs 延迟；安全 vs 有用 | **隐式 trade-off**：模型替你选 | 显式成本矩阵、阈值 |

共同点：模型替你做了仲裁；仲裁受顺序、先验、显著性影响。表现不是“变笨”，是“在某些区域偏、在某些边界摇”。

---

## 13. LLM 测试：不是找边界 case，是测分布

### 13.1 四种测试，只有一种能支持系统级结论

| 设计 | 得到什么 | 能回答什么 |
|---|---|---|
| 1 条 case × 1 次 | 轶事 | “它这次对了” |
| 多 case × 1 次 | 抽样调查 | “它大概多准” |
| 1 条 case × N 次 | 稳定性 | “这条稳不稳” |
| **多 case × N 次** | **分布 + 稳定性** | **“系统可不可信”** |

### 13.2 为什么“case 组合”不够

- LLM 输入是自然语言，空间无限；
- 模型行为是概率的、连续的，不是离散分支；
- 组合测试（pairwise / 正交表）适合离散配置，不适合语义输入。

**换成分布覆盖**：

- 按语义维度分层：子类 × 难度 × 歧义 × 例外类型；
- 每层采样，不追求全组合；
- 加扰动和反事实，测鲁棒性。

### 13.3 实验矩阵

```
             run1  run2  run3  run4  run5
case 1        ✓     ✓     ✗     ✓     ✓
case 2        ✓     ✓     ✓     ✓     ✓
case 3        ✗     ✗     ✗     ✗     ✗
...
case 500      ✓     ✗     ✓     ✓     ✗
```

- 行 = case，按 10 个子类分层，每类 30–50 条，共 300–500 条；
- 列 = 同一 case 跑 N 次（建议 5 次，边界 case 10 次）；
- 格子 = 输出标签 / 置信度。

### 13.4 从矩阵里算

1. **每条 case 的 agreement**：5 次里几次一致。
   - 5/5 稳；3/5 摇摆；0/5 稳定地错。
2. **flaky rate**：agreement < 0.8 的 case 占比。
3. **per-subclass F1 + 置信区间**：不是总体 accuracy。
4. **exception recall**：例外有没有漏。
5. **calibration**：置信度和正确率是否匹配。
6. **成本 / 延迟**：P50 / P95 / P99。

### 13.5 软工方法的升级

| 软工方法 | LLM 版 |
|---|---|
| 等价类划分 | 按子类 / 意图 / 难度 / 例外分层 |
| 边界值 | 政策阈值附近、缺信息、规则冲突 |
| 组合测试 | 配置组合（模型 × 温度 × prompt 版本） |
| 单元测试 | 单 case 断言，只做 smoke test |
| 回归测试 | golden set + 每次改动跑一遍 |
| 变异测试 | 同义改写 / 加噪声 / 换顺序，看标签是否稳定 |
| 反事实测试 | 改一个关键字段，期望标签按规则变化 |

**Metamorphic testing**：

- 同义改写 → 标签不变；
- 加无关细节 → 标签不变；
- 改关键字段 → 标签按规则变。

**Counterfactual pairs**：

- 只改一个关键属性；
- 期望输出按业务规则变化；
- 如果不变，说明模型没学到那条规则。

### 13.6 确定性内核 + 概率性外壳

灾难性、确定性失败（支付、合规、越权、隐私）不要靠 prompt + eval 兜底：

- **内核**：code / rule / 权限 / 金额校验；
- **外壳**：LLM 做取证、判断、生成；
- **中间**：eval 决定路由和阈值。

---

## 14. L0 模型 vs L3 Agent：在公司约束下交付

### 14.1 公司为什么想要 L0

- **成本**：推理成本可控，不被 API 计价。
- **数据/隐私**：数据不出域，合规。
- **差异化**：模型是资产，不是租来的。
- **可控性**：延迟、吞吐、版本、部署。
- **不被锁定**：不依赖某家 Agent 平台。

这些理由都合理，不要正面反对。

### 14.2 L0 单独不够

一个裸模型搞不定：

- 多源输入解析；
- 检索/知识；
- 工具调用；
- 状态/例外；
- 评测/监控；
- 格式/合规。

所以“只要 L0”在工程上不成立。但你可以**不叫它 Agent**。

### 14.3 调和：L0 core + thin deterministic wrapper

```
输入
 → 规范化（code）
 → L0 模型（取证/分类）
 → 判决层（规则 / GBDT / decision table）
 → 例外 fallback（强模型 / 人工）
 → 输出
```

- L0 模型是核心；
- wrapper 是**确定性、薄、可审计**的；
- 它不是“自主规划的 Agent”，是**模型的服务管线**。

> **模型负责“看见”，wrapper 负责“保证”。**

### 14.4 怎么说（给业务/主管）

不要说“我们需要一个 Agent”，要说：

> “我会交付一个 L0 模型。为了让它达到生产可靠性，需要一个薄的确定性服务层：输入规范化、规则判决、评测。这不是 Agent，是模型的 serving pipeline。裸模型会有不可接受的边界错误，这层是让 L0 可上线的必要条件。”

把“wrapper”翻译成“模型服务”，把“Agent”从词汇里拿掉。

### 14.5 明天先问清

1. 你们说的“L0 模型”具体指什么？checkpoint / API / 私有化 / 微调？
2. 质量、延迟、成本的硬指标是什么？
3. 是否允许内部低置信路由到强模型/人工？对外仍输出 0/1。
4. 现有数据/金标规模？10 个子类各多少？
5. 部署环境：GPU、serving 栈、并发、P99 目标。
6. 谁对“什么算对”负责？业务能否参与评审？

### 14.6 第一周

1. 写一页 **L0 + thin wrapper** 架构图。
2. 建 300–500 条 golden set（10 子类 × 30–50）。
3. 跑 baseline：现有 prompt vs 小模型 vs GBDT。
4. 定指标：per-subclass F1、flaky rate、P99、成本。
5. 和主管对齐“L0 指什么、wrapper 允许什么”。

### 14.7 你的定位

> **你不是“训模型的人”，你是“让模型在生产里可靠的人”。**

- 模型是耗材；
- eval + 数据飞轮 + 判决层是复利资产；
- 谁能定义“什么算对”，谁拿定价权。

---

## 15. 案例：噪声意图识别（小模型 prompt 示例）

### 15.1 任务

二分类：**噪声 / 非噪声**。  
噪声子类：**重复、附和**。

上下文：

- `bot_last`：机器人上一句
- `user_last`：用户上一句
- `user_current`：用户当前句

### 15.2 坏例子：说教式 prompt

```text
你是一个专业的对话意图识别专家。请你严格按照以下步骤思考：
第一步：通读全文，理解对话背景。
第二步：分析机器人上一句话的意图，判断是提问、确认、问候还是陈述。
第三步：分析用户上一句话的意图，判断是否与当前话相关。
第四步：判断当前话是否属于噪声。噪声包括：问候、重复、附和、...
第五步：如果是重复，判断是字面重复还是语义重复；如果是语义重复，
        判断相似度是否超过 0.8；如果超过，则...
第六步：如果是附和，判断是否包含新意图；如果包含，则...
第七步：如果...
（约 2000 字）
```

**问题**：

- 它是 **procedure**，不是 policy；
- 让小模型做它做不稳的事：相似度阈值、状态跟踪、多步分支；
- 任何没覆盖的 case，模型就现场编；
- 太长，注意力被稀释；
- 出错后不知道是哪一步错；
- 本质是**用长文掩盖“没有数据 / 没有 rubric”**。

### 15.3 好例子：任务卡式 prompt

```text
任务：判断用户当前话语是否为噪声。噪声只有两类：重复、附和。

上下文：
bot_last: {bot_last}
user_last: {user_last}
user_current: {user_current}

定义：
- 重复：与 user_last 表达同一意思，没有新增信息。
- 附和：仅表示收到/同意/礼貌，没有新增意图。

规则（按优先级）：
1. 与 user_last 语义重复 → 重复
2. 只有“好的/嗯/收到”等，且无新增意图 → 附和
3. 其他 → 非噪声

输出 JSON：
{"label":"noise|non_noise","subclass":"repeat|ack|null","evidence":"引用原文"}
```

**为什么好**：

- 短，接近训练分布；
- 只留 **任务 + 上下文 + 定义 + 3 条规则 + schema**；
- 优先级明确，冲突少；
- 有 `evidence`，可审计；
- 出错时能定位：上下文没给？定义不清？规则冲突？

### 15.4 Decision table

| 优先级 | 条件 | label | subclass |
|---|---|---|---|
| 1 | 与 `user_last` 语义重复 | noise | repeat |
| 2 | 只有附和词，且无新增意图 | noise | ack |
| 3 | 默认 | non_noise | null |

### 15.5 训练数据格式

```json
{
  "bot_last": "请问您要查询订单还是退款？",
  "user_last": "订单",
  "user_current": "订单",
  "label": "noise",
  "subclass": "repeat",
  "evidence": "用户重复了上一轮的“订单”，无新增信息"
}
```

**关键**：训练和推理用**同一种 prompt 格式**。不要训练短 prompt、推理塞 10k。

### 15.6 “教模型思考”到底好不好

| 场景 | 长 CoT / 说教 | 建议 |
|---|---|---|
| 强模型 + 复杂推理（数学、多步规划） | 可能有用 | 短 CoT / 分步 |
| 小模型 + 分类 / 打标 | **通常有害** | 短 rubric + 示例 + 规则 |
| 小模型 + 长上下文 | **有害** | 抽 context features，别让它自己找 |
| 例外多的业务 | **有害** | 拆 handler / fallback |

对小模型，长 CoT 的三个坏处：

1. **out-of-distribution**：训练时没见过这种脚本；
2. **注意力稀释**：规则越多，越容易漏；
3. **机械执行 / 事后合理化**：它可能不是按你写的想，而是编一个像样的理由。

**“教模型思考”往往是在弥补“没有数据 / 没有 rubric”。**  
更好的投资是：**示例 + 评测 + 判决层**，不是更长的说教。

如果非要引导，用**短 checklist**：

```text
判断前只问三个问题：
1. 当前话和 user_last 是否表达同一意思？
2. 当前话是否只有附和，没有新意图？
3. 是否引入了新信息 / 新请求？
```

### 15.7 一句话

> **好 prompt 是任务卡，不是教科书。**
> **教模型思考，不如给它上下文、例子和明确的判决规则。**

---

## 16. 版本

- v0.3（2026-11-19）：补 15 噪声意图识别案例（坏 / 好 prompt、decision table、训练数据、教模型思考的边界）。
- v0.2（2026-11-19）：补 12 三句话深解、13 LLM 测试矩阵、14 L0 模型 vs L3 Agent 的公司约束交付。
- v0.1（2026-11-18）：首版。
