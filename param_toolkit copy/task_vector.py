"""Task vector extraction, save, and load.

A task vector is the element-wise difference: tau = theta_finetuned - theta_base.
It captures what a fine-tuning task "taught" the model.

Supports:
  - HuggingFace .pt / .bin single-file checkpoints
  - MindSpeed/Megatron distributed checkpoints (iter_XXX/mp_rank_YY/...)
"""

from __future__ import annotations

import os
from collections.abc import Callable
from typing import Dict, List, Optional, Tuple, Union

import torch

from .loader import load_checkpoint


class TaskVector:
    """Represents tau = theta_target - theta_base as a dict of name -> tensor.

    Parameters
    ----------
    base_ckpt : str or dict
        Path to base checkpoint, or a pre-loaded state_dict.
    target_ckpt : str or dict
        Path to target checkpoint, or a pre-loaded state_dict.
    filter_fn : callable, optional
        Predicate(key) -> bool to select parameters.
    model_type : str
        Model architecture key for MindSpeed checkpoints (e.g. "qwen3", "llama3").
        Ignored for HF-single checkpoints.
    tp_size : int
        Tensor-parallel size for merging MindSpeed shards.
    pp_size : int
        Pipeline-parallel size for layer indexing.
    """

    def __init__(
        self,
        base_ckpt: Union[str, Dict[str, torch.Tensor]],
        target_ckpt: Union[str, Dict[str, torch.Tensor]],
        *,
        filter_fn: Optional[Callable[[str], bool]] = None,
        model_type: str = "qwen3",
        tp_size: int = 1,
        pp_size: int = 1,
    ):
        base = (
            load_checkpoint(base_ckpt, model_type=model_type,
                            tp_size=tp_size, pp_size=pp_size)
            if isinstance(base_ckpt, str)
            else base_ckpt
        )
        target = (
            load_checkpoint(target_ckpt, model_type=model_type,
                            tp_size=tp_size, pp_size=pp_size)
            if isinstance(target_ckpt, str)
            else target_ckpt
        )

        self._vectors: Dict[str, torch.Tensor] = {}
        self._metadata: Dict[str, int] = {}

        all_keys = set(base.keys()) | set(target.keys())
        for name in sorted(all_keys):
            if name not in base:
                self._vectors[name] = target[name].clone()
                continue
            if name not in target:
                self._vectors[name] = -base[name].clone()
                continue
            if filter_fn is not None and not filter_fn(name):
                continue
            self._vectors[name] = target[name].float() - base[name].float()

        self.total_params = sum(v.numel() for v in self._vectors.values())

    # ── dict-like access ──────────────────────────────────
    def keys(self):
        return self._vectors.keys()

    def items(self):
        return self._vectors.items()

    def values(self):
        return self._vectors.values()

    def __getitem__(self, name: str) -> torch.Tensor:
        return self._vectors[name]

    def __len__(self) -> int:
        return len(self._vectors)

    def __repr__(self) -> str:
        return f"TaskVector({len(self)} tensors, {self.total_params:,} params)"

    # ── I/O ───────────────────────────────────────────────
    def save(self, path: str) -> None:
        os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
        torch.save({"vectors": self._vectors, "metadata": self._metadata}, path)

    @classmethod
    def load(cls, path: str) -> "TaskVector":
        obj = cls.__new__(cls)
        data = torch.load(path, map_location="cpu", weights_only=True)
        obj._vectors = data["vectors"]
        obj._metadata = data.get("metadata", {})
        obj.total_params = sum(v.numel() for v in obj._vectors.values())
        return obj

    # ── aliases ───────────────────────────────────────────
    @classmethod
    def from_checkpoints(
        cls,
        base_ckpt: Union[str, Dict],
        target_ckpt: Union[str, Dict],
        **kwargs,
    ) -> "TaskVector":
        return cls(base_ckpt, target_ckpt, **kwargs)

    @classmethod
    def from_state_dicts(
        cls,
        base: Dict[str, torch.Tensor],
        target: Dict[str, torch.Tensor],
        **kwargs,
    ) -> "TaskVector":
        obj = cls.__new__(cls)
        obj._vectors = {}
        for name in base:
            obj._vectors[name] = target[name].float() - base[name].float()
        obj.total_params = sum(v.numel() for v in obj._vectors.values())
        obj._metadata = {}
        return obj
