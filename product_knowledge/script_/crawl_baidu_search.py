"""
百度搜索语料爬虫 — 适配 corpus_v4
特点: 礼貌访问(长延时), 退避重试, 无并发, 先试水再全量
"""
import json, re, time, os, sys, hashlib
from collections import defaultdict
from urllib.parse import quote

if sys.platform == 'win32':
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')

try:
    import requests
    from bs4 import BeautifulSoup
except ImportError:
    print("需要: pip install requests beautifulsoup4")
    sys.exit(1)

# ============================================================
# 配置
# ============================================================
HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/126.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "zh-CN,zh;q=0.9",
}

PRODUCT_PATH = r"D:\新建文件夹\grad_t\product_knowledge\data_\华为产品属性.json"
OUT_DIR = r"D:\新建文件夹\grad_t\product_knowledge\data_\corpus_v4\\"
ARTICLES_DIR = OUT_DIR + "articles\\"

BASE_DELAY = 5          # 基础延时(秒)
MAX_DELAY = 120          # 最大退避延时(秒)
REQUEST_TIMEOUT = 20     # 请求超时

# 试水产品 (为空则全量)
TRIAL_PRODUCTS = []

# ============================================================
# 搜索 + 解析
# ============================================================

def search_baidu(keyword, max_retries=3):
    """搜索百度, 返回结果列表。带退避重试。"""
    params = {"wd": keyword, "pn": 0, "rn": 10}
    url = "https://www.baidu.com/s?" + "&".join(f"{k}={quote(str(v))}" for k, v in params.items())

    delay = BASE_DELAY
    for attempt in range(max_retries):
        try:
            resp = requests.get(url, headers=HEADERS, timeout=REQUEST_TIMEOUT)
            resp.encoding = "utf-8"

            if resp.status_code == 200:
                break  # 200 就直接用, 不检查长度
            elif resp.status_code in (403, 429):
                print(f"      被限(HTTP {resp.status_code}), 等待 {delay}s...")
                time.sleep(delay)
                delay = min(delay * 2, MAX_DELAY)
            else:
                print(f"      状态 {resp.status_code}, 等待 {delay}s...")
                time.sleep(delay)
                delay = min(delay * 2, MAX_DELAY)
        except requests.RequestException as e:
            print(f"      网络错误: {e}, 等待 {delay}s...")
            time.sleep(delay)
            delay = min(delay * 2, MAX_DELAY)
    else:
        return []

    soup = BeautifulSoup(resp.text, "html.parser")
    results = []

    # 百度搜索结果容器
    containers = soup.select("div.result, div.c-container, div.result-op")
    if not containers:
        containers = soup.select("div[tpl], div[srcid]")

    for div in containers:
        # 标题
        title_el = div.select_one("h3 a, h3.t a, a[class*='title']")
        title = title_el.get_text(strip=True) if title_el else ""

        # 摘要
        snippet_el = div.select_one(
            "span.content-right_8Zs40, div.c-abstract, span.c-abstract, "
            "span.newTimeFactor_before_abs, div.c-span-last, span.c-gap-right"
        )
        snippet = snippet_el.get_text(strip=True) if snippet_el else ""

        if not snippet:
            texts = [t.strip() for t in div.get_text("\n", strip=True).split("\n") if len(t.strip()) > 10]
            snippet = texts[1] if len(texts) >= 2 else ""

        if not title or len(title) < 3:
            continue

        results.append({"title": title, "snippet": snippet, "keyword": keyword})

    return results


def is_good_result(r):
    """过滤广告/低质量结果"""
    title = r.get("title", "")
    snippet = r.get("snippet", "")
    combined = title + snippet

    # 广告
    ad_words = ["淘宝", "天猫", "京东", "苏宁", "拼多多", "购物", "价格", "报价",
                 "促销", "热卖", "好物", "精选笔记", "视频大全", "高清在线"]
    if any(w in title for w in ad_words):
        return False

    # 内容太短
    if len(snippet) < 15:
        return False

    # 明显的百度导航页
    if "百度为您找到" in title:
        return False

    return True


# ============================================================
# 主流程
# ============================================================

def build_keywords(product_name, product_info):
    """为一个产品构造搜索关键词"""
    name = product_name
    series = product_info.get("series", "")
    cat = product_info.get("category", "")

    keywords = [f"华为 {name}", f"华为{name}"]
    # 对手机/平板/手表等品类加评测/参数关键词
    if cat in ("手机", "平板", "笔记本", "智能手表", "耳机"):
        keywords.append(f"华为{name} 评测")
        keywords.append(f"华为{name} 参数配置")
        keywords.append(f"华为{name} 发布时间")
    if cat == "智能汽车":
        keywords.append(f"{name} 车型")
        keywords.append(f"{name} 价格")

    return keywords


def crawl_product(name, product_info, dry_run=False):
    """爬取一个产品的语料, 返回 article 对象"""
    keywords = build_keywords(name, product_info)
    all_results = []

    for kw in keywords:
        if dry_run:
            print(f"    [试水] 关键词: {kw}")
        else:
            print(f"    搜索: {kw}")

        results = search_baidu(kw)
        good = [r for r in results if is_good_result(r)]

        if dry_run:
            print(f"      获得 {len(good)} 条有效 (共 {len(results)} 条)")
            for r in good[:3]:
                print(f"      · {r['title'][:60]}")
                print(f"        {r['snippet'][:100]}")
        else:
            print(f"      {len(good)} 条有效")

        all_results.extend(good)

        # 每个关键词之间延时
        if not dry_run:
            time.sleep(BASE_DELAY + 1)

    if dry_run:
        # 试水也存盘, 便于检查
        unique = []
        seen = set()
        for r in all_results:
            key = r["title"][:30].strip().lower()
            if key not in seen:
                seen.add(key)
                unique.append(r)
        dry_path = os.path.join(ARTICLES_DIR, f"_trial_{name.replace(' ', '_')[:30]}.json")
        with open(dry_path, "w", encoding="utf-8") as f:
            json.dump({"product": name, "results": unique}, f, ensure_ascii=False, indent=2)
        print(f"    → 试水结果已存: {dry_path} ({len(unique)} 条)")
        return None

    # 去重
    seen = set()
    unique = []
    for r in all_results:
        key = r["title"][:30].strip().lower()
        if key not in seen:
            seen.add(key)
            unique.append(r)

    # 构造 article
    full_text = "\n".join([f"{r['title']}\n{r['snippet']}" for r in unique])
    chunks = []
    for i, r in enumerate(unique):
        chunk_text = f"{r['title']}。{r['snippet']}"
        if len(chunk_text) >= 30:
            chunks.append({"idx": i, "text": chunk_text})

    safe_name = re.sub(r'[/\\:*?"<>|]', '_', name).replace(' ', '_')[:40]
    art_id = f"baidu_{hashlib.md5(name.encode()).hexdigest()[:8]}_{safe_name}"

    article = {
        "id": art_id,
        "title": f"百度搜索: {name}",
        "source_type": "baidu_search",
        "crawl_date": time.strftime("%Y-%m-%d"),
        "char_count": len(full_text),
        "keywords_searched": keywords,
        "chunks": chunks,
    }

    return article


def update_index_and_manifest(product_name, article, product_info):
    """更新 corpus_index.json 和 article_manifest.json"""
    index_path = OUT_DIR + "corpus_index.json"
    manifest_path = OUT_DIR + "article_manifest.json"

    # 读现有
    with open(index_path, "r", encoding="utf-8") as f:
        index = json.load(f)
    with open(manifest_path, "r", encoding="utf-8") as f:
        manifest = json.load(f)

    # 更新 index
    cat = product_info.get("category", "")
    ser = product_info.get("series", "")
    sub = product_info.get("sub_series", "")

    if product_name not in index:
        tree_path = f"华为 > {cat} > {ser}"
        if sub and sub != ser:
            tree_path += f" > {sub}"
        index[product_name] = {
            "tree_path": tree_path,
            "category": cat,
            "series": ser,
            "articles": [],
            "chunk_count": 0,
        }

    # 去重: 如果已有同 source 的引用, 先删
    index[product_name]["articles"] = [
        a for a in index[product_name]["articles"]
        if a.get("id") != article["id"]
    ]
    index[product_name]["articles"].append({
        "id": article["id"],
        "source": article["title"],
        "type": "baidu_search",
    })
    index[product_name]["chunk_count"] = sum(
        len(article["chunks"])
        for a in index[product_name]["articles"]
        for _ in [1]
    )

    # 更新 manifest
    manifest = [m for m in manifest if m["id"] != article["id"]]
    manifest.append({
        "id": article["id"],
        "title": article["title"],
        "category": cat,
        "series": ser,
        "chunk_count": len(article["chunks"]),
        "char_count": article["char_count"],
    })

    # 写回
    with open(index_path, "w", encoding="utf-8") as f:
        json.dump(index, f, ensure_ascii=False, indent=2)
    with open(manifest_path, "w", encoding="utf-8") as f:
        json.dump(manifest, f, ensure_ascii=False, indent=2)


def main():
    os.makedirs(ARTICLES_DIR, exist_ok=True)

    # 加载产品树
    with open(PRODUCT_PATH, "r", encoding="utf-8") as f:
        products = json.load(f)

    # 构建名称→信息映射
    product_db = {p["name"]: p for p in products}

    # ================================================================
    # 阶段1: 试水
    # ================================================================
    print("=" * 60)
    print("阶段1: 试水 (只搜不存, 检查质量)")
    print("=" * 60)

    for name in TRIAL_PRODUCTS:
        if name not in product_db:
            print(f"\n  [跳过] 产品 '{name}' 不在产品树中")
            continue
        info = product_db[name]
        print(f"\n--- {name} [{info['category']} > {info['series']}] ---")
        crawl_product(name, info, dry_run=True)

    print(f"\n{'=' * 60}")
    print("试水完成。请检查上面的语料质量。")
    print("确认后, 修改脚本中 TRIAL_PRODUCTS = [] 并将 FULL_RUN = True 来全量运行。")
    print(f"{'=' * 60}")

    # ================================================================
    # 阶段2: 全量 (需手动开启)
    # ================================================================
    FULL_RUN = True
    if FULL_RUN:
        print("\n开始全量爬取 (跳过已爬产品)...")
        total = len(products)
        skipped = 0
        for i, p in enumerate(products):
            name = p["name"]
            safe_name = re.sub(r'[/\\:*?"<>|]', '_', name).replace(' ', '_')[:40]
            art_id = f"baidu_{hashlib.md5(name.encode()).hexdigest()[:8]}_{safe_name}"
            # 检查是否已爬过
            art_path = ARTICLES_DIR + art_id + ".json"
            if os.path.exists(art_path):
                skipped += 1
                continue
            print(f"\n[{i+1}/{total}] {name} ...")
            article = crawl_product(name, p)
            if article:
                with open(art_path, "w", encoding="utf-8") as f:
                    json.dump(article, f, ensure_ascii=False, indent=2)
                update_index_and_manifest(name, article, p)
                print(f"    → 保存: {art_path} ({article['char_count']}字, {len(article['chunks'])} chunks)")
            time.sleep(BASE_DELAY + 2)

        print(f"\n完成! 跳过 {skipped} 个已爬产品")

        # 最终统计
        with open(OUT_DIR + "corpus_index.json", "r", encoding="utf-8") as f:
            index = json.load(f)
        covered = sum(1 for v in index.values() if v["articles"])
        total_chunks = sum(v["chunk_count"] for v in index.values())
        print(f"\n完成! 覆盖 {covered}/{total} 产品, 总计 ~{total_chunks} chunks")
    else:
        print("\n[全量运行未开启] 设置 FULL_RUN = True 并重新运行此脚本。")


if __name__ == "__main__":
    main()
