"""
Step 1: 建产品树 + 爬百度百科自然语料
======================================
产品树 = Company → Category → Series → SubSeries → SPU
自然语料 = 百度百科对应词条的正文文本

两套输出:
  1. product_tree.json — 完整的树结构
  2. crawled_corpus/ — 每个树节点对应的自然语料
"""

import json
import re
import time
import os
import sys
import hashlib
from collections import defaultdict

# Fix encoding for Windows
if sys.platform == 'win32':
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')

# ============================================================
# Part A: 建产品树
# ============================================================

INPUT_PATH = r"D:\新建文件夹\grad_t\product_knowledge\data_\华为产品属性.json"
OUT_DIR = r"D:\新建文件夹\grad_t\product_knowledge\data_\corpus_v4\\"


class TreeNode:
    def __init__(self, name, node_type, **attrs):
        self.name = name
        self.node_type = node_type  # Company, Category, Series, SubSeries, SPU
        self.attrs = attrs
        self.children = []

    def add_child(self, child):
        self.children.append(child)
        return child

    def to_dict(self):
        return {
            "name": self.name,
            "type": self.node_type,
            "attrs": self.attrs,
            "children": [c.to_dict() for c in self.children]
        }

    def find(self, name):
        if self.name == name:
            return self
        for c in self.children:
            r = c.find(name)
            if r: return r
        return None

    def path(self):
        """返回从根到当前节点的路径"""
        return [self.name]

    def all_nodes(self):
        """BFS 遍历所有节点"""
        nodes = [self]
        for c in self.children:
            nodes.extend(c.all_nodes())
        return nodes


def build_tree(products):
    company = products[0]["company"]
    root = TreeNode(company, "Company")

    # 按层级组织
    cat_nodes = {}
    ser_nodes = {}
    sub_nodes = {}

    for p in products:
        cat = p["category"]
        ser = p["series"]
        sub = p.get("sub_series")

        # Category
        if cat not in cat_nodes:
            cat_nodes[cat] = root.add_child(TreeNode(cat, "Category"))

        # Series (用 category+series 做 key, 因为不同 category 可能有同名 series)
        ser_key = f"{cat}::{ser}"
        if ser_key not in ser_nodes:
            ser_nodes[ser_key] = cat_nodes[cat].add_child(TreeNode(ser, "Series"))

        # SubSeries (只对手机品类有, 其他品类直接挂 SPU)
        if sub and sub != ser:
            sub_key = f"{ser_key}::{sub}"
            if sub_key not in sub_nodes:
                sub_nodes[sub_key] = ser_nodes[ser_key].add_child(TreeNode(sub, "SubSeries"))
            sub_nodes[sub_key].add_child(TreeNode(p["name"], "SPU",
                price=p.get("price", ""),
                talking_points=p.get("talking_points", []),
                positioning=p.get("positioning", []),
                status=p.get("status", ""),
                generation=p.get("generation", ""),
                aliases=p.get("alias", []),
            ))
        else:
            ser_nodes[ser_key].add_child(TreeNode(p["name"], "SPU",
                price=p.get("price", ""),
                talking_points=p.get("talking_points", []),
                positioning=p.get("positioning", []),
                status=p.get("status", ""),
                generation=p.get("generation", ""),
                aliases=p.get("alias", []),
            ))

    return root


def print_tree(node, indent=0):
    lines = []
    prefix = "  " * indent + ("├─ " if indent > 0 else "")
    extra = ""
    if node.node_type == "SPU":
        price = node.attrs.get("price", "")
        if price and "待" not in price:
            extra = f"  [{price}]"
    lines.append(f"{prefix}{node.node_type}: {node.name}{extra}")
    for c in node.children:
        lines.extend(print_tree(c, indent + 1))
    return lines


# ============================================================
# Part B: 维基百科 API 爬取
# ============================================================

try:
    import requests
    HAS_CRAWLER = True
except ImportError:
    print("[WARN] 缺少 requests, 将跳过爬取部分")
    HAS_CRAWLER = False

WIKI_API = "https://zh.wikipedia.org/w/api.php"

# 搜索词: 在中文维基上搜这些词条
CRAWL_TARGETS = [
    # 系列级 (维基上通常有系列词条)
    ("华为Mate系列", "Series", "手机"),
    ("华为Pura系列", "Series", "手机"),
    ("华为P系列", "Series", "手机"),  # Pura前身
    ("华为nova系列", "Series", "手机"),
    ("华为畅享系列", "Series", "手机"),
    ("华为Mate X系列", "Series", "手机"),  # 折叠屏
    # 平板
    ("华为MatePad", "SPU", "平板"),
    ("华为MatePad Pro", "SPU", "平板"),
    # 笔记本
    ("华为MateBook", "SPU", "笔记本"),
    ("华为MateBook X Pro", "SPU", "笔记本"),
    # 手表
    ("华为WATCH", "SPU", "智能手表"),
    ("华为WATCH GT", "SPU", "智能手表"),
    # 耳机
    ("华为FreeBuds", "SPU", "耳机"),
    ("华为FreeBuds Pro", "SPU", "耳机"),
    # 智慧屏
    ("华为智慧屏", "SPU", "智慧屏"),
    # 汽车
    ("鸿蒙智行", "Series", "智能汽车"),
    ("问界", "Series", "智能汽车"),
    ("AITO问界", "Series", "智能汽车"),
    # 芯片
    ("麒麟芯片", "SPU", "手机"),  # 麒麟(芯片)
    ("海思麒麟", "SPU", "手机"),
    # 系统
    ("HarmonyOS", "SPU", "手机"),  # 鸿蒙系统
    ("鸿蒙系统", "SPU", "手机"),
    # 公司
    ("华为", "Company", ""),
]


def crawl_wiki(keyword, timeout=15):
    """通过中文维基百科 API 获取词条内容"""
    if not HAS_CRAWLER:
        return None
    headers = {"User-Agent": "KnowledgeInjectionBot/1.0 (research; contact@example.com)"}
    try:
        search_params = {"action": "query", "format": "json", "list": "search", "srsearch": keyword, "srlimit": 3}
        resp = requests.get(WIKI_API, params=search_params, headers=headers, timeout=timeout)
        if resp.status_code != 200:
            return {"keyword": keyword, "status": resp.status_code, "error": f"HTTP {resp.status_code}"}
        results = resp.json().get("query", {}).get("search", [])
        if not results:
            return {"keyword": keyword, "status": 404, "error": "No results"}
        best_title = results[0]["title"]
        extract_params = {"action": "query", "format": "json", "titles": best_title, "prop": "extracts", "explaintext": 1}
        resp2 = requests.get(WIKI_API, params=extract_params, headers=headers, timeout=timeout)
        if resp2.status_code != 200:
            return {"keyword": keyword, "title": best_title, "status": resp2.status_code, "error": "Extract failed"}
        pages = resp2.json().get("query", {}).get("pages", {})
        for pid, page in pages.items():
            text = page.get("extract", "")
            return {"keyword": keyword, "title": best_title, "wiki_pageid": page.get("pageid", pid),
                    "status": 200, "char_count": len(text), "text": text}
    except requests.Timeout:
        return {"keyword": keyword, "status": 0, "error": "Timeout"}
    except Exception as e:
        return {"keyword": keyword, "status": 0, "error": str(e)}


def crawl_all_wiki(targets, delay=1.5):
    """批量爬取维基百科"""
    import random as _random
    results = []
    for i, (keyword, node_type, category) in enumerate(targets):
        print(f"  [{i+1}/{len(targets)}] 爬取: {keyword} ...", end=" ")
        result = crawl_wiki(keyword)
        if result:
            result["_tree_node_type"] = node_type
            result["_tree_category"] = category
            results.append(result)
            if "error" in result:
                print(f"失败: {result['error']}")
            else:
                print(f"成功 ({result.get('char_count', 0)} 字) -> {result.get('title', '')}")
        else:
            print("跳过")
        if i < len(targets) - 1:
            time.sleep(delay + _random.random())
    return results


def crawl_baike(keyword, timeout=15):
    """爬取百度百科词条的正文"""
    if not HAS_CRAWLER:
        return None

    url = BAIKE_SEARCH + keyword
    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/120.0.0.0 Safari/537.36"
        ),
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
        "Accept-Encoding": "gzip, deflate",
        "Connection": "keep-alive",
        "Referer": "https://www.baidu.com/",
    }

    try:
        session = requests.Session()
        resp = session.get(url, headers=headers, timeout=timeout, allow_redirects=True)
        resp.encoding = 'utf-8'

        # 百度百科可能返回验证页面
        if resp.status_code != 200:
            return {"keyword": keyword, "url": url, "status": resp.status_code, "error": f"HTTP {resp.status_code}"}
        if len(resp.text) < 500:
            return {"keyword": keyword, "url": url, "status": resp.status_code, "error": "Response too short (可能被拦截)"}

        soup = BeautifulSoup(resp.text, 'html.parser')

        # 提取正文
        paras = []
        for selector in [".para", ".lemma-content .para", "[class*=lemma] p", ".main-content p"]:
            for p_elem in soup.select(selector):
                text = p_elem.get_text(strip=True)
                if text and len(text) > 20:
                    paras.append(text)
            if len(paras) >= 3:
                break

        if len(paras) < 3:
            for p_elem in soup.find_all("p"):
                text = p_elem.get_text(strip=True)
                if text and len(text) > 20:
                    paras.append(text)

        title_elem = soup.select_one("h1")
        title = title_elem.get_text(strip=True) if title_elem else keyword

        full_text = "\n".join(paras)
        return {
            "keyword": keyword, "url": resp.url, "title": title,
            "status": resp.status_code, "char_count": len(full_text),
            "para_count": len(paras), "text": full_text,
        }

    except requests.Timeout:
        return {"keyword": keyword, "url": url, "status": 0, "error": "Timeout"}
    except Exception as e:
        return {"keyword": keyword, "url": url, "status": 0, "error": str(e)}


def crawl_all(targets, delay=2.0):
    """批量爬取, 带延时"""
    import random as _random
    results = []
    for i, (keyword, node_type, category) in enumerate(targets):
        print(f"  [{i+1}/{len(targets)}] 爬取: {keyword} ...", end=" ")
        result = crawl_baike(keyword)
        if result:
            result["_tree_node_type"] = node_type
            result["_tree_category"] = category
            results.append(result)
            if "error" in result:
                print(f"失败: {result['error']}")
            else:
                print(f"成功 ({result.get('char_count', 0)} 字)")
        else:
            print("跳过")

        if i < len(targets) - 1:
            time.sleep(delay + _random.random())

    return results


# ============================================================
# Part C: 语料 → 树节点映射
# ============================================================

def map_corpus_to_tree(tree, crawl_results):
    """
    把爬取的每篇语料映射到产品树上的节点。
    输出格式: {tree_path: [corpus_chunks]}
    """
    mapping = defaultdict(list)

    for result in crawl_results:
        if "error" in result or not result.get("text"):
            continue

        keyword = result["keyword"]
        node_type = result.get("_tree_node_type", "SPU")
        category = result.get("_tree_category", "")

        # 在树上查找匹配节点
        matched_node = tree.find(keyword)
        if not matched_node:
            # 尝试不带"华为"前缀匹配
            if keyword.startswith("华为"):
                matched_node = tree.find(keyword[2:])

        if matched_node:
            tree_path = "/".join([n.name for n in tree._path_to(matched_node)]) if hasattr(tree, '_path_to') else keyword
        else:
            tree_path = f"未匹配::{category}"

        # 分 chunk (按段落, 每个 chunk ≤ 500 字)
        text = result["text"]
        chunks = []
        for para in text.split("\n"):
            para = para.strip()
            if len(para) < 30:
                continue
            if len(para) > 500:
                # 按句号切分
                sentences = re.split(r"[。；;]", para)
                current = ""
                for s in sentences:
                    if len(current) + len(s) > 500 and current:
                        chunks.append(current.strip())
                        current = s
                    else:
                        current += s + "。"
                if current.strip():
                    chunks.append(current.strip())
            else:
                chunks.append(para)

        for chunk in chunks:
            mapping[tree_path].append({
                "keyword": keyword,
                "title": result.get("title", ""),
                "chunk": chunk,
            })

    return dict(mapping)


# Add _path_to helper
def add_path_method(tree):
    """给树节点添加 _path_to 方法"""
    def path_to(target_name):
        # BFS
        from collections import deque
        q = deque()
        q.append((tree, [tree.name]))
        while q:
            node, path = q.popleft()
            if node.name == target_name:
                return path
            for c in node.children:
                q.append((c, path + [c.name]))
        return [target_name]
    tree._path_to = path_to


# ============================================================
# Main
# ============================================================

def main():
    import random
    os.makedirs(OUT_DIR, exist_ok=True)

    # --- 建树 ---
    products = load_products(INPUT_PATH)
    tree = build_tree(products)
    add_path_method(tree)

    tree_dict = tree.to_dict()
    tree_path = OUT_DIR + "product_tree.json"
    with open(tree_path, "w", encoding="utf-8") as f:
        json.dump(tree_dict, f, ensure_ascii=False, indent=2)

    # 打印树
    print("产品树结构:")
    for line in print_tree(tree):
        print(line)

    print(f"\n树节点总数: {len(tree.all_nodes())}")
    print(f"树导出: {tree_path}")

    # --- 爬取 ---
    if HAS_CRAWLER:
        print(f"\n开始爬取百度百科 ({len(CRAWL_TARGETS)} 个目标)...")
        print("注意: 这是真实网络请求, 请确保网络通畅\n")

        crawl_results = crawl_all_wiki(CRAWL_TARGETS, delay=1.5)

        # 保存原始爬取结果
        crawl_path = OUT_DIR + "crawled_raw.json"
        with open(crawl_path, "w", encoding="utf-8") as f:
            json.dump(crawl_results, f, ensure_ascii=False, indent=2)

        succeed = sum(1 for r in crawl_results if "error" not in r and r.get("text"))
        print(f"\n爬取结果: {succeed}/{len(crawl_results)} 成功, 保存至 {crawl_path}")

        # --- 映射 ---
        mapping = map_corpus_to_tree(tree, crawl_results)
        map_path = OUT_DIR + "corpus_tree_mapping.json"
        with open(map_path, "w", encoding="utf-8") as f:
            json.dump(mapping, f, ensure_ascii=False, indent=2)

        total_chunks = sum(len(v) for v in mapping.values())
        print(f"语料→树映射: {len(mapping)} 个节点, {total_chunks} 个 chunk, 保存至 {map_path}")

        # 自然语料文本 (纯文本, 每个 chunk 带节点标注)
        text_path = OUT_DIR + "corpus_natural.txt"
        with open(text_path, "w", encoding="utf-8") as f:
            for tree_path, chunks in mapping.items():
                f.write(f"\n## {tree_path}\n\n")
                for c in chunks:
                    f.write(c["chunk"] + "\n\n")
        print(f"自然语料文本: {text_path}")
    else:
        print("\n[跳过] 缺少 requests/beautifulsoup4, 请运行: pip install requests beautifulsoup4")
        print("然后重新执行本脚本即可爬取。")

    print("\n完成！")


def load_products(path):
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


if __name__ == "__main__":
    main()
