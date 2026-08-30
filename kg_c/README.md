# Product Knowledge — 产品知识注入方案

将产品结构化数据转化为 SFT 训练语料和评测集，用于大模型知识注入。

## 目录结构

```
product_knowledge/
├── README.md                          # 本文件 — 项目总览
├── doc_/
│   ├── 华为产品树.md                   # 原始产品数据（人工整理）
│   ├── 设计思路.md                     # 方案设计思路与决策理由
│   ├── 数据说明.md                     # 数据格式、字段、演进
│   └── 脚本使用指南.md                 # 各脚本的用法与参数
├── data_/
│   ├── 华为产品属性.json               # 结构化产品数据（89个产品，输入源）
│   ├── 华为评测集.jsonl               # 评测集 692条（实体链接任务）
│   ├── 华为训练语料.jsonl              # 训练语料·模板版 807条
│   ├── 华为训练语料_自然版.jsonl       # 训练语料·LLM自然版 608条 ★
│   └── llm_seeds.jsonl               # LLM扩增种子 19条（已用于生成自然版）
└── script_/
    ├── gen_eval.py                     # 评测集生成脚本（通用，模板驱动）
    ├── gen_train.py                    # 训练语料生成脚本（通用，模板驱动）
    └── merge_train.py                  # 多路 LLM 输出合并脚本
```

## 快速开始

### 1. 准备产品数据

按 `华为产品属性.json` 的格式整理你的产品数据：

```json
{
  "company": "公司名",
  "category": "手机",
  "series": "旗舰系列",
  "sub_series": "X80系列",
  "name": "X80 Pro Max",
  "alias": ["X80PM", "超大杯"],
  "positioning": ["商务旗舰", "顶配影像"],
  "talking_points": ["双潜望长焦", "卫星通信"],
  "generation": "最新款",
  "price": "¥7499起",
  "status": "在售"
}
```

### 2. 生成评测集

```bash
python script_/gen_eval.py data_/你的产品属性.json data_/评测集.jsonl
```

### 3. 生成训练语料

**模板版**（快速，可复现）：
```bash
python script_/gen_train.py data_/你的产品属性.json data_/训练语料_模板版.jsonl
```

**自然版**（需要 LLM，质量更高）：
用 `doc_/设计思路.md` 中描述的 Agent 分流方案，或按照 `llm_seeds.jsonl` 的种子提示让 LLM 批量扩增。

## 设计目标

- **可复用**：换一份产品 JSON，脚本就能跑，不绑定华为
- **可评测**：评测集答案精确可控，不需要人工打分
- **有层次**：模板版兜底 60% 场景，自然版覆盖闲聊/口语/跨品类
- **可追溯**：从原始产品树 → 结构化 JSON → 评测集+训练集，链路完整

## 演进路径

原始产品树 (md) → 结构化属性 (json) → 模板生成 → LLM 扩增 → 合并训练语料
