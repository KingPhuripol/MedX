# Slice s8r: Evaluation harness v1.1, integrity fixes

- Owner (Gantt): สุปรียา (same rows as s8: 21-23)
- Delta on: `slices/s8/SPEC.md` at commit `5515f59` (implementation `eval/`). Everything in s8 still applies unless this file changes it.
- Source of truth: `docs/PROPOSAL.md` (v8), sections 3.4 (patient-level split; the test set is not used for tuning) and 3.6 / Table 3.2 (every metric has a patient-level bootstrap 95% CI; "System Evaluation" label).
- Status: PLAN, written by the planner. Tier 0 only (CPU, synthetic toy inputs). No GPU, no real data, no external service.

## Why this slice exists

Review of s8 found three integrity gaps:

| Sev | Gap in s8 (verified in code) | Consequence |
|---|---|---|
| HIGH | `runner._refusal_checks` rejects patients that are *not* on `split_patient_list`, but nothing checks that every *listed* patient has predictions. A run with patients left out succeeds. | A model that fails, crashes or times out on hard patients can drop them and score higher. Survivor bias gets into Table 3.2. |
| MEDIUM | The ledgers (`eval/ledger/frozen.jsonl`, `runs.jsonl`) are plain JSONL, and only `.gitkeep` is committed. If the file is missing, it is silently created empty. `--ledger-dir` / `EVAL_LEDGER_DIR` can point anywhere. | Deleting or editing the ledger, or pointing to a fresh directory, gets around the freeze-before-test and anti-resubmission rules without any trace. |
| LOW | `json.loads` accepts `NaN`, `Infinity`, `-Infinity` and `1e999`. `_is_missing` treats NaN as *missing*, so under abstention metrics a NaN counts as abstain. `+inf` passes binary AUROC ranks, latency, cost and recomputed-node means. `np.asarray(nan, bool)` is `True`, so a NaN mask voxel counts as foreground in Dice. | Corrupt scores become numbers or abstentions in the results instead of errors. |

## Scope

### 1. Split coverage: silent omission is impossible (HIGH)

1. **Listed set.** For each task declared in `metrics[]`, the listed set L is `split_patient_list`. The manifest may also declare `task_patient_lists: {"<task>" | "<task>:<population>": [patient_id, ...]}`, for example the pharmacist-reviewed precision sample, or the Voice Agent's simulated-conversation patients. It is frozen with the manifest. Each list must be a subset of `split_patient_list`. Otherwise the manifest is invalid (exit 3).
2. **Predicted set.** P = the patients with at least one prediction row for that task (and population, where one applies). `n_missing = |L \ P|`. The system file and every comparator file are checked on their own.
3. **Policy.** The check applies whenever `split_patient_list` is present. It is always present on test.
   - If a task has at least one metric that is **not** abstention-aware (not in `registry.ABSTENTION_AWARE`) and `n_missing > 0`, the run is **refused**:
     - exit code 2 (`RunRefused`);
     - 0 result files written;
     - 0 lines appended to `runs.jsonl`.
     - stderr states `task`, `n_listed`, `n_predicted`, `n_missing`. Up to 3 example patient IDs are shown, but only when `data_class=synthetic`.
   - If **all** metrics of the task are abstention-aware (`coverage`, `selective_accuracy`), each missing patient is **counted as abstain**:
     - One imputed decision point per missing patient: `decision_point_id="__missing__"`, `y_pred=null`, `imputed_missing=true`. It is added to every arm (system and comparators) that lacks the patient, so the paired comparison keeps the same keys.
     - A `(patient, decision_point)` key that is present in one arm but absent from another is imputed as abstain in the arm where it is absent.
     - Imputed rows need no gold `y_true`, because abstained rows never enter the answered set.
     - The bootstrap `n_patients` includes these patients, so `n_patients` equals `n_listed`.
4. **Report.** `results.json` gets a top-level `split_coverage` array: one entry per task (and per population), with `task`, `population|null`, `n_listed`, `n_predicted`, `n_missing`, `missing_policy` (`complete` | `counted_as_abstain`), `n_imputed_abstain_decision_points`, and `imputation_unit="1 decision point per missing patient"`.
   - For a dev run with no list, `n_listed` is `null` and the entry carries a reason.
   - `results.md` and `results.html` render a "Split coverage" table with these fields.
   - `results.schema.json` is extended, and `n_listed == n_predicted + n_missing` is asserted.

### 2. Durable, tamper-evident ledger (MEDIUM)

1. **Location.** `eval/ledger/frozen.jsonl` and `eval/ledger/runs.jsonl` are committed to git, each starting with a genesis entry. `.gitkeep` is removed.
   - `.gitignore` gets an explicit `!eval/ledger/*.jsonl`.
   - `.gitattributes` gets `eval/ledger/*.jsonl -text -merge`. This keeps the bytes exact, and concurrent appends conflict instead of being auto-merged.
2. **Hash chain.** Each line is `canonical_bytes(entry)`. Every entry has:
   - `seq` (0-based, equal to the line index);
   - `prev_hash` (the previous entry's `entry_hash`; genesis uses 64 zeros);
   - `entry_hash = sha256(canonical_bytes(entry minus entry_hash))`;
   - a `ledger` name that matches the file (`frozen` | `runs`).
   Genesis has `kind="genesis"`. The file must end in `\n`. A line that is not byte-identical to its canonical re-serialization is invalid.
3. **Verify before use.** `Ledger.verify()` runs before every `freeze` and every `run` (dev or test), and in `python -m eval ledger verify`. Any failure raises `LedgerIntegrityError` (a subclass of `RunRefused`, exit 2). Failures include:
   - a missing file;
   - a bad line;
   - a broken chain, a seq gap or out-of-order lines;
   - a git-anchor mismatch.
   Nothing is written after a failure.
4. **No silent re-creation.**
   - A missing ledger file is never auto-created.
   - `python -m eval ledger init --ledger-dir D` writes genesis files only when both files are absent **and** the path has no git history. `git log --all -- <path>` must be empty, so a tracked ledger cannot be re-initialized.
   - `demo` and the tests call `init` on a `tmp_path` ledger.
5. **Git anchor.** This catches tail truncation, which a chain alone cannot detect. When the ledger file is tracked in a git work tree:
   - the committed version (`git show HEAD:<path>`) must be a byte prefix of the working file;
   - `ledger verify --git-history` checks that every committed version of each ledger file is a byte prefix of the next version.
6. **Real-data guard.** For `data_class` in {`mimic`, `hospital`} on a test split, the runner refuses unless:
   - both ledger files are git-tracked, so a fresh untracked `--ledger-dir` cannot be used to bypass the checks; and
   - both files have no uncommitted lines. This means the freeze was committed before any test result exists, and the previous run was committed.
   `synthetic` is exempt, so tests stay hermetic.
7. **Content.** Ledger entries hold only the `evaluation_id`, hashes, `seq`, timestamps and `kind`. Patient IDs and data are never stored.
   - `results.json` embeds `frozen_entry_hash`. It stays static, so byte-reproducibility is preserved.
8. **Commit policy.** This is documented in `eval/ledger/README.md` (at most about 40 lines) and in the CLI `--help`.
   - Ledger appends happen on one integration branch only (`main`).
   - Order: `freeze`, then commit (`eval(ledger): freeze <evaluation_id>`, with the manifest). Then `run`, then commit (`eval(ledger): run <evaluation_id>`).
   - Commits that touch `eval/ledger/` are never amended, rebased, squashed or force-pushed.
   - A merge conflict in the ledger is resolved by redoing the other branch's freeze or run on top of `main`, never by editing lines.
   - Residual risk: rewriting git history on the remote is not detectable locally. This is disclosed in the README.

### 3. Non-finite values are rejected everywhere (LOW)

1. **Parse layer.** Predictions JSONL, comparator JSONL, the manifest and the ledger are parsed with `parse_constant` rejecting `NaN`, `Infinity` and `-Infinity`, and with `parse_float` rejecting values that overflow to ±inf (for example `1e999`). The error is `NonFiniteValueError(ValueError)` naming the file and line, exit 3, with no results written.
2. **Metric layer.** Every public function in `eval/metrics.py` and every `registry.REGISTRY` adapter rejects a float NaN or ±inf (Python or numpy) in any score, label, mask, count, latency or cost input with `NonFiniteValueError`. This covers all 20 registry metrics; binary, multiclass and multilabel AUROC; and Dice masks.
3. **NaN is not missing.** `_is_missing` becomes `v is None`. A NaN is never treated as abstain, as missing, or as negative. This tightens S8-A07. Missing still means `None` or an absent field.

## Out of scope

- Everything that s8 lists as out of scope. No real data. No new metrics.
- Signing ledger entries (GPG/Sigstore) or an external timestamp anchor. The detection of remote git-history rewrites is a documented residual risk.
- Detecting missing decision points *inside* a listed patient. This slice covers the patient level. A frozen per-patient decision-point list is a follow-up.
- Concurrent writers and file locking. The policy is a single writer.
- CI and pre-commit hooks.

## Acceptance

| ID | Criterion | Threshold | How measured |
|---|---|---|---|
| S8R-A00 | No s8 regression | S8-A01..S8-A19 all pass (19/19). S8-A07 is amended by S8R-A12: NaN is an error, not missing. The s8 test names are unchanged. | `make test`. All s8 tests are listed as passed. |
| S8R-A01 | A test run with a listed patient missing is refused (non-abstention task) | 4/4 cases (1 of N missing; all but 1 missing; missing only in the comparator; a task-list subset patient missing) exit 2. Each has 0 result files and 0 new `runs.jsonl` lines, and stderr contains `n_listed=`, `n_predicted=`, `n_missing=` with the correct values. | pytest `test_missing_listed_patient_refuses`, `test_missing_in_comparator_refuses`, `test_task_patient_list_missing_refuses` |
| S8R-A02 | For an abstention-only task, missing listed patients count as abstain | Hand example: 10 listed, 9 predicted with 1 DP each, all answered. Coverage = 0.9 exactly. Selective accuracy equals its value on the 9 answered rows. `n_patients` = 10. The comparator arm shares the imputed keys, so paired draws are identical (asserted). | pytest `test_missing_counts_as_abstain`, `test_abstain_imputation_paired` |
| S8R-A03 | A mixed task (abstention plus non-abstention metric) with a missing patient is refused | Exit 2, 0 files | pytest `test_mixed_task_missing_refuses` |
| S8R-A04 | The report states split coverage | 100% of tasks in `results.json` have a `split_coverage` entry with `n_listed`, `n_predicted`, `n_missing`, `missing_policy`, and `n_listed == n_predicted + n_missing`. MD and HTML both show all three counts (2/2). Schema-valid. | pytest `test_split_coverage_reported`, `test_results_schema` (extended) |
| S8R-A05 | Silent omission is impossible (property) | Over 200 seeded random removal patterns on the toy test set (removing patients and/or rows across tasks and arms), each run either refuses or reports `n_missing` equal to the true number of removed patients. 0 runs succeed with an understated `n_missing`. | pytest `test_no_silent_omission_property` |
| S8R-A06 | `task_patient_lists` is validated | A list that is not a subset of `split_patient_list` gives an invalid manifest (exit 3). An unknown task key is invalid. Coverage is checked against the task list when one is declared. | pytest `test_task_patient_lists_validation` |
| S8R-A07 | The ledger is a valid hash chain | A freshly initialized ledger plus N freezes and runs verifies (exit 0). Every line has `seq`, `prev_hash`, `entry_hash`, `ledger`. Each line is byte-identical to its canonical form. | pytest `test_ledger_chain_valid`, CLI `ledger verify` |
| S8R-A08 | Tampering makes the runner (and freeze) refuse | 3/3 required cases: (1) edit one byte of an earlier entry, (2) delete a middle line, (3) delete the file. Plus 3/3 extra cases: reorder two lines, a whitespace-only edit, and tail truncation of a git-tracked ledger (git anchor). Each case gives exit 2, 0 result files, and no new ledger bytes. | pytest `test_ledger_tamper_edit_refuses`, `test_ledger_tamper_delete_line_refuses`, `test_ledger_tamper_delete_file_refuses`, `test_ledger_tamper_reorder_whitespace_refuses`, `test_ledger_tail_truncation_git_anchor` (tmp git repo) |
| S8R-A09 | A ledger is never silently created | With the file missing, `run` and `freeze` refuse (2/2). `ledger init` succeeds only on an absent, history-free path. It refuses when files exist and when the path has git history (2/2). | pytest `test_ledger_missing_not_autocreated`, `test_ledger_init_guards` |
| S8R-A10 | The ledger path is tracked in git and documented | `git ls-files --error-unmatch eval/ledger/frozen.jsonl eval/ledger/runs.jsonl` exits 0. `git check-ignore` exits 1 for both. `.gitattributes` has the rule. The committed ledgers verify. `ledger verify --git-history` passes on the branch. `eval/ledger/README.md` contains the location, format and commit-policy sections. The test is **not skipped** in a clean clone. | pytest `test_committed_ledger_tracked_and_valid`, `test_ledger_readme_policy` |
| S8R-A11 | Real-data guard | A `data_class=mimic` test run refuses when (a) the ledger is untracked, (b) the freeze line is uncommitted, or (c) the previous run line is uncommitted (3/3). It succeeds once committed. | pytest `test_real_data_requires_committed_ledger` (tmp git repo) |
| S8R-A12 | NaN and inf are rejected at parse time | `NaN`, `Infinity`, `-Infinity`, `1e999` in predictions, the comparator and the manifest: 12/12 give exit 3 with the file and line in the message, and 0 result files. | pytest `test_parse_rejects_nonfinite` |
| S8R-A13 | NaN and inf are rejected in every metric | For each of the 20 `REGISTRY` metrics (pure function and registry adapter) x {nan, +inf, -inf}, `NonFiniteValueError` is raised: 60/60 per path. Binary, multiclass and multilabel AUROC are each covered explicitly. A NaN Dice mask voxel is covered. numpy `float64` values are included. | pytest `test_metric_rejects_nonfinite[<metric>-<value>]`, `test_auroc_binary_rejects_nonfinite`, `test_dice_rejects_nan_mask` |
| S8R-A14 | NaN is never missing or abstain | For `coverage` and `selective_accuracy`, a NaN `y_pred` raises and does not count as abstain. `None` still counts as abstain. | pytest `test_nan_is_not_abstain` |
| S8R-A15 | Reproducibility and privacy are kept | Same inputs give byte-identical `results.*` (S8-A14 still holds), with `frozen_entry_hash` embedded. A scan of every ledger line after the toy runs finds 0 patient IDs. | pytest `test_byte_reproducible`, `test_ledger_has_no_patient_ids` |
| S8R-A16 | `make test` is green | Exit 0, 0 failed, 0 errors. There are 0 skips among the s8r tests. The s0 and s8 tests still pass. No new dependencies (`requirements.lock` unchanged). | `make test` in a clean clone of `factory/s8r`, with `-rs` output recorded |

## Required test cases (all in `eval/tests/`, run by `make test`)

- **Coverage:** `test_missing_listed_patient_refuses`, `test_missing_in_comparator_refuses`, `test_task_patient_list_missing_refuses`, `test_missing_counts_as_abstain`, `test_abstain_imputation_paired`, `test_mixed_task_missing_refuses`, `test_split_coverage_reported`, `test_no_silent_omission_property`, `test_task_patient_lists_validation`
- **Ledger:** `test_ledger_chain_valid`, `test_ledger_tamper_edit_refuses`, `test_ledger_tamper_delete_line_refuses`, `test_ledger_tamper_delete_file_refuses`, `test_ledger_tamper_reorder_whitespace_refuses`, `test_ledger_tail_truncation_git_anchor`, `test_ledger_missing_not_autocreated`, `test_ledger_init_guards`, `test_committed_ledger_tracked_and_valid`, `test_ledger_readme_policy`, `test_real_data_requires_committed_ledger`, `test_ledger_has_no_patient_ids`
- **Non-finite:** `test_parse_rejects_nonfinite`, `test_metric_rejects_nonfinite` (parametrized, 20 x 3, over pure and registry paths), `test_auroc_binary_rejects_nonfinite`, `test_dice_rejects_nan_mask`, `test_nan_is_not_abstain`
- **Existing tests to update, not weaken:** `test_results_schema` (adds `split_coverage`), `test_ledgers_append_only` (now on a chained ledger), `test_demo_end_to_end` (the demo inits its own tmp ledger), and the toy fixtures (every listed patient is predicted).

Tests write only to `tmp_path` ledgers or `tmp_path` git repos (`git init` via subprocess; no network). They never modify the committed `eval/ledger/`. The only exception is the read-only verify in S8R-A10.

## Clinical and validity risks

| Risk | Mitigation |
|---|---|
| Hard patients (crashes, timeouts, refusals) are dropped and inflate Table 3.2 | Coverage refusal, abstain imputation and `n_missing` in every report (A01-A05) |
| Abstain imputation at 1 DP per missing patient understates the abstention of patients with several decision points | The unit is stated in `split_coverage.imputation_unit`. A per-DP list is a follow-up. The policy fails closed for all non-abstention metrics. |
| The freeze or resubmission record is erased, edited or bypassed by a new ledger dir | Hash chain, no auto-create, git anchor, tracked-path and committed-freeze guard for real data (A07-A11) |
| Remote history rewrite (force-push) | Not detectable locally. Disclosed in the README. Branch protection on `main` is recommended to humans. |
| Corrupt scores become numbers or abstentions | Parse-level and metric-level non-finite rejection. NaN is not missing (A12-A14). |
| Patient identifiers leak through the git-tracked ledger or logs | The ledger holds hashes only (A15). Refusal messages show IDs only for synthetic data. |
| Reports are read as clinical efficacy | The s8 banners are unchanged (S8-A15 via A00) |

## Run commands

```bash
make test
.venv/bin/python -m eval ledger verify                       # committed ledger
.venv/bin/python -m eval ledger verify --git-history
.venv/bin/python -m eval ledger init --ledger-dir /tmp/s8r-ledger
.venv/bin/python -m eval --ledger-dir /tmp/s8r-ledger freeze eval/examples/toy_manifest_test.json
.venv/bin/python -m eval --ledger-dir /tmp/s8r-ledger run --manifest eval/examples/toy_manifest_test.json \
    --predictions eval/examples/toy_predictions.jsonl --comparator eval/examples/toy_comparator.jsonl --out /tmp/s8r-run
.venv/bin/python -m eval demo --out /tmp/s8r-demo
```

## Decisions needed (none blocking)

- Human: enable branch protection (no force-push) on `main` for `eval/ledger/`. This is outside the repo and removes the residual risk in the table above.
- Manifest schema: this slice adds the optional `task_patient_lists` field. Manifests frozen under s8 stay valid (the field is optional). Their ledgers are not chained, so they must be re-frozen into a chained ledger. No s8 ledger with real content exists: only `.gitkeep` was committed.
