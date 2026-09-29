"""S9R-A07..A09: LoRA targets are anchored, backbone-only regexes (never the vision tower or connector).

The three candidate architectures are built from tiny configs on CPU (random init, no weights, no hub).
"""

from __future__ import annotations

import re

import pytest
import torch

from research.train import models

from .conftest import load_cfg

CANDIDATES = {"medgemma-27b-it": "gemma3", "lingshu-32b": "qwen2_5_vl", "qwen3.8-27b": "qwen3_5"}
BARE_NAMES = ["q_proj", "k_proj", "v_proj", "o_proj", "gate_proj", "up_proj", "down_proj"]


def _tiny_vlm(arch: str) -> torch.nn.Module:
    import transformers as T

    text = dict(vocab_size=128, hidden_size=16, intermediate_size=32, num_attention_heads=2, num_key_value_heads=1)
    vision = dict(hidden_size=16, intermediate_size=32)
    if arch == "gemma3":
        cfg = T.Gemma3Config(text_config=dict(text, num_hidden_layers=2, head_dim=8),
                             vision_config=dict(vision, num_hidden_layers=2, num_attention_heads=2, image_size=28,
                                                patch_size=14), mm_tokens_per_image=4)
        return T.Gemma3ForConditionalGeneration(cfg)
    if arch == "qwen2_5_vl":
        cfg = T.Qwen2_5_VLConfig(text_config=dict(text, num_hidden_layers=2),
                                 vision_config=dict(vision, depth=2, num_heads=2, out_hidden_size=16, fullatt_block_indexes=[1]))
        return T.Qwen2_5_VLForConditionalGeneration(cfg)
    if arch == "qwen3_5":  # 3 Gated DeltaNet (linear_attention) layers + 1 full-attention layer
        cfg = T.Qwen3_5Config(text_config=dict(text, num_hidden_layers=4, head_dim=8, linear_key_head_dim=8,
                                               linear_value_head_dim=8, linear_num_key_heads=2, linear_num_value_heads=2,
                                               full_attention_interval=4),
                              vision_config=dict(vision, depth=2, num_heads=2, out_hidden_size=16))
        return T.Qwen3_5ForConditionalGeneration(cfg)
    raise ValueError(arch)


def _wrapped(peft_model) -> list[str]:
    """Module paths (relative to the wrapped model) that received a LoRA adapter."""
    from peft.tuners.lora import LoraLayer

    prefix = "base_model.model."
    return [n[len(prefix):] if n.startswith(prefix) else n for n, mod in peft_model.named_modules() if isinstance(mod, LoraLayer)]


def _apply(model, targets):
    from peft import LoraConfig, get_peft_model

    return get_peft_model(model, LoraConfig(r=1, lora_alpha=2, lora_dropout=0.0, target_modules=targets))


def test_lora_targets_are_anchored_regex():
    cfg = load_cfg("stage3")
    real = cfg["real_run"]["lora"]["target_modules"]
    assert isinstance(real, dict) and set(real) == set(CANDIDATES)
    entries = [*real.values(), cfg["dry_run"]["lora"]["target_modules"]]
    for regex in entries:
        assert isinstance(regex, str), regex  # 0 bare leaf-name lists
        assert regex.startswith("^") and regex.endswith("$"), regex
        re.compile(regex)
        assert models.lora_target_regex(regex) == regex
    for cand in CANDIDATES:
        assert "language_model" in models.real_run_lora_target(cfg, cand)
    for bad in (BARE_NAMES, "q_proj", "model\\.layers\\.\\d+\\.self_attn\\.q_proj"):
        with pytest.raises(ValueError):
            models.lora_target_regex(bad)


@pytest.mark.parametrize("candidate", list(CANDIDATES), ids=list(CANDIDATES.values()))
def test_lora_backbone_only(candidate):
    model = _tiny_vlm(CANDIDATES[candidate])
    text_cfg = model.config.text_config
    layer_types = list(text_cfg.layer_types)
    n_layers = text_cfg.num_hidden_layers
    n_attn = sum(t != "linear_attention" for t in layer_types)
    wrapped = _wrapped(_apply(model, models.real_run_lora_target(load_cfg("stage3"), candidate)))
    assert wrapped
    assert [n for n in wrapped if not n.startswith("model.language_model.")] == []
    assert [n for n in wrapped if "linear_attn" in n] == []
    assert len(wrapped) == 3 * n_layers + 4 * n_attn, (len(wrapped), n_layers, n_attn)
    if CANDIDATES[candidate] == "qwen3_5":
        assert n_attn < n_layers  # the fixture really has Gated DeltaNet layers to exclude


@pytest.mark.parametrize("arch", ["gemma3", "qwen2_5_vl"])
def test_bare_names_would_wrap_vision(arch):
    """Negative control: the S9 bare leaf-name list wraps vision-tower modules, so the test above can fail."""
    wrapped = _wrapped(_apply(_tiny_vlm(arch), list(BARE_NAMES)))
    vision = [n for n in wrapped if not n.startswith("model.language_model.")]
    assert len(vision) > 0 and all(("vision_tower" in n) or ("visual" in n) for n in vision), vision


def test_dry_run_lora_scope():
    from peft.tuners.lora import LoraLayer

    cfg = load_cfg("stage3")
    model = models.build_model(cfg, dry_run=True)
    wrapped = [n for n, mod in model.named_modules() if isinstance(mod, LoraLayer)]
    assert [n for n in wrapped if n.startswith(("encoder.", "connector."))] == []
    assert all(n.startswith("backbone.") for n in wrapped)
    assert len(wrapped) == 7 * cfg["dry_run"]["backbone"]["num_hidden_layers"]
