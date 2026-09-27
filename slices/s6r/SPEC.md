# Slice s6r — Care suggestion v1.1: dev-only improvement, fresh held-out test run once

- Owner (Gantt): ธัญรดา. Delta on `slices/s6/SPEC.md` (tip c08584c). Everything in s6 stays in force unless changed here.
- Source of truth: `docs/PROPOSAL.md` v8, sections 1.3.1, 3.4 (patient-level split, no leakage), 3.6 / Table 3.2 (label (3) proxy, coverage + answered accuracy vs always-answer, patient-level bootstrap 95% CI, System Evaluation without expert review).
- Governing decision: `docs/DECISIONS.md` "2026-09-27 — S6 test split redone on a fresh held-out set" (commit e111658). This spec does not add or record any approval.
- Tier 0 only: CPU, synthetic, offline, deterministic, no external provider. Ports **8106 / 3106**.
- Open checker failure being closed: S6-A09 FAIL on c08584c (the A10 harness re-render appended a second frozen run for `s6-care-test-0001`, runs seq 4). S6-A10 was fixed in a88edf1. The checker also filed "measure `git diff main -- casegraph/` against ef4a3d2", adopted below.

## Fixed choices (predeclared here, before any held-out data exists)

| Item | Value |
|---|---|
| Retired evaluation | `s6-care-test-0001`. Label: `seen — not a held-out result` |
| Dev evaluation ids | before = `s6-care-dev-0001` (committed, rules `care-rules-1.0.0`); after = `s6-care-dev-0002` (rules `care-rules-1.1.0`) |
| New held-out evaluation id | `s6-care-test-0002` (manifest `slices/s6/eval/manifest_test_0002.json`, results `slices/s6/eval/results_test_0002/`, summary `slices/s6/eval/summary_test_0002.json`) |
| Ledger | the existing slice ledger `slices/s6/eval/ledger/` (append only; history kept) |
| Generator | `data_factory` `GENERATOR_VERSION = "1.2.1"` |
| Held-out seed | **20260927** (unused anywhere in the repo at spec time; fixed here so no seed can be chosen after seeing data) |
| Held-out size | **72 patients** (8 revisit), 80 cases, 160 decision points, split name `test`, same `QUOTAS` as v1. 72 is chosen, not 36, because the retired set had only 17 answered evaluable decision points (below the s6 minimum of 30) |
| Held-out identity namespace | patients `SYNH-NNNN`, cases `SYNHE-NNNN`; path `data/synthetic/s6r-heldout` |
| Bootstrap | eval defaults, n_boot 2000, seed 20260926, patient level |

## Scope

1. **Retire `s6-care-test-0001`.** A deterministic, idempotent command (e.g. `python -m app.care.evaluate retire`) adds to `slices/s6/eval/results_test/results.json` a top-level `retired` object (`label`, `reason`, `decision: "DECISIONS.md 2026-09-27"`, `original_results_sha256`), and puts the label as the first banner line of `results.md`, `results.html` and in `summary_test.json`. Ledger lines are never edited or deleted. Paths are kept. Any doc or report that shows an S6 test number shows `s6-care-test-0002` only.
2. **Runner re-render fix** (`eval/runner.py`). On a frozen **test** manifest, a run whose manifest sha, predictions sha and comparator sha all equal an existing run line for the same `evaluation_id` is a re-render. It writes the report (the never-overwrite-different-bytes rule still holds, so a harness change renders to a new directory), prints `re-render of run seq N; no ledger line appended`, and appends **0** lines. On **dev** the S8 rule is unchanged: an identical-input re-run appends a run line. Resubmission with different inputs on test is still refused. `eval/tests/test_runner.py::test_runner_rerun_same_inputs_ok` changes its test-split count from 2 to 1 (the only sanctioned edit to an existing test; D-s6r-1).
3. **Care engine v1.1 from train/dev only.** `care_rules_v1.json` → `care-rules-1.1.0` with a new pinned sha256. Error analysis uses dev (and train) predictions only. Known dev defects at spec time: pathway top-1 misses on `SYNE-0011:T1/T2` (engine `CP-NEWS-URGENT-REVIEW`, gold `CP-SEPSIS-SCREEN` when qSOFA and NEWS co-fire), and proxy hit@3 0.032 because gold `ordered_after_T` is mostly routine labs (CREAT/HGB/WBC) that no sourced complaint rule suggests. Every rule change is logged in `backend/app/care/rules/CHANGELOG.md` with the motivating train/dev decision-point ids and ≥1 verified source ref. A rule whose only motive is to raise the proxy, with no guideline source, is not allowed. Red-flag rules, `casegraph`, the gateway contract and the gold templates are not changed.
4. **Fresh held-out set** (`data_factory` v1.2.1). The change is additive: an identity namespace plus a held-out mode that writes only the `test` split at the fixed size. At the default seed the output keeps every `inputs/**` byte-identical to v1.2.0 and the gold identical except `label_version`. Leakage and factory audit PASS. The held-out set is generated only **after** the `care-rules-1.1.0` commit. The manifest (with the held-out `tree_sha256`, the seed and the 72-patient list) is written from gold, not from predictions, committed and frozen. Only then is it run, exactly once.
5. **Evaluation and reporting.** `app.care.evaluate` gains `--dataset` and `--evaluation-id`. It **refuses** `--split test` against the v1 dataset (retired) with a message naming the decision. `make care-eval` gains `DATASET` / `EVAL_ID` variables. `slices/s6r/eval/dev_before_after.{json,md}` gives the before/after dev table. `results_test_0002` reports the held-out results. Both are labelled "System Evaluation on synthetic data — not clinical performance".

## Out of scope

- Any use of the v1 `test` split or of `results_test/` for a design, rule, threshold or metric choice. Invariant tests that already run over all splits (abstention exactness, time validity, claim scan) keep running and do not tune anything.
- New metrics, changed thresholds or changed metric definitions. The s6 manifest metric set, comparators and thresholds are reused unchanged.
- Changes to red-flag rules, the s4 adapter mapping, `casegraph` types, the gateway contract, the web UI, the gold templates or the care gold semantics.
- Symptom-to-red-flag wiring (D2), expert rating (D1), real or external data, calibrated probabilities.
- Deleting or rewriting any ledger line, result directory or run evidence.

## Acceptance

"All splits" means v1 train + dev + test (seed 20260926) plus the held-out set, both decision points.

| ID | Criterion | Threshold | How measured |
|---|---|---|---|
| S6R-A01 | Retired run relabelled, evidence untouched | `results_test/results.{json,md,html}` and `summary_test.json` each contain the exact string `seen — not a held-out result`. `results.json` minus `retired`, re-serialised with `eval` canonical bytes, has a sha256 equal to the `results_sha256` of a `s6-care-test-0001` run line. `git diff e111658 -- slices/s6/eval/ledger/` shows additions only (0 changed or deleted lines). Running the retire command twice gives byte-identical files. 0 files outside `results_test/` and `summary_test.json` report `s6-care-test-0001` numbers as the S6 test result | pytest `test_retired_label_present`, `test_retired_hash_matches_ledger`, `test_retire_idempotent`, `test_no_report_cites_retired_as_test`; checker `git diff` |
| S6R-A02 | Test re-render appends no run line | Frozen test, identical manifest + predictions + comparator: exit 0, runs ledger line count +0, frozen ledger +0, stdout contains `re-render of run seq`. Dev identical re-run: +1 line (S8 rule kept). Test with different predictions: refused, +0 lines, 0 files written. Re-render after a report-format change into the existing directory: refused (never overwrite); into a new directory: exit 0, +0 lines. All s8/s8r tests pass, with the single sanctioned count edit | pytest `eval/tests/test_s6r_rerender.py::{test_test_rerender_no_run_line, test_dev_rerun_still_appends, test_test_resubmission_still_refused, test_rerender_new_dir_after_format_change}`; `test_runner_rerun_same_inputs_ok` |
| S6R-A03 | Dev before/after table committed | `slices/s6r/eval/dev_before_after.{json,md}` lists, for dev-0001 and dev-0002: coverage, selective hit@3, always-answer hit@3 (all evaluable + on answered), train-prior hit@3, proxy hit@3, pathway top-1, each with point, patient-level 95% CI, exact interval when triggered, `n_patients`, `n_decision_points` and the scored subset. Every value equals the matching `results.json` cell (100%) | pytest `test_dev_before_after_matches_results`; checker recompute (`tests/e2e/s6_recompute_metrics.py`) |
| S6R-A04 | Improvement without regression, dev only | dev-0002 vs dev-0001: selective hit@3 point ≥ 0.80 and ≥ before; pathway top-1 point ≥ before; coverage identical (abstention is gold-exact); proxy hit@3 point ≥ before. ≥1 known dev defect fixed or explained in CHANGELOG. Every CHANGELOG entry cites ≥1 train/dev decision-point id (0 ids from the v1 test split or held-out) and ≥1 source ref that resolves in `references.json`. `care-rules-1.1.0` sha pinned | pytest `test_rules_changelog_ids_train_dev_only`, `test_rules_changelog_sources_resolve`, `test_rules_hash_pinned_to_version`; `dev_before_after.json` delta cells |
| S6R-A05 | Retired test cannot be used | `python -m app.care.evaluate --split test` with the v1 dataset exits non-zero, writes 0 files and names the decision. `git log` order: `care-rules-1.1.0` commit < `manifest_test_0002.json` commit < freeze ledger commit < `s6-care-test-0002` run commit | pytest `test_evaluate_refuses_retired_test`; checker `git log --format='%h %s' -- <paths>` |
| S6R-A06 | Generator v1.2.1 is additive | At seed 20260926: 100% of `inputs/**` hashes equal v1.2.0, and gold is equal except `label_version`. `git diff c08584c -- data_factory/templates/` is empty. Held-out output has only `inputs/test` and `gold/test`; its `manifest.json` and `DATACARD.md` record seed 20260927 and generator 1.2.1 | pytest `test_inputs_unchanged_vs_v120`, `test_templates_unchanged`, `test_heldout_only_test_split`, `test_heldout_seed_recorded` |
| S6R-A07 | Held-out patients disjoint and same case mix | 72 patients, 8 revisit, 80 cases, 160 decision points. 0 overlap of patient refs and case ids with v1 `splits.json` (all 180) and with every `patient_id` in committed `slices/*/eval/**/*.jsonl`. Every ref matches `^SYNH-\d{4}$`. Each quota count (red_flag, missing_info, no_medication, late_items, near_miss, text_near_miss, pregnancy) is within ±2 of 2× the v1 test-split count | pytest `data_factory/tests/test_heldout.py::{test_heldout_disjoint_from_all_splits, test_heldout_size, test_heldout_case_mix}` |
| S6R-A08 | Held-out audit PASS | `make audit OUT=data/synthetic/s6r-heldout` prints `STEP leakage: PASS` and `STEP factory: PASS`. `make audit` (v1) is still PASS. A planted `care` key in a held-out input fails the audit | `make audit`; pytest `test_audit_bans_care_gold_in_heldout_inputs` |
| S6R-A09 | Frozen before run, run once (closes S6-A09) | `manifest_test_0002.json`: `dataset.version` = held-out `tree_sha256`, `split_patient_list` = the 72 held-out refs, `split_version` names seed 20260927, and metrics, comparators and thresholds are identical to `manifest_test.json` except ids and lists. In the ledger, the freeze line for `s6-care-test-0002` precedes **exactly 1** run line for it (`frozen: true`). `python -m eval ledger verify --ledger-dir slices/s6/eval/ledger` exits 0. `s6-care-test-0001` keeps its 2 lines | checker ledger script; pytest `test_manifest_0002_matches_s6_metric_set` |
| S6R-A10 | Table 3.2 metrics on dev and fresh test | `results_dev` (dev-0002) and `results_test_0002`: coverage, selective hit@3, always-answer (all evaluable + paired on answered), train-prior (from v1 train), proxy hit@3 and pathway top-1, each with point, patient-level bootstrap 95% CI, `n_patients`, `n_decision_points`, scored subset and exact Clopper–Pearson interval whenever the bootstrap CI has zero width or is unstable. `split_coverage` complete. Label "System Evaluation" present. Summary states `underpowered` if answered evaluable < 30. Test selective hit@3 < 0.70 is flagged "overfitting risk" (non-gating) | `make care-eval …` (see Run commands); pytest `test_results_0002_complete`; checker |
| S6R-A11 | All S6 acceptance still green | S6-A01–A20 pass with "all splits" as defined above. S6-A07 is measured as `git diff ef4a3d2 -- casegraph/` empty. S6-A12 is measured on dev-0002 / test-0002. S6-A16 claim scan covers held-out assessments. S6-A15 `GET /cases` returns 0 `SYNH-` ids | full `backend/tests/care`, `data_factory/tests`, `eval/tests`, Vitest, Playwright on 8106/3106 |
| S6R-A12 | Deterministic | dev-0002 and held-out predictions JSONL byte-identical across two runs. Held-out generation at seed 20260927 byte-identical across two runs (`tree_sha256`) | pytest `test_care_deterministic`, `test_heldout_reproducible`; checker `sha256sum` |
| S6R-A13 | `make test` green | Exit 0, 0 failed, offline. pytest + Vitest counts ≥ the c08584c baseline plus the new tests | `make test` from a clean checkout |

## Required test cases

- `eval/tests/test_s6r_rerender.py`: the 4 cases in A02. Edit `test_runner_rerun_same_inputs_ok` (test split: 1 line).
- `data_factory/tests/test_heldout.py`: disjoint, size, case mix, only-test, seed recorded, reproducible, `test_inputs_unchanged_vs_v120`, `test_templates_unchanged`, `test_audit_bans_care_gold_in_heldout_inputs`.
- `backend/tests/care/test_s6r.py`: `test_retired_label_present`, `test_retired_hash_matches_ledger`, `test_retire_idempotent`, `test_no_report_cites_retired_as_test`, `test_evaluate_refuses_retired_test`, `test_rules_changelog_ids_train_dev_only`, `test_rules_changelog_sources_resolve`, `test_dev_before_after_matches_results`, `test_manifest_0002_matches_s6_metric_set`, `test_results_0002_complete`, `test_cases_never_serve_heldout`.
- Engine regression: a fixture where qSOFA and NEWS co-fire → pathway ordering follows the CHANGELOG rule, alerts and screening byte-identical to v1.0.0 output.

## Clinical risks

| Risk | Mitigation |
|---|---|
| Circular tuning to the synthetic generator (rules written to hit labels the generator made) | Dev/train only; each change cites a guideline source and the dev rows it fixes; no proxy-only rules (A04); fresh held-out from a fixed seed; System Evaluation label; D1 expert review still required |
| The retired test leaks into choices (the planner saw its summary table while scoping) | No choice in this spec comes from it: the defects listed are from dev predictions. Evaluating the v1 test is refused (A05). CHANGELOG ids are checked (A04) |
| Seed or set shopping for a favourable held-out | Seed, size, namespace and id fixed in this spec. Git order and ledger freeze-before-single-run (A05, A09). Re-render cannot add a second result (A02) |
| A rule change weakens urgency | Red-flag rules untouched; alerts and screening are computed before the provider and are byte-identical across rule versions (engine regression test; S6-A04/A05 still gating) |
| A re-render fix is abused to swap results | Only an identical manifest + predictions + comparator hash counts as a re-render; different inputs are refused; files are never overwritten (A02) |
| Small held-out gives an unstable estimate | 72 patients; patient-level CI plus an exact interval; `underpowered` stated; hit@3 described as lenient |

## Run commands

```bash
make test
python -m app.care.evaluate retire                                     # S6R-A01, idempotent
make data && make audit                                                # v1 at seed 20260926 (v1.2.1)
make care-eval SPLIT=dev EVAL_ID=s6-care-dev-0002                      # after care-rules-1.1.0 is committed
# only after the rules commit:
python -m data_factory generate --seed 20260927 --heldout --out data/synthetic/s6r-heldout
make audit OUT=data/synthetic/s6r-heldout
python -m app.care.evaluate --split test --dataset data/synthetic/s6r-heldout \
  --evaluation-id s6-care-test-0002 --write-manifest                    # commit manifest_test_0002.json
python -m eval freeze slices/s6/eval/manifest_test_0002.json --ledger-dir slices/s6/eval/ledger   # commit
make care-eval SPLIT=test DATASET=data/synthetic/s6r-heldout EVAL_ID=s6-care-test-0002          # once; commit
python -m eval ledger verify --ledger-dir slices/s6/eval/ledger
API_PORT=8106 WEB_PORT=3106 make e2e
```

## Decisions required

- **D-s6r-1:** The s8 owner (สุปรียา) reviews the runner change (test-split identical re-run = re-render, no ledger line) and the edited count in `test_runner_rerun_same_inputs_ok`. It follows the owner decision, but it changes shared harness semantics.
- The s6 decisions D1 (expert review), D2 (symptom red-flag wiring), D3 (`CareSuggestion` extension) and D4 (slice ledger vs main ledger) remain open.
