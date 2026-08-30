"""
台阶二题型的输入生成: 2-2 多条件筛选 / 2-3 同代对比 / 2-4 代际对比 / 2-5 上级归纳
"""
import json, os, re, sys, random
from collections import defaultdict

if sys.platform == 'win32':
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')

random.seed(42)
TDIR = r"C:\Users\LuMin\Desktop\kg_workspace\data_\corpus_v5\tuples"
BASE = r"C:\Users\LuMin\Desktop\kg_workspace\出题"

entities = []
for f in sorted(os.listdir(TDIR)):
    with open(os.path.join(TDIR, f), 'r', encoding='utf-8') as fp:
        d = json.load(fp)
    for e in d['entities']:
        entities.append({
            'entity': e['entity'], 'level': e['level'], 'tree_path': d['tree_path'],
            'triples': [(t['relation'], t['value'], t.get('bucket', 'A')) for t in e['triples']],
        })

def write(path, lines):
    with open(path, 'w', encoding='utf-8') as f:
        for l in lines:
            f.write(json.dumps(l, ensure_ascii=False) + '\n')
    print(f'  {os.path.basename(os.path.dirname(path))}: {len(lines)} 个输入包')

# ============================================================
# 2-2 多条件筛选
# ============================================================
spu_ents = [e for e in entities if e['level'] in ('SPU', '代', '版本')]
by_scope = defaultdict(list)
for e in spu_ents:
    scope = e['tree_path'].split(' > ')[-1]
    by_scope[scope].append(e)

FILTERABLE = re.compile(r'芯片|屏幕|电池|快充|防水|定位|配色|智驾|动力|悬架|驱动|座位|售价|系统|特性|单次续航|整机续航|重量')
lines = []
for scope, ents in by_scope.items():
    if len(ents) < 2:
        continue
    r_values = defaultdict(set)
    for e in ents:
        for r, v, b in e['triples']:
            if b == 'A' and r != 'is_a' and FILTERABLE.search(r):
                r_values[r].add(v)
    good_rs = [r for r, vs in r_values.items() if 2 <= len(vs) <= len(ents) - 1]
    if not good_rs:
        continue
    r = random.choice(good_rs)
    v = random.choice(list(r_values[r]))
    matches = [e['entity'] for e in ents if any(rr == r and vv == v for rr, vv, _ in e['triples'])]
    if len(matches) < 1 or len(matches) >= len(ents):
        continue
    lines.append({
        'scope': scope,
        'tree_path': ents[0]['tree_path'],
        'candidate_entities': [
            {'name': e['entity'], 'attributes': [{'relation': rr, 'value': vv} for rr, vv, _ in e['triples'] if _ == 'A']}
            for e in ents
        ],
        'conditions': [{'relation': r, 'value': v}],
    })
write(os.path.join(BASE, '台阶二_知识应用', '2-2_多条件筛选', 'input.jsonl'), lines)

# ============================================================
# 2-3 同代横向对比
# ============================================================
lines = []
for scope, ents in by_scope.items():
    if len(ents) < 2:
        continue
    for i in range(len(ents)):
        for j in range(i + 1, len(ents)):
            a, b = ents[i], ents[j]
            a_attrs = {(r, v) for r, v, _ in a['triples'] if _ == 'A' and r != 'is_a'}
            b_attrs = {(r, v) for r, v, _ in b['triples'] if _ == 'A' and r != 'is_a'}
            if not a_attrs or not b_attrs:
                continue
            lines.append({
                'pair': [
                    {'name': a['entity'], 'attributes': [{'relation': r, 'value': v} for r, v in a_attrs]},
                    {'name': b['entity'], 'attributes': [{'relation': r, 'value': v} for r, v in b_attrs]},
                ],
                'tree_path': a['tree_path'],
            })
write(os.path.join(BASE, '台阶二_知识应用', '2-3_同代横向对比', 'input.jsonl'), lines)

# ============================================================
# 2-4 代际纵向对比
# ============================================================
gen_ents = [e for e in entities if e['level'] in ('代', '版本')]
by_series = defaultdict(list)
for e in gen_ents:
    series = ' > '.join(e['tree_path'].split(' > ')[:-1])
    by_series[series].append(e)

lines = []
for series, ents in by_series.items():
    if len(ents) < 2:
        continue
    def year_of(e):
        for r, v, _ in e['triples']:
            if r == '发布时间':
                m = re.search(r'20\d{2}', v)
                return int(m.group(0)) if m else 9999
        return 9999
    ents_sorted = sorted(ents, key=year_of)
    for old, new in zip(ents_sorted, ents_sorted[1:]):
        old_attrs = {(r, v) for r, v, _ in old['triples'] if _ == 'A' and r != 'is_a'}
        new_attrs = {(r, v) for r, v, _ in new['triples'] if _ == 'A' and r != 'is_a'}
        if not old_attrs or not new_attrs:
            continue
        lines.append({
            'old_gen': {'name': old['entity'], 'attributes': [{'relation': r, 'value': v} for r, v in old_attrs]},
            'new_gen': {'name': new['entity'], 'attributes': [{'relation': r, 'value': v} for r, v in new_attrs]},
            'tree_path': series,
        })
write(os.path.join(BASE, '台阶二_知识应用', '2-4_代际纵向对比', 'input.jsonl'), lines)

# ============================================================
# 2-5 上级归纳
# ============================================================
lines = []
for e in entities:
    if e['level'] not in ('代', '系列'):
        continue
    series_triples = [(r, v) for r, v, b in e['triples'] if b == 'A' and r != 'is_a']
    if not series_triples:
        continue
    members = [m['entity'] for m in entities if m['tree_path'].startswith(e['tree_path']) and m['entity'] != e['entity']]
    if not members:
        continue
    lines.append({
        'series_entity': e['entity'],
        'tree_path': e['tree_path'],
        'series_triples': [{'relation': r, 'value': v} for r, v in series_triples],
        'member_entities': members,
    })
write(os.path.join(BASE, '台阶二_知识应用', '2-5_上级归纳', 'input.jsonl'), lines)

print('完成')
