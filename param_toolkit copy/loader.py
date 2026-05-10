"""Unified checkpoint loader for HF and MindSpeed/Megatron formats.

Auto-detects checkpoint format and loads into a flat, HF-keyed state_dict
suitable for TaskVector construction.

Supported formats:
  hf_single    — single .pt / .bin  (our v1/v2 format, torch.save(state_dict))
  megatron     — iter_XXX/mp_rank_YY/model_optim_rng.pt  (MindSpeed / Megatron-LM)
"""

from __future__ import annotations

import os
import re
from typing import Dict, List, Optional, Tuple

import torch

from .key_mapping import megatron_to_hf_state_dict, MODEL_PRESETS


# ── Format detection ────────────────────────────────────────


class CheckpointFormat:
    HF_SINGLE = "hf_single"
    MEGATRON = "megatron"
    UNKNOWN = "unknown"


def detect_format(path: str) -> str:
    """Auto-detect the checkpoint format.

    Heuristics:
      - path is a .pt/.bin file                        → hf_single
      - path contains iter_*/mp_rank_*/model_optim_rng.pt → megatron
      - path is a directory with iter_* subdirs         → megatron (root dir)
      - path is a directory with mp_rank_* subdirs      → megatron (iteration dir)
    """
    # Direct file: assume HF single-file format
    if os.path.isfile(path):
        if path.endswith((".pt", ".bin", ".pth")):
            return CheckpointFormat.HF_SINGLE
        return CheckpointFormat.UNKNOWN

    # Directory: check for Megatron directory structure
    if os.path.isdir(path):
        # iter_XXX pattern
        if _find_iter_dirs(path):
            return CheckpointFormat.MEGATRON

        # mp_rank_* subdirectories at the ckpt root
        entries = os.listdir(path)
        if any(re.match(r"mp_rank_\d+", e) for e in entries):
            return CheckpointFormat.MEGATRON

        # tp_rank_* subdirectories (newer Megatron)
        if any(re.match(r"tp_rank_\d+", e) for e in entries):
            return CheckpointFormat.MEGATRON

        # Check subdirectories for model_optim_rng.pt
        for entry in entries:
            subpath = os.path.join(path, entry)
            if os.path.isdir(subpath):
                sub_entries = os.listdir(subpath)
                if any("model_optim_rng" in e for e in sub_entries):
                    return CheckpointFormat.MEGATRON

    return CheckpointFormat.UNKNOWN


def _find_iter_dirs(root: str) -> List[str]:
    """Find iter_XXX subdirectories in the given path."""
    if not os.path.isdir(root):
        return []
    iters = []
    for entry in os.listdir(root):
        if re.match(r"iter_\d+", entry):
            iters.append(os.path.join(root, entry))
    return sorted(iters)


# ── Unified loader ──────────────────────────────────────────


def load_checkpoint(
    path: str,
    *,
    model_type: str = "qwen3",
    format: Optional[str] = None,
    tp_size: int = 1,
    pp_size: int = 1,
    iteration: Optional[int] = None,
) -> Dict[str, torch.Tensor]:
    """Load a checkpoint from any supported format → flat HF-keyed state_dict.

    Args:
        path:         Path to checkpoint file or directory.
        model_type:   One of MODEL_PRESETS keys, e.g. "qwen3", "llama3".
        format:       Force format ("hf_single", "megatron"). Auto-detect if None.
        tp_size:      Tensor-parallel size (for merging shards).
        pp_size:      Pipeline-parallel size (for layer offset).
        iteration:    Specific iteration to load (if path is a root dir with
                      multiple iter_XXX subdirs).  Default: latest.

    Returns:
        Flat state_dict with HuggingFace-compatible keys.
    """
    fmt = format or detect_format(path)

    if fmt == CheckpointFormat.HF_SINGLE:
        return _load_hf_single(path)
    elif fmt == CheckpointFormat.MEGATRON:
        return _load_megatron(path, model_type, tp_size, pp_size, iteration)
    else:
        raise ValueError(
            f"Unknown checkpoint format at '{path}'. "
            f"Try specifying format='megatron' or format='hf_single'."
        )


# ── HF single-file loader ────────────────────────────────────


def _load_hf_single(path: str) -> Dict[str, torch.Tensor]:
    """Load a single .pt/.bin file containing a state_dict."""
    if not os.path.isfile(path):
        # Try common filenames inside a directory
        for name in ["model.pt", "pytorch_model.bin", "model.safetensors"]:
            candidate = os.path.join(path, name)
            if os.path.isfile(candidate):
                path = candidate
                break
        else:
            raise FileNotFoundError(
                f"No model file found in '{path}'. "
                f"Expected model.pt, pytorch_model.bin, or model.safetensors."
            )

    data = torch.load(path, map_location="cpu", weights_only=True)

    # If the loaded object is a dict with 'model' key, extract it
    if isinstance(data, dict) and "model" in data and isinstance(data["model"], dict):
        return data["model"]

    if isinstance(data, dict):
        # Check if it looks like a state_dict (first value is a tensor)
        for v in data.values():
            if isinstance(v, torch.Tensor):
                return data
            break

    raise ValueError(
        f"File '{path}' does not contain a recognizable state_dict."
    )


# ── Megatron/MindSpeed loader ────────────────────────────────


def _load_megatron(
    path: str,
    model_type: str,
    tp_size: int,
    pp_size: int,
    iteration: Optional[int],
) -> Dict[str, torch.Tensor]:
    """Load a Megatron/MindSpeed distributed checkpoint.

    Directory layout expected:
      path/                        ← root (or specific iter dir)
        iter_0000100/
          mp_rank_00/
            model_optim_rng.pt
          mp_rank_01/
            model_optim_rng.pt
          ...

    Or (newer format):
      path/
        mp_rank_00/
          model_optim_rng.pt
        mp_rank_01/
          model_optim_rng.pt
    """
    ckpt_dir = path

    # If path points to an iter dir, use it directly
    if os.path.isdir(path):
        entries = os.listdir(path)
        if any(re.match(r"mp_rank_\d+", e) for e in entries) or \
           any(re.match(r"tp_rank_\d+", e) for e in entries):
            ckpt_dir = path
        else:
            # Look for iter_XXX subdirectories
            iter_dirs = _find_iter_dirs(path)
            if iter_dirs:
                if iteration is not None:
                    ckpt_dir = os.path.join(path, f"iter_{iteration:07d}")
                else:
                    ckpt_dir = iter_dirs[-1]  # latest
            # else: assume this IS the iter dir with mp_rank subdirs

    # Find all rank dirs
    rank_dirs = _find_rank_dirs(ckpt_dir)
    if not rank_dirs:
        raise FileNotFoundError(
            f"No rank directories (mp_rank_* / tp_rank_*) found in '{ckpt_dir}'."
        )

    print(f"  Found {len(rank_dirs)} rank directories in {ckpt_dir}")

    # Load and merge all shards
    all_shards: List[Dict[str, torch.Tensor]] = []
    for rank_dir in rank_dirs:
        shard_path = _find_model_file(rank_dir)
        if shard_path is None:
            print(f"  Warning: no model file in {rank_dir}, skipping")
            continue
        shard = _load_megatron_shard(shard_path)
        all_shards.append(shard)

    if not all_shards:
        raise FileNotFoundError(f"No valid model shards found in '{ckpt_dir}'.")

    # Detect actual TP size from loaded shards
    actual_tp = len(all_shards) if tp_size <= 1 else tp_size

    # Merge TP shards
    merged = _merge_tp_shards(all_shards, actual_tp)

    # Convert Megatron keys to HF keys
    hf_sd = megatron_to_hf_state_dict(
        merged, model_type,
        tp_rank=0, tp_size=1,  # already merged
        pp_rank=0, pp_size=pp_size,
    )

    return hf_sd


def _find_rank_dirs(ckpt_dir: str) -> List[str]:
    """Find mp_rank_* or tp_rank_* subdirectories."""
    rank_dirs = []
    if not os.path.isdir(ckpt_dir):
        return rank_dirs
    for entry in sorted(os.listdir(ckpt_dir)):
        full = os.path.join(ckpt_dir, entry)
        if os.path.isdir(full) and re.match(r"(?:mp|tp)_rank_\d+", entry):
            rank_dirs.append(full)
    return rank_dirs


def _find_model_file(rank_dir: str) -> Optional[str]:
    """Find the model checkpoint file inside a rank directory."""
    # Common names in order of preference
    candidates = [
        "model_optim_rng.pt",
        "model.pt",
        "pytorch_model.bin",
    ]
    for name in candidates:
        path = os.path.join(rank_dir, name)
        if os.path.isfile(path):
            return path

    # Also check for any .pt files
    if os.path.isdir(rank_dir):
        for entry in os.listdir(rank_dir):
            if entry.endswith(".pt"):
                return os.path.join(rank_dir, entry)

    return None


def _load_megatron_shard(shard_path: str) -> Dict[str, torch.Tensor]:
    """Load a single Megatron shard file, extracting model weights."""
    data = torch.load(shard_path, map_location="cpu", weights_only=False)

    # Try to find model state dict in the loaded data
    if isinstance(data, dict):
        # Standard Megatron: {"model": {...}, "optimizer": {...}, ...}
        if "model" in data and isinstance(data["model"], dict):
            return data["model"]
        # Nested: {"state_dict": {"model": {...}}}
        if "state_dict" in data:
            inner = data["state_dict"]
            if isinstance(inner, dict) and "model" in inner:
                return inner["model"]
        # Might be a raw state_dict (already model keys)
        for v in data.values():
            if isinstance(v, torch.Tensor):
                return data
        # Empty or unknown dict → try using it as state_dict
        return data

    raise ValueError(f"Cannot extract model weights from '{shard_path}'.")


# ── TP shard merging ─────────────────────────────────────────


def _merge_tp_shards(
    shards: List[Dict[str, torch.Tensor]],
    tp_size: int,
) -> Dict[str, torch.Tensor]:
    """Merge tensor-parallel shards into a single state_dict.

    TP sharding rules (Megatron convention):
      Column-parallel: weights split along dim=0 (QKV, FC1)
      Row-parallel:    weights split along dim=1 (attention output, FC2)

    Heuristic: if all shards have the same key with the same shape,
    we try to merge along dim=0 if total matches a common pattern
    (e.g. n*tp = full size), otherwise dim=1.
    """
    if len(shards) == 1:
        return dict(shards[0])

    merged: Dict[str, torch.Tensor] = {}
    all_keys = set()
    for shard in shards:
        all_keys.update(shard.keys())

    for key in sorted(all_keys):
        tensors = [s[key] for s in shards if key in s]

        if len(tensors) < len(shards):
            # Key missing in some shards (e.g. PP-sharded layers)
            # Take the one that exists
            merged[key] = tensors[0].clone()
            continue

        if len(tensors) == 1:
            merged[key] = tensors[0].clone()
            continue

        # Check if all same shape
        shapes = [t.shape for t in tensors]
        if all(s == shapes[0] for s in shapes):
            # Decide merge dimension based on parameter type
            merge_dim = _infer_tp_merge_dim(key)
            try:
                merged[key] = torch.cat(tensors, dim=merge_dim)
            except RuntimeError:
                merged[key] = tensors[0].clone()
        else:
            # Different shapes: keep the first one (likely PP sharding)
            merged[key] = tensors[0].clone()

    return merged


def _infer_tp_merge_dim(key: str) -> int:
    """Infer which dimension to merge for TP-sharded weights.

    Megatron convention:
      Column-parallel (dim=0): QKV, FC1 (gate+up), embedding
      Row-parallel (dim=1):    attention output (dense/proj), FC2 (down)
    """
    kl = key.lower()
    if any(x in kl for x in ["linear_proj", "dense", "fc2", "dense_4h_to_h"]):
        return 1  # row-parallel
    return 0  # column-parallel (default)


# ── Public convenience ───────────────────────────────────────


def load_model(state_dict_path: str, **kwargs) -> Dict[str, torch.Tensor]:
    """Convenience alias for load_checkpoint."""
    return load_checkpoint(state_dict_path, **kwargs)
