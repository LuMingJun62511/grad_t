#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
generate_sarcasm_data_v2.py — 改进版反讽数据集生成脚本

v2 改进:
  1. 分批增量落库 —— 每批生成完立即追加写入 JSONL，不堆积内存，不怕崩溃
  2. 走 DeepSeek Anthropic 兼容端点（/v1/messages），已验证 deepseek-v4-pro 可用
  3. 更健壮的 JSON 解析（无 response_format 依赖）
  4. 支持 --resume 断点续传

用法:
  # 20条快速验证
  python generate_sarcasm_data_v2.py --category S1 --count 20

  # 全部20类，每类20条，验证全流程
  python generate_sarcasm_data_v2.py --all --samples-per-category 20

  # 正式跑：每类1000条，每50条落库
  python generate_sarcasm_data_v2.py --all --samples-per-category 1000 --flush-every 50
"""

import argparse
import json
import os
import re
import sys
import time
import traceback
from typing import Any, Callable, Dict, List, Optional

import requests

# ============================================================
# 导入原版常量
# ============================================================
_SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, _SCRIPT_DIR)
from _sarcasm_constants import (  # type: ignore
    CATEGORY_DEFINITIONS, SYSTEM_PROMPT,
    COT_TEMPLATE_SARCASTIC, COT_TEMPLATE_NON_SARCASTIC,
    HUAWEI_ENTITIES, SCENE_VARIANTS, TONE_VARIANTS,
    build_generation_prompt, check_cot_quality, check_diversity,
)

# ============================================================
# DeepSeek Anthropic 端点配置
# ============================================================
DEEPSEEK_DEFAULT_BASE = "https://api.deepseek.com/anthropic"
DEEPSEEK_DEFAULT_MODEL = "deepseek-v4-pro"


# ============================================================
# 一、增量 JSONL 写入器
# ============================================================

class IncrementalWriter:
    """增量 JSONL 写入器。

    - append 模式打开，每批写完立刻 flush 到磁盘
    - 记录已写入条数，支持查询进度
    - 线程安全由调用方保证（当前脚本是单线程的）
    """

    def __init__(self, filepath: str):
        self.filepath = filepath
        self.count = 0
        # 如果文件已存在（resume 场景），统计已有条数
        if os.path.exists(filepath):
            with open(filepath, "r", encoding="utf-8") as f:
                self.count = sum(1 for line in f if line.strip())
        self._fd = None

    def __enter__(self):
        self._fd = open(self.filepath, "a", encoding="utf-8")
        return self

    def __exit__(self, *args):
        if self._fd:
            self._fd.close()
            self._fd = None

    def write_batch(self, samples: List[Dict]) -> None:
        """写入一批样本，立即 flush。"""
        for s in samples:
            self._fd.write(json.dumps(s, ensure_ascii=False) + "\n")
        self._fd.flush()
        os.fsync(self._fd.fileno())  # 确保落到磁盘
        self.count += len(samples)
        print(f"  [落库] +{len(samples)}条 → {self.filepath}  (累计 {self.count} 条)",
              flush=True)

    def write_one(self, sample: Dict) -> None:
        self.write_batch([sample])

    def get_existing_labels(self) -> Dict[str, int]:
        """读取已有输出文件，返回每个 label 的已有条数（用于 resume）。"""
        counts: Dict[str, int] = {}
        if not os.path.exists(self.filepath):
            return counts
        with open(self.filepath, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    s = json.loads(line)
                    lbl = s.get("label", "__unknown__")
                    counts[lbl] = counts.get(lbl, 0) + 1
                except json.JSONDecodeError:
                    pass
        return counts


# ============================================================
# 二、多样性控制器
# ============================================================

# 产品品类（用于轮换焦点）
PRODUCT_CATEGORIES = [
    "手机旗舰 (Mate/Pura系列)",
    "折叠屏手机",
    "中端/性价比手机 (nova/畅享)",
    "PC/平板 (MateBook/MatePad)",
    "穿戴/音频 (Watch/FreeBuds)",
    "智能汽车 (问界/智界/享界/尊界)",
    "芯片/底层技术 (麒麟/昇腾/鲲鹏/鸿蒙)",
    "ToB/企业业务 (华为云/昇腾NPU/5.5G)",
]

# 反讽显性程度（仅反讽类使用）
INTENSITY_LEVELS = ["微妙暗示——不仔细读看不出来在讽刺",
                    "明显阴阳——读者一眼能看出在说反话",
                    "尖锐攻击——讽刺力度很强，几乎等于开骂"]


class DiversityController:
    """多样性控制器 —— 通过轮换维度组合，确保每批样本的硬性约束不重复。

    五个维度:
      - 场景 (SCENE_VARIANTS, 9种)
      - 语气 (TONE_VARIANTS, 6种)
      - 文本长度 (短/中/长)
      - 产品品类 (PRODUCT_CATEGORIES, 8种)
      - 反讽显性程度 (INTENSITY_LEVELS, 3种，仅反讽类)
    """

    LENGTH_BUCKETS = [
        ("短", 20, 50),
        ("中", 50, 100),
        ("长", 100, 200),
    ]

    def __init__(self, seed: int = 42):
        import random
        self._rng = random.Random(seed)
        # 打乱初始顺序，避免每次启动都从同一个组合开始
        self._scenes = list(SCENE_VARIANTS)
        self._tones = list(TONE_VARIANTS)
        self._categories = list(PRODUCT_CATEGORIES)
        self._intensities = list(INTENSITY_LEVELS)
        self._rng.shuffle(self._scenes)
        self._rng.shuffle(self._tones)
        self._rng.shuffle(self._categories)
        self._rng.shuffle(self._intensities)

        # 指针（轮换用）
        self._scene_ptr = 0
        self._tone_ptr = 0
        self._len_ptr = 0
        self._cat_ptr = 0
        self._intensity_ptr = 0

        # 已使用的组合记录（用于去重）
        self._used_combos: set = set()
        # 实体使用计数
        self._entity_counts: Dict[str, int] = {}

    def next_batch_specs(self, batch_size: int, is_sarcastic: bool) -> List[Dict]:
        """为下一批的每条样本生成多样性约束。

        Returns:
            [{"scene": str, "tone": str, "length_label": str,
              "min_len": int, "max_len": int, "category": str,
              "intensity": str | None}, ...]
        """
        specs = []
        for _ in range(batch_size):
            spec = {
                "scene": self._scenes[self._scene_ptr % len(self._scenes)],
                "tone": self._tones[self._tone_ptr % len(self._tones)],
                "length_label": self.LENGTH_BUCKETS[self._len_ptr % 3][0],
                "min_len": self.LENGTH_BUCKETS[self._len_ptr % 3][1],
                "max_len": self.LENGTH_BUCKETS[self._len_ptr % 3][2],
                "category": self._categories[self._cat_ptr % len(self._categories)],
                "intensity": (self._intensities[self._intensity_ptr % 3]
                             if is_sarcastic else None),
            }
            # 生成唯一键，检测是否重复组合
            combo_key = (spec["scene"], spec["tone"], spec["length_label"],
                        spec["category"], spec.get("intensity", ""))
            skip_count = 0
            while combo_key in self._used_combos and skip_count < 50:
                # 微调长度桶来打破重复
                self._len_ptr += 1
                spec["length_label"] = self.LENGTH_BUCKETS[self._len_ptr % 3][0]
                spec["min_len"] = self.LENGTH_BUCKETS[self._len_ptr % 3][1]
                spec["max_len"] = self.LENGTH_BUCKETS[self._len_ptr % 3][2]
                combo_key = (spec["scene"], spec["tone"], spec["length_label"],
                            spec["category"], spec.get("intensity", ""))
                skip_count += 1

            self._used_combos.add(combo_key)
            specs.append(spec)

            # 推进所有指针
            self._scene_ptr += 1
            self._tone_ptr += 1
            self._len_ptr += 1
            self._cat_ptr += 1
            self._intensity_ptr += 1

        return specs

    @staticmethod
    def build_diversity_prompt(specs: List[Dict]) -> str:
        """将多样性 spec 转成注入 prompt 的硬性约束文本。"""
        lines = [
            "",
            "### 🎯 本批次每条样本的硬性约束（必须严格遵守，否则视为不合格）",
        ]
        for i, spec in enumerate(specs, 1):
            parts = [
                f"- 第{i}条：",
                f"{spec['length_label']}文本({spec['min_len']}-{spec['max_len']}字)",
                f"| 场景={spec['scene']}",
                f"| 语气={spec['tone']}",
                f"| 关注={spec['category']}",
            ]
            if spec["intensity"]:
                parts.append(f"| 反讽显性程度={spec['intensity']}")
            lines.append(" ".join(parts))

        lines.append("")
        lines.append("注意：文本字数必须落在指定范围内，不是建议，是硬性要求。")
        return "\n".join(lines)


# ============================================================
# 三、生成器（DeepSeek Anthropic 端点）
# ============================================================

class SarcasmDataGeneratorV2:
    """反讽数据生成器 v2 —— 走 Anthropic Messages API 格式，支持自定义 base_url。"""

    def __init__(
        self,
        base_url: str = DEEPSEEK_DEFAULT_BASE,
        model: str = DEEPSEEK_DEFAULT_MODEL,
        api_key: str = "",
        temperature: float = 0.9,
        max_tokens: int = 16000,
        timeout: int = 180,
    ):
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.api_key = api_key
        self.temperature = temperature
        self.max_tokens = max_tokens
        self.timeout = timeout
        self._diversity = DiversityController()

    # ---- 底层 API 调用 ----

    def _call_api(self, prompt: str, category_label: str,
                  expected_count: int) -> List[Dict]:
        """调用 Anthropic Messages API，返回样本列表。"""
        url = f"{self.base_url}/v1/messages"

        headers = {
            "x-api-key": self.api_key,
            "anthropic-version": "2023-06-01",
            "Content-Type": "application/json",
        }

        payload: Dict[str, Any] = {
            "model": self.model,
            "max_tokens": self.max_tokens,
            "temperature": self.temperature,
            "system": SYSTEM_PROMPT,
            "messages": [
                {"role": "user", "content": prompt},
            ],
        }

        resp = requests.post(url, headers=headers, json=payload,
                            timeout=self.timeout)

        if resp.status_code == 401:
            # 换 Bearer 认证重试
            headers2 = {
                "Authorization": f"Bearer {self.api_key}",
                "anthropic-version": "2023-06-01",
                "Content-Type": "application/json",
            }
            resp = requests.post(url, headers=headers2, json=payload,
                                timeout=self.timeout)

        resp.raise_for_status()
        data = resp.json()

        # 提取文本 (Anthropic 格式)
        content_blocks = data.get("content", [])
        text_parts = []
        for block in content_blocks:
            if block.get("type") == "text":
                text_parts.append(block["text"])
        raw_text = "\n".join(text_parts)

        if not raw_text.strip():
            raise ValueError(f"API 返回空文本。usage={data.get('usage')}")

        return self._parse_response(raw_text, category_label)

    # ---- 响应解析 ----

    @staticmethod
    def _parse_response(content: str, category_label: str) -> List[Dict]:
        """从 LLM 返回的文本中提取 JSON 数组。比原版更健壮。"""
        content = content.strip()

        # 1) 直接解析
        try:
            data = json.loads(content)
        except json.JSONDecodeError:
            data = None

        # 2) 去掉 markdown 代码块后再试
        if data is None:
            cleaned = content
            for fence in ["```json", "```"]:
                if cleaned.startswith(fence):
                    cleaned = cleaned[len(fence):].strip()
            if cleaned.endswith("```"):
                cleaned = cleaned[:-3].strip()
            try:
                data = json.loads(cleaned)
            except json.JSONDecodeError:
                data = None

        # 3) 正则找 JSON 数组
        if data is None:
            match = re.search(r"\[.*\]", content, re.DOTALL)
            if match:
                try:
                    data = json.loads(match.group())
                except json.JSONDecodeError:
                    data = None

        # 4) 正则找 JSON 对象
        if data is None:
            match = re.search(r"\{.*\}", content, re.DOTALL)
            if match:
                try:
                    data = json.loads(match.group())
                except json.JSONDecodeError:
                    pass

        if data is None:
            snippet = content[:500].replace("\n", "\\n")
            raise ValueError(f"无法从 LLM 响应中解析 JSON。前 500 字符: {snippet}")

        # 标准化为列表
        if isinstance(data, dict):
            samples = data.get("samples", data.get("data", []))
        elif isinstance(data, list):
            samples = data
        else:
            raise ValueError(f"意外的响应类型: {type(data)}")

        # 补全缺失字段
        cat_def = CATEGORY_DEFINITIONS.get(category_label, {})
        for s in samples:
            if "label" not in s:
                s["label"] = category_label
            if "category" not in s:
                s["category"] = cat_def.get("name", category_label)
            if "is_sarcastic" not in s:
                s["is_sarcastic"] = cat_def.get("is_sarcastic", None)

        return samples

    # ---- 批量生成（带回调） ----

    def generate_batch(
        self,
        category_label: str,
        count: int,
        seed_examples: Optional[List[Dict]] = None,
        batch_size: int = 5,
        on_batch: Optional[Callable[[List[Dict]], None]] = None,
        max_retries: int = 3,
    ) -> List[Dict]:
        """为一个分类生成指定数量的样本。

        Args:
            category_label: 分类标签 (S1-S10, N1-N10)
            count: 目标数量
            seed_examples: 种子样本 (few-shot)
            batch_size: 每批 LLM 调用生成的条数
            on_batch: 每批生成完的回调函数，签名为 (samples: List[Dict]) -> None
            max_retries: 每批最大重试次数
        """
        all_samples: List[Dict] = []
        remaining = count

        while remaining > 0:
            current_batch_size = min(batch_size, remaining)

            # 获取多样性约束
            cat_def = CATEGORY_DEFINITIONS.get(category_label, {})
            is_sarc = cat_def.get("is_sarcastic", False)
            div_specs = self._diversity.next_batch_specs(current_batch_size, is_sarc)
            div_prompt = DiversityController.build_diversity_prompt(div_specs)

            # 构建 prompt = 基础生成 prompt + 多样性硬性约束
            base_prompt = build_generation_prompt(category_label, current_batch_size,
                                                  seed_examples)
            prompt = base_prompt + "\n" + div_prompt
            batch = None
            for attempt in range(1, max_retries + 1):
                try:
                    batch = self._call_api(prompt, category_label, current_batch_size)
                    break
                except Exception as e:
                    print(f"  [{category_label}] 第{attempt}次尝试失败: {e}", flush=True)
                    if attempt < max_retries:
                        wait = 2 ** attempt
                        print(f"  [{category_label}] 等待{wait}秒后重试...", flush=True)
                        time.sleep(wait)
                    else:
                        print(f"  [{category_label}] 已达最大重试次数，跳过本批",
                              file=sys.stderr, flush=True)
                        batch = []

            if batch:
                all_samples.extend(batch)
                remaining -= len(batch)
                # 回调（用于增量落库）
                if on_batch:
                    on_batch(batch)
                print(f"  [{category_label}] 进度 {len(all_samples)}/{count}",
                      flush=True)
            else:
                # 空批也扣减，避免死循环（稳妥起见，break）
                print(f"  [{category_label}] 本批为空，终止生成", file=sys.stderr)
                break

        return all_samples[:count]


# ============================================================
# 三、命令行接口
# ============================================================

def main():
    parser = argparse.ArgumentParser(
        description="反讽数据集生成器 v2 —— 支持 DeepSeek Anthropic 端点 + 分批落库",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例:
  # 20条快速验证
  python generate_sarcasm_data_v2.py --category S1 --count 20

  # 全部20类各20条
  python generate_sarcasm_data_v2.py --all --samples-per-category 20

  # 正式跑：每类1000条，每50条落库
  python generate_sarcasm_data_v2.py --all --samples-per-category 1000 --flush-every 50

  # 自定义端点（如果跟默认不同）
  python generate_sarcasm_data_v2.py --all --samples-per-category 20 \\
      --base-url https://api.deepseek.com/anthropic --model deepseek-v4-pro

  # 断点续传（读取已有输出，只补未完成的）
  python generate_sarcasm_data_v2.py --all --samples-per-category 1000 --resume
""",
    )

    # ---- 分类选择 ----
    g = parser.add_mutually_exclusive_group(required=True)
    g.add_argument("--category", type=str, help="单个分类标签（如 S1, N3）")
    g.add_argument("--categories", type=str, help="多个分类，逗号分隔（如 S1,S2,N1）")
    g.add_argument("--all", action="store_true", help="生成全部20个分类")

    # ---- 数量 ----
    parser.add_argument("--count", type=int, default=10,
                        help="单分类模式下的生成数量 (default: 10)")
    parser.add_argument("--samples-per-category", type=int, default=10,
                        help="多分类/全部分类模式下每类数量 (default: 10)")

    # ---- API 配置 ----
    parser.add_argument("--base-url", type=str,
                        default=os.environ.get("ANTHROPIC_BASE_URL", DEEPSEEK_DEFAULT_BASE),
                        help=f"API 基础 URL (default: {DEEPSEEK_DEFAULT_BASE})")
    parser.add_argument("--model", type=str,
                        default=DEEPSEEK_DEFAULT_MODEL,
                        help=f"模型名称 (default: {DEEPSEEK_DEFAULT_MODEL})")
    parser.add_argument("--api-key", type=str,
                        default=os.environ.get("ANTHROPIC_AUTH_TOKEN", ""),
                        help="API Key (default: 读取 ANTHROPIC_AUTH_TOKEN 环境变量)")

    # ---- 生成参数 ----
    parser.add_argument("--batch-size", type=int, default=5,
                        help="每批 LLM 调用生成条数 (default: 5)")
    parser.add_argument("--temperature", type=float, default=0.9)
    parser.add_argument("--max-tokens", type=int, default=16000)
    parser.add_argument("--timeout", type=int, default=180,
                        help="API 超时秒数 (default: 180)")

    # ---- 输出 ----
    parser.add_argument("--output", type=str, default="./sarcasm_output_v2.jsonl",
                        help="输出 JSONL 文件路径 (default: ./sarcasm_output_v2.jsonl)")
    parser.add_argument("--flush-every", type=int, default=0,
                        help="累积多少条后强制落库一次 (default: 0=每批都落)")

    # ---- 其他 ----
    parser.add_argument("--seed-file", type=str,
                        help="种子数据 JSONL 文件路径（用于few-shot）")
    parser.add_argument("--validate", action="store_true",
                        help="生成后运行质量检查")
    parser.add_argument("--resume", action="store_true",
                        help="断点续传：读取已有输出文件，只补未完成的分类和条数")

    args = parser.parse_args()

    # ---- 确定分类列表 ----
    if args.category:
        categories = [args.category]
    elif args.categories:
        categories = [c.strip() for c in args.categories.split(",")]
    else:
        categories = list(CATEGORY_DEFINITIONS.keys())

    # 验证
    for cat in categories:
        if cat not in CATEGORY_DEFINITIONS:
            print(f"错误: 未知分类 '{cat}'。可用: {list(CATEGORY_DEFINITIONS.keys())}")
            sys.exit(1)

    # 每类数量
    count_per = args.samples_per_category if (args.all or args.categories) else args.count

    # ---- 加载种子数据 ----
    seed_examples: Dict[str, List[Dict]] = {}
    if args.seed_file:
        with open(args.seed_file, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                s = json.loads(line)
                lbl = s["label"]
                seed_examples.setdefault(lbl, []).append(s)
        total_seeds = sum(len(v) for v in seed_examples.values())
        print(f"已加载种子数据: {total_seeds} 条")

    # ---- 断点续传：计算每类还需生成多少 ----
    resume_counts: Dict[str, int] = {}
    if args.resume and os.path.exists(args.output):
        existing = {}
        with open(args.output, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    s = json.loads(line)
                    lbl = s.get("label", "__unknown__")
                    existing[lbl] = existing.get(lbl, 0) + 1
                except json.JSONDecodeError:
                    pass
        for cat in categories:
            already = existing.get(cat, 0)
            need = max(0, count_per - already)
            resume_counts[cat] = need
            if need == 0:
                print(f"[{cat}] 已完成 ({already}/{count_per})，跳过")
            else:
                print(f"[{cat}] 已有 {already}，还需 {need}")
    else:
        for cat in categories:
            resume_counts[cat] = count_per

    # ---- 初始化生成器 ----
    generator = SarcasmDataGeneratorV2(
        base_url=args.base_url,
        model=args.model,
        api_key=args.api_key,
        temperature=args.temperature,
        max_tokens=args.max_tokens,
        timeout=args.timeout,
    )

    print(f"\nAPI 端点: {args.base_url}/v1/messages")
    print(f"模型: {args.model}")
    print(f"输出文件: {args.output}")
    print(f"分类数: {len(categories)}, 总目标: {sum(resume_counts.values())} 条")
    print(f"每批条数: {args.batch_size}, 落库间隔: {'每批' if not args.flush_every else f'{args.flush_every}条'}")
    print(f"{'='*60}\n")

    # ---- 逐分类生成 + 实时落库 ----
    t0 = time.time()
    grand_total = 0
    pending_buffer: List[Dict] = []

    with IncrementalWriter(args.output) as writer:
        for cat in categories:
            need = resume_counts.get(cat, 0)
            if need <= 0:
                continue

            cat_def = CATEGORY_DEFINITIONS[cat]
            print(f"\n{'='*60}")
            print(f"[{cat}] {cat_def['name']}  —  目标 {need} 条")
            print(f"{'='*60}")

            def make_callback(label: str):
                """闭包：把生成结果同时写入 buffer 和增量落库"""
                def callback(batch: List[Dict]):
                    nonlocal grand_total, pending_buffer
                    pending_buffer.extend(batch)
                    grand_total += len(batch)
                    # 检查是否达到 flush 阈值
                    flush_every = args.flush_every or args.batch_size
                    if len(pending_buffer) >= flush_every:
                        writer.write_batch(pending_buffer)
                        pending_buffer.clear()
                return callback

            seeds = seed_examples.get(cat, []) if seed_examples else []
            _ = generator.generate_batch(
                category_label=cat,
                count=need,
                seed_examples=seeds,
                batch_size=args.batch_size,
                on_batch=make_callback(cat),
            )

        # 兜底：写掉 buffer 里剩余的
        if pending_buffer:
            writer.write_batch(pending_buffer)
            pending_buffer.clear()

    elapsed = time.time() - t0
    print(f"\n{'='*60}")
    print(f"全部完成！共 {writer.count} 条，耗时 {elapsed:.0f}s "
          f"({writer.count/elapsed:.1f} 条/s)")
    print(f"输出文件: {args.output}")
    print(f"{'='*60}")

    # ---- 质量验证 ----
    if args.validate:
        print(f"\n{'='*60}")
        print("质量检查...")
        print(f"{'='*60}")
        issues_found = 0
        with open(args.output, "r", encoding="utf-8") as f:
            all_samples = [json.loads(line) for line in f if line.strip()]

        # 按分类汇总
        by_cat: Dict[str, List[Dict]] = {}
        for s in all_samples:
            lbl = s.get("label", "__unknown__")
            by_cat.setdefault(lbl, []).append(s)

        for cat, samples in sorted(by_cat.items()):
            cat_passed = cat_warned = cat_failed = 0
            for s in samples:
                result = check_cot_quality(s.get("cot", ""), s.get("is_sarcastic", False))
                if not result["passed"]:
                    cat_failed += 1
                    if issues_found < 10:  # 只打印前10个
                        print(f"  [FAIL] {s['label']}: {result['issues']}")
                    issues_found += 1
                elif result["warnings"]:
                    cat_warned += 1
                else:
                    cat_passed += 1

            # 多样性检查
            div = check_diversity(samples)
            div_status = "OK" if div["passed"] else ("WARN: " + "; ".join(div.get("warnings", [])))

            print(f"  [{cat}] 通过:{cat_passed} 警告:{cat_warned} "
                  f"失败:{cat_failed} 多样性:{div_status}")

        print(f"\n  总计问题: {issues_found}")


if __name__ == "__main__":
    main()
