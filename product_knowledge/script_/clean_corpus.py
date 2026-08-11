"""
清洗百度语料: 去广告, 去空文, 去混淆, 去裸URL, 重建干净索引
"""
import json, os, re, sys
from collections import defaultdict

if sys.platform == 'win32':
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')

ARTS_DIR = r"D:\新建文件夹\grad_t\product_knowledge\data_\corpus_v4\articles"
INDEX_PATH = r"D:\新建文件夹\grad_t\product_knowledge\data_\corpus_v4\corpus_index.json"
MANIFEST_PATH = r"D:\新建文件夹\grad_t\product_knowledge\data_\corpus_v4\article_manifest.json"

# 广告/无关关键词
AD_PATTERNS = [
    r'(?i)淘宝|天猫|京东|苏宁|拼多多|热卖|促销|包邮|限时|抢购|点击购买|优惠|打折|大牌集结',
    r'手机壳|保护套|贴膜|钢化膜|充电器|数据线|手机支架|自拍杆|耳机套',
    r'SurfacePro|微软平板|iPad|苹果平板|联想平板|小米平板',
    r'更多新闻|构建万物互联|星河\d+系列.*路由器|红点产品设计奖',
]
# 裸URL & 无意义内容
JUNK_PATTERNS = [
    r'^(https?://|view\.inews\.|www\.)[^\s]*$',
    r'^[\s]*$',
    r'^\d+_\d+_\d+.*仅代表.*观点',
]

def is_junk_chunk(text):
    for pat in AD_PATTERNS:
        if re.search(pat, text):
            return "ad"
    for pat in JUNK_PATTERNS:
        if re.search(pat, text[:50]):
            return "junk"
    # 太短
    if len(text) < 25:
        return "short"
    return None


def main():
    files = [f for f in os.listdir(ARTS_DIR) if f.startswith('baidu_')]
    print(f"原始文件: {len(files)} 个")

    total_before = 0
    total_after = 0
    removed_empty = []
    stats = defaultdict(lambda: {"before": 0, "after": 0, "removed_ad": 0, "removed_junk": 0})

    for f in sorted(files):
        path = os.path.join(ARTS_DIR, f)
        with open(path, "r", encoding="utf-8") as fp:
            a = json.load(fp)

        name = a["title"].replace("百度搜索: ", "")
        cat = a.get("_category", "")
        old_chunks = a.get("chunks", [])
        total_before += len(old_chunks)

        # 过滤
        new_chunks = []
        removed_ad = 0
        removed_junk = 0
        for c in old_chunks:
            reason = is_junk_chunk(c["text"])
            if reason == "ad":
                removed_ad += 1
            elif reason in ("junk", "short"):
                removed_junk += 1
            else:
                new_chunks.append({"idx": len(new_chunks), "text": c["text"]})

        total_after += len(new_chunks)

        if len(new_chunks) == 0 and len(old_chunks) > 0:
            removed_empty.append(f"{name}: {len(old_chunks)}个chunk全被过滤")
        elif len(old_chunks) == 0:
            removed_empty.append(f"{name}: 原本就空")

        if len(new_chunks) == 0:
            # 删除空文章
            os.remove(path)
            continue

        # 更新chunks
        a["chunks"] = new_chunks
        a["char_count"] = sum(len(c["text"]) for c in new_chunks)
        with open(path, "w", encoding="utf-8") as fp:
            json.dump(a, fp, ensure_ascii=False, indent=2)

        stats[name] = {"before": len(old_chunks), "after": len(new_chunks),
                       "removed_ad": removed_ad, "removed_junk": removed_junk}

    # 重建索引
    remaining = [f for f in os.listdir(ARTS_DIR) if f.startswith("baidu_")]
    new_index = {}
    new_manifest = []

    for f in remaining:
        with open(os.path.join(ARTS_DIR, f), "r", encoding="utf-8") as fp:
            a = json.load(fp)
        name = a["title"].replace("百度搜索: ", "")
        if name not in new_index:
            new_index[name] = {
                "articles": [], "chunk_count": 0,
            }
        new_index[name]["articles"].append({
            "id": a["id"], "source": a["title"], "type": "baidu_search",
        })
        new_index[name]["chunk_count"] += len(a["chunks"])
        new_manifest.append({
            "id": a["id"], "title": a["title"],
            "chunk_count": len(a["chunks"]), "char_count": a["char_count"],
        })

    with open(INDEX_PATH, "w", encoding="utf-8") as f:
        json.dump(new_index, f, ensure_ascii=False, indent=2)
    with open(MANIFEST_PATH, "w", encoding="utf-8") as f:
        json.dump(new_manifest, f, ensure_ascii=False, indent=2)

    # 报告
    print(f"\n清洗完成:")
    print(f"  原始 chunks: {total_before}")
    print(f"  清洗后:      {total_after}")
    print(f"  删除空文件:  {len(removed_empty)} 个")
    print(f"  保留文件:    {len(remaining)} 个")

    if removed_empty:
        print(f"\n删除的空文章:")
        for s in removed_empty[:15]:
            print(f"  - {s}")
        if len(removed_empty) > 15:
            print(f"  ... 还有 {len(removed_empty)-15} 个")

    # 按品类统计
    print(f"\n按品类统计:")
    prod_db = {}
    with open(r"D:\新建文件夹\grad_t\product_knowledge\data_\华为产品属性.json", "r", encoding="utf-8") as f:
        products = json.load(f)
    for p in products:
        prod_db[p["name"]] = p

    cat_stats = defaultdict(lambda: {"count": 0, "chunks": 0, "chars": 0})
    for f in remaining:
        with open(os.path.join(ARTS_DIR, f), "r", encoding="utf-8") as fp:
            a = json.load(fp)
        name = a["title"].replace("百度搜索: ", "")
        cat = prod_db.get(name, {}).get("category", "未知")
        cat_stats[cat]["count"] += 1
        cat_stats[cat]["chunks"] += len(a["chunks"])
        cat_stats[cat]["chars"] += a["char_count"]

    for cat in sorted(cat_stats.keys()):
        s = cat_stats[cat]
        print(f"  [{cat}] {s['count']}个产品, {s['chunks']} chunks, {s['chars']:,}字")

    print(f"\n新索引: {INDEX_PATH}")
    print(f"新清单: {MANIFEST_PATH}")


if __name__ == "__main__":
    main()
