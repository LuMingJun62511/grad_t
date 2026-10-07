# pipeline_v2.01 · 产品知识出题流水线（可插拔）

> 目标：`schema 先行 → mindmap → SCPT → 出题(可插拔) → CoT → 组装 → 审阅`。
> 每个阶段 = 一个独立脚本（明确输入/输出），**可单独替换**（公司版出题不同也不影响其它阶段）。

## 目录
```
pipeline_v2.01/                     ← ★ 整个文件夹打包带走即可续（自洽）
├─ README.md                 本文件（入口/导航）
├─ 交付说明.md               打包带走说明（先看这个）
├─ 接口规范.md               ★ 各阶段 I/O 契约 + 树/schema/CoT 组件 + 校验器 + 排错表
├─ 待做.md                   收尾清单（明天接着干）
├─ schema版本记录.md         schema v1→v2 迁移与留痕
├─ 多跳题制式.md             3-1 多跳题定义
├─ 设计/                     ★ 设计与取舍（决策表簿 D-1…D-8 等）
│   ├─ 决策表簿.md
│   ├─ 设计_节点级知识.md
│   ├─ schema草稿.md
│   ├─ 工具与产物总览.md
│   └─ 今日目标.md
├─ tools/                    各阶段脚本（编号=阶段顺序）
├─ node_knowledge/           ★ 阶段 0.5 · 节点级知识（系列/代 facts + L1/L2 + D-6 实验）
├─ prompts/<题型>/           3a 出题用的原始 prompt + 模板池
├─ input/<品类>/             数据.jsonl + 出题建议.csv（+ schema_<产线>.csv）
├─ out/<品类>/               产出（出题/ cot/ sft/ scpt/ review_all.html …）
└─ _依赖/                    随包内置的源文件（Mate 三元组 / 耳机三元组 / 产品树）
```
> **本包自洽**：主链 `tools/` 全 argparse（无写死路径、无外部依赖）；节点知识在 `node_knowledge/`；
> 源文件在 `_依赖/`。**打包本文件夹 = 全量可续**。

## 阶段与数据形状（**契约**）

| # | 阶段 | 脚本 | 输入 | 输出（数据形状） | 可插拔点 |
|---|---|---|---|---|---|
| 0 | 地基 | `0_validate.py` `0_normalize_tree.py` `0_make_suggest.py` | 数据 jsonl | 校验报告 / 归一数据 / **出题建议.csv** | 换校验规则 |
| 1 | mindmap | `1_make_mindmap.py` | 数据 jsonl | `mindmap.txt`（ASCII 树） | 换渲染粒度 |
| 2 | SCPT | `2_gen_scpt.py`（LLM） | 数据 jsonl + 品类名 | `{input, output, _meta}`，命名 `scpt_entity_llm.jsonl` | 换语料策略（规则/LLM/口语） |
| 3 | **出题** | **3a** `3a_gen_questions_prompt.py`（**prompt 驱动·正宗**，LLM）<br>**3b** `3b_gen_questions_template.py`（模板·快，0 LLM） | 数据 jsonl + （3b 还需）出题建议.csv + 品类名；3a 另读 `prompts/<题型>/prompt.txt`+模板池 | **`{type, q, a}`**，文件名=题型（`1-1.jsonl`…） | ★ **换出题方法只换这一步**：3a/3b 即两种实现，同契约 |
| 4 | CoT | `4_gen_cot.py` | 题 jsonl + 数据 + (语料) | `{question, answer, response, _meta}` | 换 CoT 结构 |
| 5 | 组装 | `5_assemble_sft.py` | `<pkg>/cot/*.jsonl` | `{input, output}` → `sft/sft_cot.jsonl` | 换训练格式 |
| 6 | 审阅 | `6_make_review.py` | `<pkg>` | `review_all.html` | —— |

### 关键中间产物字段
- **数据**：`{"entity","tree_path","triples":[{"relation","value"}]}`（`tree_path` 到"系列"为止，实体单独给）
- **出题建议表**（CSV，人工可改）：`关系,出现次数,出对比,权重,备注` → 决定"哪些知识值得出对比题(2-6)"
- **出题**：`{"type":"1-1","q":"…","a":"…"}`（`type` ∈ 1-1/1-2/1-3/1-4/2-1/2-2/2-3/2-4/2-5/2-6）
- **CoT**：`{"question","answer","response"}`，response = 【知识结构】+【相关原文】+【推理】+【答案】
- **SFT**：`{"input": 问题, "output": CoT}`

## 包目录约定（stage3/4/5/6 共用）
```
<品类包>/
├─ 1-1.jsonl … 2-6.jsonl     ← 出题（stage3 产出，文件名=题型）
├─ cot/<题型>.jsonl          ← CoT（stage4）
├─ sft/sft_cot.jsonl         ← SFT（stage5）
├─ scpt/*.jsonl              ← SCPT（stage2，名字含 llm/leaf 以识别）
└─ review_all.html           ← 审阅（stage6）
```

## 一条完整命令链（以"笔记本"为例；Windows PowerShell）
```powershell
$env:ANTHROPIC_BASE_URL=...; $env:ANTHROPIC_AUTH_TOKEN=...; $env:DS_MODEL=deepseek-v4-flash
$IN="input\笔记本"; $PKG="out\笔记本"
# 0 建议表
python tools\0_make_suggest.py --data "$IN\数据.jsonl" --out "$IN\出题建议.csv"   # 之后可人工改
# 1 mindmap
python tools\1_make_mindmap.py --data "$IN\数据.jsonl" --out "$PKG\mindmap.txt"
# 2 SCPT
python tools\2_gen_scpt.py --data "$IN\数据.jsonl" --category 华为笔记本 --outdir "$PKG\scpt" --scpt
#   （把 scpt.jsonl 改名 scpt_entity_llm.jsonl）
# 3 出题（★可插拔）
python tools\3_gen_questions.py --data "$IN\数据.jsonl" --outdir $PKG --suggest "$IN\出题建议.csv" --category 华为笔记本
# 4 CoT
foreach ($t in '1-1','1-2','1-3','1-4','2-1','2-2','2-3','2-4','2-5','2-6') {
  if (Test-Path "$PKG\$t.jsonl") { python tools\4_gen_cot.py --questions "$PKG\$t.jsonl" --data "$IN\数据.jsonl" --out "$PKG\cot\$t.jsonl" } }
# 5 组装 + 6 审阅
python tools\5_assemble_sft.py --pkg $PKG
python tools\6_make_review.py --pkg $PKG --title 笔记本
```

## 出题的两种实现（3a / 3b，同一契约）
- **3a prompt 版（正宗）**：照着**原始 9 套 prompt** —— 把三元组按题型组输入包、填 `prompt.txt` + **模板池轮换**，喂 LLM 出题。
  ```powershell
  python tools\3a_gen_questions_prompt.py --data "$IN\数据.jsonl" --outdir $PKG --category 华为笔记本 --prompts prompts
  ```
- **3b 模板版（快）**：确定性填空，0 LLM；2-6 读"出题建议表"。
- 两者输出**完全同构**（`{type,q,a}`），下游 CoT/组装/审阅不区分。

## 换品类 / 换方法
- **换品类**：在 `input/` 放该品类的 `数据.jsonl` + `出题建议.csv`，改 `--category`，跑同一链。
- **换出题方法（公司版）**：只替换 **stage3**（保持输出 `{type,q,a}` + 文件名=题型 的契约），下游 stage4/5/6 不动。
- **换语料策略**：只替换 **stage2**（保持 `{input,output}` 契约）。

## 依赖
- 需要 LLM 的阶段：2(SCPT)、3?（当前 3 是纯模板，0 LLM）、4(CoT)。用环境变量配置：
  `ANTHROPIC_BASE_URL` / `ANTHROPIC_AUTH_TOKEN` / `DS_MODEL`（Anthropic 兼容，`thinking:disabled`）。
