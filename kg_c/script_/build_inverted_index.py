"""
2-2 的真值组织: 以宾语为根, 按 scope 分桶的倒排索引
结构: scope -> relation -> value -> [主语集合]
这是 2-2 出题与核验的唯一事实来源
"""
import json, os, sys
from collections import defaultdict

if sys.platform == 'win32':
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')

TDIR = r"C:\Users\LuMin\Desktop\kg_workspace\data_\corpus_v5\tuples"
OUT = r"C:\Users\LuMin\Desktop\kg_workspace\出题\台阶二_知识应用\2-2_多条件筛选\truth_inverted_index.json"

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

# 倒排索引: scope -> relation -> value -> set(entity)
inv = defaultdict(lambda: defaultdict(lambda: defaultdict(set)))
for e in entities:
    scope = scope_of(e['tree_path'])
    if not scope:
        continue
    for r, v, b in e['triples']:
        if b == 'A' and r != 'is_a' and v:
            inv[scope][r][v].add(e['entity'])

# 序列化
out = {}
for scope, rels in sorted(inv.items()):
    out[scope] = {}
    for r, vals in sorted(rels.items()):
        out[scope][r] = {v: sorted(es) for v, es in sorted(vals.items())}

with open(OUT, 'w', encoding='utf-8') as f:
    json.dump(out, f, ensure_ascii=False, indent=2)

# 统计: 可出题的 (r,v) 组合 (主语数 2~N-1)
total = 0
usable = 0
for scope, rels in out.items():
    scope_ents = set()
    for r, vals in rels.items():
        for v, es in vals.items():
            scope_ents.update(es)
    for r, vals in rels.items():
        for v, es in vals.items():
            total += 1
            if 2 <= len(es) <= len(scope_ents) - 1:
                usable += 1

print(f'倒排索引: {OUT}')
print(f'总 (r,v) 组合: {total}, 可出筛选题的 (2≤主语数<N): {usable}')
print()
print('=== 各 scope 的可出题组合示例 ===')
for scope, rels in out.items():
    scope_ents = set()
    for r, vals in rels.items():
        for v, es in vals.items():
            scope_ents.update(es)
    n_scope = len(scope_ents)
    shown = 0
    for r, vals in rels.items():
        for v, es in vals.items():
            if 2 <= len(es) <= n_scope - 1 and shown < 3:
                print(f'  [{scope}] {r}={v} → {es}')
                shown += 1
