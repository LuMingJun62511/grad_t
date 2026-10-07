# attach_v1.01 · 节点级知识实验（系列级命名规律）

> 目标：验证"**把知识挂到树的中间节点**（如系列）"这件事的**操作**，且**树无关**（公司树不一样，但操作用同一套）。

## 实验设定
- **范围**：系列级（以 `Mate 系` 为例）。
- **知识**：schema 先行——**命名规律**：`Mate 系` 只出现过 `Pro / Pro Max / RS 非凡大师` 后缀，**没有 `Ultra`**。
- **影响**：这类知识会**改树**（中间节点开始携带 facts）。

## 数据（三种，全程树无关）
1. **树**：`tree.json`（`公司→产线→系列→代→SPU`，公司可换）。
2. **节点知识**：`nodes.jsonl`：
   ```json
   {"path":"华为 > 手机 > Mate 系","level":"系列","facts":[
     {"relation":"命名后缀","value":"Pro / Pro Max / RS 非凡大师","semantics":"规则"},
     {"relation":"命名排除","value":"Ultra","semantics":"规则"}]}
   ```
   → 用 **path 定位节点**（不靠具体树结构），所以换树也能挂。
3. **成员**：由树自动给出（`Mate 80 系列` 及其 SPU）。

## 操作（5 步，树无关）
| # | 操作 | 脚本 | 输入→输出 |
|---|---|---|---|
| 1 | **挂知识**到节点 | `attach.py` | tree.json + nodes.jsonl → attached_tree.json |
| 2 | **渲染**（路径+祖先 facts，防臃肿） | `render.py` | attached_tree.json (+目标节点) → mindmap |
| 3 | **出层级/规则题** | `gen_level_q.py` | attached_tree.json → 题（系列正向 / 规则判断 / 成员继承） |
| 4 | 校验 | `validate_nodes.py` | nodes.jsonl（节点存在？语义必填？） |
| 5 | 接入主管线 | （后续）| 节点 facts 进 mindmap → SCPT/CoT |

## 关键点（回答"树不一样怎么办"）
- 定位靠 **`path`**；**不依赖树的具体形状/名字**；
- 挂载 = "在路径末端节点上追加 facts"；
- 渲染 = "沿路径取祖先 facts"；
- 出题 = "按语义(全称/典型/规则)选题型"。
→ **换树只换 `tree.json`；节点知识按 path 迁移即可复用。**
