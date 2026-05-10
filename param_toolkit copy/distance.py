"""Distance metrics in parameter space: L2 norm, cosine, per-layer breakdown."""

from __future__ import annotations

import math
from typing import Dict, List, Tuple

import torch

from .task_vector import TaskVector


def _flat(vec: TaskVector) -> torch.Tensor:
    """Flatten all task-vector tensors into a single 1-D tensor."""
    parts = [v.flatten() for v in vec.values()]
    if not parts:
        return torch.tensor([])
    return torch.cat(parts)


def _group_by_layer(vec: TaskVector) -> Dict[str, torch.Tensor]:
    """Group parameters by layer prefix (e.g. 'model.layers.0.*' → 'layers.0')."""
    groups: Dict[str, List[torch.Tensor]] = {}
    for name, tensor in vec.items():
        # extract layer-like prefix, e.g. model.layers.5 or lm_head
        parts = name.split(".")
        if "layers" in parts:
            idx = parts.index("layers")
            key = ".".join(parts[idx : idx + 2])  # "layers.N"
        elif "embed" in name.lower():
            key = "embeddings"
        elif "lm_head" in name.lower() or "output" in name.lower():
            key = "head"
        elif "norm" in name.lower():
            key = "norms"
        else:
            key = "other"
        groups.setdefault(key, []).append(tensor.flatten())
    return {k: torch.cat(v) for k, v in groups.items()}


# ── Whole-model metrics ───────────────────────────────────


def compute_distance(vec: TaskVector) -> Dict[str, float]:
    """Compute global distance metrics for a task vector.

    Returns:
        dict with keys: l1, l2, rms, cosine_with_sign (proportion of
        parameters that increased vs decreased).
    """
    flat = _flat(vec)
    l1 = flat.abs().sum().item()
    l2_sq = flat.dot(flat).item()
    l2 = math.sqrt(l2_sq)
    n = flat.numel()
    rms = math.sqrt(l2_sq / n) if n else 0.0

    increased = (flat > 0).sum().item()
    decreased = (flat < 0).sum().item()
    unchanged = (flat == 0).sum().item()

    return {
        "l1": l1,
        "l2": l2,
        "rms": rms,
        "n_params": n,
        "increased_pct": increased / n * 100,
        "decreased_pct": decreased / n * 100,
        "unchanged_pct": unchanged / n * 100,
    }


def cosine_similarity(vec_a: TaskVector, vec_b: TaskVector) -> float:
    """Cosine similarity between two task vectors (whole-model)."""
    a = _flat(vec_a)
    b = _flat(vec_b)
    dot = a.dot(b).item()
    norm_a = a.norm().item()
    norm_b = b.norm().item()
    if norm_a == 0 or norm_b == 0:
        return 0.0
    # Clamp to [-1, 1] — floating-point accumulation over 100M+ params
    # can push the raw dot/(norm_a*norm_b) fractionally outside the interval.
    raw = dot / (norm_a * norm_b)
    return max(-1.0, min(1.0, raw))


# ── Per-layer breakdown ───────────────────────────────────


def per_layer_distance(vec: TaskVector) -> List[Dict]:
    """L2 distance and RMS broken down by layer.

    Returns a list of dicts sorted by layer index, each containing:
        layer, l2, rms, n_params.
    """
    groups = _group_by_layer(vec)
    results = []
    for key, flat in sorted(groups.items()):
        l2 = flat.norm().item()
        n = flat.numel()
        rms = math.sqrt(l2 * l2 / n) if n else 0.0
        results.append({"layer": key, "l2": l2, "rms": rms, "n_params": n})
    return results
