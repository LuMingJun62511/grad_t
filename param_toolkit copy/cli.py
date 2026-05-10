#!/usr/bin/env python
"""CLI for param_toolkit — analyse task vectors between model checkpoints.

Usage:
    # Analyse one task vector (base → target)
    python -m param_toolkit.cli base.pt target.pt

    # Compare two task vectors
    python -m param_toolkit.cli base.pt targetA.pt targetB.pt

    # Specify a saved task vector directly
    python -m param_toolkit.cli --tv task_vec.pt
"""

from __future__ import annotations

import argparse
import json
import os
import sys

from .task_vector import TaskVector
from .distance import compute_distance, per_layer_distance, cosine_similarity
from .direction import (
    sign_agreement,
    top_directions,
    task_direction_summary,
)
from .compatibility import compatibility_matrix, conflict_report


def _print_header(text: str) -> None:
    print(f"\n{'='*60}")
    print(f"  {text}")
    print(f"{'='*60}")


def _print_json(obj: dict | list) -> None:
    print(json.dumps(obj, indent=2, ensure_ascii=False, default=str))


def analyse_single(base: str, target: str) -> None:
    """Analyse one τ = target − base."""
    tv = TaskVector(base, target)

    _print_header("1. Global Distance")
    dist = compute_distance(tv)
    _print_json(dist)

    _print_header("2. Direction Summary")
    ds = task_direction_summary(tv)
    _print_json(ds)

    _print_header("3. Per-Layer Breakdown")
    layers = per_layer_distance(tv)
    for row in layers:
        print(
            f"  {row['layer']:>20s}  l2={row['l2']:12.4f}  "
            f"rms={row['rms']:.6f}  params={row['n_params']:,}"
        )

    _print_header("4. Top-Changed Parameters (by abs mean)")
    top = top_directions(tv, top_k=10)
    for i, row in enumerate(top, 1):
        print(
            f"  {i:2d}. {row['name']:<50s}  |Δ|={row['abs_mean']:.6f}  "
            f"σ={row['std']:.6f}  dir={row['direction']}"
        )

    print()


def analyse_pair(base: str, target_a: str, target_b: str) -> None:
    """Compare two task vectors τ_A and τ_B."""
    tv_a = TaskVector(base, target_a)
    tv_b = TaskVector(base, target_b)

    _print_header("1. Per-Task Distances")
    for label, tv in [("Task A", tv_a), ("Task B", tv_b)]:
        dist = compute_distance(tv)
        print(f"  {label}: l2={dist['l2']:.4f}, rms={dist['rms']:.6f}")

    _print_header("2. Cosine Similarity")
    cos = cosine_similarity(tv_a, tv_b)
    print(f"  cos(τ_A, τ_B) = {cos:.4f}")

    _print_header("3. Sign Agreement")
    sa = sign_agreement(tv_a, tv_b)
    _print_json(sa)

    _print_header("4. Compatibility Matrix")
    result = compatibility_matrix({"task_A": tv_a, "task_B": tv_b})
    print(conflict_report(result))

    print()


def main() -> None:
    parser = argparse.ArgumentParser(
        description="param_toolkit — analyse parameter-space task vectors"
    )
    parser.add_argument(
        "ckpts", nargs="*", help="checkpoints: [base target] or [base targetA targetB]"
    )
    parser.add_argument(
        "--tv", type=str, help="path to a pre-saved task vector (.pt)"
    )
    parser.add_argument(
        "--save-tv", type=str, help="save the computed task vector to path"
    )
    args = parser.parse_args()

    if args.tv:
        tv = TaskVector.load(args.tv)
        _print_header("Loaded Task Vector")
        dist = compute_distance(tv)
        _print_json(dist)
        return

    if len(args.ckpts) == 1:
        # Assume the single ckpt is a task vector file
        tv = TaskVector.load(args.ckpts[0])
        _print_header("Loaded Task Vector")
        dist = compute_distance(tv)
        _print_json(dist)
    elif len(args.ckpts) == 2:
        base, target = args.ckpts
        tv = TaskVector(base, target)
        if args.save_tv:
            tv.save(args.save_tv)
            print(f"Task vector saved to {args.save_tv}")
        analyse_single(base, target)
    elif len(args.ckpts) == 3:
        base, t_a, t_b = args.ckpts
        analyse_pair(base, t_a, t_b)
    else:
        print(
            "Usage:  python -m param_toolkit.cli base.pt target.pt\n"
            "        python -m param_toolkit.cli base.pt targetA.pt targetB.pt\n"
            "        python -m param_toolkit.cli --tv saved_tv.pt"
        )
        sys.exit(1)


if __name__ == "__main__":
    main()
