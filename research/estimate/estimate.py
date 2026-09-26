"""Memory and compute estimate for the base-model candidates (slice s9).

Every figure produced here is an ESTIMATE, NOT A MEASUREMENT. Formulas are implemented once, in the
functions below, in integer bytes; ESTIMATE.md is generated from them byte-identically:

    python -m research.estimate.estimate --out research/estimate/ESTIMATE.md

Inputs live in research/estimate/inputs/*.json. Each input has a primary source URL or is labelled
ASSUMPTION (with a low/high range where it drives the 27B compute/storage/cost figures).
"""

from __future__ import annotations

import argparse
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

HERE = Path(__file__).resolve().parent
INPUTS = HERE / "inputs"
DEFAULT_OUT = HERE / "ESTIMATE.md"
CANDIDATES = ("medgemma-27b-it", "qwen3.8-27b", "lingshu-32b")
STAGES = ("stage2_connector", "stage3_lora")
GB = 10**9
KORTHIKANTI = "https://arxiv.org/abs/2205.05198"
LORA_PAPER = "https://arxiv.org/abs/2106.09685"
ZERO_PAPER = "https://arxiv.org/abs/1910.02054"
MANIFEST_IDS = [f"smoke-{s}-{c}" for c in CANDIDATES for s in ("s2-connector", "s3-lora")]


def ceil_div(a: int, b: int) -> int:
    return -(-a // b)


# ------------------------------------------------------------------------------------------------
# Formulas (integer bytes)
# ------------------------------------------------------------------------------------------------


def weights_bytes(p_total: int, zero_stage: int, n_gpu: int) -> int:
    """M_weights = 2 B x P_total (bf16, frozen). ZeRO-3 shards parameters over the N GPUs."""
    m = 2 * p_total
    return ceil_div(m, n_gpu) if zero_stage == 3 else m


def lora_params(shapes: list[tuple[int, int]], r: int) -> int:
    """P_lora = sum over adapted matrices of r x (d_in + d_out)."""
    return sum(r * (d_in + d_out) for d_in, d_out in shapes)


def trainable_state_bytes(p_trainable: int, zero_stage: int, n_gpu: int) -> int:
    """M_trainable = 16 B x P_t (bf16 param 2 + fp32 master 4 + Adam m 4 + v 4 + grad 2).

    ZeRO-2 shards optimizer state and gradients (14 B) over N, keeps the bf16 param replica (2 B).
    ZeRO-3 shards all 16 B. No ZeRO (1 GPU): nothing is sharded.
    """
    if zero_stage == 3:
        return ceil_div(16 * p_trainable, n_gpu)
    if zero_stage == 2:
        return 2 * p_trainable + ceil_div(14 * p_trainable, n_gpu)
    return 16 * p_trainable


def layer_recompute_bytes(s: int, b: int, h: int, a: int, span: int) -> int:
    """One layer's activations (Korthikanti et al. 2022): s*b*h*34 + 5*a*s*span*b bytes.

    `span` is the attended length: s for full attention, min(s, window) for sliding-window attention,
    0 for linear-attention (Gated DeltaNet) layers, where the quadratic attention term does not apply.
    """
    return s * b * h * 34 + 5 * a * s * span * b


def activation_bytes(L: int, s: int, b: int, h: int, a: int, layer_types: dict[str, int],
                     window: int | None = None) -> int:
    """Gradient checkpointing: stored layer inputs L*s*b*h*2 + the largest single recomputed layer.

    Upper bound when fused/flash attention is used (the 5*a*s^2*b score term is never materialised).
    """
    spans = {"full": s, "sliding": min(s, window or s), "linear": 0}
    worst = max(layer_recompute_bytes(s, b, h, a, spans[t]) for t, n in layer_types.items() if n > 0)
    return L * s * b * h * 2 + worst


def logits_bytes(b: int, s: int, vocab: int) -> int:
    """b x s x V x 4 B (fp32 logits for the loss)."""
    return b * s * vocab * 4


def tokens_per_step(micro_batch: int, seq_len: int, grad_accum: int, data_parallel: int) -> int:
    return micro_batch * seq_len * grad_accum * data_parallel


def n_patches(volume_hwd: list[int], patch_hw: int, patch_d: int) -> int:
    h, w, d = volume_hwd
    return (h // patch_hw) * (w // patch_hw) * (d // patch_d)


def enc3d_bytes(b: int, volume_hwd: list[int], patch_hw: int, patch_d: int, d_enc: int, heads: int) -> int:
    """Frozen CT encoder under no_grad: peak of one factorised (spatial/temporal) layer.

    b*N*d_enc*34 + 5*heads*b*max(frames*S^2, S*frames^2), S = spatial tokens per frame.
    """
    s_sp = (volume_hwd[0] // patch_hw) * (volume_hwd[1] // patch_hw)
    frames = volume_hwd[2] // patch_d
    n = s_sp * frames
    return b * n * d_enc * 34 + 5 * heads * b * max(frames * s_sp * s_sp, s_sp * frames * frames)


def connector_params(d_in: int, d: int, n_query: int, n_layers: int, d_out: int) -> int:
    """FixedTokenConnector (research/train/models.py):
    d_in*d + d + n_query*d + n_layers*(12*d^2 + 15*d) + 2*d + d*d_out + d_out."""
    return d_in * d + d + n_query * d + n_layers * (12 * d * d + 15 * d) + 2 * d + d * d_out + d_out


def connector_act_bytes(b: int, n_patch: int, d: int, n_query: int, n_layers: int, heads: int) -> int:
    """Trainable connector, stored for backward: projected+normed patches b*N*d*2*(1+n_layers)
    + per layer b*(n_query*d*34 + 5*heads*n_query*N) (cross-attention scores over all patches)."""
    return b * n_patch * d * 2 * (1 + n_layers) + n_layers * b * (n_query * d * 34 + 5 * heads * n_query * n_patch)


def adapted_shapes(arch: dict[str, Any], targets: list[str]) -> list[tuple[int, int]]:
    """(d_in, d_out) of every adapted Linear in the language model.

    Attention projections exist in full and sliding layers (not in linear-attention layers); the MLP
    exists in every layer. With an output gate (Qwen3.8 Gated Attention) q_proj emits 2*a*hd.
    """
    h, a, kv, hd, ffn = arch["hidden_size"], arch["attention_heads"], arch["kv_heads"], arch["head_dim"], arch["ffn_intermediate"]
    q_out = a * hd * (2 if arch.get("attn_output_gate") else 1)
    attn = {"q_proj": (h, q_out), "k_proj": (h, kv * hd), "v_proj": (h, kv * hd), "o_proj": (a * hd, h)}
    mlp = {"gate_proj": (h, ffn), "up_proj": (h, ffn), "down_proj": (ffn, h)}
    types = arch["layer_types"]
    n_attn = types.get("full", 0) + types.get("sliding", 0)
    n_all = sum(types.values())
    shapes: list[tuple[int, int]] = []
    for name in targets:
        if name in attn:
            shapes += [attn[name]] * n_attn
        elif name in mlp:
            shapes += [mlp[name]] * n_all
        else:
            raise ValueError(f"unknown target module {name}")
    return shapes


def train_flops(c: float, p_active: int, tokens: float) -> float:
    return c * p_active * tokens


def gpu_hours(flops: float, peak: float, mfu: float) -> float:
    return flops / (peak * mfu) / 3600


# ------------------------------------------------------------------------------------------------
# Inputs
# ------------------------------------------------------------------------------------------------


def _load(name: str) -> dict[str, Any]:
    return json.loads((INPUTS / f"{name}.json").read_text(encoding="utf-8"))


def _v(section: dict[str, Any], key: str) -> Any:
    return section[key]["value"]


def candidate_arch(cand: dict[str, Any]) -> dict[str, Any]:
    return {k: v["value"] for k, v in cand["inputs"].items()}


@dataclass(frozen=True)
class Row:
    candidate: str
    stage: str
    rank: int
    hw: str
    n_gpu: int
    zero: int
    weights: int
    trainable: int
    activations: int
    logits: int
    path3d: int
    overhead: int
    tokens_step: int
    p_trainable: int

    @property
    def total(self) -> int:
        return self.weights + self.trainable + self.activations + self.logits + self.path3d + self.overhead


HW_CONFIGS = (("1x B200, no ZeRO (Tier-2 smoke)", 1, 0), ("8x B200, ZeRO-2", 8, 2), ("8x B200, ZeRO-3", 8, 3))


def memory_rows() -> list[Row]:
    plan = _load("plan")
    run, enc, con = plan["run"], plan["enc3d"], plan["connector"]
    b = _v(run, "micro_batch")
    n_patch = n_patches(_v(enc, "volume_shape_hwd"), _v(enc, "patch_hw"), _v(enc, "patch_d"))
    p3d = enc3d_bytes(b, _v(enc, "volume_shape_hwd"), _v(enc, "patch_hw"), _v(enc, "patch_d"), _v(enc, "enc_dim"), _v(enc, "enc_heads"))
    p3d += connector_act_bytes(b, n_patch, _v(con, "d_model"), _v(con, "n_query"), _v(con, "n_layers"), _v(con, "n_heads"))
    rows: list[Row] = []
    for cid in CANDIDATES:
        arch = candidate_arch(_load(cid))
        p_con = connector_params(_v(enc, "enc_dim"), _v(con, "d_model"), _v(con, "n_query"), _v(con, "n_layers"), arch["hidden_size"])
        shapes = adapted_shapes(arch, _v(run, "lora_target_modules"))
        for stage in STAGES:
            s = _v(run, "seq_len_stage2") if stage == "stage2_connector" else _v(run, "seq_len_stage3")
            act = activation_bytes(arch["num_layers"], s, b, arch["hidden_size"], arch["attention_heads"],
                                   arch["layer_types"], arch.get("sliding_window"))
            lg = logits_bytes(b, s, arch["vocab_size"])
            for r in _v(run, "lora_ranks"):
                p_t = p_con + (lora_params(shapes, r) if stage == "stage3_lora" else 0)
                for hw, n_gpu, zero in HW_CONFIGS:
                    accum = _v(run, "grad_accum_1gpu") if n_gpu == 1 else _v(run, "grad_accum_8gpu")
                    dp = 1 if n_gpu == 1 else _v(run, "data_parallel_8gpu")
                    rows.append(Row(cid, stage, r, hw, n_gpu, zero, weights_bytes(arch["P_total"], zero, n_gpu),
                                    trainable_state_bytes(p_t, zero, n_gpu), act, lg, p3d,
                                    _v(run, "framework_overhead_bytes"), tokens_per_step(b, s, accum, dp), p_t))
    return rows


def fits(total: int, capacity: int, headroom: float) -> bool:
    return total <= capacity * (1 - headroom)


# ------------------------------------------------------------------------------------------------
# Report
# ------------------------------------------------------------------------------------------------


def _gb(x: float) -> str:
    return f"{x / GB:,.1f}"


def _src(item: dict[str, Any]) -> str:
    src = item["source"]
    return src if src == "ASSUMPTION" or not src.startswith("http") else f"<{src}>"


def _val(item: dict[str, Any]) -> str:
    if "low" in item:
        return f"{item['low']:,} to {item['high']:,}" if isinstance(item["low"], int) else f"{item['low']} to {item['high']}"
    v = item["value"]
    return f"{v:,}" if isinstance(v, int) and not isinstance(v, bool) else json.dumps(v, ensure_ascii=False)


def compute_27b() -> dict[str, dict[str, float]]:
    """Per candidate: low/high GPU-hours, cost, wall-clock days on 8 GPUs (estimates)."""
    plan, hw = _load("plan"), _load("b200")
    comp = plan["compute"]
    peak = _v(hw["inputs"], "bf16_dense_flops_per_gpu")
    n = _v(hw["inputs"], "gpus_per_node")
    out = {}
    for cid in CANDIDATES:
        p = candidate_arch(_load(cid))["P_total"]
        res = {}
        for side in ("low", "high"):
            other = "high" if side == "low" else "low"
            t2 = comp["stage2_samples"][side] * comp["stage2_tokens_per_sample"][side] * comp["stage2_epochs"][side]
            t3 = comp["stage3_tokens"][side]
            c = comp["c_lora"][side]
            mfu = comp["mfu"][other]  # low GPU-hours use the high MFU
            once = gpu_hours(train_flops(c, p, t2), peak, mfu) + gpu_hours(train_flops(c, p, t3), peak, mfu)
            total = once * comp["runs_multiplier"][side]
            res[f"tokens_s2_{side}"] = t2
            res[f"tokens_s3_{side}"] = t3
            res[f"gpu_hours_once_{side}"] = once
            res[f"gpu_hours_{side}"] = total
            res[f"cost_{side}"] = total * comp["price_usd_per_gpu_hour"][side]
            res[f"days_{side}"] = total / n / 24
        out[cid] = res
    return out


def storage_27b() -> dict[str, dict[str, int]]:
    plan = _load("plan")
    run, enc, con, st, comp = plan["run"], plan["enc3d"], plan["connector"], plan["storage"], plan["compute"]
    ranks = _v(run, "lora_ranks")
    n_patch = n_patches(_v(enc, "volume_shape_hwd"), _v(enc, "patch_hw"), _v(enc, "patch_d"))
    out = {}
    for cid in CANDIDATES:
        arch = candidate_arch(_load(cid))
        p_con = connector_params(_v(enc, "enc_dim"), _v(con, "d_model"), _v(con, "n_query"), _v(con, "n_layers"), arch["hidden_size"])
        shapes = adapted_shapes(arch, _v(run, "lora_target_modules"))
        res = {}
        for side, r in (("low", min(ranks)), ("high", max(ranks))):
            p_t = p_con + lora_params(shapes, r)
            res[f"base_{side}"] = arch["bf16_checkpoint_bytes"]
            res[f"adapter_{side}"] = 2 * p_t
            res[f"resume_ckpts_{side}"] = 16 * p_t * st["checkpoint_retention"][side]
            res[f"datasets_{side}"] = st["ct_rate_bytes"][side] + st["mimic_cxr_bytes"][side] + st["mimic_iv_bytes"][side]
            res[f"cache3d_{side}"] = comp["stage2_samples"][side] * n_patch * _v(enc, "enc_dim") * 2
            res[f"total_{side}"] = sum(v for k, v in res.items() if k.endswith(side))
        out[cid] = res
    return out


def render() -> str:
    plan, hw = _load("plan"), _load("b200")
    cands = {cid: _load(cid) for cid in CANDIDATES}
    cap = _v(hw["inputs"], "memory_bytes_per_gpu")
    headroom = _v(plan["run"], "headroom_fraction")
    L: list[str] = []
    add = L.append
    add("# Memory and compute estimate (slice s9)")
    add("")
    add("<!-- Generated by `python -m research.estimate.estimate`. Do not edit by hand; tests regenerate and diff it. -->")
    add("")
    add("> **Every number in this document is an estimate, not a measurement.** Research prototype, not for clinical use. "
        "No GPU job was run to produce it. The Tier-2 smoke manifests listed at the end name the measurements that will "
        "replace these figures.")
    add("")
    add("## Formulas")
    add("")
    add("Implemented once in `research/estimate/estimate.py`; integer bytes. `B` = bytes.")
    add("")
    add("| Term | Formula | Notes |")
    add("|---|---|---|")
    add("| Frozen weights | `M_weights = 2 B x P_total` | bf16. ZeRO-3 shards it: `/ N`. ZeRO-2 and 1 GPU do not. |")
    add(f"| LoRA parameters | `P_lora = sum_(adapted matrices) r x (d_in + d_out)` | Hu et al. <{LORA_PAPER}>. |")
    add(f"| Trainable state | `M_trainable = 16 B x (P_lora + P_connector)` | bf16 param 2 + fp32 master 4 + Adam m 4 + v 4 + grad 2. "
        f"ZeRO-2: `2 P_t + 14 P_t / N`; ZeRO-3: `16 P_t / N` (Rajbhandari et al. <{ZERO_PAPER}>). |")
    add(f"| Activations | `L x s x b x h x 2 B + max_layer_type [s x b x h x (34 + 5 a s_span / h)]` | Gradient checkpointing: stored "
        f"layer inputs plus one recomputed layer (Korthikanti et al. 2022 <{KORTHIKANTI}>). `s_span = s` (full attention), "
        "`min(s, window)` (sliding), `0` (linear attention: the attention-only term does not apply in hybrid models). "
        "Upper bound when fused/flash attention is used. |")
    add("| Logits | `b x s x V x 4 B` | fp32 logits; large vocabularies make this a real term. Chunked loss would remove most of it. |")
    add("| 3D path | `b N d_enc 34 + 5 heads b max(F S^2, S F^2)` + connector `b N d 2 (1 + n_layers) + n_layers b (n_q d 34 + 5 heads_c n_q N)` "
        "| Frozen CT-CLIP encoder under no_grad (factorised spatial/temporal attention; `S` tokens per frame, `F` frames, `N = S F`) "
        "plus the trainable fixed-token connector at the declared volume shape and `n_q` tokens. |")
    add("| Connector parameters | `P_connector = d_in d + d + n_q d + n_layers (12 d^2 + 15 d) + 2 d + d d_out + d_out` | Matches `FixedTokenConnector`. |")
    add("| Tokens per step | `micro_batch x seq_len x grad_accum x data_parallel` | |")
    add("| Compute | `FLOPs ~= c x P_active x T_tokens` | `P_active = P_total` (conservative: includes the idle 2D vision tower). |")
    add("| Time | `time = FLOPs / (N_gpu x peak x MFU)` | GPU-hours = `FLOPs / (peak x MFU) / 3600`. |")
    add("")
    add("**The value of `c`.** Full fine-tuning costs about 6 FLOPs per parameter per token (forward 2, backward 4: activation "
        "gradients 2 plus weight gradients 2). With a frozen backbone and LoRA, weight gradients exist only for the small "
        "adapters and the connector, but activation gradients must still flow back through every frozen layer to reach the "
        "adapters (stage 3) and the image tokens at the input (stage 2). That gives `c ~= 4`. Gradient checkpointing reruns "
        "the forward pass (+2), so `c ~= 6`. This estimate uses the range `c = 4 to 6`.")
    add("")
    add("## Inputs")
    add("")
    add("`ASSUMPTION` marks a value with no primary source. Such values are design choices or ranges to be replaced by measurements.")
    add("")
    add("| Input | Value | Source | Note |")
    add("|---|---|---|---|")
    for cid, cand in cands.items():
        for key, item in cand["inputs"].items():
            add(f"| {cid}.{key} | {_val(item)} | {_src(item)} | {item.get('note', '')} |")
    for key, item in hw["inputs"].items():
        add(f"| b200.{key} | {_val(item)} | {_src(item)} | {item.get('note', '')} |")
    for section in ("run", "enc3d", "connector", "compute", "storage", "schedule"):
        for key, item in plan[section].items():
            add(f"| plan.{section}.{key} | {_val(item)} | {_src(item)} | {item.get('note', '')} |")
    add("")
    add(f"## Per-GPU memory (GB, estimate, not measurement)")
    add("")
    add(f"B200 capacity {_gb(cap)} GB per GPU; declared headroom {headroom:.0%}; FITS means total <= {_gb(cap * (1 - headroom))} GB. "
        "Stage 2 trains only the connector (no LoRA), so its rows do not change with `r`; they are repeated for a complete grid. "
        "The 3D path is included in every row.")
    add("")
    add("| Candidate | Stage | r | Hardware | Trainable params | Weights | Trainable state | Activations | Logits | 3D path | Overhead | Total | Tokens/step | Verdict |")
    add("|---|---|---|---|---|---|---|---|---|---|---|---|---|---|")
    for row in memory_rows():
        verdict = "FITS" if fits(row.total, cap, headroom) else "DOES NOT FIT"
        r = f"{row.rank}" if row.stage == "stage3_lora" else f"{row.rank} (unused)"
        add(f"| {row.candidate} | {row.stage} | {r} | {row.hw} | {row.p_trainable:,} | {_gb(row.weights)} | {_gb(row.trainable)} | "
            f"{_gb(row.activations)} | {_gb(row.logits)} | {_gb(row.path3d)} | {_gb(row.overhead)} | **{_gb(row.total)}** | "
            f"{row.tokens_step:,} | {verdict} |")
    add("")
    comp, stor = compute_27b(), storage_27b()
    add("## 27B flagship")
    add("")
    add("Required by CLAUDE.md before any flagship run. **Every figure below is an estimate, not a measurement.** "
        "No figure is carried over from the withdrawn 4B target; all are computed here from the approximately 27B candidates' "
        "own cited parameter counts. Lingshu-32B is shown at its true size (about 33.45B).")
    add("")
    add("### Compute")
    add("")
    add("GPU-hours for stage 2 (connector) + stage 3 (LoRA), times the runs multiplier. Low = low tokens, `c = 4`, high MFU, "
        "low multiplier; high = the opposite.")
    add("")
    add("| Candidate | Stage-2 tokens (low to high) | Stage-3 tokens (low to high) | GPU-hours, one pass (low to high) | GPU-hours incl. runs multiplier (low to high) |")
    add("|---|---|---|---|---|")
    for cid, r in comp.items():
        add(f"| {cid} | {r['tokens_s2_low']:,.0f} to {r['tokens_s2_high']:,.0f} | {r['tokens_s3_low']:,.0f} to {r['tokens_s3_high']:,.0f} | "
            f"{r['gpu_hours_once_low']:,.1f} to {r['gpu_hours_once_high']:,.1f} | {r['gpu_hours_low']:,.1f} to {r['gpu_hours_high']:,.1f} |")
    add("")
    add("### Storage")
    add("")
    add("Itemized, decimal GB. Adapter and checkpoint sizes use r = 8 (low) and r = 64 (high). Resume checkpoints hold the "
        "trainable state only (16 B per trainable parameter), times the retention count. Dataset sizes are ASSUMPTION ranges.")
    add("")
    add("| Candidate | Base weights | Adapter (bf16) | Resume checkpoints x retention | Datasets (CT-RATE, MIMIC-CXR, MIMIC-IV) | Cached 3D encoder features | Total (low to high) |")
    add("|---|---|---|---|---|---|---|")
    for cid, s in stor.items():
        add(f"| {cid} | {_gb(s['base_low'])} | {_gb(s['adapter_low'])} to {_gb(s['adapter_high'])} | "
            f"{_gb(s['resume_ckpts_low'])} to {_gb(s['resume_ckpts_high'])} | {_gb(s['datasets_low'])} to {_gb(s['datasets_high'])} | "
            f"{_gb(s['cache3d_low'])} to {_gb(s['cache3d_high'])} | {_gb(s['total_low'])} to {_gb(s['total_high'])} |")
    add("")
    add("Preliminary experiments hold all three base checkpoints at once: "
        f"{_gb(sum(s['base_low'] for s in stor.values()))} GB.")
    add("")
    add("### Cost")
    add("")
    add("GPU-hours x price per GPU-hour. **The price is an ASSUMPTION** "
        f"(USD {plan['compute']['price_usd_per_gpu_hour']['low']} to {plan['compute']['price_usd_per_gpu_hour']['high']}); "
        "with a granted allocation it is the opportunity cost.")
    add("")
    add("| Candidate | Cost, USD (low to high) |")
    add("|---|---|")
    for cid, r in comp.items():
        add(f"| {cid} | {r['cost_low']:,.0f} to {r['cost_high']:,.0f} |")
    add("")
    add("### Schedule")
    add("")
    weeks = _v(plan["schedule"], "semester2_window_weeks")
    add(f"Wall-clock on one 8x B200 node, assuming the whole node is available. Proposal 1.5: base-model study and preliminary "
        f"fine-tune (tasks 6-7) in semester 1, before the progress report on 4 Dec 2026; the approximately 27B fine-tune (task 9) "
        f"in semester 2, January to May 2027 (about {weeks} weeks).")
    add("")
    add("| Candidate | Wall-clock days on 8x B200 (low to high) | Share of the semester-2 window (low to high) |")
    add("|---|---|---|")
    for cid, r in comp.items():
        add(f"| {cid} | {r['days_low']:,.1f} to {r['days_high']:,.1f} | {r['days_low'] / (weeks * 7):.1%} to {r['days_high'] / (weeks * 7):.1%} |")
    add("")
    add("Compute time is not the binding constraint on these assumptions; data access (CT-RATE, PhysioNet), the Tier-3/4 "
        "approval, and evaluation are. Any Tier-3/4 run needs explicit human approval recorded in docs/DECISIONS.md.")
    add("")
    add("### Fallback")
    add("")
    add("If stable approximately 27B training is not possible on the granted compute, the fallback is the strongest valid smaller "
        "model, reported at its true scale and never relabelled (proposal 1.3.4: reduce the base-model size or the training scope).")
    add("")
    add("## Measurements that replace these estimates")
    add("")
    add("The Tier-2 smoke manifests (`research/manifests/`, status `planned`) each measure peak GPU memory, tokens/s, "
        "loss decrease and a checkpoint round-trip on one B200 for at most 60 minutes:")
    add("")
    for mid in MANIFEST_IDS:
        add(f"- `{mid}`")
    add("")
    return "\n".join(L)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    args = parser.parse_args(argv)
    args.out.write_text(render(), encoding="utf-8")
    print(f"wrote {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
