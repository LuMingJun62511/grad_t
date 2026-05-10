"""Direction analysis for task vectors: sign agreement, PCA, summary."""

from __future__ import annotations

import math
from typing import Dict, List, Tuple

import torch

from .task_vector import TaskVector


def sign_agreement(vec_a: TaskVector, vec_b: TaskVector) -> Dict[str, float]:
    """What fraction of parameters move in the same direction for two task vectors?

    For each parameter, checks whether sign(τ_a) == sign(τ_b).  Parameters
    whose sign is zero in either vector are excluded.

    Returns:
        dict with:
            agreement   — fraction sharing the same sign  [0, 1]
            same_pos    — fraction both positive
            same_neg    — fraction both negative
            opposite    — fraction with opposite signs
            a_only       — fraction only A has non-zero sign
            b_only       — fraction only B has non-zero sign
    """
    a = _flat(vec_a)
    b = _flat(vec_b)

    mask = (a != 0) & (b != 0)
    n = mask.sum().item()
    if n == 0:
        return {"agreement": 1.0, "same_pos": 0, "same_neg": 0,
                "opposite": 0, "a_only": 0, "b_only": 0}

    a_sign = a[mask].sign()
    b_sign = b[mask].sign()

    agree = (a_sign == b_sign).float()
    both_pos = ((a_sign > 0) & (b_sign > 0)).float()
    both_neg = ((a_sign < 0) & (b_sign < 0)).float()
    opposite = (a_sign != b_sign).float()

    total = a.numel()
    n_total = n

    return {
        "agreement": agree.mean().item(),
        "same_pos": both_pos.sum().item() / n_total,
        "same_neg": both_neg.sum().item() / n_total,
        "opposite": opposite.mean().item(),
        "a_only": ((a != 0) & (b == 0)).sum().item() / total,
        "b_only": ((a == 0) & (b != 0)).sum().item() / total,
    }


def _flat(vec: TaskVector) -> torch.Tensor:
    parts = [v.flatten() for v in vec.values()]
    if not parts:
        return torch.tensor([])
    return torch.cat(parts)


# ── Top-change direction analysis ─────────────────────────


def top_directions(vec: TaskVector, top_k: int = 10) -> List[Dict]:
    """Find the top-k parameters (by absolute change) and report their stats.

    Returns a list of dicts with keys: name, abs_mean, std, direction (+1/-1).
    """
    results = []
    for name, tensor in vec.items():
        t = tensor.float()
        abs_mean = t.abs().mean().item()
        std = t.std().item()
        # direction: +1 if most params increased, -1 if most decreased
        direction = "+" if t.mean().item() > 0 else "-"
        results.append({
            "name": name,
            "abs_mean": abs_mean,
            "std": std,
            "direction": direction,
            "n_params": t.numel(),
        })
    results.sort(key=lambda x: x["abs_mean"], reverse=True)
    return results[:top_k]


def task_direction_summary(vec: TaskVector) -> Dict:
    """Single-task direction summary.

    Returns:
        dict with:
            overall_mean     — mean of τ across all params
            overall_std      — std of τ across all params
            positive_frac    — fraction of params with τ > 0
            negative_frac    — fraction of params with τ < 0
            zero_frac        — fraction of params with τ == 0
    """
    flat = _flat(vec)
    n = flat.numel()
    return {
        "overall_mean": flat.mean().item(),
        "overall_std": flat.std().item(),
        "positive_frac": (flat > 0).sum().item() / n,
        "negative_frac": (flat < 0).sum().item() / n,
        "zero_frac": (flat == 0).sum().item() / n,
    }
