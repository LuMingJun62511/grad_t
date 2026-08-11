"""
全量维基百科语料爬取
策略: 按系列爬取(省请求) + 旗舰单品补充
输出: 每个产品都有对应的自然语料
"""

import json, re, time, os, sys
from collections import defaultdict

if sys.platform == 'win32':
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')

WIKI_API = "https://zh.wikipedia.org/w/api.php"
HEADERS = {"User-Agent": "KnowledgeInjectionBot/1.0 (research; example@test.com)"}
DELAY = 3.0  # 秒，尊重API限流

PRODUCT_PATH = r"D:\新建文件夹\grad_t\product_knowledge\data_\华为产品属性.json"
OUT_DIR = r"D:\新建文件夹\grad_t\product_knowledge\data_\corpus_v4\\"

try:
    import requests
except ImportError:
    print("需要 requests: pip install requests")
    sys.exit(1)


def wiki_search(keyword, timeout=15):
    """搜索维基百科词条, 返回最佳匹配"""
    try:
        resp = requests.get(WIKI_API, params={
            "action": "query", "format": "json",
            "list": "search", "srsearch": keyword, "srlimit": 3,
        }, headers=HEADERS, timeout=timeout)
        if resp.status_code != 200:
            return None
        results = resp.json().get("query", {}).get("search", [])
        return results[0]["title"] if results else None
    except:
        return None


def wiki_extract(title, timeout=15):
    """获取词条全文"""
    try:
        resp = requests.get(WIKI_API, params={
            "action": "query", "format": "json",
            "titles": title, "prop": "extracts",
            "explaintext": 1, "exsectionformat": "plain",
        }, headers=HEADERS, timeout=timeout)
        if resp.status_code != 200:
            return None
        pages = resp.json().get("query", {}).get("pages", {})
        for pid, page in pages.items():
            text = page.get("extract", "")
            if text:
                return {
                    "title": page.get("title", title),
                    "pageid": page.get("pageid", pid),
                    "char_count": len(text),
                    "text": text,
                }
    except:
        pass
    return None


def chunk_text(text, max_len=500):
    """把长文本切成段落级chunk"""
    chunks = []
    for para in text.split("\n"):
        para = para.strip()
        if len(para) < 30:
            continue
        if len(para) <= max_len:
            chunks.append(para)
        else:
            for sent in re.split(r"[。；;]", para):
                sent = sent.strip()
                if sent and len(sent) >= 10:
                    chunks.append(sent + "。")
    return chunks


def main():
    os.makedirs(OUT_DIR, exist_ok=True)

    with open(PRODUCT_PATH, "r", encoding="utf-8") as f:
        products = json.load(f)

    # ---- 构建爬取目标 ----
    # 1. 系列级别 (每个(品类,系列)爬一次)
    # 2. 旗舰SPU补充 (Mate Pro/RS, Pura Ultra/Pro Max等)
    series_targets = {}  # key -> {category, series, keywords}
    spu_targets = []     # [(spu_name, keyword), ...]

    for p in products:
        cat, ser = p["category"], p["series"]
        skey = f"{cat}::{ser}"

        # 系列级搜索词
        if skey not in series_targets:
            kw = f"华为{ser}" if "华为" not in ser else ser
            series_targets[skey] = {"category": cat, "series": ser, "keyword": kw}

        # 旗舰单品补充: Pro, Pro Max, RS, Ultra, Ultimate, 非凡大师
        name = p["name"]
        is_flagship = any(tag in name for tag in [
            "Pro Max", "Pro+", "Pro", "RS", "Ultra", "Ultimate",
            "非凡大师", "Max", "Art", "Paper", "Lipstick"
        ])
        if is_flagship and len(spu_targets) < 50:
            spu_kw = f"华为{name}" if "华为" not in name else name
            spu_targets.append((name, spu_kw))

    print(f"爬取目标: {len(series_targets)} 个系列 + {len(spu_targets)} 个旗舰单品")
    print(f"预计耗时: ~{(len(series_targets)+len(spu_targets))*DELAY/60:.0f} 分钟\n")

    # ---- 爬取 ----
    crawled = {}  # keyword -> wiki_result

    # 先爬系列
    for i, (skey, info) in enumerate(series_targets.items()):
        kw = info["keyword"]
        if kw in crawled:
            continue

        print(f"[系列 {i+1}/{len(series_targets)}] {kw} ...", end=" ", flush=True)
        title = wiki_search(kw)
        if not title:
            print("未找到")
            crawled[kw] = None
        else:
            result = wiki_extract(title)
            if result:
                print(f"-> {title} ({result['char_count']}字)")
                result["_query"] = kw
                result["_category"] = info["category"]
                result["_series"] = info["series"]
                crawled[kw] = result
            else:
                print(f"-> {title} (提取失败)")
                crawled[kw] = None
        time.sleep(DELAY)

    # 再爬旗舰单品
    for i, (spu_name, kw) in enumerate(spu_targets):
        if kw in crawled:
            continue

        print(f"[单品 {i+1}/{len(spu_targets)}] {kw} ...", end=" ", flush=True)
        title = wiki_search(kw)
        if not title:
            print("未找到")
            crawled[kw] = None
        else:
            result = wiki_extract(title)
            if result:
                print(f"-> {title} ({result['char_count']}字)")
                result["_query"] = kw
                result["_spu"] = spu_name
                crawled[kw] = result
            else:
                print(f"-> {title} (提取失败)")
                crawled[kw] = None
        time.sleep(DELAY)

    # ---- 去重: 同一 pageid 只保留一份 ----
    by_pageid = {}
    for kw, result in crawled.items():
        if result and result.get("pageid"):
            pid = result["pageid"]
            if pid not in by_pageid or len(result["text"]) > len(by_pageid[pid]["text"]):
                by_pageid[pid] = {**result, "_keywords": [kw]}
        elif result:
            by_pageid[kw] = {**result, "_keywords": [kw]}

    # 合并同 pageid 的多个 keyword
    for pid, result in by_pageid.items():
        existing_kws = set()
        for kw, r in crawled.items():
            if r and r.get("pageid") == pid:
                existing_kws.add(kw)
        result["_keywords"] = list(existing_kws)

    unique_results = list(by_pageid.values())
    succeed = sum(1 for r in unique_results if r and r.get("text"))
    print(f"\n去重后: {len(unique_results)} 篇独立词条, {succeed} 篇有正文")

    # ---- 保存原始结果 ----
    raw_path = OUT_DIR + "wiki_raw.json"
    with open(raw_path, "w", encoding="utf-8") as f:
        json.dump(unique_results, f, ensure_ascii=False, indent=2)
    print(f"原始语料: {raw_path}")

    # ---- 语料 → 产品树映射 ----
    # 策略: 系列级文章分配给该系列下所有SPU
    #       单品文章只分配给对应SPU
    spu_corpus = defaultdict(list)  # spu_name -> [chunks]

    for result in unique_results:
        if not result or not result.get("text"):
            continue

        cat = result.get("_category", "")
        ser = result.get("_series", "")
        spu_name = result.get("_spu", "")
        chunks = chunk_text(result["text"])

        if spu_name:
            # 单品文章 → 只给该SPU
            for c in chunks:
                spu_corpus[spu_name].append({
                    "source": result["title"],
                    "chunk": c,
                })
        elif cat and ser:
            # 系列文章 → 给该系列下所有SPU
            series_spus = [p["name"] for p in products if p["category"] == cat and p["series"] == ser]
            for spu in series_spus:
                for c in chunks:
                    spu_corpus[spu].append({
                        "source": result["title"],
                        "chunk": c,
                    })

    # 统计覆盖率
    covered = sum(1 for p in products if spu_corpus.get(p["name"]))
    total_chunks = sum(len(v) for v in spu_corpus.values())
    print(f"语料覆盖: {covered}/{len(products)} 个产品 ({100*covered//len(products)}%)")
    print(f"总chunk数: {total_chunks}")

    # ---- 输出 ----
    # 1. 自然语料文本 (按产品分组)
    text_path = OUT_DIR + "corpus_by_product.txt"
    with open(text_path, "w", encoding="utf-8") as f:
        for p in products:
            name = p["name"]
            chunks = spu_corpus.get(name, [])
            if chunks:
                f.write(f"\n{'='*60}\n")
                f.write(f"## {name} [{p['category']} > {p['series']}]\n")
                f.write(f"{'='*60}\n\n")
                for c in chunks:
                    f.write(f"[来源: {c['source']}]\n")
                    f.write(c["chunk"] + "\n\n")
    print(f"产品语料文本: {text_path}")

    # 2. JSON映射
    map_json = {}
    for p in products:
        name = p["name"]
        chunks = spu_corpus.get(name, [])
        if chunks:
            map_json[name] = {
                "category": p["category"],
                "series": p["series"],
                "chunks": [{"source": c["source"], "text": c["chunk"]} for c in chunks],
            }

    map_path = OUT_DIR + "corpus_product_mapping.json"
    with open(map_path, "w", encoding="utf-8") as f:
        json.dump(map_json, f, ensure_ascii=False, indent=2)
    print(f"产品语料映射: {map_path}")

    # 3. 统计摘要
    summary = {
        "total_products": len(products),
        "covered_products": covered,
        "coverage_rate": f"{100*covered//len(products)}%",
        "wiki_articles": len(unique_results),
        "articles_with_text": succeed,
        "total_chunks": total_chunks,
        "avg_chunks_per_covered_product": f"{total_chunks//covered if covered else 0}",
    }
    summary_path = OUT_DIR + "crawl_summary.json"
    with open(summary_path, "w", encoding="utf-8") as f:
        json.dump(summary, f, ensure_ascii=False, indent=2)

    print(f"\n=== 爬取完成 ===")
    for k, v in summary.items():
        print(f"  {k}: {v}")


if __name__ == "__main__":
    main()
