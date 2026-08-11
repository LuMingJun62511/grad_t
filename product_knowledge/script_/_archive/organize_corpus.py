"""
语料组织结构梳理
从现有维基爬取结果中:
  1. 过滤错误匹配
  2. 拆成独立的 article 文件
  3. 生成产品→语料的索引
"""
import json, re, os, sys
from collections import defaultdict

if sys.platform == 'win32':
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')

PRODUCT_PATH = r"D:\新建文件夹\grad_t\product_knowledge\data_\华为产品属性.json"
WIKI_RAW = r"D:\新建文件夹\grad_t\product_knowledge\data_\corpus_v4\wiki_raw.json"
OUT_DIR = r"D:\新建文件夹\grad_t\product_knowledge\data_\corpus_v4\\"
ARTICLES_DIR = OUT_DIR + "articles\\"

os.makedirs(ARTICLES_DIR, exist_ok=True)

# ============================================================
# 1. 加载
# ============================================================
with open(PRODUCT_PATH, "r", encoding="utf-8") as f:
    products = json.load(f)
with open(WIKI_RAW, "r", encoding="utf-8") as f:
    articles = json.load(f)

# ============================================================
# 2. 过滤错误匹配
# ============================================================
# 黑名单: 明确不相关的词条
REJECT_TITLES = {
    "荣耀终端", "舒马赫", "Android 10", "高通元件列表", "海思半导体",
}
# 白名单: product category → 该品类相关的维基词条的关键词
CATEGORY_KEYWORDS = {
    "手机":     ["手机", "Mate", "Pura", "Nova", "华为", "折叠", "麒麟", "畅享", "P系列", "P60"],
    "平板":     ["平板", "MatePad", "Pad", "华为", "鸿蒙"],
    "笔记本":   ["笔记本", "MateBook", "Book", "华为", "轻薄本"],
    "智能手表": ["手表", "WATCH", "穿戴", "华为", "GT", "手环"],
    "耳机":     ["耳机", "FreeBuds", "FreeClip", "音频", "降噪"],
    "音箱":     ["音箱", "Sound", "帝瓦雷", "音频"],
    "智慧屏":   ["智慧屏", "Vision", "电视", "MiniLED", "华为"],
    "智能汽车": ["问界", "智界", "享界", "尊界", "鸿蒙智行", "汽车", "AITO"],
    "智能眼镜": ["眼镜", "AR", "AI"],
    "显示器":   ["显示器", "MateView", "电竞"],
}

def validate_article(article, target_category, target_series, product_db=None):
    """检查维基词条是否与目标品类/系列相关"""
    title = article.get("title", "")
    text = article.get("text", "")[:500]
    combined = title + " " + text
    spu_name = article.get("_spu", "")

    # 黑名单
    if title in REJECT_TITLES:
        return False, f"黑名单: {title}"
    # 排除完全无关的词条
    if any(kw in title for kw in ["Android", "舒马赫", "高通", "荣耀终端", "海思"]):
        if target_category not in ("手机", "平板") or spu_name:
            pass  # 对手机平板类别, 海思/荣耀可能相关
        else:
            return False, f"标题可疑: {title}"

    # 单品搜索: 从产品库查真正的品类
    actual_category = target_category
    if spu_name and product_db:
        prod = product_db.get(spu_name)
        if prod:
            actual_category = prod["category"]

    # 品类关键词匹配
    keywords = CATEGORY_KEYWORDS.get(actual_category, [actual_category])
    matched = [kw for kw in keywords if kw in combined]

    # 单品匹配放松条件: title中包含sub_series名就算通过
    if spu_name and not matched:
        # 检查title是否和产品名有交集
        spu_short = spu_name.replace("华为", "").strip()
        title_short = title.replace("华为", "").strip()
        if spu_short[:6] in title_short or title_short[:6] in spu_short:
            return True, f"单品标题匹配: {spu_short} ↔ {title_short}"
        return False, f"单品不匹配: {spu_short} vs {title_short}"

    if not matched and not spu_name:
        return False, f"关键词不匹配, 品类={actual_category}"

    return True, f"命中: {matched[:3]}"


# ============================================================
# 3. 切 chunk → 写 article 文件
# ============================================================
def chunk_text(text, max_len=500):
    chunks = []
    for para in text.split("\n"):
        para = para.strip()
        if len(para) < 30: continue
        if len(para) <= max_len:
            chunks.append(para)
        else:
            for sent in re.split(r"[。；;]", para):
                sent = sent.strip()
                if sent and len(sent) >= 15:
                    chunks.append(sent + "。")
    return chunks


article_files = {}   # article_id -> file_path
valid_articles = []  # 通过验证的 article 元信息
rejected = []        # 被拒绝的

# 构建产品名→产品信息 查找表
product_db = {p["name"]: p for p in products}

for i, a in enumerate(articles):
    if not a or not a.get("text"): continue

    title = a.get("title", "unknown")
    cat = a.get("_category", "") or a.get("_query", "")
    ser = a.get("_series", "") or ""

    # 验证
    ok, reason = validate_article(a, cat, ser, product_db)
    if not ok:
        rejected.append({"title": title, "query": a.get("_query",""), "category": cat, "reason": reason})
        continue

    # 对单品文章, 从产品库补全category和series
    spu_name = a.get("_spu", "")
    if spu_name and spu_name in product_db:
        cat = product_db[spu_name]["category"]
        ser = product_db[spu_name]["series"]

    # 生成 article id
    source_type = "wiki"
    safe_name = re.sub(r"[^\w\u4e00-\u9fff\-]", "_", title)[:60]
    art_id = f"{source_type}_{i+1:03d}_{safe_name}"

    # 切分 chunk
    chunks = chunk_text(a["text"])

    # 写 article 文件
    art_obj = {
        "id": art_id,
        "title": title,
        "pageid": a.get("pageid", ""),
        "source_type": source_type,
        "crawl_date": "2026-08-10",
        "char_count": a.get("char_count", 0),
        "chunks": [{"idx": j, "text": c} for j, c in enumerate(chunks)],
    }
    art_path = ARTICLES_DIR + art_id + ".json"
    with open(art_path, "w", encoding="utf-8") as f:
        json.dump(art_obj, f, ensure_ascii=False, indent=2)

    article_files[art_id] = art_path
    valid_articles.append({
        "id": art_id,
        "title": title,
        "category": cat,
        "series": ser,
        "chunk_count": len(chunks),
        "char_count": a.get("char_count", 0),
        "keywords": a.get("_keywords", []),
    })


# ============================================================
# 4. 构建产品 → article 索引
# ============================================================
corpus_index = {}

for p in products:
    name = p["name"]
    cat = p["category"]
    ser = p["series"]
    sub = p.get("sub_series", "")

    # 构建树路径
    tree_path = f"华为 > {cat} > {ser}"
    if sub and sub != ser:
        tree_path += f" > {sub}"

    # 查找属于该产品的语料
    # 逻辑: 系列级文章 → 分配给同系列所有产品
    #       单品级文章 → 只分配给该 SPU
    linked = []

    for art in valid_articles:
        # 系列匹配
        if art["category"] == cat and art["series"] == ser:
            linked.append({"id": art["id"], "source": art["title"], "type": "wiki_series"})
        # 单品匹配 (title或keywords中包含产品名)
        elif name in art["title"] or name in str(art.get("keywords", [])):
            linked.append({"id": art["id"], "source": art["title"], "type": "wiki_spu"})

    corpus_index[name] = {
        "tree_path": tree_path,
        "category": cat,
        "series": ser,
        "articles": linked,
        "chunk_count": sum(
            art["chunk_count"] for art in valid_articles
            if any(l["id"] == art["id"] for l in linked)
        ),
    }

# ============================================================
# 5. 写输出
# ============================================================
# 索引
index_path = OUT_DIR + "corpus_index.json"
with open(index_path, "w", encoding="utf-8") as f:
    json.dump(corpus_index, f, ensure_ascii=False, indent=2)

# 语料清单
manifest_path = OUT_DIR + "article_manifest.json"
with open(manifest_path, "w", encoding="utf-8") as f:
    json.dump(valid_articles, f, ensure_ascii=False, indent=2)

# 拒绝记录
reject_path = OUT_DIR + "rejected_articles.json"
with open(reject_path, "w", encoding="utf-8") as f:
    json.dump(rejected, f, ensure_ascii=False, indent=2)

# 人类可读文本
txt_path = OUT_DIR + "corpus_by_product.txt"
with open(txt_path, "w", encoding="utf-8") as f:
    for p in products:
        info = corpus_index.get(p["name"], {})
        if not info.get("articles"):
            continue
        f.write(f"\n{'='*60}\n")
        f.write(f"## {p['name']}  [{info['tree_path']}]\n")
        f.write(f"{'='*60}\n\n")

        for link in info["articles"]:
            art_id = link["id"]
            art_path = ARTICLES_DIR + art_id + ".json"
            if os.path.exists(art_path):
                with open(art_path, "r", encoding="utf-8") as af:
                    art_obj = json.load(af)
                f.write(f"[来源: {link['source']}] ({link['type']})\n\n")
                for c in art_obj["chunks"]:
                    f.write(c["text"] + "\n\n")

# ============================================================
# 6. 统计
# ============================================================
covered = sum(1 for v in corpus_index.values() if v["articles"])
total_chunks = sum(info["chunk_count"] for info in corpus_index.values())
print(f"产品总数: {len(products)}")
print(f"维基词条: {len(articles)} → 验证通过 {len(valid_articles)} 篇, 拒绝 {len(rejected)} 篇")
print(f"产品覆盖: {covered}/{len(products)} ({100*covered//len(products)}%)")
print(f"总 chunk: {total_chunks}")
print(f"\n输出:")
print(f"  语料索引:     {index_path}")
print(f"  语料清单:     {manifest_path}")
print(f"  Article文件:  {ARTICLES_DIR} ({len(article_files)} 个)")
print(f"  拒绝记录:     {reject_path}")
print(f"  可读文本:     {txt_path}")

if rejected:
    print(f"\n被拒绝的词条:")
    for r in rejected[:15]:
        print(f"  ✗ [{r['category']}] {r['title']} — {r['reason']}")

# 展示索引结构
print(f"\n{'='*60}")
print("corpus_index.json 结构示例:")
for name in ["Mate 80", "MatePad Pro 13.2 2025", "问界 M9", "WATCH GT 7 Pro 46mm"]:
    info = corpus_index.get(name, {})
    if info:
        arts = [a["source"] for a in info["articles"]]
        print(f"  {name}")
        print(f"    tree_path: {info['tree_path']}")
        print(f"    articles: {arts}")
        print(f"    chunks: {info['chunk_count']}")
        print()
