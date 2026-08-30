"""
把各题型的旧 prompt.md (混合格式) 拆成 prompt.txt (纯正文) + README.md (说明)
"""
import os, re, sys

if sys.platform == 'win32':
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')

BASE = r"C:\Users\LuMin\Desktop\kg_workspace\出题"

for root, dirs, files in os.walk(BASE):
    if 'prompt.md' not in files:
        continue
    pmd = os.path.join(root, 'prompt.md')
    with open(pmd, 'r', encoding='utf-8') as f:
        md = f.read()

    # 提取 Prompt 正文
    m = re.search(r"## Prompt 正文\s*\n---\s*\n(.*?)\n---", md, re.DOTALL)
    if not m:
        print(f'跳过 (无正文标记): {root}')
        continue
    prompt_text = m.group(1).strip()

    # 其余部分 → README
    readme_body = md.replace(m.group(0), '')
    readme_body = re.sub(r'\n{3,}', '\n\n', readme_body).strip()

    with open(os.path.join(root, 'prompt.txt'), 'w', encoding='utf-8') as f:
        f.write(prompt_text + '\n')
    with open(os.path.join(root, 'README.md'), 'w', encoding='utf-8') as f:
        f.write(readme_body + '\n')
    os.remove(pmd)
    print(f'转换: {os.path.relpath(root, BASE)}')
