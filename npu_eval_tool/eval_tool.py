#!/usr/bin/env python3
"""
NPU Distributed Evaluation Tool
================================
单文件、数据并行、模块化的昇腾 NPU 模型推理评测工具。

Usage:
    # 单卡评测
    python eval_tool.py -m /path/to/model -d data.jsonl -o ./results

    # 多卡数据并行评测
    torchrun --nproc_per_node=8 eval_tool.py -m /path/to/model -d data.jsonl -o ./results

    # 指定评测指标
    python eval_tool.py -m /path/to/model -d data.jsonl --metrics exact_match json_accuracy

    # 自定义 prompt 模板
    python eval_tool.py -m /path/to/model -d data.jsonl --prompt_template chatml

数据格式 (JSONL):
    {"instruction": "...", "input": "...", "output": "..."}
    {"instruction": "...", "input": "...", "output": "{\"level1\": \"A\", \"level2\": \"B\"}"}

扩展新指标:
    @register_metric("my_metric")
    def my_metric(predictions, references):
        ...
        return {"score": 0.9, "per_sample": [...]}

Requirements: torch, torch_npu, transformers
"""

import argparse
import json
import math
import os
import sys
import time
import traceback
from collections import Counter, defaultdict
from typing import Any, Callable, Dict, List, Optional, Sequence, Tuple, Union

# ============================================================================
# Metric Registry
# ============================================================================

METRIC_REGISTRY: Dict[str, Callable] = {}

def register_metric(name: str, description: str = ""):
    """注册一个评测指标。被装饰的函数签名: (predictions, references) -> dict"""
    def decorator(fn: Callable) -> Callable:
        fn._metric_name = name
        fn._description = description
        METRIC_REGISTRY[name] = fn
        return fn
    return decorator


# ============================================================================
# JSON Utilities
# ============================================================================

def _try_parse_json(text: Any) -> Any:
    """尝试将字符串解析为 JSON 对象。如果 text 已经是 dict/list 则直接返回。"""
    if text is None:
        return None
    if isinstance(text, (dict, list, int, float, bool)):
        return text
    if not isinstance(text, str):
        return str(text)

    s = text.strip()
    # 尝试直接解析
    try:
        return json.loads(s)
    except (json.JSONDecodeError, ValueError):
        pass

    # 尝试从文本中提取 JSON 对象或数组
    for start_ch, end_ch in [("{", "}"), ("[", "]")]:
        start = s.find(start_ch)
        end = s.rfind(end_ch)
        if start != -1 and end > start:
            try:
                return json.loads(s[start:end + 1])
            except (json.JSONDecodeError, ValueError):
                pass

    return text  # 解析失败，返回原字符串


def _json_deep_compare(obj1: Any, obj2: Any, prefix: str = "") -> Dict[str, float]:
    """递归比较两个 JSON 对象，返回每个字段路径的正确/错误 (1.0/0.0)。"""
    results: Dict[str, float] = {}

    if isinstance(obj1, dict) and isinstance(obj2, dict):
        all_keys = set(obj1.keys()) | set(obj2.keys())
        if not all_keys:
            results[prefix or "value"] = 1.0
            return results
        for key in sorted(all_keys):
            key_path = f"{prefix}.{key}" if prefix else key
            v1, v2 = obj1.get(key), obj2.get(key)
            results.update(_json_deep_compare(v1, v2, key_path))

    elif isinstance(obj1, list) and isinstance(obj2, list):
        max_len = max(len(obj1), len(obj2))
        if max_len == 0:
            results[prefix or "value"] = 1.0
            return results
        for i in range(max_len):
            key_path = f"{prefix}[{i}]"
            v1 = obj1[i] if i < len(obj1) else None
            v2 = obj2[i] if i < len(obj2) else None
            results.update(_json_deep_compare(v1, v2, key_path))

    else:
        # 标量比较
        s1 = str(obj1).strip() if obj1 is not None else ""
        s2 = str(obj2).strip() if obj2 is not None else ""
        results[prefix or "value"] = 1.0 if s1 == s2 else 0.0

    return results


# ============================================================================
# Built-in Metrics
# ============================================================================

def _normalize_refs(references: List[Any]) -> List[str]:
    """将 reference 统一转为字符串（用于非 JSON 类指标）。"""
    out = []
    for r in references:
        if isinstance(r, (dict, list)):
            out.append(json.dumps(r, ensure_ascii=False))
        else:
            out.append(str(r))
    return out


@register_metric("exact_match", "预测文本与参考答案完全一致（strip 后比较）")
def metric_exact_match(predictions: List[str], references: List[str]) -> Dict[str, Any]:
    refs = _normalize_refs(references)
    per_sample = [
        1.0 if p.strip() == r.strip() else 0.0
        for p, r in zip(predictions, refs)
    ]
    correct = int(sum(per_sample))
    return {
        "score": correct / len(per_sample) if per_sample else 0.0,
        "per_sample": per_sample,
        "correct": correct,
        "total": len(per_sample),
    }


@register_metric("contains", "参考答案是否完整出现在预测文本中")
def metric_contains(predictions: List[str], references: List[str]) -> Dict[str, Any]:
    refs = _normalize_refs(references)
    per_sample = [
        1.0 if r.strip() in p.strip() else 0.0
        for p, r in zip(predictions, refs)
    ]
    correct = int(sum(per_sample))
    return {
        "score": correct / len(per_sample) if per_sample else 0.0,
        "per_sample": per_sample,
        "correct": correct,
        "total": len(per_sample),
    }


@register_metric("json_accuracy", "解析 JSON 后逐字段比较，返回 overall 和 per-field 准确率")
def metric_json_accuracy(predictions: List[str], references: List[str]) -> Dict[str, Any]:
    per_sample: List[float] = []
    field_correct: Dict[str, float] = defaultdict(float)
    field_total: Dict[str, int] = defaultdict(int)

    for p, r in zip(predictions, references):
        p_parsed = _try_parse_json(p)
        r_parsed = _try_parse_json(r)

        if isinstance(p_parsed, (dict, list)) and isinstance(r_parsed, (dict, list)):
            field_results = _json_deep_compare(p_parsed, r_parsed)
            if field_results:
                sample_score = sum(field_results.values()) / len(field_results)
            else:
                sample_score = 1.0
            for key, val in field_results.items():
                field_correct[key] += val
                field_total[key] += 1
            per_sample.append(sample_score)
        else:
            # 至少有一方不是 JSON，退化为字符串匹配
            s1 = str(p).strip()
            s2 = str(r).strip()
            per_sample.append(1.0 if s1 == s2 else 0.0)

    field_scores = {
        k: field_correct[k] / field_total[k]
        for k in sorted(field_total.keys())
    } if field_total else {}

    return {
        "score": sum(per_sample) / len(per_sample) if per_sample else 0.0,
        "per_sample": per_sample,
        "field_scores": field_scores,
    }


@register_metric("json_exact_match", "解析 JSON 后进行结构化全等比较")
def metric_json_exact_match(predictions: List[str], references: List[str]) -> Dict[str, Any]:
    per_sample = []
    for p, r in zip(predictions, references):
        p_parsed = _try_parse_json(p)
        r_parsed = _try_parse_json(r)
        per_sample.append(1.0 if p_parsed == r_parsed else 0.0)
    correct = int(sum(per_sample))
    return {
        "score": correct / len(per_sample) if per_sample else 0.0,
        "per_sample": per_sample,
        "correct": correct,
        "total": len(per_sample),
    }


@register_metric("char_f1", "字符级 F1 分数（字符集合重叠）")
def metric_char_f1(predictions: List[str], references: List[str]) -> Dict[str, Any]:
    refs = _normalize_refs(references)
    per_sample = []
    for p, r in zip(predictions, refs):
        p_chars = set(p.strip())
        r_chars = set(r.strip())
        if not p_chars and not r_chars:
            per_sample.append(1.0)
        elif not p_chars or not r_chars:
            per_sample.append(0.0)
        else:
            overlap = len(p_chars & r_chars)
            precision = overlap / len(p_chars)
            recall = overlap / len(r_chars)
            if precision + recall > 0:
                per_sample.append(2 * precision * recall / (precision + recall))
            else:
                per_sample.append(0.0)
    return {
        "score": sum(per_sample) / len(per_sample) if per_sample else 0.0,
        "per_sample": per_sample,
    }


@register_metric("bleu", "字符级 BLEU-1/2/4（不依赖 nltk）")
def metric_bleu(predictions: List[str], references: List[str]) -> Dict[str, Any]:
    refs = _normalize_refs(references)

    def _char_ngrams(text: str, n: int) -> Counter:
        text = text.strip()
        if len(text) < n:
            return Counter([text] if text else [])
        return Counter(text[i:i + n] for i in range(len(text) - n + 1))

    max_n = 4
    bleu_vals = {n: [] for n in range(1, max_n + 1)}
    per_sample = []

    for p, r in zip(predictions, refs):
        p_clean, r_clean = p.strip(), r.strip()
        sample_bleu = {}
        for n in range(1, max_n + 1):
            pred_ngrams = _char_ngrams(p_clean, n)
            ref_ngrams = _char_ngrams(r_clean, n)
            total = sum(pred_ngrams.values())
            if total == 0:
                sample_bleu[n] = 0.0
            else:
                overlap = sum(min(pred_ngrams[ng], ref_ngrams[ng]) for ng in pred_ngrams)
                sample_bleu[n] = overlap / total
            bleu_vals[n].append(sample_bleu[n])

        # 几何平均 (加平滑避免 log(0))
        vals = [max(sample_bleu.get(n, 0.0), 1e-10) for n in range(1, max_n + 1)]
        geo_mean = math.exp(sum(math.log(v) for v in vals) / len(vals))
        # 简短惩罚 (brevity penalty)
        bp = min(1.0, math.exp(1 - len(r_clean) / max(len(p_clean), 1)))
        per_sample.append(bp * geo_mean)

    result = {f"bleu{n}": sum(vals) / len(vals) if vals else 0.0 for n, vals in bleu_vals.items()}
    result["score"] = sum(per_sample) / len(per_sample) if per_sample else 0.0
    result["per_sample"] = per_sample
    return result


# ============================================================================
# Data Loading
# ============================================================================

def load_data(data_path: str) -> List[Dict[str, Any]]:
    """加载 JSONL 数据文件。

    每行是一个 JSON 对象，需包含以下字段：
        instruction, input, output
    可选字段：
        labels (dict): 用于分组统计的多级标签
    """
    data = []
    if not os.path.isfile(data_path):
        raise FileNotFoundError(f"Data file not found: {data_path}")

    with open(data_path, "r", encoding="utf-8") as f:
        raw = f.read().strip()

    # 尝试作为 JSON 数组解析
    if raw.startswith("["):
        loaded = json.loads(raw)
        if isinstance(loaded, list):
            data = loaded
        else:
            data = [loaded]
    else:
        # 按 JSONL 逐行解析
        for line_num, line in enumerate(raw.split("\n"), 1):
            line = line.strip()
            if not line:
                continue
            try:
                data.append(json.loads(line))
            except json.JSONDecodeError as e:
                print(f"[WARN] Skipping line {line_num}: {e}", file=sys.stderr)

    if not data:
        raise ValueError(f"No valid data found in {data_path}")

    # 校验必要字段
    missing = [i for i, d in enumerate(data) if "output" not in d]
    if missing:
        print(f"[WARN] {len(missing)} samples missing 'output' field (indices: {missing[:10]}...)", file=sys.stderr)

    print(f"Loaded {len(data)} samples from {data_path}")
    return data


# ============================================================================
# Prompt Templates
# ============================================================================

DEFAULT_TEMPLATE = "{instruction}\n{input}"

CHATML_TEMPLATE = (
    "<|im_start|>user\n{instruction}\n{input}<|im_end|>\n"
    "<|im_start|>assistant\n"
)

QWEN_TEMPLATE = (
    "<|im_start|>system\nYou are a helpful assistant.<|im_end|>\n"
    "<|im_start|>user\n{instruction}\n{input}<|im_end|>\n"
    "<|im_start|>assistant\n"
)

PRESET_TEMPLATES = {
    "default": DEFAULT_TEMPLATE,
    "chatml": CHATML_TEMPLATE,
    "qwen": QWEN_TEMPLATE,
}


def build_prompt(sample: Dict[str, Any], template: str = "default") -> str:
    """根据模板构建 prompt 字符串。"""
    instruction = str(sample.get("instruction", "")).strip()
    input_text = str(sample.get("input", "")).strip()

    # 获取模板字符串
    tmpl = PRESET_TEMPLATES.get(template, template)

    # 处理特殊情况
    if instruction and input_text:
        return tmpl.format(instruction=instruction, input=input_text)
    elif instruction and not input_text:
        return tmpl.format(instruction=instruction, input="")
    elif not instruction and input_text:
        return input_text
    else:
        return ""


# ============================================================================
# Inference Engine
# ============================================================================

class InferEngine:
    """NPU 推理引擎，负责模型加载和批量推理。"""

    def __init__(
        self,
        model_path: str,
        torch_dtype: str = "float16",
        trust_remote_code: bool = False,
        max_input_length: int = 2048,
    ):
        self.model_path = model_path
        self._torch_dtype = getattr(__import__("torch"), torch_dtype)
        self._trust_remote_code = trust_remote_code
        self._max_input_length = max_input_length
        self.model = None
        self.tokenizer = None
        self._device_id: Optional[int] = None

    def load(self) -> "InferEngine":
        """加载模型和分词器到 NPU。"""
        import torch
        import torch_npu  # noqa: F401

        from transformers import AutoModelForCausalLM, AutoTokenizer

        local_rank = int(os.environ.get("LOCAL_RANK", 0))
        self._device_id = local_rank % torch.npu.device_count()
        torch.npu.set_device(self._device_id)

        rank = os.environ.get("RANK", "0")
        print(f"[Rank {rank}] Loading model from {self.model_path} onto NPU:{self._device_id}...",
              flush=True)

        self.tokenizer = AutoTokenizer.from_pretrained(
            self.model_path, trust_remote_code=self._trust_remote_code,
        )
        if self.tokenizer.pad_token is None:
            self.tokenizer.pad_token = self.tokenizer.eos_token

        self.model = AutoModelForCausalLM.from_pretrained(
            self.model_path,
            torch_dtype=self._torch_dtype,
            trust_remote_code=self._trust_remote_code,
        )
        self.model = self.model.to(f"npu:{self._device_id}")
        self.model.eval()

        print(f"[Rank {rank}] Model loaded.", flush=True)
        return self

    @property
    def device(self):
        return self.model.device if self.model is not None else None

    def unload(self):
        """释放模型内存。"""
        import torch
        if self.model is not None:
            del self.model
            self.model = None
        if self.tokenizer is not None:
            del self.tokenizer
            self.tokenizer = None
        if torch.npu.is_available():
            torch.npu.empty_cache()

    def generate(
        self,
        prompts: List[str],
        max_new_tokens: int = 256,
        temperature: float = 0.0,
        top_p: float = 1.0,
        do_sample: bool = False,
        batch_size: int = 8,
    ) -> List[Dict[str, Any]]:
        """批量推理，返回每条结果的 dict。

        Returns:
            [{"prompt": str, "generated": str, "error": None | str}, ...]
        """
        import torch

        results: List[Dict[str, Any]] = []
        total = len(prompts)

        for batch_start in range(0, total, batch_size):
            batch_end = min(batch_start + batch_size, total)
            batch = prompts[batch_start:batch_end]

            try:
                inputs = self.tokenizer(
                    batch,
                    return_tensors="pt",
                    padding=True,
                    truncation=True,
                    max_length=self._max_input_length,
                )
                inputs = {k: v.to(self.device) for k, v in inputs.items()}

                with torch.no_grad():
                    outputs = self.model.generate(
                        **inputs,
                        max_new_tokens=max_new_tokens,
                        temperature=temperature if do_sample else 1.0,
                        top_p=top_p,
                        do_sample=do_sample,
                        pad_token_id=self.tokenizer.pad_token_id
                            or self.tokenizer.eos_token_id,
                        eos_token_id=self.tokenizer.eos_token_id,
                    )

                input_len = inputs["input_ids"].shape[1]
                generated_ids = outputs[:, input_len:]
                texts = self.tokenizer.batch_decode(
                    generated_ids, skip_special_tokens=True,
                )

                for prompt, text in zip(batch, texts):
                    results.append({
                        "prompt": prompt,
                        "generated": text.strip(),
                        "error": None,
                    })

                if (batch_start // batch_size) % 10 == 0:
                    print(f"  [{batch_start}/{total}] done...", flush=True)

            except torch.cuda.OutOfMemoryError as e:
                err = f"OOM: {e}"
                print(f"[ERROR] Batch [{batch_start}:{batch_end}]: {err}", file=sys.stderr, flush=True)
                for prompt in batch:
                    results.append({"prompt": prompt, "generated": "", "error": err})
            except Exception as e:
                err = f"{type(e).__name__}: {e}"
                print(f"[ERROR] Batch [{batch_start}:{batch_end}]: {err}", file=sys.stderr, flush=True)
                traceback.print_exc(file=sys.stderr)
                for prompt in batch:
                    results.append({"prompt": prompt, "generated": "", "error": err})

            # 及时清理 batch 级显存
            del inputs, outputs
            if torch.npu.is_available():
                torch.npu.empty_cache()

        return results


# ============================================================================
# Evaluator (Main Orchestrator)
# ============================================================================

class Evaluator:
    """评测编排器：加载数据 → 分布式推理 → 收集结果 → 计算指标 → 输出报告。"""

    def __init__(self, args: argparse.Namespace):
        self.args = args
        self._rank = 0
        self._world_size = 1
        self._local_rank = 0
        self._distributed = False

    def _setup_distributed(self) -> None:
        """初始化 HCCL 分布式环境。"""
        if "LOCAL_RANK" not in os.environ:
            import torch
            import torch_npu  # noqa: F401
            if torch.npu.is_available():
                torch.npu.set_device(0)
            return

        import torch
        import torch_npu  # noqa: F401

        self._distributed = True
        self._local_rank = int(os.environ["LOCAL_RANK"])
        self._rank = int(os.environ.get("RANK", self._local_rank))
        self._world_size = int(os.environ.get("WORLD_SIZE", 1))

        torch.distributed.init_process_group(backend="hccl")
        torch.npu.set_device(self._local_rank)
        print(f"[Rank {self._rank}/{self._world_size}] HCCL initialized on NPU:{self._local_rank}",
              flush=True)

    def _cleanup_distributed(self) -> None:
        if self._distributed:
            import torch
            torch.distributed.destroy_process_group()

    def _shard_data(self, data: List[Dict]) -> List[Dict]:
        """将数据按 rank 分片（尾部多余数据归入最后一个 rank）。"""
        base = len(data) // self._world_size
        remainder = len(data) % self._world_size
        start = self._rank * base + min(self._rank, remainder)
        end = start + base + (1 if self._rank < remainder else 0)
        return data[start:end]

    def run(self) -> Dict[str, Any]:
        import torch

        self._setup_distributed()

        # ---- 1. Load data ----
        if self._rank == 0:
            print(f"Loading data from {self.args.data_path}...", flush=True)
        all_data = load_data(self.args.data_path)
        my_data = self._shard_data(all_data)

        if self._rank == 0:
            print(f"Total: {len(all_data)} samples, {self._world_size} rank(s), "
                  f"~{len(my_data)} per rank")

        # ---- 2. Build prompts ----
        prompts = [build_prompt(s, self.args.prompt_template) for s in my_data]
        references = [s.get("output", "") for s in my_data]

        # ---- 3. Inference ----
        engine = InferEngine(
            model_path=self.args.model_path,
            torch_dtype=self.args.torch_dtype,
            trust_remote_code=self.args.trust_remote_code,
            max_input_length=self.args.max_input_length,
        )
        engine.load()

        if self._rank == 0:
            print(f"Generating (max_new_tokens={self.args.max_new_tokens}, "
                  f"batch_size={self.args.batch_size})...", flush=True)

        t0 = time.time()
        gen_results = engine.generate(
            prompts=prompts,
            max_new_tokens=self.args.max_new_tokens,
            temperature=self.args.temperature,
            top_p=self.args.top_p,
            do_sample=self.args.do_sample,
            batch_size=self.args.batch_size,
        )
        elapsed = time.time() - t0
        if self._rank == 0:
            print(f"Generation done: {len(gen_results)} samples in {elapsed:.1f}s "
                  f"({len(gen_results)/elapsed:.1f} samples/s)", flush=True)

        engine.unload()

        # ---- 4. Build local results ----
        local_results = []
        for sample, gr in zip(my_data, gen_results):
            local_results.append({
                "prompt": gr["prompt"],
                "reference": sample.get("output", ""),
                "prediction": gr["generated"],
                "error": gr["error"],
                "_meta": _extract_meta(sample),
            })

        # ---- 5. Gather across ranks ----
        if self._distributed:
            gathered = [None] * self._world_size
            torch.distributed.all_gather_object(gathered, local_results)
            if self._rank == 0:
                all_results: List[Dict] = []
                for g in gathered:
                    all_results.extend(g)
            else:
                all_results = []
        else:
            all_results = local_results

        # ---- 6. Compute metrics & save (rank 0 only) ----
        if self._rank == 0:
            metrics = self._compute_metrics(all_results)
            self._save_outputs(all_results, metrics)
            self._print_summary(metrics)
            ret = {"metrics": metrics, "num_results": len(all_results)}
        else:
            ret = {}

        self._cleanup_distributed()
        return ret

    # ---- Metrics ----

    def _compute_metrics(self, all_results: List[Dict]) -> Dict[str, Any]:
        """计算所有指定指标，并分组统计（如果数据中有 labels 字段）。"""
        predictions = [r["prediction"] for r in all_results]
        references = [r["reference"] for r in all_results]

        valid_idx = [i for i, r in enumerate(all_results) if r["error"] is None]
        valid_preds = [predictions[i] for i in valid_idx]
        valid_refs = [references[i] for i in valid_idx]
        num_errors = len(all_results) - len(valid_idx)

        metrics: Dict[str, Any] = {
            "num_samples": len(all_results),
            "num_valid": len(valid_idx),
            "num_errors": num_errors,
            "scores": {},
        }

        if not valid_idx:
            metrics["error"] = "all_samples_failed"
            return metrics

        metric_names = self.args.metrics or ["exact_match"]
        for name in metric_names:
            fn = METRIC_REGISTRY.get(name)
            if fn is None:
                print(f"[WARN] Unknown metric '{name}', skipped. "
                      f"Available: {list(METRIC_REGISTRY.keys())}", file=sys.stderr)
                continue
            print(f"Computing {name}...", flush=True)
            try:
                metrics["scores"][name] = fn(valid_preds, valid_refs)
            except Exception as e:
                print(f"[ERROR] Metric '{name}' failed: {e}", file=sys.stderr)
                traceback.print_exc(file=sys.stderr)
                metrics["scores"][name] = {"error": str(e)}

        # 分组统计 (如果数据带有 labels / groups 字段)
        group_field = self.args.group_by
        if group_field:
            metrics["group_scores"] = self._compute_group_metrics(
                all_results, valid_idx, group_field,
            )

        return metrics

    def _compute_group_metrics(
        self,
        all_results: List[Dict],
        valid_idx: List[int],
        group_field: str,
    ) -> Dict[str, Any]:
        """按指定字段分组统计各指标。"""
        groups: Dict[str, Dict[str, List[int]]] = defaultdict(
            lambda: defaultdict(list),
        )

        for i in valid_idx:
            meta = all_results[i].get("_meta", {})
            group_val = meta.get(group_field)
            if group_val is None:
                continue
            key = str(group_val)
            groups[key]["__indices__"].append(i)

        if not groups:
            return {}

        predictions = [r["prediction"] for r in all_results]
        references = [r["reference"] for r in all_results]

        group_scores: Dict[str, Any] = {}
        for group_name, group_data in sorted(groups.items()):
            idx = group_data["__indices__"]
            g_preds = [predictions[i] for i in idx]
            g_refs = [references[i] for i in idx]
            group_scores[group_name] = {
                "count": len(idx),
                "scores": {},
            }
            for name in (self.args.metrics or ["exact_match"]):
                fn = METRIC_REGISTRY.get(name)
                if fn:
                    try:
                        group_scores[group_name]["scores"][name] = fn(g_preds, g_refs)
                    except Exception:
                        group_scores[group_name]["scores"][name] = {"error": "metric_failed"}

        return group_scores

    # ---- Output ----

    def _save_outputs(self, all_results: List[Dict], metrics: Dict[str, Any]) -> None:
        """保存 results.json, summary.json, report.txt。"""
        out_dir = self.args.output_dir
        os.makedirs(out_dir, exist_ok=True)

        # 逐条结果 (去掉 _meta 中的冗余，但保留分组字段)
        clean_results = []
        for r in all_results:
            clean = {
                "prompt": r["prompt"],
                "reference": r["reference"],
                "prediction": r["prediction"],
                "error": r["error"],
            }
            meta = r.get("_meta", {})
            if meta:
                clean["meta"] = meta
            clean_results.append(clean)

        with open(os.path.join(out_dir, "results.json"), "w", encoding="utf-8") as f:
            json.dump(clean_results, f, ensure_ascii=False, indent=2)
        print(f"Saved: {out_dir}/results.json")

        with open(os.path.join(out_dir, "summary.json"), "w", encoding="utf-8") as f:
            json.dump(metrics, f, ensure_ascii=False, indent=2)
        print(f"Saved: {out_dir}/summary.json")

        self._write_report(metrics, os.path.join(out_dir, "report.txt"))
        print(f"Saved: {out_dir}/report.txt")

    def _write_report(self, metrics: Dict[str, Any], path: str) -> None:
        """生成人类可读的报告文本。"""
        lines = [
            "=" * 64,
            "  EVALUATION REPORT",
            "=" * 64,
            f"  Model    : {self.args.model_path}",
            f"  Data     : {self.args.data_path}",
            f"  Date     : {time.strftime('%Y-%m-%d %H:%M:%S')}",
            f"  Samples  : {metrics['num_samples']} total, "
            f"{metrics['num_valid']} valid, "
            f"{metrics['num_errors']} errors",
            "",
            "-" * 64,
            "  OVERALL METRICS",
            "-" * 64,
        ]

        for name, result in metrics.get("scores", {}).items():
            lines.append(f"  [{name}]")
            if result.get("error"):
                lines.append(f"    ERROR: {result['error']}")
                continue

            score = result.get("score", "N/A")
            if isinstance(score, (int, float)):
                lines.append(f"    score:        {score:.4f}  ({score*100:.2f}%)")
            else:
                lines.append(f"    score:        {score}")

            if "correct" in result:
                lines.append(f"    correct/total: {int(result['correct'])}/{int(result['total'])}")

            field_scores = result.get("field_scores")
            if field_scores:
                lines.append("    field_scores:")
                for field, fs in field_scores.items():
                    lines.append(f"      {field:30s} {fs:.4f}  ({fs*100:.1f}%)")

            bleu_keys = [k for k in result if k.startswith("bleu")]
            if bleu_keys:
                for bk in sorted(bleu_keys):
                    lines.append(f"    {bk}:           {result[bk]:.4f}")

            lines.append("")

        # 分组统计
        group_scores = metrics.get("group_scores")
        if group_scores:
            lines.append("-" * 64)
            lines.append(f"  GROUP SCORES (by '{self.args.group_by}')")
            lines.append("-" * 64)
            for gname, gdata in group_scores.items():
                lines.append(f"  [{gname}]  ({gdata['count']} samples)")
                for mname, mresult in gdata.get("scores", {}).items():
                    score = mresult.get("score", "N/A")
                    if isinstance(score, (int, float)):
                        lines.append(f"    {mname}: {score:.4f}  ({score*100:.2f}%)")
                    else:
                        lines.append(f"    {mname}: {score}")
                lines.append("")

        # 错误汇总
        if metrics.get("num_errors", 0) > 0:
            lines.append("-" * 64)
            lines.append("  ERROR DISTRIBUTION")
            lines.append("-" * 64)

        lines.append("=" * 64)

        with open(path, "w", encoding="utf-8") as f:
            f.write("\n".join(lines) + "\n")

    def _print_summary(self, metrics: Dict[str, Any]) -> None:
        """终端输出简短汇总。"""
        print()
        print("=" * 64)
        print(f"  Done — {metrics['num_valid']}/{metrics['num_samples']} valid, "
              f"{metrics['num_errors']} errors")
        print("=" * 64)
        for name, result in metrics.get("scores", {}).items():
            score = result.get("score", "N/A")
            if isinstance(score, (int, float)):
                print(f"  {name:20s} {score:.4f}  ({score*100:.2f}%)")
            else:
                print(f"  {name:20s} {score}")
        if metrics.get("group_scores"):
            print(f"  --- Group scores available ({len(metrics['group_scores'])} groups) ---")
        print("=" * 64)


# ============================================================================
# Helpers
# ============================================================================

def _extract_meta(sample: Dict[str, Any]) -> Dict[str, Any]:
    """提取非 prompt/output 字段作为 meta 信息（用于分组统计）。"""
    return {k: v for k, v in sample.items() if k not in ("instruction", "input", "output")}


# ============================================================================
# CLI
# ============================================================================

def _make_parser() -> argparse.ArgumentParser:
    available = ", ".join(METRIC_REGISTRY.keys())
    return argparse.ArgumentParser(
        description="NPU Distributed Evaluation Tool — 数据并行、模块化的模型评测框架",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=f"""
Examples:
  python eval_tool.py -m ./model -d data.jsonl -o ./results
  python eval_tool.py -m ./model -d data.jsonl --metrics exact_match json_accuracy
  torchrun --nproc_per_node=8 eval_tool.py -m ./model -d data.jsonl -o ./results
  python eval_tool.py -m ./model -d data.jsonl --prompt_template chatml \\
      --group_by category --batch_size 16

Available metrics:
  {available}
""",
    )

    # Required
    parser = argparse.ArgumentParser(add_help=False)
    parser.add_argument("-m", "--model_path", required=True, help="HuggingFace 模型路径")
    parser.add_argument("-d", "--data_path", required=True, help="JSONL 数据文件路径")
    parser.add_argument("-o", "--output_dir", default="./eval_results", help="输出目录")

    # Metrics
    parser.add_argument("--metrics", nargs="+", default=["exact_match"],
                        help="要计算的评测指标 (default: exact_match)")
    parser.add_argument("--group_by", default=None,
                        help="按数据中的某字段分组统计 (如 category, labels.level1)")

    # Prompt
    parser.add_argument("--prompt_template", default="default",
                        help="Prompt 模板: default, chatml, qwen, 或自定义字符串")

    # Generation
    parser.add_argument("--max_new_tokens", type=int, default=256)
    parser.add_argument("--max_input_length", type=int, default=2048)
    parser.add_argument("--temperature", type=float, default=0.0)
    parser.add_argument("--top_p", type=float, default=1.0)
    parser.add_argument("--do_sample", action="store_true",
                        help="启用采样 (默认 greedy)")
    parser.add_argument("--batch_size", type=int, default=8,
                        help="每卡推理 batch size")

    # Model loading
    parser.add_argument("--torch_dtype", default="float16",
                        choices=["float16", "bfloat16", "float32"])
    parser.add_argument("--trust_remote_code", action="store_true",
                        help="允许执行模型仓库中的自定义代码")

    return parser


def main():
    parser = _make_parser()
    args = parser.parse_args()

    # 验证指标
    unknown = [m for m in args.metrics if m not in METRIC_REGISTRY]
    if unknown:
        print(f"[WARN] Unknown metrics: {unknown}", file=sys.stderr)
    valid_metrics = [m for m in args.metrics if m in METRIC_REGISTRY]
    if not valid_metrics:
        print(f"[ERROR] No valid metrics. Available: {list(METRIC_REGISTRY.keys())}",
              file=sys.stderr)
        sys.exit(1)
    args.metrics = valid_metrics

    evaluator = Evaluator(args)
    evaluator.run()


if __name__ == "__main__":
    main()
