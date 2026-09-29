# Slice s9r — Research v1.1: approval gate and data-safety fixes

- Owner (Gantt): ธนาพล
- Type: delta on `slices/s9/SPEC.md` at tip `c83d914`. Every S9 acceptance item (S9-A01..A20) stays in force and must still pass. The one deliberate change is that S9-A16's positive fixture must now carry an explicit approval record (a stricter gate, not a relaxed one).
- Source of truth: `docs/PROPOSAL.md` v8. Sections used: 1.3.4 (MIMIC stays on team-controlled machines; fine-tune size depends on the GPU allocation), 2.1.2 (LoRA freezes the base weights and trains small added matrices), 3.3 (stage 3: "Fine-tune **Backbone** with LoRA together with the Connector", with modality dropout and report substitution "only for tasks whose label does not come from that report"), 3.4 (patient-level split; a report is never an input when it is the label source). Also binding: the `CLAUDE.md` training tiers and human approval gates ("Record each approved action as a dated entry in `docs/DECISIONS.md` (what, who approved, scope)").
- Status: PLAN, written by the planner. No GPU, no network, no downloads, no real data.

## Why (reviewer conditions on s9)

| Severity | Finding | Evidence |
|---|---|---|
| HIGH | `research/manifest_validation.py` accepts a tier-3/4 manifest when `approval.decision_ref` equals **any** dated heading in `docs/DECISIONS.md`. The existing heading `2026-09-26 — Reset to Proposal v8` is therefore enough to "approve" an 8-GPU run. The approval scope (tier, GPUs, budget, approver) is never compared with the manifest. | `semantic_errors()`: only `decision_ref in dated_headings()` and `run_id == experiment_id` are checked |
| MEDIUM | `stage3_lora.yaml` `target_modules` are bare leaf names (`q_proj … down_proj`). PEFT matches these by suffix, so they also wrap vision-tower and connector modules when LoRA is applied to a real VLM. | Planner check (transformers 5.17.0, config-only on the meta device, default configs): Gemma3ForConditionalGeneration (MedGemma) has `model.vision_tower.encoder.layers.N.self_attn.{q,k,v}_proj`. Qwen2_5_VLForConditionalGeneration (Lingshu) has `model.visual.blocks.N.mlp.{gate,up,down}_proj`. Qwen3_5ForConditionalGeneration (Qwen3.8) has `model.language_model.layers.N.linear_attn.*` (Gated DeltaNet, which the config says are not adapted). The language-model paths are `model.language_model.layers.N.{self_attn,mlp}.*` in all three. |
| MEDIUM | The collator blocks report substitution only when `label_source == report_ref` by exact string equality. `MIMIC-CXR/s50414267` and `mimic-cxr:files/p10/p10000032/s50414267.txt` name the same report and would pass. | `research/train/data.py` `decide_modalities()` and the collator's defence-in-depth check |
| LOW | The launcher writes `run.json` only for `NonFiniteLossError`, `CheckpointError` and `KeyboardInterrupt`. Any other exception leaves a run directory with no status record, which hides a failed run. | `research/train/launcher.py` `run_dry()` |

## Scope

1. **Explicit, scope-bound approvals** (`research/manifest_validation.py`, new `schemas/approval-record.schema.json`, `scripts/validate_manifest.py`)
   - An approval is valid only if it is a fenced block with info string `approval`, containing one JSON object, placed inside the section of a dated heading `## YYYY-MM-DD …` in `docs/DECISIONS.md`. Prose, heading text, HTML comments and blocks outside a dated section do not count.
   - Record fields (the schema is closed, `additionalProperties: false`): `experiment_id`, `manifest_sha256` (required for tier 4, optional for tier 3), `tier`, `gpu_count`, `max_minutes`, `gpu_hours`, `cost_usd_max`, `approved_by`, `date`, `scope`.
   - `manifest_sha256` is the sha256 of the canonical JSON of the manifest with the keys `approval`, `status` and `result` removed (`sort_keys=True`, `separators=(",", ":")`, `ensure_ascii=False`, UTF-8). A status change from planned to approved to running does not invalidate the approval. Any change to resources, config, data, code or model does. `scripts/validate_manifest.py --approval-sha <manifest>` prints this value so a human can write it into the record.
   - For tier ≥ 3, the validator requires all of the following:
     - `approval.decision_ref` equals the full heading text exactly;
     - that section contains exactly one approval record for this `experiment_id`, and the whole log contains no other record for it;
     - record `experiment_id` = manifest `experiment_id` = `approval.run_id`;
     - record `tier` = `run_tier`, and record `gpu_count` = `resources.gpu_count`;
     - manifest `max_minutes`, `budget.gpu_hours` and `budget.cost_usd_max` are each ≤ the record's value;
     - record `approved_by` = `approval.approved_by`;
     - record `date` = `approval.date` = the heading date;
     - if `manifest_sha256` is present (always for tier 4), it equals the recomputed hash;
     - `approved_by` is not an agent identity (case-insensitive match against the stems of `.claude/agents/*.md` and the tokens `claude`, `agent`, `assistant`, `bot`, `orchestrator`, `planner`, `builder`, `checker`, `reviewer`).
   - Every failure produces a specific message. The launcher calls the same code (S9-A17 is unchanged).
2. **Language-backbone-only LoRA** (`research/configs/stage3_lora.yaml`, `research/train/models.py`)
   - `real_run.lora.target_modules` becomes a map from candidate id to one anchored regex string (`^…$`, used by PEFT's full-match mode). Each regex matches only `model.language_model.layers.\d+.` paths: `self_attn.{q,k,v,o}_proj` and `mlp.{gate,up,down}_proj`. For Qwen3.8, `linear_attn.*` is excluded, in line with the existing scope note.
   - `dry_run.lora.target_modules` becomes an anchored regex for the tiny model's backbone paths.
   - Bare leaf-name lists are rejected by a config test.
   - The config sha changes, so `dryrun-s3.json` and the three `smoke-s3-lora-*.json` manifests get their `config_sha256` updated and must still validate.
3. **Normalized label-source identity** (`research/train/data.py`)
   - `canonical_source_id(ref) -> (dataset, study_id)` applies, in order: Unicode NFKC and casefold, trimming, `file://` removal, `\` → `/`, collapsing duplicate slashes, stripping directories and the `.txt` extension, a dataset alias table (e.g. `mimic-cxr`, `MIMIC_CXR`, `mimiccxr` and `mimic-cxr-jpg` → `mimic-cxr`, because MIMIC-CXR-JPG reuses the MIMIC-CXR reports; `ct-rate`, `CT_RATE` and `ctrate` → `ct-rate`; `synthetic`), and study-id normalization (`s50414267` ≡ `50414267`).
   - Both `decide_modalities()` and the collator's defence-in-depth check compare canonical ids, not strings.
   - **Fail closed:** if either reference cannot be parsed or names an unknown dataset, substitution is treated as forbidden for that sample. The existing rule then applies: keep the image if the modality is required, otherwise drop it. The event is counted.
   - Structured, non-report label sources (e.g. `structured:service`) remain eligible for substitution.
4. **`run.json` for every failure** (`research/train/launcher.py`)
   - As soon as the run directory exists, `run.json` is written with status `running`, so a hard kill leaves a non-terminal record rather than none. All writes are atomic (temp file plus `os.replace`).
   - Any `Exception` after the run directory is created (model build, parameter cap, dataset, collator, optimizer, training step, checkpoint, environment capture) is caught at one outer boundary and produces:
     - `status: failed`, with `error_type`, `error` and a traceback tail;
     - `steps_completed`;
     - exit code `EXIT_FAILED` (3);
     - the traceback on stderr.
   - `KeyboardInterrupt` still means `stopped`. Preflight refusals still exit 2 before any run directory is created.

## Out of scope

- Any Tier ≥ 1 execution, GPU use, weight or dataset download, or network access in tests.
- Committing a tier-3/4 manifest, or adding an approval record to the real `docs/DECISIONS.md`. Forgery and approval fixtures live only in `tmp_path`.
- Proving that a human wrote an approval record. This remains a git-review responsibility (see Risks).
- Real MIMIC or CT-RATE loaders. Changes to the selection matrix, ESTIMATE.md numbers, `backend/`, `casegraph/` or `web/`.

## Acceptance

| ID | Criterion | Threshold | How measured |
|---|---|---|---|
| S9R-A01 | Every S9 acceptance item still passes | S9-A01..A20: every S9 test named in `slices/s9/SPEC.md` still exists and passes, with 0 skipped, xfailed or deleted. S9-A16 keeps its 10 rejections, and its positive case now uses an explicit record. S9-A02 is not re-run, because the matrix is unchanged: `git diff c83d914 -- research/base_model/` is empty. | `make test`; checker diffs the collected S9 test IDs against the S9 spec list and re-runs the S9 CLI commands |
| S9R-A02 | Approval-record format is defined and parsed | `schemas/approval-record.schema.json` exists (closed schema, all fields above). The parser extracts only fenced `approval` blocks inside dated sections (fixture with 1 valid block, 1 block in prose, 1 in an HTML comment, 1 under an undated heading gives exactly 1 record). | pytest `test_approval_record_parsing` |
| S9R-A03 | Forged or mis-scoped tier ≥ 3 approvals are rejected | 14/14 negative fixtures (13 forgery paths + `record_schema_invalid`) exit non-zero with a case-specific message (list below). This includes the actual HIGH case: `decision_ref` = the real heading `2026-09-26 — Reset to Proposal v8`. | pytest `test_validator_rejects_forged_approval[...]` (14 cases); `test_validator_rejects_real_reset_heading` against the real `docs/DECISIONS.md` |
| S9R-A04 | A correct explicit approval is accepted | 3/3 accepted: tier 3 with record by id only; tier 3 with id and correct sha; tier 4 with id and correct sha. The same tier-4 manifest with `status` changed planned → approved → running is still accepted (3/3). Changing `resources.gpu_count`, `code.config_sha256` or a dataset `split_version` after approval is rejected (3/3). | pytest `test_validator_accepts_explicit_approval[...]`, `test_approval_sha_status_invariant`, `test_approval_sha_binds_content[...]` |
| S9R-A05 | The launcher enforces the same gate | A tier-3 manifest with a forged approval (the reset-heading case) makes `python -m research.train` exit 2. The model factory is called 0 times (spy), and 0 run directories are created. | pytest `test_launcher_rejects_forged_approval` |
| S9R-A06 | The approval sha helper matches the validator | `scripts/validate_manifest.py --approval-sha <m>` prints the same 64-hex value the validator recomputes, for 2 manifests. | pytest `test_approval_sha_cli` |
| S9R-A07 | LoRA targets are fully qualified and backbone-only in config | Every `target_modules` entry in `stage3_lora.yaml` (3 candidates + dry run) is a single string anchored `^…$`. 0 bare leaf-name lists. Each candidate regex contains `language_model`. | pytest `test_lora_targets_are_anchored_regex` |
| S9R-A08 | LoRA wraps 0 vision or connector modules on the three candidate architectures | For tiny config-only CPU instances (no weights, no hub) of `Gemma3ForConditionalGeneration`, `Qwen2_5_VLForConditionalGeneration` and `Qwen3_5ForConditionalGeneration`, applying the matching candidate regex through PEFT gives: 0 LoRA-wrapped modules outside `model.language_model.`; 0 in `linear_attn` (Qwen3.5); and a wrapped count exactly equal to 3 × (decoder layers) + 4 × (full-attention layers). **Negative control:** the S9 bare-name list wraps > 0 vision modules on Gemma3 and on Qwen2.5-VL, which proves the test can fail. | pytest `test_lora_backbone_only[gemma3,qwen2_5_vl,qwen3_5]`, `test_bare_names_would_wrap_vision[gemma3,qwen2_5_vl]` |
| S9R-A09 | LoRA wraps 0 3D-encoder or connector modules on the dry-run model | On the stage-3 tiny `CaseModel`, 0 LoRA layers under `encoder.` or `connector.`. The wrapped count equals 7 × the tiny backbone's layers. S9-A10 (trainable count equals the PEFT report; base weights bit-identical) still passes. | pytest `test_dry_run_lora_scope`; `test_stage3_dry_run` |
| S9R-A10 | Label-source report substitution is blocked under identity variants | ≥ 12 variant pairs, with the report and `label_source` naming the same (dataset, study), cover at least: case; surrounding whitespace; NFKC full-width characters; relative path; absolute path; `file://` URI; backslash path; `.txt` suffix; study id with and without the `s` prefix; dataset alias `MIMIC_CXR`/`mimiccxr`; `mimic-cxr-jpg` versus `mimic-cxr`; `CT_RATE`/`ctrate`. Each gives 0 substitutions over 1,000 seeded draws with dropout p = 1.0. The collator's defence check raises `ReportLeakageError` when a substituted decision is forced for each variant. | pytest `test_no_substitution_under_identity_variants[...]` (≥ 12), `test_collator_defence_uses_canonical_id[...]` |
| S9R-A11 | Unknown or unparseable sources fail closed | With `label_source` or `report_ref` unparseable or naming an unknown dataset: 0 substitutions over 1,000 draws. A required modality keeps its image (100%). A counter records the fail-closed events (> 0). | pytest `test_unparseable_source_fails_closed` |
| S9R-A12 | No over-blocking | Substitution still happens (> 0 over 1,000 draws, p = 1.0) for: a different study of the same patient; the same numeric id in a different dataset; the label source `structured:service`. S9-A12's empirical dropout rate is still within ±0.05 of p. | pytest `test_substitution_allowed_for_distinct_source[...]`; `test_modality_dropout_rate` |
| S9R-A13 | Every launcher exception leaves a failed `run.json` | Faults are injected (monkeypatch) at ≥ 7 points after run-directory creation: `build_model`; parameter-cap `LaunchRefused`; dataset constructor; `Collator`; `make_optimizer`; `train_steps` (a generic `RuntimeError`); `save_checkpoint` (an `OSError`); `environment()`. In 100% of cases `run.json` exists, parses, and has `status == "failed"`, a non-empty `error_type` and `error`, and `steps_completed`. The exit code is 3. `KeyboardInterrupt` still gives `stopped` with exit 130. Between run-directory creation and model build, `run.json` has `status == "running"`. Preflight refusal creates 0 run directories. | pytest `test_run_json_on_every_exception[...]` (≥ 7), `test_run_json_written_before_model_build`, `test_interrupt_still_stopped`, `test_launcher_rejects_before_model_build` |
| S9R-A14 | The whole suite is green, offline, CPU-only and fast | `make test` exits 0. Sockets are disabled, `CUDA_VISIBLE_DEVICES=""`, and `HF_HUB_OFFLINE=1` (S9-A14 conftest). `research/tests` finish in ≤ 180 s wall-clock (S9-A13), including the new tiny-VLM tests. 0 `from_pretrained` calls with a hub id. | Checker runs `make test` from a clean clone with `pytest --durations=15` and records the time |
| S9R-A15 | No real approval or high-tier manifest is committed | `git diff c83d914 -- docs/DECISIONS.md` adds 0 fenced `approval` blocks. `research/manifests/` still holds exactly the 8 S9 manifests, all `status: planned` and tier ≤ 2. | pytest `test_committed_manifests_valid` (S9); checker inspects the diff |

### S9R-A03 negative fixtures (each rejected with its own message)

1. `reset_heading_no_record`: `decision_ref` names an existing dated heading whose section has no approval block (the real reset heading).
2. `record_other_experiment`: the record's `experiment_id` is another manifest's id.
3. `record_in_prose`: the approval JSON appears in the section as plain text, not as a fenced `approval` block.
4. `record_in_other_section`: a valid record sits under a different heading from `decision_ref`.
5. `tier_mismatch`: the record approves tier 3; the manifest is tier 4.
6. `gpu_count_exceeds`: the record approves 4 GPUs; the manifest asks for 8.
7. `minutes_exceed`: manifest `max_minutes` > record `max_minutes`.
8. `budget_exceeds`: manifest `gpu_hours` or `cost_usd_max` > record value.
9. `approver_mismatch`: manifest `approval.approved_by` ≠ record `approved_by`.
10. `agent_self_approval`: `approved_by` is an agent identity (e.g. `research-lead`, `Claude`).
11. `date_mismatch`: record date ≠ heading date or ≠ `approval.date`.
12. `sha_mismatch_or_missing_tier4`: tier 4 with no `manifest_sha256`, or a sha that does not match the manifest content.
13. `duplicate_record`: two records for the same `experiment_id` anywhere in the log.
(Also, a malformed record that fails the schema is rejected, tested as `record_schema_invalid`.)

## Required test cases (`research/tests/`, all run by `make test`)

`test_approval_record_parsing`, `test_validator_rejects_forged_approval[reset_heading_no_record|record_other_experiment|record_in_prose|record_in_other_section|tier_mismatch|gpu_count_exceeds|minutes_exceed|budget_exceeds|approver_mismatch|agent_self_approval|date_mismatch|sha_mismatch_or_missing_tier4|duplicate_record|record_schema_invalid]`, `test_validator_rejects_real_reset_heading`, `test_validator_accepts_explicit_approval[tier3_id|tier3_sha|tier4_sha]`, `test_approval_sha_status_invariant`, `test_approval_sha_binds_content[gpu_count|config_sha|split_version]`, `test_approval_sha_cli`, `test_launcher_rejects_forged_approval`, `test_lora_targets_are_anchored_regex`, `test_lora_backbone_only[gemma3|qwen2_5_vl|qwen3_5]`, `test_bare_names_would_wrap_vision[gemma3|qwen2_5_vl]`, `test_dry_run_lora_scope`, `test_no_substitution_under_identity_variants[≥12]`, `test_collator_defence_uses_canonical_id[...]`, `test_unparseable_source_fails_closed`, `test_substitution_allowed_for_distinct_source[other_study|other_dataset|structured]`, `test_run_json_on_every_exception[build_model|param_cap|dataset|collator|optimizer|train_step|checkpoint|environment]`, `test_run_json_written_before_model_build`, `test_interrupt_still_stopped`, plus every S9 test listed in `slices/s9/SPEC.md`.

Gold labels: none are clinical. The evaluation set is the fixed synthetic fixtures above: 14 approval fixtures plus 3 positive cases, 3 tiny VLM architectures plus the dry-run model, ≥ 12 identity-variant pairs plus 3 distinct-source controls, and ≥ 8 fault-injection points.

## Clinical and research-validity risks

| Risk | Mitigation |
|---|---|
| An agent or a copy-paste launches an unapproved multi-GPU or 27B run by citing an unrelated decision | Scope-bound, per-manifest records (S9R-A02..A05). Tier 4 is bound to the manifest's content hash. |
| Residual: the validator cannot prove that a human wrote the record | Records reach `main` only through human-reviewed commits. The reviewer checks that any commit adding an `approval` block was authored or approved by a named human. Agent-identity approvers are rejected (fixture 10). |
| Label leakage: the report that is the label source is fed as input through an equivalent but differently spelled reference, inflating findings metrics (proposal 3.4) | Canonical identity plus fail-closed behaviour (S9R-A10, A11), with an over-blocking control (A12) so the rule is not trivially "never substitute". |
| Unintended adaptation of the vision tower or connector: this changes which weights are trained, breaks matched-budget comparisons against the base model (Table 3.2), and alters the 2D encoder without validation | Anchored backbone-only regexes, verified on the real architecture classes with a negative control (S9R-A07..A09). |
| A failed run leaves no status record and disappears from the evidence (CLAUDE.md: never hide failed runs) | `run.json` from creation onward, with a failed status on every exception (S9R-A13). |

## Run commands

```bash
make test
python3 scripts/validate_manifest.py research/manifests/*.json
python3 scripts/validate_manifest.py --approval-sha research/manifests/smoke-s3-lora-qwen3.8-27b.json
python -m research.train --config research/configs/stage3_lora.yaml --manifest research/manifests/dryrun-s3.json --dry-run
.venv/bin/python -m pytest -q research/tests --durations=15
```

## Decisions needed (humans; none block this slice)

- Whether `approved_by` should also be checked against a named human-approver allowlist (for example, the project owner and the advisor). This slice only rejects agent identities.
