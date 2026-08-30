# Prompt: 2-2 多条件筛选

## 题型定义

信息结构：**题目指向 R+O 的组合条件，题点是 S，答案是满足条件的 S 集合**。
用途：台阶二评测。多条独立属性做交集，模型必须组合两条以上单独训练过的知识。

## 输入格式 (JSON)

```json
{
  "scope": "Mate 80 系列",
  "tree_path": "华为 > 手机 > Mate 系 > Mate 80 系列",
  "candidate_entities": [
    {
      "name": "Mate 80",
      "attributes": [{"relation": "搭载芯片", "value": "麒麟9020"}, {"relation": "防水", "value": "IP68"}]
    },
    {
      "name": "Mate 80 Pro",
      "attributes": [{"relation": "搭载芯片", "value": "麒麟9030"}, {"relation": "防水", "value": "IP68"}]
    }
  ],
  "conditions": [
    {"relation": "搭载芯片", "value": "麒麟9030"}
  ]
}
```

## 输出示例

```json
[
  {"question": "Mate 80 系列里搭载麒麟9030的机型有哪些？", "answer": "Mate 80 Pro"}
]
```

## 质量自检清单

- [ ] 答案与条件逐一核对无误？
- [ ] 每个条件的知识在台阶一都单独训练过（组合评测成立）？
- [ ] 条件问法自然，无字段腔？
