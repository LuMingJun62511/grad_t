# Prompt: 2-5 上级归纳

## 题型定义

信息结构：**题目指向代层（系列的全称特性），题点是全称规则，答案是规则值**。
用途：台阶二评测。树的上层（代/系列）参与出题——模型要能从成员共性归纳出"全系标配"。

前置条件：代层实体有全称特性（输入中的 series_triples 来自代层实体），成员实体共享该值（可验证）。

## 输入格式 (JSON)

```json
{
  "series_entity": "Mate 80 系列",
  "tree_path": "华为 > 手机 > Mate 系 > Mate 80 系列",
  "series_triples": [
    {"relation": "操作系统", "value": "HarmonyOS 6"}
  ],
  "member_entities": ["Mate 80", "Mate 80 Pro", "Mate 80 Pro Max", "Mate 80 RS 非凡大师"]
}
```

## 输出示例

```json
[
  {"relation": "操作系统", "question": "Mate 80 系列全系搭载什么操作系统？", "answer": "HarmonyOS 6"}
]
```

## 质量自检清单

- [ ] 问题指向系列而非单个产品？
- [ ] 答案是全称规则值（全系成立）？
- [ ] 每个成员在台阶一都单独训练过该特性（归纳评测成立）？
