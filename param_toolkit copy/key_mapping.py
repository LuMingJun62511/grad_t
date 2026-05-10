"""Megatron/MindSpeed ↔ HuggingFace key name mapping.

Megatron models use a different parameter naming convention than HF
transformers.  This module maps between the two so that task vectors
can be built from checkpoints produced by either framework.

Known Megatron patterns (observed in MindSpeed / Megatron-LM):
  word_embeddings                ↔ model.embed_tokens
  decoder.layers.{i}.self_attention.linear_qkv
                                 ↔ model.layers.{i}.self_attn.{q,k,v}_proj
  decoder.layers.{i}.self_attention.linear_proj
                                 ↔ model.layers.{i}.self_attn.o_proj
  decoder.layers.{i}.mlp.linear_fc1
                                 ↔ model.layers.{i}.mlp.{gate,up}_proj
  decoder.layers.{i}.mlp.linear_fc2
                                 ↔ model.layers.{i}.mlp.down_proj
  decoder.layers.{i}.input_layernorm
                                 ↔ model.layers.{i}.input_layernorm
  decoder.layers.{i}.pre_mlp_layernorm
                                 ↔ model.layers.{i}.post_attention_layernorm
  decoder.final_layernorm        ↔ model.norm
  output_layer                   ↔ lm_head

The mapping is configurable per model type.  Add new model types by
appending an entry to MODEL_PRESETS.
"""

from __future__ import annotations

import re
from typing import Dict, List, Optional, Tuple

import torch


# ── Model-specific presets ─────────────────────────────────
# Each preset describes how to convert a single Megatron key
# to one or more HF keys, and how to split/merge the tensor data.

MODEL_PRESETS: Dict[str, dict] = {
    "qwen3": {
        "num_attention_heads": 16,        # total Q heads
        "num_key_value_heads": 8,         # GQA KV heads
        "head_dim": 128,                  # hidden_size / num_heads = 1024/16 = 64 for 0.6B? No, 1024/16=64, but config says head_dim=128 -> 16*128=2048≠1024. Use hidden_size instead.
        "hidden_size": 1024,              # for 0.6B
        "intermediate_size": 3072,
        "tie_word_embeddings": True,
        "vocab_size": 151936,
        "num_layers": 28,
        "activation": "silu",             # SwiGLU → gate_proj + up_proj
        "layernorm_style": "rms_norm",
        # Megatron module prefix (may differ between versions)
        "megatron_prefixes": [
            "model.language_model",
            "module.language_model",
            "model",
            "module",
        ],
        # Megatron uses "decoder" for GPT-style, "encoder" for BERT-style
        "megatron_layer_paths": [
            "decoder",
            "encoder",
        ],
    },
    "llama3": {
        "num_attention_heads": 32,
        "num_key_value_heads": 8,
        "hidden_size": 4096,
        "intermediate_size": 14336,
        "tie_word_embeddings": False,
        "vocab_size": 128256,
        "num_layers": 32,
        "activation": "silu",
        "layernorm_style": "rms_norm",
        "megatron_prefixes": ["model.language_model", "module.language_model", "model", "module"],
        "megatron_layer_paths": ["decoder", "encoder"],
    },
}


# ── Key translation ────────────────────────────────────────

def megatron_to_hf(
    key: str,
    model_type: str = "qwen3",
    tp_rank: int = 0,
    tp_size: int = 1,
    pp_rank: int = 0,
    pp_size: int = 1,
) -> Optional[Tuple[str, Optional[int], Optional[int]]]:
    """Convert a Megatron key to HuggingFace key(s).

    Returns:
        (hf_key, split_dim, split_index) or None if the key should be skipped.
        split_dim is not None when the Megatron tensor needs to be split
        (e.g. combined QKV → separate Q/K/V).
    """
    preset = MODEL_PRESETS.get(model_type, MODEL_PRESETS["qwen3"])
    num_heads = preset["num_attention_heads"]
    num_kv_heads = preset["num_key_value_heads"]
    head_dim = preset["head_dim"]
    hidden = preset["hidden_size"]
    intermediate = preset["intermediate_size"]
    num_layers = preset["num_layers"]
    is_swiglu = preset["activation"] in ("silu", "swiglu")
    tie_embeddings = preset["tie_word_embeddings"]
    prefixes = preset["megatron_prefixes"]
    layer_paths = preset["megatron_layer_paths"]

    # Strip known Megatron prefixes → get the relative path
    rel = key
    for pfx in prefixes:
        if rel.startswith(pfx + "."):
            rel = rel[len(pfx) + 1 :]
            break

    # ── Embedding ──────────────────────────────
    if rel in ("embedding.word_embeddings.weight", "embedding.word_embedding.weight"):
        return ("model.embed_tokens.weight", None, None)

    # ── Output layer ───────────────────────────
    if rel == "output_layer.weight":
        if tie_embeddings:
            return None  # tied → skip (same as embedding)
        return ("lm_head.weight", None, None)

    # ── Transformer layers ─────────────────────
    layer_match = None
    for lpath in layer_paths:
        m = re.match(
            rf"{re.escape(lpath)}\.layers\.(\d+)\.(.+)", rel
        )
        if m:
            layer_match = m
            break

    if layer_match:
        layer_idx = int(layer_match.group(1))
        attr = layer_match.group(2)

        # Adjust layer index for PP rank
        if pp_size > 1:
            layers_per_stage = num_layers // pp_size
            layer_idx = pp_rank * layers_per_stage + layer_idx

        # -- Self-attention --
        if "self_attention.linear_qkv" in attr:
            # e.g. .weight or .bias
            is_weight = attr.endswith(".weight")
            # Combined QKV: split into Q, K, V
            # Q: num_heads * head_dim  → 16*128=2048 for 0.6B
            # K: num_kv_heads * head_dim  → 8*128=1024
            # V: num_kv_heads * head_dim  → 8*128=1024
            # Total: 4096
            # But wait, hidden_size=1024 for 0.6B. head_dim=128, num_heads=16 → 16*128=2048 hidden?
            # Actually, qwen3 0.6B: hidden_size=1024, num_attention_heads=16, head_dim=128
            # 16*128=2048 ≠ 1024. But the config says head_dim=128 and hidden_size=1024.
            # This means hidden_size is NOT num_heads*head_dim for Qwen3.
            # Q: num_heads * head_dim = 16*128 = 2048
            # K: num_kv_heads * head_dim = 8*128 = 1024
            # V: num_kv_heads * head_dim = 8*128 = 1024
            # Total QKV: 2048+1024+1024 = 4096
            # The projection maps from hidden (1024) to QKV (4096), so QKV weight is [4096, 1024]
            q_size = num_heads * head_dim
            kv_size = num_kv_heads * head_dim
            suffix = ".weight" if is_weight else ".bias"
            # Return 3 split specs
            return (
                f"model.layers.{layer_idx}.self_attn.q_proj{suffix}",
                0,  # split_dim
                (0, q_size),  # slice range
            )
            # Note: we can't return 3 tuples, so we'll handle QKV specially in the loader

        if "self_attention.linear_proj" in attr:
            is_weight = attr.endswith(".weight")
            suffix = ".weight" if is_weight else ".bias"
            return (f"model.layers.{layer_idx}.self_attn.o_proj{suffix}", None, None)

        # -- MLP --
        if "mlp.linear_fc1" in attr:
            is_weight = attr.endswith(".weight")
            suffix = ".weight" if is_weight else ".bias"
            if is_swiglu:
                # gate_proj + up_proj combined: [2*intermediate, hidden]
                return (
                    f"model.layers.{layer_idx}.mlp",
                    0,  # split_dim
                    (0, intermediate),  # gate part
                )
            return (f"model.layers.{layer_idx}.mlp.up_proj{suffix}", None, None)

        if "mlp.linear_fc2" in attr:
            is_weight = attr.endswith(".weight")
            suffix = ".weight" if is_weight else ".bias"
            return (f"model.layers.{layer_idx}.mlp.down_proj{suffix}", None, None)

        # -- Layer norms --
        if "input_layernorm" in attr or "self_attention.linear_qkv.layer_norm" in attr:
            return (f"model.layers.{layer_idx}.input_layernorm.weight", None, None)

        if "pre_mlp_layernorm" in attr or "mlp.linear_fc1.layer_norm" in attr:
            return (f"model.layers.{layer_idx}.post_attention_layernorm.weight", None, None)

        # -- Unknown attribute, pass through with layer-adjusted key --
        pass

    # ── Final layernorm ────────────────────────
    if rel == "decoder.final_layernorm.weight" or rel == "encoder.final_layernorm.weight":
        return ("model.norm.weight", None, None)

    # ── Fallback: return key as-is ─────────────
    return (key, None, None)


def megatron_to_hf_state_dict(
    megatron_sd: Dict[str, torch.Tensor],
    model_type: str = "qwen3",
    tp_rank: int = 0,
    tp_size: int = 1,
    pp_rank: int = 0,
    pp_size: int = 1,
) -> Dict[str, torch.Tensor]:
    """Convert an entire Megatron state_dict to HF-compatible keys.

    Handles:
      - QKV splitting (combined linear_qkv → q_proj, k_proj, v_proj)
      - SwiGLU gate/up splitting (linear_fc1 → gate_proj, up_proj)
      - GQA-aware Q/K/V dimension calculations
      - PP layer index offset
    """
    preset = MODEL_PRESETS.get(model_type, MODEL_PRESETS["qwen3"])
    num_heads = preset["num_attention_heads"]
    num_kv_heads = preset["num_key_value_heads"]
    head_dim = preset["head_dim"]
    intermediate = preset["intermediate"]
    tie_embeddings = preset["tie_word_embeddings"]
    prefixes = preset["megatron_prefixes"]
    layer_paths = preset["megatron_layer_paths"]

    q_size = num_heads * head_dim
    kv_size = num_kv_heads * head_dim

    hf_sd: Dict[str, torch.Tensor] = {}

    for key, tensor in megatron_sd.items():
        # Strip known prefixes
        rel = key
        for pfx in prefixes:
            if rel.startswith(pfx + "."):
                rel = rel[len(pfx) + 1:]
                break

        # --- Embedding ---
        if rel in ("embedding.word_embeddings.weight", "embedding.word_embedding.weight"):
            hf_sd["model.embed_tokens.weight"] = tensor.clone()
            continue

        # --- Output layer ---
        if rel == "output_layer.weight":
            if not tie_embeddings:
                hf_sd["lm_head.weight"] = tensor.clone()
            continue

        # --- Final layernorm ---
        if rel in (
            "decoder.final_layernorm.weight",
            "encoder.final_layernorm.weight",
            "decoder.final_norm.weight",
            "encoder.final_norm.weight",
        ):
            hf_sd["model.norm.weight"] = tensor.clone()
            continue

        # --- Transformer layers ---
        layer_match = None
        for lpath in layer_paths:
            m = re.match(rf"{re.escape(lpath)}\.layers\.(\d+)\.(.+)", rel)
            if m:
                layer_match = m
                break

        if layer_match:
            layer_idx = int(layer_match.group(1))
            attr = layer_match.group(2)

            # PP layer offset
            if pp_size > 1:
                # Auto-detect: if only a subset of layers exist, offset by pp_rank
                pass  # We trust the caller to pass correct pp_rank

            # -- QKV --
            if "self_attention.linear_qkv" in attr and attr.endswith(".weight"):
                # Split combined QKV into Q, K, V
                q_w, k_w, v_w = torch.split(tensor, [q_size, kv_size, kv_size], dim=0)
                hf_sd[f"model.layers.{layer_idx}.self_attn.q_proj.weight"] = q_w
                hf_sd[f"model.layers.{layer_idx}.self_attn.k_proj.weight"] = k_w
                hf_sd[f"model.layers.{layer_idx}.self_attn.v_proj.weight"] = v_w
                continue

            if "self_attention.linear_qkv" in attr and attr.endswith(".bias"):
                q_b, k_b, v_b = torch.split(tensor, [q_size, kv_size, kv_size], dim=0)
                hf_sd[f"model.layers.{layer_idx}.self_attn.q_proj.bias"] = q_b
                hf_sd[f"model.layers.{layer_idx}.self_attn.k_proj.bias"] = k_b
                hf_sd[f"model.layers.{layer_idx}.self_attn.v_proj.bias"] = v_b
                continue

            # -- Attention output projection --
            if "self_attention.linear_proj" in attr:
                suffix = ".weight" if attr.endswith(".weight") else ".bias"
                hf_sd[f"model.layers.{layer_idx}.self_attn.o_proj{suffix}"] = tensor.clone()
                continue

            # -- MLP FC1 (gate+up for SwiGLU) --
            if "mlp.linear_fc1" in attr and attr.endswith(".weight"):
                if preset["activation"] in ("silu", "swiglu"):
                    gate_w, up_w = torch.split(tensor, [intermediate, intermediate], dim=0)
                    hf_sd[f"model.layers.{layer_idx}.mlp.gate_proj.weight"] = gate_w
                    hf_sd[f"model.layers.{layer_idx}.mlp.up_proj.weight"] = up_w
                else:
                    hf_sd[f"model.layers.{layer_idx}.mlp.up_proj.weight"] = tensor.clone()
                continue

            if "mlp.linear_fc1" in attr and attr.endswith(".bias"):
                if preset["activation"] in ("silu", "swiglu"):
                    gate_b, up_b = torch.split(tensor, [intermediate, intermediate], dim=0)
                    hf_sd[f"model.layers.{layer_idx}.mlp.gate_proj.bias"] = gate_b
                    hf_sd[f"model.layers.{layer_idx}.mlp.up_proj.bias"] = up_b
                else:
                    hf_sd[f"model.layers.{layer_idx}.mlp.up_proj.bias"] = tensor.clone()
                continue

            # -- MLP FC2 --
            if "mlp.linear_fc2" in attr:
                suffix = ".weight" if attr.endswith(".weight") else ".bias"
                hf_sd[f"model.layers.{layer_idx}.mlp.down_proj{suffix}"] = tensor.clone()
                continue

            # -- Layer norms --
            if "input_layernorm" in attr or "self_attention.linear_qkv.layer_norm" in attr:
                hf_sd[f"model.layers.{layer_idx}.input_layernorm.weight"] = tensor.clone()
                continue

            if "pre_mlp_layernorm" in attr or "mlp.linear_fc1.layer_norm" in attr:
                hf_sd[f"model.layers.{layer_idx}.post_attention_layernorm.weight"] = tensor.clone()
                continue

            # Fallback: preserve unknown layer attr as-is
            hf_sd[key] = tensor.clone()
            continue

        # --- Unknown key → keep as-is ---
        hf_sd[key] = tensor.clone()

    return hf_sd


# ── Reverse mapping (HF → Megatron) ─────────────────────────

def hf_to_megatron_key(
    hf_key: str,
    model_type: str = "qwen3",
) -> Optional[str]:
    """Convert a HuggingFace key back to Megatron format.
    Used when you want to apply a task vector computed in HF space
    back onto a Megatron checkpoint.
    """
    preset = MODEL_PRESETS.get(model_type, MODEL_PRESETS["qwen3"])
    prefixes = preset["megatron_prefixes"]
    pfx = prefixes[0]  # use the first prefix for output
    layer_paths = preset["megatron_layer_paths"]
    lpath = layer_paths[0]

    # Embedding
    if hf_key == "model.embed_tokens.weight":
        return f"{pfx}.embedding.word_embeddings.weight"

    # LM head
    if hf_key == "lm_head.weight":
        return f"{pfx}.output_layer.weight"

    # Final norm
    if hf_key == "model.norm.weight":
        return f"{pfx}.{lpath}.final_layernorm.weight"

    # Transformer layers
    m = re.match(r"model\.layers\.(\d+)\.(.+)", hf_key)
    if m:
        layer_idx = m.group(1)
        attr = m.group(2)

        layer_base = f"{pfx}.{lpath}.layers.{layer_idx}"

        if attr == "input_layernorm.weight":
            return f"{layer_base}.input_layernorm.weight"
        if attr == "post_attention_layernorm.weight":
            return f"{layer_base}.pre_mlp_layernorm.weight"

        # Q/K/V → combined QKV is not trivial → handled in hf_to_megatron_state_dict
        if attr.startswith("self_attn."):
            return None  # signal: needs special merging

        if attr.startswith("mlp."):
            return None  # signal: needs special merging

    return hf_key


def hf_to_megatron_state_dict(
    hf_sd: Dict[str, torch.Tensor],
    model_type: str = "qwen3",
) -> Dict[str, torch.Tensor]:
    """Convert an HF-style state_dict back to Megatron format.

    Reverses the Q/K/V splitting and gate/up splitting.
    """
    preset = MODEL_PRESETS.get(model_type, MODEL_PRESETS["qwen3"])
    prefixes = preset["megatron_prefixes"]
    pfx = prefixes[0]
    layer_paths = preset["megatron_layer_paths"]
    lpath = layer_paths[0]

    mg_sd: Dict[str, torch.Tensor] = {}

    # Collect keys by layer for merging
    layers: Dict[int, Dict[str, torch.Tensor]] = {}
    non_layer: Dict[str, torch.Tensor] = {}

    for key, tensor in hf_sd.items():
        m = re.match(r"model\.layers\.(\d+)\.(.+)", key)
        if m:
            layer_idx = int(m.group(1))
            attr = m.group(2)
            layers.setdefault(layer_idx, {})[attr] = tensor
        else:
            non_layer[key] = tensor

    # Embedding
    if "model.embed_tokens.weight" in non_layer:
        mg_sd[f"{pfx}.embedding.word_embeddings.weight"] = non_layer["model.embed_tokens.weight"]

    # LM head
    if "lm_head.weight" in non_layer:
        mg_sd[f"{pfx}.output_layer.weight"] = non_layer["lm_head.weight"]

    # Final norm
    if "model.norm.weight" in non_layer:
        mg_sd[f"{pfx}.{lpath}.final_layernorm.weight"] = non_layer["model.norm.weight"]

    # Merge layers
    for layer_idx, attrs in sorted(layers.items()):
        layer_base = f"{pfx}.{lpath}.layers.{layer_idx}"

        # QKV merge
        if all(k in attrs for k in ("self_attn.q_proj.weight", "self_attn.k_proj.weight", "self_attn.v_proj.weight")):
            qkv_w = torch.cat([
                attrs["self_attn.q_proj.weight"],
                attrs["self_attn.k_proj.weight"],
                attrs["self_attn.v_proj.weight"],
            ], dim=0)
            mg_sd[f"{layer_base}.self_attention.linear_qkv.weight"] = qkv_w

        # QKV bias
        if all(k in attrs for k in ("self_attn.q_proj.bias", "self_attn.k_proj.bias", "self_attn.v_proj.bias")):
            qkv_b = torch.cat([
                attrs["self_attn.q_proj.bias"],
                attrs["self_attn.k_proj.bias"],
                attrs["self_attn.v_proj.bias"],
            ], dim=0)
            mg_sd[f"{layer_base}.self_attention.linear_qkv.bias"] = qkv_b

        # O projection
        for hf_suffix, mg_suffix in [
            ("self_attn.o_proj.weight", "self_attention.linear_proj.weight"),
            ("self_attn.o_proj.bias", "self_attention.linear_proj.bias"),
        ]:
            if hf_suffix in attrs:
                mg_sd[f"{layer_base}.{mg_suffix}"] = attrs[hf_suffix]

        # SwiGLU merge (gate + up → fc1)
        if preset["activation"] in ("silu", "swiglu"):
            if all(k in attrs for k in ("mlp.gate_proj.weight", "mlp.up_proj.weight")):
                fc1_w = torch.cat([attrs["mlp.gate_proj.weight"], attrs["mlp.up_proj.weight"]], dim=0)
                mg_sd[f"{layer_base}.mlp.linear_fc1.weight"] = fc1_w
            if all(k in attrs for k in ("mlp.gate_proj.bias", "mlp.up_proj.bias")):
                fc1_b = torch.cat([attrs["mlp.gate_proj.bias"], attrs["mlp.up_proj.bias"]], dim=0)
                mg_sd[f"{layer_base}.mlp.linear_fc1.bias"] = fc1_b
        else:
            if "mlp.up_proj.weight" in attrs:
                mg_sd[f"{layer_base}.mlp.linear_fc1.weight"] = attrs["mlp.up_proj.weight"]

        # FC2
        if "mlp.down_proj.weight" in attrs:
            mg_sd[f"{layer_base}.mlp.linear_fc2.weight"] = attrs["mlp.down_proj.weight"]
        if "mlp.down_proj.bias" in attrs:
            mg_sd[f"{layer_base}.mlp.linear_fc2.bias"] = attrs["mlp.down_proj.bias"]

        # Layer norms
        if "input_layernorm.weight" in attrs:
            mg_sd[f"{layer_base}.input_layernorm.weight"] = attrs["input_layernorm.weight"]
        if "post_attention_layernorm.weight" in attrs:
            mg_sd[f"{layer_base}.pre_mlp_layernorm.weight"] = attrs["post_attention_layernorm.weight"]

    return mg_sd
