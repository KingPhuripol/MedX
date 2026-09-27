"""S9-A06, A07, A08, A18: estimate report, arithmetic, 27B section, DeepSpeed configs."""

from __future__ import annotations

import json
from urllib.parse import urlparse

import pytest

from research.estimate import estimate as E

from .conftest import REPO_ROOT, load_cfg

ESTIMATE_MD = REPO_ROOT / "research" / "estimate" / "ESTIMATE.md"
INPUT_ALLOW = {
    "huggingface.co": ["/google/", "/Qwen/", "/lingshu-medical-mllm/", "/api/models/"],
    "github.com": ["/google-deepmind/", "/ibrahimethemhamamci/CT-CLIP/"],
    "arxiv.org": ["/abs/"],
    "www.nvidia.com": ["/en-us/data-center/"],
}


def test_estimate_report_regenerates():
    assert E.render() == ESTIMATE_MD.read_text(encoding="utf-8")


def test_estimate_inputs_sourced_or_assumption():
    md = ESTIMATE_MD.read_text(encoding="utf-8")
    for path in sorted((REPO_ROOT / "research" / "estimate" / "inputs").glob("*.json")):
        doc = json.loads(path.read_text(encoding="utf-8"))
        sections = [doc["inputs"]] if "inputs" in doc else [v for k, v in doc.items() if isinstance(v, dict)]
        for section in sections:
            for key, item in section.items():
                src = item["source"]
                if src == "ASSUMPTION" or src.startswith("docs/PROPOSAL.md"):
                    continue
                u = urlparse(src)
                assert u.scheme == "https" and any(u.path.startswith(p) for p in INPUT_ALLOW.get(u.netloc, [])), (path.name, key, src)
    for formula in ("M_weights = 2 B x P_total", "P_lora = sum_(adapted matrices) r x (d_in + d_out)",
                    "M_trainable = 16 B x (P_lora + P_connector)", "b x s x V x 4 B",
                    "micro_batch x seq_len x grad_accum x data_parallel", "c x P_active x T_tokens",
                    "FLOPs / (N_gpu x peak x MFU)", "34 + 5 a s_span / h"):
        assert formula in md, formula
    assert "| ASSUMPTION |" in md
    rows = [ln for ln in md.splitlines() if ln.startswith("| ") and ln.split("|")[1].strip() in E.CANDIDATES
            and ln.rstrip().endswith(("| FITS |", "| DOES NOT FIT |"))]
    assert len(rows) == 3 * 2 * 3 * 3  # candidates x stages x ranks x {1 GPU, 8 GPU ZeRO-2, 8 GPU ZeRO-3}
    for cand in E.CANDIDATES:
        for stage in E.STAGES:
            for hw, _, _ in E.HW_CONFIGS:
                for r in (8, 16, 64):
                    assert any(ln.startswith(f"| {cand} | {stage} | {r}") and f"| {hw} |" in ln for ln in rows), (cand, stage, hw, r)


def test_estimate_terms_hand_calc():
    # Hand-worked reference: P_total=1000, L=2, s=4, b=1, h=8, a=2, V=10.
    assert E.weights_bytes(1000, 0, 1) == 2000
    assert E.weights_bytes(1000, 2, 4) == 2000
    assert E.weights_bytes(1000, 3, 4) == 500
    shapes = [(8, 8), (8, 16)]
    assert E.lora_params(shapes, 2) == 2 * 16 + 2 * 24 == 80
    p_t = 80 + 20  # + connector
    assert E.trainable_state_bytes(p_t, 0, 1) == 1600
    assert E.trainable_state_bytes(p_t, 2, 4) == 2 * 100 + 14 * 100 // 4 == 550
    assert E.trainable_state_bytes(p_t, 3, 4) == 400
    # stored 2*4*1*8*2 = 128; full layer 4*1*8*34 + 5*2*4*4*1 = 1088 + 160 = 1248
    assert E.activation_bytes(2, 4, 1, 8, 2, {"full": 2}) == 128 + 1248
    # hybrid: linear-attention layers have no quadratic term; the worst layer is still the full one
    assert E.activation_bytes(2, 4, 1, 8, 2, {"linear": 1, "full": 1}) == 128 + 1248
    assert E.activation_bytes(2, 4, 1, 8, 2, {"linear": 2}) == 128 + 1088
    # sliding window 2: 5*2*4*2*1 = 80
    assert E.activation_bytes(2, 4, 1, 8, 2, {"sliding": 2}, window=2) == 128 + 1088 + 80
    assert E.logits_bytes(1, 4, 10) == 160
    assert E.tokens_per_step(2, 4, 3, 2) == 48
    assert E.connector_params(4, 8, 2, 1, 6) == 4 * 8 + 8 + 2 * 8 + (12 * 64 + 15 * 8) + 16 + 8 * 6 + 6
    assert E.n_patches([40, 40, 20], 20, 10) == 8
    # 3D: S=4 per frame, F=2 frames, N=8, d=3, heads=1, b=1: 8*3*34 + 5*1*max(2*16, 4*4) = 816 + 160
    assert E.enc3d_bytes(1, [40, 40, 20], 20, 10, 3, 1) == 976
    assert E.train_flops(6, 10, 100) == 6000
    assert E.gpu_hours(3600 * 100.0, 100.0, 1.0) == 1.0


def _tiny_arch() -> tuple[dict, list[str], dict]:
    cfg = load_cfg("stage3")
    bb = cfg["dry_run"]["backbone"]
    arch = {"hidden_size": bb["hidden_size"], "attention_heads": bb["num_attention_heads"], "kv_heads": bb["num_key_value_heads"],
            "head_dim": bb["hidden_size"] // bb["num_attention_heads"], "ffn_intermediate": bb["intermediate_size"],
            "layer_types": {"full": bb["num_hidden_layers"]}, "attn_output_gate": False}
    return arch, cfg["dry_run"]["lora"]["target_modules"], bb


@pytest.mark.parametrize("r", [8, 16, 64])
def test_lora_param_formula_matches_peft(r):
    from peft import LoraConfig, get_peft_model

    from research.train.models import build_tiny_backbone

    arch, targets, bb = _tiny_arch()
    peft_model = get_peft_model(build_tiny_backbone(bb), LoraConfig(r=r, lora_alpha=2 * r, target_modules=targets))
    trainable, _ = peft_model.get_nb_trainable_parameters()
    assert E.lora_params(E.adapted_shapes(arch, targets), r) == trainable


def test_adapted_shapes_match_candidate_layouts():
    # Qwen3.8 Gated Attention: q_proj emits query + gate (2 * 24 * 256); only 16 layers have attention.
    q = E.candidate_arch(E._load("qwen3.8-27b"))
    shapes = E.adapted_shapes(q, ["q_proj", "o_proj", "down_proj"])
    assert shapes.count((5120, 12288)) == 16 and shapes.count((6144, 5120)) == 16 and shapes.count((17408, 5120)) == 64


def test_27b_section_complete():
    md = ESTIMATE_MD.read_text(encoding="utf-8")
    sec = md[md.index("## 27B flagship"):]
    for heading in ("### Compute", "### Storage", "### Cost", "### Schedule", "### Fallback"):
        assert heading in sec, heading
    assert "No figure is carried over from the withdrawn 4B target" in sec
    assert "strongest valid smaller model, reported at its true scale" in sec
    assert "estimate, not a measurement" in sec and "estimate, not a measurement" in md.splitlines()[4]
    assert "The price is an ASSUMPTION" in sec
    for item in ("Base weights", "Adapter", "Resume checkpoints", "Datasets", "Cached 3D encoder features"):
        assert item in sec, item
    assert "January to May 2027" in sec
    comp = E.compute_27b()
    for cid in E.CANDIDATES:
        assert 0 < comp[cid]["gpu_hours_low"] < comp[cid]["gpu_hours_high"]
        assert 0 < comp[cid]["cost_low"] < comp[cid]["cost_high"]


def test_deepspeed_configs():
    plan = E._load("plan")["run"]
    world = plan["data_parallel_8gpu"]["value"]
    expected_tokens = E.tokens_per_step(plan["micro_batch"]["value"], plan["seq_len_stage3"]["value"],
                                        plan["grad_accum_8gpu"]["value"], world)
    md = ESTIMATE_MD.read_text(encoding="utf-8")
    for name, stage in (("zero2", 2), ("zero3", 3)):
        cfg = json.loads((REPO_ROOT / "research" / "configs" / "deepspeed" / f"{name}.json").read_text())
        assert cfg["bf16"]["enabled"] is True
        assert not cfg.get("fp16", {}).get("enabled", False)
        assert cfg["zero_optimization"]["stage"] == stage
        seqs = cfg["train_micro_batch_size_per_gpu"] * cfg["gradient_accumulation_steps"] * world
        assert seqs == cfg["train_batch_size"]
        assert cfg["train_micro_batch_size_per_gpu"] == plan["micro_batch"]["value"]
        assert cfg["gradient_accumulation_steps"] == plan["grad_accum_8gpu"]["value"]
        assert seqs * plan["seq_len_stage3"]["value"] == expected_tokens
        assert f"| 8x B200, ZeRO-{stage} |" in md and f"| {expected_tokens:,} |" in md
