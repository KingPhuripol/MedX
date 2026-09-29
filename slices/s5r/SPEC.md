# Slice s5r — Pharma Agent v1.1 (owner decisions on evaluation)

- Owner (Gantt): ธัญรดา / ภูริณัฐ
- Source of truth: `docs/PROPOSAL.md` (v8) 3.2.4 and 3.6 / Table 3.2 (recall from synthetic error injection, 95% patient-level bootstrap CIs, System Evaluation label). Decision: `docs/DECISIONS.md` entry "2026-09-27 — S5 Pharma evaluation definitions" (project owner).
- **Delta** on `slices/s5/SPEC.md` at branch tip `7a2c6e8`. Everything in s5 still applies unless a section below replaces it. Where the two conflict, this file wins.
- Status: PLAN. All data synthetic (`data_class="synthetic"`). No external provider run. Servers, if started: API 8105, web 3105.

## Scope (what changes)

1. **`missing_field` becomes a discrepancy type (9 types total).** Replaces s5 §3 bullet `missing_field` notice.
   - Rule `missing_field` (pure function, own `rule_id@rule_version`): for every extracted entry of a recognised ingredient in **any** source whose `dose_value` (with `dose_unit`) or `frequency_code` is `null`, raise one issue per (entry, field). Payload `field ∈ {dose, frequency}`.
   - `conflicting_sources[]`: the incomplete entry (`source_type`, `evidence_ref`, `available_at_time`, `raw_span`, extracted fields with the null shown) plus every other in-snapshot entry of the same ingredient set. At least 1 entry; at least 2 when the ingredient appears in 2 or more source types.
   - A missing value is **never** agreement: a comparison involving a `null` dose or frequency never produces "no issue" silently and never produces a `dose_mismatch`/`frequency_mismatch` from that entry; it is counted in `unchecked_comparisons` and covered by the `missing_field` issue. Comparisons among sources that do state the field still run as before.
   - Severity: same tier as dose/frequency, ranked after the two mismatch types and before omission. Model output cannot change it.
   - `missing_field` is removed from `NoticeType`. Remaining notices: `unrecognised_drug`, `allergy_unmapped`, `source_unreadable`, `source_missing`.
   - Phrasing validation, pharmacist confirm/dismiss, audit and append-only storage apply to it exactly as to the other 8 types. The page shows the missing field as "not stated" in the sources table.
2. **Clean fixtures are fully specified.** Every entry of every source in every clean patient has non-null gold `dose_value`, `dose_unit`, `frequency_code`. Incompleteness exists only as an injected `missing_field` case.
3. **Fixture set ≥ 90 patients** (replaces s5 §8 counts): at least 60 `dev` and at least 30 `test`, split by `patient_ref` before injection; no patient in two splits. The 10 existing test `patient_ref`s stay in `test`. Discontinuation at least 15 (at least 5 in test); Thai brand / Thai-script mentions at least 30 (at least 10 in test). The test manifest is re-frozen as `generator_version` `s5-fixtures-2.x` with a new committed sha256 **before** any test-split evaluation of v1.1.
4. **Injection** (replaces s5 §8 `inject.py` rule): seeded; one case = one patient × one type with exactly one injected discrepancy; at most one case per (patient, type). Every test patient must be injectable for all 9 types (the injector may add an entry, e.g. an allergy record or a new order, to make a type applicable). `missing_field` cases blank dose or frequency in one entry of one source and cover both fields and all three source types. Log line gains `field` for `missing_field`.
5. **Metrics** (`run_eval.py`): per-type recall on `test` and `all` with 95% patient-level bootstrap CI (resample unit = patient, 1000 resamples, fixed seed), plus an exact Clopper–Pearson 95% interval reported alongside (the bootstrap interval is degenerate `[1,1]` when every case is detected). False alerts per clean list count every issue and notice, now including `missing_field`, with bootstrap CI. Remove the informational `informational_mean_excluding_missing_field` field; keep `alert_breakdown` by type. `results.json` records the test manifest sha256 and generator version.
6. **Records:** `docs/DECISIONS.md` on this branch carries the 2026-09-27 decision and marks the 2026-09-26 OPEN entry resolved.

## Out of scope

- Any threshold change (recall ≥ 0.95, false alerts ≤ 0.10 stay as decided).
- New discrepancy types beyond the 9, DDI, dose-range/renal checks, real or MIMIC data, TMT/ATC codes, external providers.
- Expert pharmacist precision review (Proposal 3.6, later). Results stay labelled **System Evaluation**.
- Changing s0 contracts or the gateway contract version.

## Acceptance

Thresholds apply to the frozen `test` split **and** to all patients; both are reported.

| ID | Criterion | Threshold | How measured |
|---|---|---|---|
| S5R-A01 | All s5 acceptance items still pass under the new definitions | S5-A01..A18 all pass; A03, A05, A06, A15 as amended by S5R-A03..A07; A08 and A11 include `missing_field` issues | `make test`, `make pharma-eval`, `make e2e-pharma`; checklist S5-A01..A18 in the builder report with evidence per ID |
| S5R-A02 | `make test` is green | Exit 0, 0 failed, 0 errors, 0 xfail/skip on pharma tests, offline; s0 suite passes; `test_eval_thresholds` passes on A05 and A06 with no known-failing message | `make test` from a clean clone of `factory/s5r` |
| S5R-A03 | Fixture set size and split | ≥ 90 patients; ≥ 30 `test`, ≥ 60 `dev`; 0 `patient_ref` in more than one split; 10/10 original test refs still in `test`; manifest sha256 matches; 100% items `data_class=synthetic` with `available_at_time`, `provenance`, `version`; discontinuation ≥ 15 (≥ 5 test); Thai mentions ≥ 30 (≥ 10 test) | pytest `test_fixtures_valid`, `test_fixture_split_disjoint`, `test_original_test_refs_kept` |
| S5R-A04 | Clean lists fully specified | 100% of entries in every source of every clean patient have non-null gold `dose_value`, `dose_unit`, `frequency_code` | pytest `test_clean_fixtures_fully_specified` |
| S5R-A05 | Injected cases per type | 9 types incl. `missing_field`; ≥ 30 cases per type on `test` (≥ 90 on all); ≤ 1 case per (patient, type); exactly 1 injected discrepancy per case; `missing_field` on test covers dose ≥ 10 and frequency ≥ 10 and each source type ≥ 5; log byte-identical from seed | pytest `test_injection_counts`, `test_injection_one_per_patient_type`, `test_injection_reproducible`; `results.json.counts` |
| S5R-A06 | Recall per type with CI | Point recall ≥ 0.95 for **each** of 9 types on test and on all; each reports patient-level bootstrap 95% CI (1000 resamples, fixed seed, patient resampling unit) and Clopper–Pearson 95% interval | `results.json.recall[type].{test,all}.{recall,ci95,ci95_exact}`; pytest `test_eval_thresholds`, `test_bootstrap_resamples_patients` |
| S5R-A07 | False alerts per clean list | Mean ≤ 0.10 on test and on all, counting every issue and every notice (incl. any `missing_field`), bootstrap CI reported; extra non-injected issues per injected case ≤ 0.10; `informational_mean_excluding_missing_field` absent | `results.json.clean_false_alerts`, `.extra_issues_per_injected_case`, `.alert_breakdown`; pytest `test_eval_thresholds` |
| S5R-A08 | No missing value read as agreement | 0 code paths: for every comparison rule (dose, frequency) × every ordered source-type pair × {field null in first, null in second, null in both}, the output contains a `missing_field` issue for each null and no silent pass; mismatch rules never fire from a null entry; `unchecked_comparisons` equals the number of skipped comparisons; mock extraction yields `null` (0 fabricated values) for 100% of blanked `missing_field` fields | pytest `test_missing_never_agreement[...]` (parametrized, exhaustive), `test_unchecked_comparisons_count`, `test_extraction_null_preserved` |
| S5R-A09 | `missing_field` is a full issue type | Issue has `rule_id@version`, `field`, non-empty `conflicting_sources` (≥ 2 when ingredient is in ≥ 2 source types); severity order allergy > duplication > dose/frequency mismatch > missing_field > omission > notices; `missing_field` not in `NoticeType`; confirm/dismiss audited like other types; page shows "not stated" and never filters it out | pytest `test_rule_missing_field`, `test_severity_order`, `test_decision_audit[missing_field]`; Vitest `pharma-page.test.tsx` |
| S5R-A10 | Test split frozen before evaluation | The commit that writes manifest v2 precedes (or equals) the first commit containing v1.1 test metrics; `results.json` manifest sha256 = committed manifest sha256 | `git log` order check in builder report; pytest `test_results_manifest_matches` |
| S5R-A11 | Decision recorded | `docs/DECISIONS.md` on this branch contains the 2026-09-27 entry verbatim and the 2026-09-26 OPEN entry is marked resolved | pytest `test_decisions_recorded` (string check) |

## Required test cases

Backend (`make test`), new or changed:
- `test_rule_missing_field` (positive per field and source type; negative on a fully specified entry)
- `test_missing_never_agreement[...]` (exhaustive parametrization as in S5R-A08)
- `test_unchecked_comparisons_count`, `test_extraction_null_preserved`
- `test_rule_dose_mismatch` / `test_rule_frequency_mismatch` updated: a null entry gives no mismatch and a `missing_field` issue; stated-vs-stated mismatch still detected when a third source is null
- `test_severity_order`, `test_decision_audit[missing_field]`
- `test_fixtures_valid` (≥ 90 / ≥ 30), `test_fixture_split_disjoint`, `test_original_test_refs_kept`, `test_clean_fixtures_fully_specified`
- `test_injection_counts`, `test_injection_one_per_patient_type`, `test_injection_reproducible`
- `test_bootstrap_resamples_patients` (two cases of one patient always resampled together)
- `test_eval_thresholds` (A05/A06 on test and all, 9 types), `test_results_manifest_matches`, `test_decisions_recorded`
- All other s5 required tests unchanged and passing.

Web: `pharma-page.test.tsx` gains a `missing_field` issue render check ("not stated", in list, not filterable). Browser: `e2e/pharma.spec.ts`, `e2e/pharma-a11y.spec.ts` still pass on 3105/8105.

## Clinical risks

| Risk | Mitigation |
|---|---|
| A missing dose or frequency hides a real discrepancy | It is an issue, not agreement; exhaustive test (S5R-A08); `unchecked_comparisons` reported per run. |
| Fully specified clean fixtures overstate precision; real lists (especially patient-reported) often omit dose, so `missing_field` volume will be higher on real data | Report labelled System Evaluation; `alert_breakdown` by type kept; note in results that clean-list false alerts assume fully specified sources. Real-data alert burden needs pharmacist review before any non-synthetic use. |
| Perfect recall with a degenerate `[1,1]` bootstrap CI read as certainty | Clopper–Pearson interval reported alongside (30/30 gives lower bound about 0.88). |
| Rules tuned to the test split | Manifest v2 frozen and committed before test evaluation (S5R-A10); rules tuned on `dev` only. |
| `missing_field` volume causes alert fatigue and masks allergies | Severity keeps allergy and duplication above it; allergy issues cannot be filtered out. |
| Injector makes a type applicable by adding content that a real list would not have | Injection log records `before/after`; surface forms varied; reported as synthetic injection only. |

## Run commands

```bash
make test                                   # all unit/contract tests incl. pharma, offline
make pharma-eval                            # inject + evaluate both modes -> slices/s5/eval/{results.json,injection_log.jsonl}
make dev API_PORT=8105 WEB_PORT=3105        # API http://127.0.0.1:8105, web http://127.0.0.1:3105/pharmacist/reconcile
make e2e-pharma                             # Playwright pharma specs against 3105/8105
```

## Decisions needed (none blocking)

- Pharmacist sign-off of the `missing_field` severity placement and of whether a missing frequency on a `prn` order should differ; both before any non-synthetic use.
