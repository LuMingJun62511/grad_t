"""Multi-task compatibility analysis.

Given N task vectors τ₁ … τₙ, build a pairwise cosine-similarity matrix
and report which task pairs are compatible / conflicting.
"""

from __future__ import annotations

import math
from typing import Dict, List, Optional, Tuple

import torch

from .task_vector import TaskVector
from .distance import cosine_similarity


def compatibility_matrix(
    task_vectors: Dict[str, TaskVector],
    *,
    min_similarity: float = 0.3,
) -> Dict:
    """Compute N×N cosine-similarity matrix and flag compatible/conflicting pairs.

    Args:
        task_vectors:  {task_name: TaskVector}
        min_similarity: threshold above which two tasks are "compatible"

    Returns:
        dict with:
            matrix      — list of lists [[cos(A,A), cos(A,B), …], …]
            labels      — task names in matrix order
            compatible  — [(task_a, task_b, cos)]  cos >= min_similarity
            conflicting — [(task_a, task_b, cos)]  cos < 0
            neutral     — [(task_a, task_b, cos)]  otherwise
    """
    labels = sorted(task_vectors.keys())
    n = len(labels)
    mat = [[1.0] * n for _ in range(n)]

    compatible: List[Tuple[str, str, float]] = []
    conflicting: List[Tuple[str, str, float]] = []
    neutral: List[Tuple[str, str, float]] = []

    for i in range(n):
        for j in range(i + 1, n):
            cos = cosine_similarity(task_vectors[labels[i]], task_vectors[labels[j]])
            mat[i][j] = cos
            mat[j][i] = cos
            pair = (labels[i], labels[j], round(cos, 4))
            if cos >= min_similarity:
                compatible.append(pair)
            elif cos < 0:
                conflicting.append(pair)
            else:
                neutral.append(pair)

    # round for readability
    mat = [[round(v, 4) for v in row] for row in mat]

    return {
        "matrix": mat,
        "labels": labels,
        "compatible": compatible,
        "conflicting": conflicting,
        "neutral": neutral,
    }


def conflict_report(result: Dict) -> str:
    """Render a compatibility_matrix result as a human-readable string."""
    lines = []
    labels = result["labels"]
    n = len(labels)

    # header
    header = "        " + "  ".join(f"{l:>8}" for l in labels)
    lines.append(header)
    lines.append("-" * len(header))

    for i, label in enumerate(labels):
        row = f"{label:>8} " + "  ".join(
            f"{result['matrix'][i][j]:8.4f}" for j in range(n)
        )
        lines.append(row)

    lines.append("")

    if result["compatible"]:
        lines.append("Compatible (cos >= 0.3):")
        for a, b, c in result["compatible"]:
            lines.append(f"  {a}  ↔  {b}   cos = {c:.4f}")

    if result["conflicting"]:
        lines.append("Conflicting (cos < 0):")
        for a, b, c in result["conflicting"]:
            lines.append(f"  {a}  ✗  {b}   cos = {c:.4f}")

    if result["neutral"]:
        lines.append("Neutral (0 <= cos < 0.3):")
        for a, b, c in result["neutral"]:
            lines.append(f"  {a}  —  {b}   cos = {c:.4f}")

    return "\n".join(lines)
