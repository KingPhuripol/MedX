# Slice s8: Evaluation harness (Table 3.2) with patient-level bootstrap CI

- Owner (Gantt): สุปรียา (Gantt rows 21-23: evaluation criteria, comparison experiments, system testing)
- Source of truth: `docs/PROPOSAL.md` (v8). Sections used:
  - 1.2, objective 5: what gets evaluated.
  - 1.3.4: research prototype; evaluation scope is adults 18+.
  - 3.4: patient-level splits; the test set is not used for tuning.
  - 3.6 and Table 3.2: metrics and comparators; 95% CI from bootstrap at the patient level; results without expert review are labelled "System Evaluation", not clinical efficacy.
- Status: PLAN, written by the planner. The slice is data-agnostic. It is Tier 0 only (CPU, synthetic toy inputs), and no GPU or real data is involved.

## Scope

1. **Package `eval/`** (a Python library plus a CLI, run as `python -m eval`).
   - Pure functions: arrays or records in, floats out.
   - No imports from `backend/`, `casegraph/`, or any other slice.
   - Runtime dependency: `numpy`.
   - Test-only reference dependency: `scikit-learn` (which brings in `scipy`).
   - Both dependencies are added to `requirements.in`, and `requirements.lock` is regenerated with the uv command in its header, hash-pinned.
   - `eval/tests` is added to pytest `testpaths`.
2. **Metrics, one per row of Table 3.2.** All metrics are computed on the pooled rows of the evaluated patients, never as an average of per-patient scores (unless the metric says "per patient").

   | Table 3.2 row | Functions (`eval/metrics.py`) |
   |---|---|
   | Model, by modality | `macro_f1(y_true, y_pred, labels)`: labels are declared, with zero_division=0 as in sklearn. `multilabel_macro_f1` covers report-derived finding labels. `auroc(y_true, y_score)`: binary; multiclass OvR macro; multilabel macro. `dice(mask_true, mask_pred, empty_empty=1.0)`: per case, then averaged over cases. |
   | Case Graph | `hit_at_k` and `set_prf` (suggested vs later-ordered tests), `calls_per_patient`, `latency_per_patient` |
   | Provider swap | accuracy (any of the above), `latency_summary` (mean/median/p90, linear interpolation), `cost_per_patient` (sum over the patient's decision points, then mean over patients) |
   | Voice Agent | `field_prf(gold_fields, extracted_fields)`: exact match on normalized value per field, micro and per field. Also `response_latency` and `total_time` (via `latency_summary`). |
   | Department suggestion | `topk_accuracy(y_true, ranked, k in {1, 3})` |
   | Pharma Agent | `per_issue_type_pr(...)`: precision and recall per issue type, and each can have its own population, because recall comes from synthetic error injection and precision from the pharmacist-reviewed sample. The source of each is recorded in the output. |
   | Abstention | `coverage`, `selective_accuracy` (accuracy on answered cases). The always-answer comparator has coverage 1.0. |
   | Replay / Regenerate | `replay_determinism` (fraction of graphs whose no-cache replay node-output hashes are all identical, plus a node-level identical fraction), `recomputed_nodes` (mean/median recomputed vs a full-graph node count) |

   - An undefined value (for example, precision with 0 predicted positives, AUROC with one class, or selective accuracy at coverage 0) returns `null` with a `reason`. It never becomes 0 or 1.
   - Missing predictions are never dropped or treated as negative. They raise an error unless the metric is abstention-aware, in which case they count as abstain.
3. **Patient-level cluster bootstrap** (`eval/bootstrap.py`).
   - Resample patient IDs with replacement and keep all of each patient's decision points.
   - Recompute the metric on each resample.
   - Percentile 95% CI by default; `ci_level` and `n_boot` are configurable, with a default of 2000.
   - Fixed seed with `numpy.random.Generator(PCG64(seed))`.
   - **Paired mode** for comparator columns: system and comparator are resampled with the same patient draw, and the CI is for their difference.
   - A resample where the metric is undefined is skipped and counted (`n_degenerate`). The CI is flagged `unstable` if more than 1% of resamples are degenerate.
   - Every result reports `n_patients` and `n_decision_points`.
4. **Frozen evaluation manifest** (`eval/manifest.py` plus `eval/schemas/eval_manifest.schema.json`).
   - Fields:
     - `manifest_version`, `evaluation_id`, `slice`;
     - `dataset {name, version, data_class: synthetic|mimic|hospital}`, `split: train|dev|test`, `split_version`, `split_patient_list` (required for test);
     - `metrics[] {name, params, primary}`;
     - `comparators[]`;
     - `thresholds[] {metric, op, value, rule: point|ci_lower|ci_upper}`;
     - `bootstrap {n_boot, seed, ci_level, method}`;
     - `expert_review {done: bool, n_reviewers}`.
   - `python -m eval freeze <manifest>` validates the manifest. It then appends `{evaluation_id, sha256 of canonical JSON, frozen_at}` to the append-only ledger `eval/ledger/frozen.jsonl`.
5. **Runner** (`python -m eval run --manifest M --predictions P [--comparator C] --out DIR`). On a **test** split it refuses (non-zero exit, no results written) when any of these holds:
   - the manifest is not frozen;
   - the manifest's current hash differs from the frozen hash;
   - a predictions patient_id is not in `split_patient_list`;
   - a result was already recorded for this `evaluation_id` with a different predictions hash. Re-running with the same inputs is allowed and must reproduce the same bytes.

   Every test run is appended to `eval/ledger/runs.jsonl`. Nothing is overwritten.

   Dev-split runs without a frozen manifest are allowed, but they are stamped `UNFROZEN - exploratory (dev split)`.
6. **Outputs**, written to `DIR`:
   - `results.json`: canonical form, with sorted keys, no wall-clock time, and no absolute paths. It embeds the manifest hash, the predictions sha256, the seed, n_boot, and the numpy version.
   - `results.md` and `results.html`: a Table 3.2-style table with these columns: evaluated item, metric, point estimate, 95% CI, comparator, and difference with 95% CI. It also shows n patients / decision points and whether each threshold was met under its predeclared rule.
   - Labels:
     - The banner **"System Evaluation, not clinical efficacy"** appears whenever `expert_review.done` is false.
     - With review, the banner reads "System Evaluation with expert review - not a clinical efficacy study".
     - "Synthetic data" is shown when `data_class=synthetic`.
     - "Research prototype - not for clinical use" appears always.
7. **Toy fixtures and demo.**
   - `eval/examples/`: a toy manifest and synthetic predictions for every metric family.
   - `python -m eval demo --out DIR` produces a complete example report.

## Out of scope

- Any real, MIMIC, CT-RATE, or hospital data. There is no dependency on other slices' data, models, the Case Graph, the gateway, or the database.
- Creating the simulated patient set, simulated conversations, or clinical criteria (Gantt row 21 content). This slice only consumes their labels later.
- Defining clinical label mappings (services to department), the report-correctness labeller, or the synthetic error-injection generator.
- Running any Table 3.2 comparison experiment for real (Gantt row 22).
- UI or dashboard integration, hypothesis tests or p-values beyond paired CIs, calibration metrics, subgroup analyses, and multiple-comparison correction. These are recorded as follow-ups.

## Acceptance

| ID | Criterion | Threshold | How measured |
|---|---|---|---|
| S8-A01 | Macro-F1 (multiclass and multilabel) matches the reference | abs diff <= 1e-9 on >= 20 seeded random vectors plus edge cases (a declared label absent from y_true, a label never predicted) | pytest `test_macro_f1_matches_sklearn` against `sklearn.metrics.f1_score(average="macro", labels=..., zero_division=0)` |
| S8-A02 | AUROC (binary, multiclass OvR macro, multilabel macro) matches the reference, including ties | abs diff <= 1e-9 on >= 20 vectors per mode. A single-class input returns `null` with a reason (no exception, no 0.5). | pytest `test_auroc_matches_sklearn`, `test_auroc_single_class_null` |
| S8-A03 | Dice matches a hand-computed example and the formula | Exact on a hand-computed 2D and 3D mask. abs diff <= 1e-9 against `2|A∩B|/(|A|+|B|)` computed via `sklearn.metrics.f1_score` on flattened masks. The empty/empty case gives the declared value (1.0) and is recorded. | pytest `test_dice_hand_example`, `test_dice_matches_f1_flat`, `test_dice_empty_empty` |
| S8-A04 | Top-1 and top-3 department accuracy matches the reference | abs diff <= 1e-9 | pytest `test_topk_matches_sklearn` against `sklearn.metrics.top_k_accuracy_score` |
| S8-A05 | Field-level and per-issue-type P/R/F1 match the reference and a hand example | abs diff <= 1e-9 against `precision_recall_fscore_support`. The hand example is exact. Zero-denominator cases give `null` + reason (0 cases coerced to 0/1). Precision and recall computed on different populations carry distinct `source` tags. | pytest `test_field_prf`, `test_pharma_per_issue_pr`, `test_undefined_is_null` |
| S8-A06 | Coverage, selective accuracy, latency, cost/patient, and replay metrics match a hand-computed example | Exact on the hand examples. Percentiles match `numpy.percentile(method="linear")`. Coverage 0 gives selective accuracy `null`. | pytest `test_abstention_hand`, `test_latency_cost_hand`, `test_replay_metrics_hand` |
| S8-A07 | Missing predictions are never silently dropped or treated as negative | 100% of cases with a missing prediction raise an error (non-abstention metrics) or count as abstain (abstention metrics) | pytest `test_missing_prediction_policy` |
| S8-A08 | Cluster bootstrap resamples patients, not rows | (a) Every resample contains complete patients (all rows of a drawn patient, multiplicity preserved). (b) On a dataset of 50 patients x 10 identical rows each, the cluster CI width is >= 2.0x the row-level bootstrap CI width (expected about 3.2x). (c) With 1 row per patient, the cluster and row bootstrap give identical CIs for the same seed. | pytest `test_bootstrap_keeps_whole_patients`, `test_cluster_wider_than_row`, `test_cluster_equals_row_when_singletons` |
| S8-A09 | Simulated 95% CI coverage is correct on a known clustered distribution | For 200 patients with cluster sizes 1-5, the patient effect is p_i ~ Beta(2,2) and the rows are Bernoulli(p_i), so the true accuracy is 0.5. Over 1000 simulated datasets (n_boot=1000, fixed master seed), the cluster-bootstrap CI covers 0.5 in 0.93-0.97 of simulations. The row-level bootstrap is reported alongside it for contrast and is not gated. | pytest `test_bootstrap_coverage_simulation`, with a runtime budget of <= 120 s on a laptop CPU |
| S8-A10 | Paired comparator CI is correct | Comparing a system with itself gives difference 0 with CI [0, 0]. A constant shift of +delta in the per-patient metric gives a difference CI containing delta. The same patient draws are used for both arms (asserted). | pytest `test_paired_self_zero`, `test_paired_shift` |
| S8-A11 | Degenerate resamples are handled explicitly | `n_degenerate` is reported. A CI with more than 1% degenerate resamples is flagged `unstable`. No NaN appears in the CI bounds. | pytest `test_degenerate_resamples_flagged` |
| S8-A12 | Runner blocks test-split reporting without a frozen manifest | 5/5 refusal cases exit non-zero and write 0 result files: (1) not frozen, (2) edited after freeze (hash mismatch), (3) a patient not in `split_patient_list`, (4) test manifest missing `split_patient_list`, (5) a second test run for the same `evaluation_id` with different predictions. The same-input re-run succeeds. | pytest `test_runner_refuses_unfrozen_test`, `test_runner_refuses_hash_mismatch`, `test_runner_refuses_foreign_patient`, `test_runner_requires_split_list`, `test_runner_refuses_resubmission`, `test_runner_rerun_same_inputs_ok` |
| S8-A13 | Thresholds are predeclared and evaluated only by their declared rule | A threshold in the manifest is required for a pass/fail cell. If the manifest has none, the cell shows `not declared`. Pass/fail follows `rule` (point / ci_lower / ci_upper) exactly. The ledgers are append-only: an earlier line is never rewritten, checked by a prefix check across runs. | pytest `test_threshold_rules`, `test_ledgers_append_only` |
| S8-A14 | Results are reproducible byte-for-byte | Two runs with the same manifest, predictions, and seed produce identical sha256 hashes of `results.json`, `results.md`, and `results.html`. A different seed changes at least one CI bound. | pytest `test_byte_reproducible`, `test_seed_changes_ci` |
| S8-A15 | Report labelling is correct | With `expert_review.done=false`, the MD and HTML contain "System Evaluation, not clinical efficacy" (2/2). Every report contains "Research prototype". Synthetic data is labelled. Dev unfrozen runs are stamped `UNFROZEN`. There are 0 occurrences of "diagnos", "clinical efficacy demonstrated", or "accuracy of diagnosis" claims outside the banner. | pytest `test_report_labels`, `test_report_no_clinical_claims` |
| S8-A16 | Every result row carries a CI and sample sizes | 100% of metric rows in `results.json` have `point`, `ci_low`, `ci_high`, `ci_level`, `n_boot`, `seed`, `n_patients`, `n_decision_points` (or `null` + reason when undefined) | pytest `test_results_schema` (JSON Schema `eval/schemas/results.schema.json`) |
| S8-A17 | Data-agnostic and isolated | 0 imports of `backend`, `casegraph`, or other slice packages from `eval/`. 0 network calls (pytest-socket). All fixtures are synthetic and generated or committed under `eval/`. | pytest `test_eval_isolation` (AST scan) |
| S8-A18 | The demo produces a complete report | `python -m eval demo --out DIR` exits 0 and writes all 3 files, with one row per Table 3.2 family (8/8). | pytest `test_demo_end_to_end` |
| S8-A19 | `make test` is green | Exit 0, 0 failed, 0 errors; the existing s0 tests still pass. The new lockfile installs with `--require-hashes`. | Run `make test` in a clean clone of the branch and record the output. |

## Required test cases

These live in `eval/tests/` and run under `make test`:

- `test_macro_f1_matches_sklearn`
- `test_auroc_matches_sklearn`, `test_auroc_single_class_null`
- `test_dice_hand_example`, `test_dice_matches_f1_flat`, `test_dice_empty_empty`
- `test_topk_matches_sklearn`
- `test_field_prf`, `test_pharma_per_issue_pr`, `test_undefined_is_null`
- `test_abstention_hand`, `test_latency_cost_hand`, `test_replay_metrics_hand`
- `test_missing_prediction_policy`
- `test_bootstrap_keeps_whole_patients`, `test_cluster_wider_than_row`, `test_cluster_equals_row_when_singletons`
- `test_bootstrap_coverage_simulation`
- `test_paired_self_zero`, `test_paired_shift`, `test_degenerate_resamples_flagged`
- `test_runner_refuses_unfrozen_test`, `test_runner_refuses_hash_mismatch`, `test_runner_refuses_foreign_patient`, `test_runner_requires_split_list`, `test_runner_refuses_resubmission`, `test_runner_rerun_same_inputs_ok`
- `test_threshold_rules`, `test_ledgers_append_only`
- `test_byte_reproducible`, `test_seed_changes_ci`
- `test_report_labels`, `test_report_no_clinical_claims`
- `test_results_schema`, `test_eval_isolation`, `test_demo_end_to_end`

Ledger tests write to a `tmp_path` ledger. They never write to the committed `eval/ledger/`.

## Clinical and validity risks

| Risk | Mitigation in this slice |
|---|---|
| Reports are read as clinical efficacy | Mandatory banner and no-claim scan (A15). Synthetic data is labelled. |
| Test-set tuning or metric/threshold selection after results | Freeze-before-test with hash, append-only ledgers, refusal on resubmission, and thresholds evaluated only by their predeclared rule (A12, A13) |
| CIs too narrow because decision points of the same patient are correlated | Cluster bootstrap at the patient level, verified against the row bootstrap and by coverage simulation (A08, A09) |
| Patient leakage across splits reaches the reported numbers | The test run requires `split_patient_list` and rejects foreign patients (A12) |
| Undefined metrics are reported as 0 or 1, or missing predictions as negatives | `null` + reason, degenerate counts, and a missing-prediction policy (A02, A05, A07, A11) |
| Pharma precision and recall come from different populations and get merged into one misleading F1 | Separate `source` tags. No F1 is reported when the sources differ (A05). |
| Silent irreproducibility | Seeded PCG64, pinned numpy, canonical JSON, byte-identical reruns (A14) |

## Run commands

```bash
make test                                                      # includes eval/tests
.venv/bin/python -m eval demo --out /tmp/s8-demo               # toy report: results.json/.md/.html
.venv/bin/python -m eval freeze eval/examples/toy_manifest_test.json
.venv/bin/python -m eval run --manifest eval/examples/toy_manifest_test.json \
    --predictions eval/examples/toy_predictions.jsonl \
    [--comparator eval/examples/toy_comparator.jsonl] --out /tmp/s8-run
```

## Decisions needed (none blocking)

- New dependencies: `numpy` (runtime) and `scikit-learn` (test-only reference) change the shared `requirements.lock`. Parallel slices that also relock may conflict at merge. The integrator should relock once after merge.
- Default CI method: percentile. BCa is a later option if coverage on small n fails. Any change must be made in the manifest before results.
- The default for the `empty_empty` Dice convention is 1.0. The model slice may override it in its manifest before freezing.
