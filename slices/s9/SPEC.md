# Slice s9 — Base model selection and fine-tune plan (no GPU)

- Owner (Gantt): ธนาพล (tasks 6 "ศึกษาและคัดเลือก Base Model" and 7 "ทดลอง Fine-tune เบื้องต้น")
- Source of truth: `docs/PROPOSAL.md` (v8). Sections used: 1.3.1 (a model of about 27B, fine-tuned from an open-weight base, plus a 3D Encoder and Connector), 1.3.4 (MIMIC is processed only on team-controlled machines; fine-tune size depends on the GPU allocation, with a smaller base model or narrower scope as the fallback), 2.1.2 (LoRA; a 3D encoder with a fixed token count, as in RadFM), 2.2 Table 2.1 (PyTorch, HF Transformers, PEFT, DeepSpeed on 8x NVIDIA B200), 2.3 Table 2.2 (candidates and criteria), 3.3 (the three development stages and modality dropout with report substitution), 3.4 (patient-level split; official test sets; a report is never an input when it is the label source), 3.6 Table 3.2 (the base model before fine-tuning is a comparator).
- Also binding: `CLAUDE.md` research gates (a compute, storage, cost and schedule estimate made against 27B), training tiers, and human approval gates.
- Status: PLAN, written by the planner. This slice runs no GPU job, downloads no weights or datasets, and makes **no final base-model selection**. Proposal 2.3 says the final choice follows the semester-1 preliminary experiments. This slice produces the evidence and plumbing for those experiments.

## Scope

All new work lives under `research/`, apart from `scripts/validate_manifest.py`, one schema file, and the Makefile/pytest wiring.

1. **Selection matrix** (`research/base_model/selection_matrix.json`, rendered to `research/base_model/SELECTION_MATRIX.md` by a script)
   - Rows: MedGemma 27B (state the exact variant, e.g. `google/medgemma-27b-it` multimodal and not the text-only variant), Qwen3.8-27B, and Lingshu-32B.
   - Columns (every cell is `{value, source_url, retrieved_on, note}`):
     1. exact parameter count, total and per component (LM, vision encoder) where reported;
     2. architecture and layer layout (hidden size, layers, heads/KV heads, vocab; for Qwen3.8 this includes the hybrid Gated DeltaNet / Gated Attention layout);
     3. vision encoder name and size;
     4. image token budget per 2D image;
     5. native and maximum context length;
     6. license name;
     7. whether fine-tuning is permitted;
     8. whether redistribution of fine-tuned weights is permitted, and on what conditions (notice, use restrictions, flow-down);
     9. HF repo id, gated/ungated status, and BF16 checkpoint size;
     10. reported medical benchmark numbers (benchmark, split, metric, value, setting), each with its own citation;
     11. known overlap of the base model's training data with our evaluation sources (MIMIC-CXR, MIMIC-IV, CT-RATE);
     12. 3D support as reported;
     13. whether `transformers`/`peft` support the architecture, with the minimum version.
   - Primary sources only: official model cards, license texts, technical reports/papers, official GitHub/blog pages. If a value is not reported, store `value: null` and a `note: "not reported"`, and still cite the source that was checked.
   - Benchmark numbers from different settings are tagged `comparable_group`. The renderer never places non-comparable numbers in the same ranking.
   - Include a **pre-declared selection rubric**: criteria, weights, hard constraints and tie-breaks, committed *before* any preliminary fine-tune result exists. Include a "decision pending preliminary experiments" field. No winner is declared.

2. **Memory and compute estimate** (`research/estimate/estimate.py`, inputs in `research/estimate/inputs/*.json`, report in `research/estimate/ESTIMATE.md`)
   - Inputs per candidate come from the cited `config.json` (numbers transcribed with their URL; no weights fetched). Hardware inputs cite NVIDIA's B200 spec (memory per GPU, BF16 dense peak). Any assumption without a source (MFU, price per GPU-hour, dataset token counts) is labelled `ASSUMPTION` and given as a low/high range.
   - Formulas are shown in ESTIMATE.md and implemented once in code:
     - `M_weights = 2 B × P_total` (bf16, frozen);
     - `P_lora = Σ_{adapted matrices} r × (d_in + d_out)`;
     - `M_trainable = 16 B × (P_lora + P_connector)` (bf16 param + fp32 master + Adam m, v + grad; ZeRO stage and sharding factor applied explicitly);
     - activations per micro-batch, with gradient checkpointing: stored layer inputs `L × s × b × h × 2 B` plus one layer recomputed, `s × b × h × (34 + 5·a·s/h)` bytes (Korthikanti et al. 2022, cited). Attention-only terms apply only to attention layers in hybrid models. Treat this as an upper bound when fused/flash attention is used, and say so;
     - logits: `b × s × V × 4 B` (large vocabularies are a real term);
     - 3D path: frozen CT encoder activations plus connector, at the declared volume shape and fixed token count;
     - `tokens_per_step = micro_batch × seq_len × grad_accum × data_parallel`;
     - compute `≈ c × P_active × T_tokens`, with `c` declared (6 for full fine-tuning; the LoRA frozen-backbone value is argued in the text and shown as a range), and `time = FLOPs / (N_gpu × peak × MFU)`.
   - Outputs: per-GPU memory for each candidate × stage (stage 2 connector, stage 3 LoRA), with 1 GPU (Tier-2 smoke) and 8 GPUs (ZeRO-2/3), and for LoRA rank ∈ {8, 16, 64}. Flag each configuration FITS / DOES NOT FIT against B200 memory with a declared headroom (≥ 10%).
   - A dedicated **27B section** as required by CLAUDE.md: compute (GPU-hours, low/high), storage (base weights, adapters, checkpoints × retention, datasets, cached 3D features), cost (GPU-hours × assumed price, as a range), and schedule (wall-clock on 8x B200 against the proposal calendar in 1.5). It states that no figure is carried over from the withdrawn 4B target. It also names the fallback: the strongest valid smaller model, reported at its true scale.
   - Every figure is labelled **estimate, not measurement**. The Tier-2 manifests (item 4) name the measurements that will replace these figures.

3. **Config-first training skeleton** (`research/train/`, configs in `research/configs/`)
   - PyTorch + HF Transformers + PEFT. DeepSpeed ZeRO JSON configs are committed in `research/configs/deepspeed/` (zero2, zero3, bf16). `deepspeed` is **not** a `make test` dependency: tests validate the JSON keys/values, and the launcher imports deepspeed only when `--deepspeed` is given.
   - Components:
     - `Volume3DEncoder`, an interface with a tiny 3D-conv stand-in for CT-CLIP;
     - `FixedTokenConnector`, a Perceiver/RadFM-style resampler from any number of patches to exactly `n_query` tokens projected to the LM hidden size;
     - a backbone loaded through `AutoModelForCausalLM` (or a VLM class) **from config only** in dry-run mode;
     - a synthetic dataset of random volumes plus synthetic token ids, labelled `data_class=synthetic`.
   - Stage 2 (`stage2_connector.yaml`): the backbone and 3D encoder are frozen and only the connector trains, on paired (CT volume, report) samples. In the real run these come from CT-RATE; in the dry run they are synthetic.
   - Stage 3 (`stage3_lora.yaml`):
     - PEFT LoRA on the declared `target_modules`, and the connector is trainable;
     - modality dropout with probability `p` per modality;
     - report substitution (the image is replaced by the text report of the same image) is allowed **only** when the sample's `label_source` is not that report. This is enforced in the collator, not by convention.
   - A single entrypoint, `python -m research.train --config <yaml> --manifest <json> [--dry-run]`:
     - validates the manifest first with the same code as `scripts/validate_manifest.py`, and exits non-zero **before any model is constructed** if validation fails;
     - `--dry-run` forces CPU, a tiny model (≤ 2M params) and Tier 0;
     - it never calls `from_pretrained` with a hub id in dry-run mode;
     - it refuses to start on CUDA when the manifest tier is 0.
   - Checkpointing saves the trainable state only (connector + LoRA adapter + optimizer + RNG + step). Resume continues bit-identically on CPU.

4. **Experiment manifests and validator**
   - `schemas/experiment-manifest.schema.json` (JSON Schema 2020-12; the archived version under tag `archive/pre-factory-2026-09-26` may be reused and trimmed) and `scripts/validate_manifest.py` (schema plus semantic checks).
   - Manifests in `research/manifests/`, all with `status: "planned"`:
     - `smoke-s2-connector-<model>.json` and `smoke-s3-lora-<model>.json` for each of the 3 candidates (6 files), Tier 2, `gpu_count: 1`, `max_minutes ≤ 60`;
     - each includes the research question, the hypothesis/measurement goal (peak memory, tokens/s, loss decreases, checkpoint round-trip), seed, code revision (`UNPINNED` is allowed only while `planned`), `config_sha256`, dataset/split versions (`UNRESOLVED:<reason>` is allowed only while `planned`, because CT-RATE and PhysioNet access are pending), data classification and locality (`local_only`, no external API), budget, metrics, artifact locations, and stop rules;
     - each contains the literal note: "Tier-3/4 runs (beyond 1 GPU or 60 min, including any 8x B200 or ~27B full run) require explicit human approval recorded in docs/DECISIONS.md before launch."
   - Two Tier-0 manifests, `dryrun-s2.json` and `dryrun-s3.json` (`data_class: synthetic`, `gpu_count: 0`, tiny model). These are the manifests the CPU dry run uses.
   - Semantic rules in the validator:
     - `gpu_count > 1` or `max_minutes > 60` means tier ≥ 3;
     - tier ≥ 3 needs an `approval` block `{decision_ref, approved_by, date, budget, run_id}`, where `decision_ref` matches an existing dated heading in `docs/DECISIONS.md` and `run_id == experiment_id` (Tier 4 is approved per run);
     - `config_sha256` equals the recomputed sha256 of the referenced config file;
     - `UNPINNED`/`UNRESOLVED:` are rejected unless `status == planned`;
     - terminal statuses require a result block, and non-terminal statuses must not have one;
     - `data_class ∈ {mimic, hospital}` requires `locality: local_only`.

## Out of scope

- Downloading any weights, shards, tokenizers from the hub, or datasets. Launching any GPU, Tier-1+ or cloud job. Uploading anything to HF or any external service.
- Declaring the final base model. Any measured memory or throughput number (Tier-2 manifests are planned only).
- A real CT-CLIP checkpoint, real CT-RATE/MIMIC data loaders beyond an interface stub, the MRI encoder, evaluation metrics (task 10), and vLLM serving.
- Tier-3/4 manifests as committed artifacts. They appear only as negative test fixtures.
- Any change to `backend/`, `casegraph/`, or `web/` beyond pytest/Makefile wiring.

## Acceptance

| ID | Criterion | Threshold | How measured |
|---|---|---|---|
| S9-A01 | Every matrix cell cites a primary source | 100% of cells across 3 rows × 13 columns have `source_url` (https) on an allowlisted primary domain (huggingface.co model/license pages of the official org, arxiv.org, official vendor docs/blog/GitHub org, license text host) and `retrieved_on` (ISO date). 0 cells without a source. | pytest `test_matrix_every_cell_cited` (offline schema and allowlist check) |
| S9-A02 | Matrix values are accurate to their source | Checker opens the source for ≥ 15 cells, including every parameter count, every license/redistribution cell, and ≥ 3 benchmark numbers. 100% match the source. Any mismatch fails the slice. | Manual checker spot-check (network allowed for the checker only), recorded in the check report with URLs |
| S9-A03 | Benchmark numbers are not misleadingly compared | Every benchmark cell has `benchmark, split, metric, setting, comparable_group`. The rendered table ranks only within a `comparable_group`. 0 numbers without a citation. | pytest `test_benchmark_cells_complete`, `test_render_no_cross_group_ranking` |
| S9-A04 | Selection rubric is pre-declared and no winner is claimed | The rubric (criteria, weights summing to 1, hard constraints) exists. `final_selection` is `null` with `status: "pending_preliminary_experiments"`. The git log shows the rubric committed before any file under `research/results/`. | pytest `test_rubric_predeclared_no_winner`; reviewer checks git history |
| S9-A05 | License and contamination risks are surfaced | Each candidate has explicit fine-tune and redistribution cells (value or `null` plus a note) and a training-data overlap cell for MIMIC-CXR/MIMIC-IV/CT-RATE. Any candidate whose license restricts the open-weight release is listed under "Decisions needed". | pytest `test_license_and_overlap_cells_present`; reviewer |
| S9-A06 | Memory estimate shows its formula and inputs | ESTIMATE.md shows each formula symbolically, a table of inputs with the source URL or `ASSUMPTION` label, and results for 3 candidates × 2 stages × {1, 8} GPUs × r ∈ {8, 16, 64}. The code reproduces ESTIMATE.md byte-identically. | pytest `test_estimate_report_regenerates` (run script, diff against committed file) |
| S9-A07 | Estimate arithmetic is correct | For a hand-worked reference config in the test (small numbers), weights, LoRA params, trainable-state, activation, logits and tokens/step terms match the hand calculation exactly (integer bytes). `P_lora` matches PEFT's own `get_nb_trainable_parameters()` on the tiny model for 3 ranks. | pytest `test_estimate_terms_hand_calc`, `test_lora_param_formula_matches_peft[8,16,64]` |
| S9-A08 | The 27B estimate required by CLAUDE.md exists | ESTIMATE.md has a "27B flagship" section with compute (GPU-hours low/high), storage (itemized), cost (range, price labelled ASSUMPTION), and schedule against proposal 1.5, the no-4B-carry-over statement, and the fallback statement. Every number is labelled estimate. | pytest `test_27b_section_complete` (required headings/keys present); reviewer |
| S9-A09 | Stage 2 CPU dry run wires end to end | With the tiny model: forward, loss finite, backward, and an optimizer step over ≥ 3 steps. Connector params change. Backbone and 3D encoder params are bit-identical before and after. The connector outputs exactly `n_query` tokens for 2 different input volume shapes. | pytest `test_stage2_dry_run`, `test_connector_fixed_token_count[shapeA,shapeB]` |
| S9-A10 | Stage 3 CPU dry run wires end to end | LoRA adapters and the connector change. Base backbone weights are bit-identical. Trainable-parameter count equals the PEFT report. Loss finite for ≥ 3 steps. | pytest `test_stage3_dry_run` |
| S9-A11 | Checkpoint save/load round-trip for both stages | After save then load into a freshly built tiny model, the outputs on a fixed input are bit-identical (CPU, fixed seed). Resuming from the step-2 checkpoint and running to step 4 gives losses bit-identical to an uninterrupted 4-step run. The checkpoint contains no frozen base weights (its size is < 5% of the full tiny model state). | pytest `test_checkpoint_roundtrip[stage2,stage3]`, `test_resume_matches_uninterrupted[stage2,stage3]`, `test_checkpoint_excludes_frozen_weights` |
| S9-A12 | Modality dropout and report substitution respect label provenance | Over 1,000 synthetic samples with fixed seed: the empirical dropout rate is within ±0.05 of the configured `p` for each modality. Report substitution happens 0 times when `label_source` equals the substituted report, and > 0 times otherwise. A sample never has both the image and its report dropped when that modality is required. | pytest `test_modality_dropout_rate`, `test_no_report_substitution_when_report_is_label`, `test_required_modality_kept` |
| S9-A13 | CPU dry run is part of `make test` and is fast | `make test` runs `research/tests` (added to pytest `testpaths`) and passes. The research tests take ≤ 180 s wall-clock on a laptop CPU. | Checker runs `make test` from a clean clone and records duration (`pytest --durations`) |
| S9-A14 | No network, no GPU, no hub access in tests | The whole pytest run passes with sockets disabled (existing `--disable-socket`), `CUDA_VISIBLE_DEVICES=""`, and `HF_HUB_OFFLINE=1`/`TRANSFORMERS_OFFLINE=1` set by conftest. 0 calls to `from_pretrained` with a hub id in the dry-run path (monkeypatched to raise). A test asserts `torch.cuda.is_available()` is not relied on: the dry run passes with it patched to `True` and still runs on CPU. | pytest `test_dry_run_offline_cpu_only`, `test_no_hub_calls_in_dry_run` |
| S9-A15 | All committed manifests validate | 8/8 manifests in `research/manifests/` (6 Tier-2 smoke + 2 Tier-0 dry-run) exit 0 under `python3 scripts/validate_manifest.py research/manifests/*.json`. Each Tier-2 manifest has gpu_count 1, max_minutes ≤ 60, status planned, seed, data/split version, budget, and the Tier-3/4 human-approval note verbatim. | pytest `test_committed_manifests_valid`; checker runs the CLI |
| S9-A16 | Validator rejects unapproved or mis-tiered runs | Each negative fixture exits non-zero with a specific message: tier 3 without approval; tier 4 without approval; tier 4 whose approval `run_id` mismatches; approval `decision_ref` absent from `docs/DECISIONS.md`; tier 2 with gpu_count 2; tier 2 with 90 min; `UNPINNED` revision with status `running`; `config_sha256` mismatch; `data_class=mimic` without `local_only`; missing seed. 10/10 rejected. A tier-3 fixture with a valid approval passes (1/1). | pytest `test_validator_rejects[...]` (parametrized, 10 cases), `test_validator_accepts_approved_tier3` |
| S9-A17 | Launcher refuses invalid manifests before building a model | `python -m research.train` with an unapproved tier-3 manifest exits non-zero, and the model factory is called 0 times (spy). | pytest `test_launcher_rejects_before_model_build` |
| S9-A18 | DeepSpeed configs are well-formed and consistent | zero2/zero3 JSON parse. `bf16.enabled=true`. `train_micro_batch_size_per_gpu × gradient_accumulation_steps × world_size` equals the tokens/step basis used in ESTIMATE.md for the same config. No `fp16` block enabled. | pytest `test_deepspeed_configs` |
| S9-A19 | Repository hygiene for model artifacts | 0 tracked files > 5 MB. 0 tracked files with suffix `.safetensors, .bin, .pt, .pth, .ckpt, .gguf, .nii, .nii.gz, .dcm, .npz`. `research/**/outputs/` and checkpoint dirs are gitignored. 0 HF tokens (existing secret scan covers `research/`). | pytest `test_no_large_or_weight_files`; existing `test_repo_hygiene` |
| S9-A20 | Research dependencies are pinned and hashed | `torch` (CPU wheel), `transformers`, `peft`, `pyyaml` and `jsonschema` are pinned with `--require-hashes` in the lock used by `make test`. `deepspeed` is absent from that lock. The existing `test_provider_isolation` still passes. | Checker inspects the lock; `make test` |

The evaluation set for this slice is the fixed synthetic fixtures above: tiny model, synthetic volumes and tokens, 11 manifest fixtures, and 1 hand-worked estimate. There are no clinical gold labels, because no clinical output is produced.

## Required test cases (`research/tests/`, run by `make test`)

- `test_matrix_every_cell_cited`
- `test_benchmark_cells_complete`
- `test_render_no_cross_group_ranking`
- `test_rubric_predeclared_no_winner`
- `test_license_and_overlap_cells_present`
- `test_estimate_report_regenerates`
- `test_estimate_terms_hand_calc`
- `test_lora_param_formula_matches_peft[8|16|64]`
- `test_27b_section_complete`
- `test_stage2_dry_run`
- `test_connector_fixed_token_count[shapeA|shapeB]`
- `test_stage3_dry_run`
- `test_checkpoint_roundtrip[stage2|stage3]`
- `test_resume_matches_uninterrupted[stage2|stage3]`
- `test_checkpoint_excludes_frozen_weights`
- `test_modality_dropout_rate`
- `test_no_report_substitution_when_report_is_label`
- `test_required_modality_kept`
- `test_dry_run_offline_cpu_only`
- `test_no_hub_calls_in_dry_run`
- `test_committed_manifests_valid`
- `test_validator_rejects[tier3_no_approval|tier4_no_approval|tier4_runid_mismatch|decision_ref_missing|tier2_two_gpus|tier2_90min|unpinned_running|config_hash_mismatch|mimic_not_local|missing_seed]`
- `test_validator_accepts_approved_tier3`
- `test_launcher_rejects_before_model_build`
- `test_deepspeed_configs`
- `test_no_large_or_weight_files`

## Clinical and research-validity risks

| Risk | Mitigation in this slice |
|---|---|
| A preliminary or dry-run model is mistaken for a clinical model | Dry-run outputs are synthetic and labelled; no model output reaches `backend/` or `web/`; the research prototype claim boundary is repeated in ESTIMATE.md and SELECTION_MATRIX.md |
| Label leakage through report substitution (the report is the label source for CXR/CT findings, proposal 3.4) | Collator-level rule plus S9-A12 tests |
| Evaluation contamination: a base model was trained on MIMIC-CXR or other eval sources, inflating "base vs fine-tuned" comparisons (Table 3.2) | Overlap column (S9-A05). Such comparisons must disclose it. Official test splits only (proposal 3.4) |
| License blocks the open-weight release, or imposes use restrictions that flow down to our derivatives | License and redistribution cells (S9-A05). Release decision escalated to humans. Nothing is uploaded |
| MIMIC data leaves team control (PhysioNet rule, proposal 1.3.4) | Manifests require `locality: local_only` for mimic/hospital data (S9-A16). No external API in any stage config |
| Overstated capacity: the estimate is read as measured, or a 33B model is presented as "27B" | Every number is labelled estimate. True parameter counts come from the cited source. The fallback is reported at true scale (S9-A06, S9-A08) |
| Unapproved expensive or multi-GPU run | Validator plus launcher gate (S9-A15–A17). Tier-3/4 approval is recorded in `docs/DECISIONS.md` |
| Post-hoc selection bias in picking the base model | Rubric committed before results (S9-A04) |

## Run commands

```bash
make test                                                     # includes research/tests (CPU, offline)
python3 scripts/validate_manifest.py research/manifests/*.json
python -m research.train --config research/configs/stage2_connector.yaml --manifest research/manifests/dryrun-s2.json --dry-run
python -m research.train --config research/configs/stage3_lora.yaml     --manifest research/manifests/dryrun-s3.json --dry-run
python -m research.estimate.estimate --out research/estimate/ESTIMATE.md
python -m research.base_model.render --out research/base_model/SELECTION_MATRIX.md
```

## Decisions needed (humans; none block this slice)

- **Open-weight release versus the MedGemma license.** Whether the MedGemma license (Health AI Developer Foundations terms) allows the project's intended open-weight release of a fine-tuned derivative, and on what conditions. This must be settled before MedGemma can be the final base.
- **Lingshu-32B size.** Whether a model of about 33B counts as "approximately 27B" for the headline claim, or must be reported at its true scale.
- **Access to CT-RATE and PhysioNet.** Tier-2 manifests remain `planned` with `UNRESOLVED` data versions until access is granted and split versions exist.
- **Compute.** Whether the 8x B200 allocation is team-controlled infrastructure acceptable under the PhysioNet DUA for MIMIC processing. Any Tier-3/4 run needs a dated approval in `docs/DECISIONS.md`.
