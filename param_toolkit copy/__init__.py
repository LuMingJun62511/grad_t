"""
param_toolkit — Task Vector analysis toolkit for model parameter-space geometry.

Usage:
    from param_toolkit import TaskVector, compute_distance, compatibility_matrix
"""

from .task_vector import TaskVector
from .distance import compute_distance, per_layer_distance, cosine_similarity
from .direction import sign_agreement, top_directions, task_direction_summary
from .compatibility import compatibility_matrix, conflict_report
from .loader import load_checkpoint, detect_format
from .key_mapping import megatron_to_hf_state_dict, hf_to_megatron_state_dict

__all__ = [
    # core
    "TaskVector",
    # distance
    "compute_distance",
    "per_layer_distance",
    "cosine_similarity",
    # direction
    "sign_agreement",
    "top_directions",
    "task_direction_summary",
    # compatibility
    "compatibility_matrix",
    "conflict_report",
    # loader (MindSpeed / Megatron adapter)
    "load_checkpoint",
    "detect_format",
    # key mapping
    "megatron_to_hf_state_dict",
    "hf_to_megatron_state_dict",
]
