"""
2-1 反向指代 v2: 联合条件出题
输入 = 实体 + 品类范围 + 两条属性条件 (组合在范围内唯一, 程序已验证)
"""
import json, os, sys, random, itertools
from collections import defaultdict

if sys.platform == 'win32':
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')

random.seed(42)
TDIR = r"C:\Users\LuMin\Desktop\kg_workspace\data_\corpus_v5\tuples"
OUT = r"C:\Users\LuMin\Desktop\kg_workspace\出题\台阶二_知识应用\2-1_反向指代\input.jsonl"

entities = []
for f in sorted(os.listdir(TDIR)):
    with open(os.path.join(TDIR, f), 'r', encoding='utf-8') as fp:
        d = json.load(fp)
    for e in d['entities']:
        entities.append({
            'entity': e['entity'],
            'level': e['level'],
            'tree_path': d['tree_path'],
            'triples': [(t['relation'], t['value'], t.get('bucket', 'A')) for t in e['triples']],
        })

def scope_of(tree_path):
    parts = tree_path.split(' > ')
    return parts[1] if len(parts) > 1 else ''

# 每个实体的候选条件: A桶 (含特性, 特性在反向指代里是指代物) + 排除 is_a
def conditions_of(e):
    conds = []
    for r, v, b in e['triples']:
        if b == 'A' and r != 'is_a':
            conds.append((r, v))
    return conds

# 全局索引: (r, v) -> 拥有它的实体集合
ro_owners = defaultdict(set)
for e in entities:
    for r, v, _ in e['triples']:
        if v:
            ro_owners[(r, v)].add(e['entity'])

# 生成: 每个实体取 2 条件组合, 验证组合在同类目内唯一
lines = []
seen = set()
for e in entities:
    scope = scope_of(e['tree_path'])
    if not scope:
        continue
    conds = conditions_of(e)
    if len(conds) < 2:
        continue

    # 同范围实体的集合
    scope_entities = {x['entity'] for x in entities if scope_of(x['tree_path']) == scope}

    for (r1, v1), (r2, v2) in itertools.combinations(conds, 2):
        if (r1, v1) == (r2, v2):
            continue
        # 验证: 同类目内, 同时满足两个条件的只有当前实体
        co_owners = ro_owners[(r1, v1)] & ro_owners[(r2, v2)] & scope_entities
        if co_owners == {e['entity']}:
            key = (e['entity'], r1, v1, r2, v2)
            if key in seen:
                continue
            seen.add(key)
            lines.append({
                'entity': e['entity'],
                'scope': scope,
                'conditions': [
                    {'relation': r1, 'value': v1},
                    {'relation': r2, 'value': v2},
                ],
            })
            break  # 每实体先取一组, 控制量

random.shuffle(lines)
with open(OUT, 'w', encoding='utf-8') as f:
    for l in lines:
        f.write(json.dumps(l, ensure_ascii=False) + '\n')
print(f'2-1 联合条件输入: {len(lines)} 包')
for l in lines[:5]:
    c1, c2 = l['conditions']
    print(f'  [{l["scope"]}] {l["entity"]}: {c1["relation"]}={c1["value"]} 且 {c2["relation"]}={c2["value"]}')
