"""
跑 prompt: 读某题型的 input.jsonl + prompt.md → 逐条调 LLM → 写 output.jsonl
用法: python run_prompt.py <题型相对路径> [--limit N]
"""
import json, os, sys, time, re
import urllib.request

if sys.platform == 'win32':
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')

BASE = r"C:\Users\LuMin\Desktop\kg_workspace\出题"

# 用 Anthropic 兼容 API (本机环境变量)
API_URL = os.environ.get("ANTHROPIC_BASE_URL", "https://api.anthropic.com")
AUTH = os.environ.get("ANTHROPIC_AUTH_TOKEN", "")
MODEL = os.environ.get("ANTHROPIC_MODEL", os.environ.get("ANTHROPIC_DEFAULT_HAIKU_MODEL", "claude-haiku-4-5-20251001"))

def call_llm(prompt_text, max_retries=2):
    """Anthropic Messages API 单次调用"""
    payload = json.dumps({
        "model": MODEL,
        "max_tokens": 500,
        "temperature": 0.7,
        "thinking": {"type": "disabled"},
        "messages": [{"role": "user", "content": prompt_text}],
    }).encode("utf-8")
    req = urllib.request.Request(
        API_URL.rstrip("/") + "/v1/messages",
        data=payload,
        headers={
            "Content-Type": "application/json",
            "x-api-key": AUTH,
            "Authorization": f"Bearer {AUTH}",
            "anthropic-version": "2023-06-01",
        },
    )
    for attempt in range(max_retries + 1):
        try:
            with urllib.request.urlopen(req, timeout=60) as resp:
                data = json.loads(resp.read().decode("utf-8"))
            # 提取文本
            for block in data.get("content", []):
                if block.get("type") == "text":
                    return block["text"].strip()
            return ""
        except Exception as e:
            if attempt < max_retries:
                time.sleep(2 * (attempt + 1))
                continue
            return f"__ERROR__: {e}"

def main():
    if len(sys.argv) < 2:
        print("用法: python run_prompt.py <题型路径> [--limit N]")
        sys.exit(1)

    qtype = sys.argv[1]
    limit = None
    if "--limit" in sys.argv:
        limit = int(sys.argv[sys.argv.index("--limit") + 1])
    maxcalls = None
    if "--maxcalls" in sys.argv:
        maxcalls = int(sys.argv[sys.argv.index("--maxcalls") + 1])

    folder = os.path.join(BASE, qtype)
    prompt_path = os.path.join(folder, "prompt.txt")   # 纯 prompt 正文
    readme_path = os.path.join(folder, "README.md")    # 说明 + 模板池
    input_path = os.path.join(folder, "input.jsonl")
    output_path = os.path.join(folder, "output.jsonl")

    # 读纯 prompt
    if not os.path.exists(prompt_path):
        print(f"缺少 prompt.txt: {prompt_path}")
        sys.exit(1)
    with open(prompt_path, "r", encoding="utf-8") as f:
        template = f.read().strip()

    # 从 README 读模板池: 取 "## 模板池" 到下一个 "## " 之间的段落, 提取编号行
    pool = []
    if os.path.exists(readme_path):
        with open(readme_path, "r", encoding="utf-8") as f:
            md = f.read()
        m2 = re.search(r"## 模板池[^\n]*\n(.*?)(?=\n## |\Z)", md, re.DOTALL)
        if m2:
            for line in m2.group(1).splitlines():
                line = re.sub(r"^\d+\.\s*", "", line.strip())
                if line:
                    pool.append(line)
    print(f"模板池: {len(pool)} 个")

    # 读输入
    inputs = []
    with open(input_path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                inputs.append(json.loads(line))
    if limit:
        inputs = inputs[:limit]
    print(f"输入包: {len(inputs)} 个")

    # 展开成单条调用 (每个三元组一次调用)
    # calls 元素: (ent, rel, val, extra)  extra 是补充占位符 {T}/{VAL} 等
    calls = []
    for pkg in inputs:
        ent = pkg.get("entity", pkg.get("scope", pkg.get("series_entity", "包")))
        if "triples" in pkg:  # 1-1 / 1-2 格式
            for t in pkg["triples"]:
                calls.append((ent, t["relation"], t["value"], {}))
        elif "multi_groups" in pkg:  # 1-3 格式
            for g in pkg["multi_groups"]:
                calls.append((ent, g["relation"], "、".join(g["values"]), {}))
        elif "items" in pkg:  # 1-4 格式: 真假定为 {T}, 值不带标签
            for it in pkg["items"]:
                truth = "真" if it["truth"] else "假"
                calls.append((ent, it["relation"], it["value"], {"T": truth}))
        elif "unique_triples" in pkg:  # 2-1 格式
            for t in pkg["unique_triples"]:
                calls.append((ent, t["relation"], t["value"], {}))
        else:  # 2-2 ~ 2-5: 整包注入, 一次调用一个包
            pkg_json = json.dumps(pkg, ensure_ascii=False, indent=2)
            calls.append((pkg.get("entity", pkg.get("scope", pkg.get("series_entity", "包"))), "package", "", {"PKG": pkg_json}))

    print(f"展开为 {len(calls)} 次单条调用")
    if maxcalls:
        calls = calls[:maxcalls]
        print(f"限制为 {len(calls)} 次调用")

    # 逐条调用, 流式写盘 (边跑边落盘, 支持中断续跑)
    # 先读已完成的, 跳过
    done_keys = set()
    if os.path.exists(output_path):
        with open(output_path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line:
                    try:
                        r = json.loads(line)
                        done_keys.add((r.get("entity"), r.get("relation"), r.get("value")))
                    except:
                        pass

    ok = 0
    skipped = 0
    call_idx = 0
    with open(output_path, "a", encoding="utf-8") as f:
        for i, (ent, rel, val, extra) in enumerate(calls):
            if (ent, rel, val) in done_keys:
                skipped += 1
                continue
            # 伪随机轮换: 用调用序号取模 + 哈希打散, 保证模板均匀分布
            chosen = pool[hash((ent, rel, val)) % len(pool)] if pool else ""
            prompt_text = template.replace("{S}", ent).replace("{R}", rel).replace("{O}", val).replace("{TEMPLATE}", chosen)
            for k, v in extra.items():
                prompt_text = prompt_text.replace("{" + k + "}", v)
            call_idx += 1
            resp = call_llm(prompt_text)
            if resp.startswith("__ERROR__"):
                r = {"entity": ent, "relation": rel, "value": val, "raw": resp, "status": "error"}
                if "T" in extra:
                    r["truth"] = extra["T"]
                print(f"  [{i+1}/{len(calls)}] ERROR: {resp[:60]}", flush=True)
            else:
                r = {"entity": ent, "relation": rel, "value": val, "raw": resp, "status": "ok"}
                if "T" in extra:
                    r["truth"] = extra["T"]
                ok += 1
                print(f"  [{i+1}/{len(calls)}] {ent} | {rel} → {resp[:50]}", flush=True)
            f.write(json.dumps(r, ensure_ascii=False) + "\n")
            f.flush()
            time.sleep(0.3)

    print(f"\n完成: 新产出 {ok} 条, 跳过 {skipped} 条")
    print(f"输出: {output_path}")

if __name__ == "__main__":
    main()
