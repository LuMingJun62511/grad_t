# 语料 V4 — 数据组织说明

> 这是知识注入方案的数据底座。上面可以长出 SCPT、SSFT、图谱 QA 等多条训练数据管线。

---

## 一、目录结构

```
corpus_v4/
├── README.md                    ← 本文件
├── product_tree.json            ← 产品树 (180节点, 10品类, 40系列)
├── corpus_index.json            ← 产品→语料索引 (核心枢纽)
├── article_manifest.json        ← 语料清单
├── articles/                    ← 语料库 (每篇语料一个JSON文件)
│   ├── wiki_001_华为Mate_60系列.json
│   ├── wiki_002_华为Pura系列.json
│   └── ...
├── corpus_by_product.txt        ← 人类可读渲染版 (自动生成)
├── rejected_articles.json       ← 被过滤的语料及原因
└── _中间结果/                   ← 构建过程的中间产物
```

---

## 二、设计理念

### 核心原则：**产品树和自然语料分离，通过索引层耦合**

```
产品树 (结构化知识)              语料库 (自然语言)
──────────────                  ──────────────
product_tree.json               articles/*.json
  公司→品类→系列→SPU              每篇独立文件
  每个节点精确可控                 随时增删, 互不影响
  
         ↘           ↙
         corpus_index.json
         (产品名 → 语料引用列表)
```

**为什么要这样设计:**

1. **语料会变，产品树也会变，但索引结构不变。** 新增一篇语料 = 在 `articles/` 放一个文件 + 在 `corpus_index.json` 加一条引用。删除同理。不会牵一发而动全身。

2. **同一批语料可以有多种消费方式。** 下面列举的 SCPT / SSFT / 图谱QA 都读同一份 `corpus_index.json`，只是渲染方式不同。

3. **产品树是可验证的 ground truth。** 不管语料怎么变，产品树的结构化字段 (芯片、价格、定位) 始终是精确的，可以用于评测。

---

## 三、核心文件格式

### product_tree.json — 产品树

```json
{
  "name": "华为", "type": "Company",
  "children": [
    {
      "name": "手机", "type": "Category",
      "children": [
        {
          "name": "Mate 系列", "type": "Series",
          "children": [
            {
              "name": "Mate 80 系列", "type": "SubSeries",
              "children": [
                {
                  "name": "Mate 80 Pro", "type": "SPU",
                  "attrs": {
                    "price": "¥6499起",
                    "talking_points": ["麒麟9030", "WiFi7", "6.9寸微曲屏"],
                    "positioning": ["商务旗舰", "全能旗舰"],
                    "status": "在售", "generation": "最新款"
                  }
                }
              ]
            }
          ]
        }
      ]
    }
  ]
}
```

### corpus_index.json — 产品→语料索引

```json
{
  "Mate 80 Pro": {                              // ← 与 product_tree.json 中 SPU 的 name 一一对应
    "tree_path": "华为 > 手机 > Mate 系列 > Mate 80 系列",
    "category": "手机",
    "series": "Mate 系列",
    "articles": [
      {"id": "wiki_001_华为Mate_60系列", "source": "华为Mate 60系列", "type": "wiki_series"},
      {"id": "wiki_020_华为Mate_40系列", "source": "华为Mate 40系列", "type": "wiki_series"}
    ],
    "chunk_count": 86
  }
}
```

### articles/{id}.json — 单篇语料

```json
{
  "id": "wiki_001_华为Mate_60系列",
  "title": "华为Mate 60系列",
  "source_type": "wikipedia",
  "crawl_date": "2026-08-10",
  "char_count": 2935,
  "chunks": [
    {"idx": 0, "text": "华为Mate 60系列是华为首次在不举办新品发布会的状况下..."},
    {"idx": 1, "text": "2023年8月29日，华为突然在尚未举办新品发布会的情況下..."}
  ]
}
```

---

## 四、用法一：构造 SCPT 训练数据 (论文路线)

### 4.1 思路

SCPT (Structure-aware Continual Pre-Training) 的核心是：**每次给模型看一段自然语言 chunk 时，前面拼上这段 chunk 在产品树上的位置**。

```
训练样本格式:

  [产品树 Mindmap — 不计算 loss]
  华为产品体系:
  手机
  ├─ Mate 系列
  │  ├─ Mate 80 系列    ← 当前 chunk 所属分支
  │  └─ Mate 70 系列
  ├─ Pura 系列
  └─ ...
  
  关于 Mate 80 系列 的自然语言介绍:
  
  [原文 chunk — 计算 loss]
  华为Mate 60系列是华为...（维基原文）
```

### 4.2 生成逻辑 (伪代码)

```python
for product_name, info in corpus_index.items():
    tree_path = info["tree_path"]           # "华为 > 手机 > Mate 系列 > Mate 80 系列"
    mindmap = render_mindmap(tree_path)      # 渲染整棵产品树, 标注当前分支
    
    for article_ref in info["articles"]:
        article = load_article(article_ref["id"])
        for chunk in article["chunks"]:
            sample = mindmap + "\n" + chunk["text"]
            # → 写入 SCPT 训练集
```

### 4.3 接入新语料时

收到一批新语料 (如客服对话、评测文章) 后:

```
① 入库: 每个语料文件 → articles/business_XXX.json
   格式同上: {id, title, source_type, chunks: [{idx, text}, ...]}

② 索引: 在 corpus_index.json 中给对应产品加上引用
   "Mate 80 Pro": {
     "articles": [
       ...原有...,
       {"id": "business_001", "source": "客服FAQ", "type": "customer_service"}
     ]
   }

③ 如果新语料涉及产品树中没有的产品:
   在 product_tree.json 中新增 SPU 节点 (保持 name 唯一)
   在 corpus_index.json 中新增该产品的条目

④ 重跑 SCPT 数据生成 → 新语料自动融入训练集
```

---

## 五、用法二：构造 SSFT 训练数据 (论文路线)

### 5.1 思路

SSFT (Structure-aware Supervised Fine-Tuning) 的训练数据有两条生成路径:

**路径 A: 从产品树 + 语料生成 QA**

在产品树上 random walk → 拿到知识路径 + 对应 chunk → 喂 LLM 生成自然语言 QA

```
输入给 LLM:
  知识路径: 华为 > 手机 > Mate 系列 > Mate 80 系列
  参考内容: [chunk1] [chunk2] ...
  
  请生成一个关于 Mate 80 系列 的知识问答对。

LLM 输出:
  Q: Mate 80 Pro 搭载的芯片是什么?
  A: 麒麟9030
```

**路径 B: 从产品树的属性直接构造 QA (我们的 V3.1 路线)**

```python
# 指代拼接
feature = "首配3D人脸"      # 从 product_tree.json 的 talking_points 提取
spu = "Mate 80"             # 从图上的 has_feature 边查
category = "手机"           # 从图上的 is_a 链上溯
series = "Mate 系列"

# 生成评测 QA
Q: "「首配3D人脸」是华为什么品类的特性?"  →  A: "手机"
Q: "「首配3D人脸」属于华为哪个系列?"     →  A: "Mate 系列"
```

### 5.2 SSFT 训练格式

```
训练时 (答案带路径):
  Q: Mate 80 Pro 的芯片是什么?
  A: [手机 > Mate 系列 > Mate 80 系列]
     Mate 80 Pro 搭载麒麟9030芯片。

评测时 (裸答案):
  Q: Mate 80 Pro 的芯片是什么?
  A: 麒麟9030
```

---

## 六、用法三：知识图谱 QA (我们的 V3.x 路线)

### 6.1 思路

从 product_tree.json 构建知识图谱 → 三元组 → QA对

```
product_tree.json
  → 节点: SPU, Chip, Feature, Price, Positioning...
  → 边: is_a, has_chip, has_feature, has_price, positioned_as...
  → 三元组: (Mate 80 Pro, has_chip, 麒麟9030)
  → QA: "Mate 80 Pro 搭载什么芯片?" → "麒麟9030"
```

### 6.2 与 SCPT/SSFT 的关系

```
                     product_tree.json
                    /                \
                   /                  \
         [图谱QA路线]            [论文SCPT/SSFT路线]
         三元组→模板QA            mindmap→条件预训练
         V3.0, V3.1               SCPT + SSFT
              \                    /
               \                  /
            评测可以混用 (指代拼接)
```

---

## 七、完整示例：新增一批语料的全流程

### 场景

收到一份华为客服关于 Mate 80 Pro 的常见问题文档。

### Step 1: 入库语料

```bash
# 新建 article 文件
articles/business_001_Mate80Pro客服FAQ.json
```

```json
{
  "id": "business_001",
  "title": "Mate 80 Pro 客服FAQ",
  "source_type": "customer_service",
  "crawl_date": "2026-08-15",
  "char_count": 1500,
  "chunks": [
    {"idx": 0, "text": "Q: Mate 80 Pro 怎么截屏? A: 同时按住音量下键和电源键即可截屏。"},
    {"idx": 1, "text": "Q: Mate 80 Pro 支持无线充电吗? A: 支持50W无线快充和7.5W反向充电。"},
    {"idx": 2, "text": "Q: Mate 80 Pro 防水吗? A: 支持IP68级防水防尘。"}
  ]
}
```

### Step 2: 更新索引

在 `corpus_index.json` 中:

```json
"Mate 80 Pro": {
  "tree_path": "华为 > 手机 > Mate 系列 > Mate 80 系列",
  "articles": [
    // ...原有引用不动...
    {"id": "business_001", "source": "Mate 80 Pro 客服FAQ", "type": "customer_service"}
  ],
  "chunk_count": 89  // 86 + 3
}
```

### Step 3: 对接训练数据生成

SCPT 脚本读取 `corpus_index.json` → 渲染 mindmap + chunk → 写出训练 JSONL。
SSFT 脚本读取 `corpus_index.json` + `product_tree.json` → 生成 QA 对。
两个脚本都只需要读这两个文件，不需要改代码。

### Step 4: 如果新语料引入了新产品

在 `product_tree.json` 的对应位置插入新 SPU 节点。
在 `corpus_index.json` 新增该产品的条目。
刷新 `corpus_by_product.txt`。

---

## 八、当前数据统计

| 指标 | 值 |
|------|-----|
| 产品总数 | 180 |
| 品类数 | 10 |
| 系列数 | 40 |
| 语料文件数 | 24 |
| 总 chunk 数 | 4,838 |
| 产品覆盖率 | 130/180 (72%) |
| 平均每覆盖产品 chunk 数 | ~37 |

### 各品类语料覆盖

| 品类 | 产品数 | 已覆盖 |
|------|--------|--------|
| 手机 | 81 | 81 (100%) |
| 平板 | 19 | 13 |
| 笔记本 | 16 | 11 |
| 智能手表 | 23 | 8 |
| 智能汽车 | 21 | 15 |
| 耳机 | 11 | 0 |
| 其他 | 9 | 2 |
