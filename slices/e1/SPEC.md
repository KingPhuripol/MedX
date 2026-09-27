# Slice e1: System evaluation of Voice (S3) and Triage (S4) on the S1r dataset

- Owner (Gantt): สุปรียา (rows 21-23: evaluation criteria, comparison experiments, system testing)
- Branch `factory/e1`, base `80fdf98` (factory/int with s1r, s3, s4, s8r merged).
- Source of truth: `docs/PROPOSAL.md` (v8).
  - 1.3.1: key intake facts are chief complaint, duration, drug allergy.
  - 3.4: patient-level split; the test set is never used for tuning.
  - 3.6 / Table 3.2: rows "Voice Agent", "การแนะนำแผนก" and "การงดให้ข้อสรุป"; patient-level bootstrap 95% CI; "System Evaluation", not clinical performance.
- Status: PLAN (planner). Tier 0 only: CPU, synthetic, offline. No GPU, no external API, no real data.
- Inputs used as-is: S1r generator 1.1.1 (`make data`, seed 20260926, 200 cases, patients 108/36/36), S3 `backend/app/voice` (mock rules), S4 `backend/app/triage` (rf-1.1.0 + kw-1.0.0 mock), S8r `eval/` (manifests, hash-chained ledger, cluster bootstrap).
- Question: how do the as-built S3 and S4 perform, end to end, on held-out synthetic S1r cases they were not written against? This slice measures. It does not improve S3/S4. A FAIL against a predeclared outcome threshold is a valid result and does not fail the slice.

## Scope

1. **Inputs and time validity.** The input builder reads only `inputs/<split>/<case_id>/snapshot_T*.json`. It never opens `journey.json` or `gold/`. A separate gold loader reads `gold/` for scoring. Every fact or turn given to S3/S4 has `available_at_time <= T`.
2. **Mapping table** `eval/adapters/mappings/e1_mapping_v1.json` plus a rendered `.md`. Every source code appears once, with a target or `UNMAPPABLE`, a one-line rationale and a source (department definition, ICD-10-CM code, or rule citation). Rows are written from definitions, never chosen to raise a score. Changes after the first dev run go into a changelog section with the reason. Required sections:
   - **Departments → evaluation space E.** S1r gold and S4 predictions both map into E:

     | E | S1r gold | S4 prediction |
     |---|---|---|
     | E-MED | 01 | MED, CARD, NEURO |
     | E-SURG | 02 | SURG, URO |
     | E-OBGYN | 03, 04 | OBGYN |
     | E-ENT | 06 | ENT |
     | E-EYE | 07 | EYE |
     | E-ORTHO | 08 | ORTHO |
     | E-PSY | 09 | PSY |

     - `11` (dental) is UNMAPPABLE: S4 has no dental code.
     - `12` (emergency) is not a department in S4, because S4 routes urgency through alerts by design. These rows are scored by the red-flag metrics.
     - `NOT_EVALUABLE` rows go to the abstention population only.
     - The S4 top-3 is mapped to E and de-duplicated, keeping order.
     - Known disagreement: S1r maps dysuria to 01, while S4 suggests URO (→ E-SURG). This is reported as-is and flagged for D1.
   - **Red-flag rules, S1r → S4:**
     - RF-NEWS-SINGLE3 → any of {RF-SPO2, RF-RR, RF-SBP, RF-HR, RF-CONSC, RF-TEMP}
     - RF-QSOFA → RF-QSOFA
     - RF-ACUTE-CHEST-PAIN → RF-CHEST
     - RF-FAST → RF-STROKE
     - RF-THUNDERCLAP → RF-THUNDER
     - RF-ANAPHYLAXIS → RF-ANAPH
     - RF-NEWS-AGG5 is UNMAPPABLE: S4 has no aggregate-NEWS rule.
     - The 5 S4 rules with no S1r counterpart (RF-SUICIDE, RF-GIBLEED, RF-ECTOPIC, RF-MENING, RF-HYPOGLY) are listed as "outside S1r registry".
   - **Vitals and demographics, S1r → S4 facts:**
     - hr, rr, sbp, dbp, spo2 and temp_c map 1:1.
     - consciousness A/V/P/U → avpu. `C` → avpu `A` plus `new_confusion=true`. This is the ACVPU convention: C scores 0 under S1r NEWS 2012 but counts for qSOFA.
     - `null` → no fact (never normal).
     - on_oxygen: S4 has no field for it, so it is UNMAPPABLE.
     - Age and sex come from Demographics. Pregnancy status: S1r has no item, so no fact is given.
     - Every Vitals item is passed with its own `available_at_time`. S4's "latest fact per kind" semantics is S4 behaviour. It is reported, not altered.
   - **Voice gold, S1r → S3:**
     - chief_complaint: the S1r `CC-*` code (with its ICD-10-CM code) → a set of acceptable S3 codes, or UNMAPPABLE when the S3 16-code vocabulary cannot express it. Example: RF-FAST → UNMAPPABLE, never `fatigue`.
     - duration {value, unit} → ISO-8601, with PnW ≡ P(7n)D. Months and years are not converted.
     - allergy `no_known_allergy` → KNOWN `none`; `known` → KNOWN `present`; `MISSING` → gold absent.
   - **S3 facts → S4 facts** (end-to-end pipeline):
     - chief_complaint = the NFC text of the span turns of S3's chief_complaint fact.
     - onset_duration = S3's ISO value.
     - S3 symptom code → S4 `symptom.<name>=present` only where the meaning is equal.
     - S4's acuity- or exposure-qualified symptoms (`acute_chest_pain`, `sudden_*`, `thunderclap_headache`, `allergen_exposure`, `airway_breathing_compromise`) are UNMAPPABLE, because S3 records no onset, acuity or exposure.
     - An S3 field that is MISSING, UNKNOWN or REFUSED → no fact.
3. **Adapters** (`eval/adapters/`). They run the product code in-process on an in-memory SQLite engine through its public service functions. They write predictions JSONL in the S8r registry format. There are 0 changes to `backend/app/voice`, `backend/app/triage` or `data_factory`. A bug found is reported, never fixed here.
   - `voice.py`: replays the T1 `IntakeTranscript` of each case through the S3 session service.
     - Speakers keep their role (nurse → nurse, patient → patient).
     - `started_at = spoken_at`; `ended_at` = the next turn's `spoken_at`, or the transcript `observed_at` for the last turn.
     - The final fact per field is taken at finish.
     - Replay deviations from live use are documented in the mapping `.md`. Example: S3's own policy decides which field it thinks was asked last.
   - `triage.py`: for each decision point (T1, T2), builds an S4 `Case` from the snapshot (vitals, demographics) plus the S3 output for that case. It then calls `engine.assess(case, T, ...)` with the kw-1.0.0 mock through the gateway.
   - `baselines.py`:
     - **Always-answer**: S4 `baseline.rank` on the same inputs with no abstain gate. An empty ranking falls back to the train-split majority E code (computed from train gold only).
     - **S1r lexical shortcut**: V and the substring semantics of S1r scope 4a. The substring s* is selected by maximum F1 for "any text red flag at T1" on **train only**. Ties go to the shorter substring, then lexicographic order. The fixed rule `contains("ทันที")` is also reported. It does not import `data_factory.generate`.
4. **Metrics, populations and predeclared outcome thresholds.** The unit is the decision point (DP), except for voice, whose unit is the case. The bootstrap is patient-cluster: 2000 resamples, seed 20260926, percentile.
   - **Voice** (Table 3.2 "Voice Agent"), per case, using T1 gold:
     - field P/R/F1 for `chief_complaint`, `onset_duration` and `allergy_status`, plus the micro-average;
     - cases whose gold CC is UNMAPPABLE are excluded from the CC field only, and counted;
     - allergy false-none rate: gold `known` or MISSING, but predicted KNOWN `none`.
     - Thresholds (from S3-A01 and S3-A02): F1 ≥ 0.80 per field (point); false-none rate ≤ 0 (point).
   - **Red flags** (the Red-flag Node that feeds "การแนะนำแผนก" and escalation):
     - (a) case-level recall over gold-positive DPs: detected when S4 raises ≥1 alert of any rule. A `not_evaluable` rule is not a detection.
     - (b) rule-level recall pooled over all gold (DP, rule) pairs: detected when a mapped S4 rule fired. Unmappable pairs count as missed. Secondary: the same over mappable pairs only.
     - (c) per-S1r-rule recall. Unmappable rules are `null` with a reason and n.
     - (d) FPR: gold-negative DPs with ≥1 alert. Secondary: the same with mapped rules only. Also a per-S4-rule count of alerts outside the S1r registry.
     - (e) text-red-flag detection at T1: the system (any alert from RF-CHEST, RF-STROKE, RF-THUNDER or RF-ANAPH) against the shortcut s* and against `ทันที`. Recall and FPR, with the paired difference.
     - Thresholds (from S4-A01): (a) ≥ 1.00 and (b) ≥ 1.00 (point).
   - **Department** ("การแนะนำแผนก"): top-1 and top-3 accuracy in E over DPs with `department_evaluable` and a mappable gold (excludes 12 and 11). Abstain or error counts as wrong.
     - Threshold (from S4-A07): top-3 ≥ 0.80 (point).
   - **Abstention** ("การงดให้ข้อสรุป"):
     - Population: the department population ∪ `NOT_EVALUABLE` DPs.
     - Coverage and selective top-1 accuracy (answering a `NOT_EVALUABLE` row is wrong), against the always-answer comparator (paired).
     - Secondary: the abstain rate on `NOT_EVALUABLE` DPs, the false-abstain rate on the department population, and 3-class `expected_action` agreement (suggest/abstain/escalate) with the confusion matrix.
     - No threshold (report only).
   - **Every population** reports n_total = n_scored + n_excluded, by reason (UNMAPPABLE, 12, 11, NOT_EVALUABLE). Nothing is dropped silently.
   - **Not evaluated** (listed as rows with the reason): the form-filling comparator (it needs a human-factors study; S3 out of scope); response latency and total time (in-process mock timing is not representative, and it would break byte reproducibility).
5. **Exact intervals (S4 reviewer condition C3).** Add `eval/exact.py`: pure Wilson and Clopper-Pearson, with no scipy at runtime.
   - Every proportion row also carries both, computed on its x/n.
   - A bootstrap CI is **degenerate** when any of these holds:
     - the S8r flag `unstable` is set;
     - `ci_low == ci_high`;
     - x ∈ {0, n}.
   - Then the reported interval is Clopper-Pearson, marked `interval_method="clopper_pearson"`.
   - The exact intervals assume independent DPs. The report states this with n_patients.
6. **Manifests, freeze, ledger.**
   - Four manifests in `eval/manifests/e1/`: `e1-voice-{dev,test}-v1` and `e1-triage-{dev,test}-v1`.
   - Each carries `split_patient_list` from `splits.json`, and gold-derived `task_patient_lists` for sub-populations.
   - `dataset.version` = `s1r-1.1.1+tree:<tree_sha256>`, and `split_version` = the sha256 of `splits.json`.
   - `$comment` holds the sha256 of the mapping file and of `eval/adapters/**/*.py`.
   - The e1 wrapper refuses to run when a current hash differs from the frozen one.
   - Order:
     1. dev iteration (unfrozen dev runs only);
     2. `freeze` all 4 manifests, then commit `eval(ledger): freeze e1-*`;
     3. run final dev and test once each, then commit `eval(ledger): run e1-*` with the predictions and results.
   - Integrate by merge only: never rebase or squash ledger commits (see D-E1-1).
7. **Outputs** in `eval/results/e1/`:
   - `{dev,test}/{voice,triage}/results.{json,md,html}` (S8r runner) plus `predictions.jsonl` and `comparator.jsonl`;
   - `e1_summary.json` and `e1_summary.md`, which carry:
     - every metric row with its bootstrap CI and exact intervals;
     - the threshold verdicts;
     - the exclusion counts;
     - the list of missed gold red flags (case_id, T, rule), with FP case ids per S4 rule;
     - the not-evaluated rows.
   - Every table is headed **"System Evaluation on synthetic data - not clinical performance"**. Output is canonical and has no wall-clock time.
8. **Make targets:** `make eval-e1-dev` and `make eval-e1-test`. Both require `make data` output at the frozen tree sha.

## Out of scope

- Changing S3/S4 rules, keywords, thresholds or code, or adding a symptom extractor. An evaluation that finds text red flags cannot be detected end to end reports it and does not fix it.
- Latency, total time, the form-filling study, Pharma, Case Graph, provider swap, replay, and the train split (it is used only for the majority class and s*).
- Clinical validation of the mapping (D1), and any real, MIMIC or hospital data.

## Acceptance

Slice acceptance tests that the evaluation is valid and honestly reported. The system outcome thresholds in scope 4 are reported as PASS or FAIL and do not gate the slice.

| ID | Criterion | Threshold | How measured |
|---|---|---|---|
| E1-A01 | The mapping table is complete and committed | 100% of source codes covered: S1r departments (10 + NOT_EVALUABLE), 7 S1r rules, all 58 CC codes, 3 allergy values, 6 duration units, 5 consciousness values; all 10 S4 departments and 16 S4 rules; S3's 16 CC codes. Each row has a target or UNMAPPABLE, plus a rationale and a source. The file is committed before the freeze commit. | `test_mapping_complete`, `test_mapping_rows_have_rationale`; `git log` |
| E1-A02 | Unmapped items are reported, not dropped | For every population in every split: n_total = n_scored + Σ n_excluded_by_reason. n_total equals the count recomputed from gold. The unmapped counts per mapping section appear in `e1_summary.*` (dev and test). | `test_population_accounting`; checker recount from `gold/` |
| E1-A03 | Model inputs are snapshot-only and time-valid | 0 opens of `journey.json` or `gold/` by the input builder (open-spy). Planting a sentinel in both changes 0 prediction bytes. 100% of S4 facts and S3 turns have `available_at_time <= T`. | `test_inputs_snapshot_only`, `test_planted_sentinel_no_effect`, `test_facts_time_valid` |
| E1-A04 | The product code is untouched | `git diff 80fdf98 -- backend/app/voice backend/app/triage data_factory` is empty. | checker `git diff` |
| E1-A05 | The exact intervals are correct | Wilson and Clopper-Pearson match `scipy.stats.binomtest(...).proportion_ci` within 1e-9 on ≥50 (x, n) pairs, including x=0, x=n and n=1. Bounds lie in [0, 1]. 0 scipy/sklearn imports in `eval/exact.py`. | `test_exact_intervals_match_scipy`, `test_eval_isolation` |
| E1-A06 | The degenerate rule is applied | 100% of proportion rows carry Wilson and CP. 100% of rows meeting the degenerate definition report CP as the interval, with `interval_method` set. Rows that are not degenerate keep the bootstrap interval. | `test_degenerate_uses_exact`; checker scan of `e1_summary.json` |
| E1-A07 | Freeze before test, in git order | Commit F (the freeze of all 4 e1 manifests in `frozen.jsonl`) is a strict ancestor of commit R (the first e1 test line in `runs.jsonl`). No commit before F contains an e1 test result or test predictions file. `git diff F R -- eval/adapters eval/manifests/e1` is empty. | checker `git merge-base --is-ancestor`, `git log -- <paths>` |
| E1-A08 | 0 test-split iterations | `runs.jsonl` has exactly 1 run entry per e1 test `evaluation_id` (2/2). `python -m eval ledger verify --git-history` exits 0. | CLI plus a line count by `evaluation_id` |
| E1-A09 | Every in-scope Table 3.2 row is reported | On dev and on test (2/2), every metric in scope 4 has point, bootstrap CI, n_patients and n_DP (or `null` + reason). Proportions also carry exact intervals. The not-evaluated rows are listed with a reason. Threshold verdicts use the predeclared rule only. | `test_e1_summary_complete` (schema), checker |
| E1-A10 | The comparators are reported | The shortcut s* is chosen on train only: perturbing dev or test text leaves s* unchanged. The s* and `ทันที` rows, with recall, FPR and the paired difference against the system, appear on dev and test. The always-answer arm has coverage = 1.0 exactly, and its paired difference is reported. | `test_shortcut_selected_on_train_only`, `test_always_answer_full_coverage` |
| E1-A11 | Safety findings are explicit | 100% of gold red-flag DPs that got no alert are listed (case_id, T, rule). The case- and rule-level recall verdicts are shown at the top of `e1_summary.md`, both dev and test. | checker cross-check against `predictions.jsonl` |
| E1-A12 | Byte-for-byte reproducible | Re-running dev and test against a tmp copy of the ledger gives identical sha256 for every file in `eval/results/e1/`. The committed ledger bytes are unchanged. | `test_e1_byte_reproducible` (small tmp dataset); checker full rerun |
| E1-A13 | The labelling is correct | 100% of tables in `e1_summary.md` and `results.md` carry "System Evaluation on synthetic data - not clinical performance". There are 0 claim terms ("diagnos", "clinical efficacy demonstrated", "accuracy of diagnosis") outside the banners. | `test_e1_labels` |
| E1-A14 | The manifests are hash-bound | The wrapper refuses (exit 2, 0 files) on a mismatched dataset tree sha, split sha, mapping sha or adapter sha (4/4). | `test_wrapper_refuses_hash_mismatch[4]` |
| E1-A15 | Isolation is not weakened | For every `eval/` file outside `eval/adapters/`, the s8 forbidden-import rule is unchanged. 0 non-adapter `eval/` modules import `eval.adapters`. Adapters import only `app.voice`, `app.triage`, `app.gateway` and `app.db`. 0 imports of `data_factory.generate` anywhere under `eval/`. | amended `test_eval_isolation`, `test_adapters_import_allowlist` |
| E1-A16 | The dataset is valid | `make data && make audit` exits 0 with both STEP lines PASS. The tree sha equals the frozen `dataset.version`. | checker log |
| E1-A17 | `make test` is green | Exit 0, 0 failed, 0 errors. The s0, s1r, s3, s4 and s8r tests pass unchanged. `requirements.lock` is unchanged. | `make test -rs` in a clean checkout |

## Required test cases (`eval/adapters/tests/`, added to pytest `testpaths`; `eval/tests/` for `exact.py`)

- Mapping: `test_mapping_complete`, `test_mapping_rows_have_rationale`
- Inputs: `test_inputs_snapshot_only`, `test_planted_sentinel_no_effect`, `test_facts_time_valid`
- Adapter behaviour:
  - `test_vitals_mapping` (C → A + new_confusion; null → no fact);
  - `test_voice_replay_hand_case` and `test_triage_hand_case` (3 hand-built mini cases with expected predictions);
  - `test_population_accounting`
- Statistics and outputs:
  - `test_exact_intervals_match_scipy`, `test_degenerate_uses_exact`
  - `test_shortcut_selected_on_train_only`, `test_always_answer_full_coverage`
  - `test_wrapper_refuses_hash_mismatch[dataset|split|mapping|adapter]`
  - `test_e1_summary_complete`, `test_e1_labels`, `test_e1_byte_reproducible`
- Isolation: `test_adapters_import_allowlist`, and `test_eval_isolation` amended as in E1-A15 (not relaxed for core).

## Clinical and validity risks

| Risk | Mitigation |
|---|---|
| S4 text rules need `symptom.*` facts that no upstream component emits, so text red flags are missed end to end | The misses are measured and listed (A11). They are reported as a system gap with a follow-up recommendation for S3/S4. They are not patched in e1 (A04). |
| RF-NEWS-AGG5 has no S4 counterpart | Unmappable pairs count as missed in primary rule-level recall. The mappable-only figure is secondary. |
| Mapping chosen to flatter scores | Rows come from definitions with a rationale. A changelog records changes after the first dev run. The mapping is hash-frozen before test (A01, A07, A14). Known disagreements (dysuria, URO) stay. |
| A "no red flag" gold is read as "safe" | Gold means only that no S1r rule fires. S4 alerts outside the registry are reported, not scored as errors in the secondary FPR. |
| Small per-rule n (2-8 DPs on test) | Exact intervals whenever the bootstrap is degenerate (A06). Claims are limited to this synthetic set. |
| Exact intervals ignore patient clustering | Both CIs are shown with n_patients, and the assumption is disclosed. |
| Circularity (the same team wrote S1r, S3 and S4) | S3/S4 were built on their own fixtures, not on S1r. Test is run once after freeze (A07, A08). The results are labelled System Evaluation. |
| Results read as clinical performance | Mandatory banner and a claim-term scan (A13). Research prototype only. |

## Run commands

```bash
make data && make audit                     # S1r v1.1.1, seed 20260926 -> data/synthetic/v1
make test
make eval-e1-dev                            # unfrozen dev iteration; UNFROZEN stamp
.venv/bin/python -m eval freeze eval/manifests/e1/e1-voice-dev-v1.json   # likewise the other 3; then commit
make eval-e1-test                           # once; then commit ledger + results
.venv/bin/python -m eval ledger verify --git-history
```

## Decisions needed

- **D-E1-1 (human, blocks only the test-split step).** `eval/ledger/README.md` says ledger appends happen only on `main`. This slice freezes and runs on `factory/e1` and is integrated by merge (no squash or rebase). Options:
  - The owner records a `docs/DECISIONS.md` entry allowing it.
  - Or e1 is merged to `main` first and freeze/run happen there.
  - Until one of these is recorded, the builder stops after the dev runs and the unfrozen manifests, and reports BLOCKED.
- **D-E1-2 (reviewer check).** Carving out `eval/adapters/` from the S8-A17 isolation scan (A15). The fallback is a top-level `eval_adapters/` package with no S8 test change.
- **D1 (extended).** Clinical review of the E-space department mapping (dysuria → 01 against URO → surgery, OBGYN merge, CARD/NEURO → MED), the ACVPU `C` mapping, and the S3 → S4 symptom map.
- Condition C3 comes from the S4 reviewer and is not yet recorded in the repo. The orchestrator should add it to the S4 record.
