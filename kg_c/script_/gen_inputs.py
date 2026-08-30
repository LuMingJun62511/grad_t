"""
从 tuples/ 生成各题型的测试输入
每个题型一个 input.jsonl，行 = 一个实体包
"""
import json, os, sys, random
from collections import defaultdict

if sys.platform == 'win32':
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')

TDIR = r"C:\Users\LuMin\Desktop\kg_workspace\data_\corpus_v5\tuples"
BASE = r"C:\Users\LuMin\Desktop\kg_workspace\出题"

random.seed(42)

# 加载全部元组
entities = []  # {entity, level, tree_path, triples: [(r,v,bucket)]}
for f in sorted(os.listdir(TDIR)):
    with open(os.path.join(TDIR, f), 'r', encoding='utf-8') as fp:
        d = json.load(fp)
    for e in d['entities']:
        entities.append({
            'entity': e['entity'],
            'level': e['level'],
            'tree_path': d['tree_path'],
            'triples': [(t['relation'], t['value'], t.get('bucket','A')) for t in e['triples']],
        })

def write_input(path, lines):
    with open(path, 'w', encoding='utf-8') as f:
        for line in lines:
            f.write(json.dumps(line, ensure_ascii=False) + '\n')
    print(f'  {path}: {len(lines)} 个实体包')

# ============================================================
# 1-1 正向属性询问: 每个实体 × 其A桶元组
# 规则:
#   - 剔除 特性 关系 (has_feature 先扔, 待细化谓语后再用 — 见待办)
#   - 剔除同实体多值关系 (如配色/定位有多个值, "X的R是什么"会造冲突答案)
#     → 多值关系归 1-3 集合枚举
# ============================================================
lines = []
for ent in entities:
    a_triples = [(r, v) for r, v, b in ent['triples'] if b == 'A' and r != 'is_a' and r != '特性']
    # 统计每关系值数量, 多值的剔除
    val_count = defaultdict(int)
    for r, v in a_triples:
        val_count[r] += 1
    single = [(r, v) for r, v in a_triples if val_count[r] == 1]
    if not single: continue
    lines.append({
        'entity': ent['entity'],
        'tree_path': ent['tree_path'],
        'triples': [{'relation': r, 'value': v} for r, v in single],
    })
write_input(os.path.join(BASE, '台阶一_属性记忆', '1-1_正向属性询问', 'input.jsonl'), lines)

# ============================================================
# 1-2 归属链询问: is_a 元组 (往上问所属)
# ============================================================
lines = []
for ent in entities:
    isa = [(r, v) for r, v, b in ent['triples'] if r == 'is_a' and b == 'A']
    if not isa: continue
    lines.append({
        'entity': ent['entity'],
        'tree_path': ent['tree_path'],
        'triples': [{'relation': r, 'value': v} for r, v in isa],
    })
write_input(os.path.join(BASE, '台阶一_属性记忆', '1-2_归属链询问', 'input.jsonl'), lines)

# ============================================================
# 1-3 属性集合枚举: 同实体同关系多值
# ============================================================
lines = []
for ent in entities:
    by_rel = defaultdict(list)
    for r, v, b in ent['triples']:
        if b == 'A' and r != 'is_a' and r != '特性':
            by_rel[r].append(v)
    multi = [{'relation': r, 'values': vs} for r, vs in by_rel.items() if len(vs) >= 2]
    if not multi: continue
    lines.append({'entity': ent['entity'], 'tree_path': ent['tree_path'], 'multi_groups': multi})
write_input(os.path.join(BASE, '台阶一_属性记忆', '1-3_属性集合枚举', 'input.jsonl'), lines)

# ============================================================
# 1-4 真伪确认: A桶元组 (肯定) + 用同域其他值构造否定
# ============================================================
# 同关系在全局的值池, 用于构造否定干扰
rel_value_pool = defaultdict(set)
for ent in entities:
    for r, v, b in ent['triples']:
        if b == 'A' and r != 'is_a' and r != '特性':
            rel_value_pool[r].add(v)

# 1-4 决策(D1): 不要确认样本, 否定样本采样 ~10%
# 先收集全部否定候选, 再全局采样
neg_candidates = []
for ent in entities:
    own_values = defaultdict(set)
    for r, v, b in ent['triples']:
        if b == 'A' and r != 'is_a' and r != '特性':
            own_values[r].add(v)
    for r, v, b in ent['triples']:
        if b == 'A' and r != 'is_a' and r != '特性':
            others = [ov for ov in rel_value_pool[r] if ov not in own_values[r]]
            if others:
                neg_candidates.append((ent, r, random.choice(others)))

neg_keep = max(1, int(len(neg_candidates) * 0.1))
sampled_neg = random.sample(neg_candidates, neg_keep)

lines = []
neg_by_ent = defaultdict(list)
for ent, r, v in sampled_neg:
    neg_by_ent[ent['entity']].append({'relation': r, 'value': v, 'truth': False})
for ent in entities:
    items = neg_by_ent.get(ent['entity'], [])
    if not items: continue
    lines.append({'entity': ent['entity'], 'tree_path': ent['tree_path'], 'items': items})
write_input(os.path.join(BASE, '台阶一_属性记忆', '1-4_真伪确认', 'input.jsonl'), lines)

# ============================================================
# 2-1 反向指代: A桶元组中 (R,O) 唯一且值适合做指代物
# ============================================================
ro_count = defaultdict(int)
for ent in entities:
    for r, v, b in ent['triples']:
        if b == 'A' and r != 'is_a':
            ro_count[(r, v)] += 1

import re
def is_referable(v):
    # 纯规格数字不适合做指代物
    if re.match(r'^[\d.]+(-[\d.]+)?\s*(mm|km|kW|kWh|L|克|英寸|元|秒|天|台|%|种|条|小时|级|X)', v):
        return False
    if len(v) > 25:
        return False
    return True

lines = []
for ent in entities:
    items = []
    for r, v, b in ent['triples']:
        if b == 'A' and r != 'is_a' and r != '特性' and ro_count[(r, v)] == 1 and is_referable(v):
            items.append({'relation': r, 'value': v})
    if not items: continue
    lines.append({'entity': ent['entity'], 'tree_path': ent['tree_path'], 'unique_triples': items})
write_input(os.path.join(BASE, '台阶二_知识应用', '2-1_反向指代', 'input.jsonl'), lines)

print('\n完成。各题型 input.jsonl 已生成。')
