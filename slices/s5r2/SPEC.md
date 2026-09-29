# Slice s5r2 — Pharma Agent v1.2 (dose quantity and scope fixes)

- Owner (Gantt): ธัญรดา / ภูริณัฐ
- Source of truth: `docs/PROPOSAL.md` (v8) 1.3.1, 2.1.5, 3.2.4 (rules primary; dose **or frequency** differences between sources; DDI out of scope), 3.6 / Table 3.2 (recall from synthetic error injection, 95% patient-level bootstrap CIs, System Evaluation label). Decisions: `docs/DECISIONS.md` 2026-09-26 (formulary licence) and 2026-09-27 (evaluation definitions).
- **Delta** on `slices/s5/SPEC.md` + `slices/s5r/SPEC.md` at branch tip `ffe4780`. Everything there still applies unless a section below replaces it. Where they conflict, this file wins.
- Trigger: clinical-safety FAIL on s5r. **B1 (HIGH):** the mock drops the per-administration quantity, so `Warfarin 3 mg 2 tabs od` vs `Warfarin 3 mg 1 tab od` and `เมทฟอร์มิน 500 มก. 2x2` vs `1x2` give 0 issues with status `complete`, and the page claims that every dose was compared. The same review also raised C1 to C6.
- Status: PLAN. All data synthetic (`data_class="synthetic"`). No external provider run. Servers, if started: API 8105, web 3105.

## Scope (what changes)

1. **Extraction schema v2 (B1).** The task becomes `pharma.extract.v2` because the output gains required fields, which is a breaking schema change. Only the pharma-local task schema changes; the gateway contract version does not. The pipeline calls only v2. S5-A02 now reads `pharma.extract.v2`. Each `ExtractedEntry` gains these fields, all required, with no defaults. A provider that omits one fails the schema and is treated as `source_unreadable`, under S5-A12.
   - `quantity: float | null`: units per administration, e.g. tablets or capsules. `null` when the text does not state it. The extractor never writes a default of 1.
   - `dose_status ∈ {resolved, not_stated, unverifiable}` and `dose_unverifiable_reason ∈ {variable_regimen, liquid_volume, multiple_strengths, ambiguous_quantity} | null`. If `dose_status` is `unverifiable`, then `dose_value` and `dose_unit` are `null`. A partial value is never emitted.
   - `frequency_status ∈ {recognised, not_stated, not_recognised}` (C3). Frequency-like text that the mock cannot map is `not_recognised`. Examples: `q4h`, `every other day`, `3 times a week`, `วันเว้นวัน`, `สัปดาห์ละ 1 ครั้ง`.
2. **Mock parsing (`mock_rules.py`).**
   - Quantity forms:
     - `NxM`: N is the quantity and M is the times per day.
     - `N tab(s)/tablet(s)/cap(s)/capsule(s)` and `N เม็ด/แคปซูล`.
     - Fractions: `1/2`, `½`, `0.5`, `1.5`, `ครึ่งเม็ด`. These are parsed exactly and never read as an integer, so `1/2 tab` is never 2.
   - Unverifiable forms:
     - Variable regimen: `except`, `ยกเว้น`, `alternating`, `สลับ`, or a weekday-specific dose.
     - Liquid concentration plus volume: `<n> mg/<n> ml <n> ml`, `มก./… มล.`.
     - Two or more distinct strengths for one single-ingredient entry: `3 mg + 1 mg`, `3 mg and 2 mg`.
     - Conflicting quantity statements, e.g. `2 tabs 1x2`.
     - Combination products written with a slash (`875/125 mg`) keep their s5/s5r gold.
   - When unsure, the mock returns `unverifiable`, never a guessed value.
3. **Dose comparison on the dose per administration (B1).** `dose_mismatch` compares the dose per administration: `dose_value × quantity` when a quantity is stated. When the quantity is `null`, the stated amount itself is taken as the dose per administration. This convention is recorded per source as `dose_basis ∈ {strength_x_quantity, stated_amount}`. `conflicting_sources[]` gains `quantity`, `dose_per_administration`, `dose_basis`, `dose_status`, `frequency_status`. The existing units-not-comparable case (`unverifiable=true`) keeps its behaviour.
4. **Unverifiable is never a silent pass.** An entry with `dose_status=unverifiable` has a `null` dose. It therefore raises `missing_field` (field `dose`) under the owner's 2026-09-27 definition, in any source, including when it is the only source. `detail.field_status` records the reason: `not_stated`, `not_recognised` or `unverifiable`, and for `unverifiable` also `detail.unverifiable_reason`.
   - It never produces or suppresses a `dose_mismatch`.
   - Every cross-source comparison involving it is counted in `unchecked_comparisons`.
   - The run adds `comparisons_made` and `unchecked_by_reason{unverifiable, not_recognised, not_stated}`. The counts sum exactly to `unchecked_comparisons`. A pair with two null sides is attributed once, to the first reason in the order unverifiable > not_recognised > not_stated.
5. **C1:** `rule_missing_field` skips inactive entries (`discontinue_intent=true`). Inactive entries may still appear as other sources on another issue.
6. **C2, pharmacist page.**
   - A visible "Scope of this check" section, present before and after a run, says in plain words:
     - what is compared: ingredient duplication, dose per administration (strength × quantity), frequency, omission, and recorded allergies;
     - what is **not** checked: drug–drug interactions, dose range, renal or hepatic adjustment, and route.
   - Every allergy issue shows its basis:
     - `allergy_cross_reactivity`: the citation and "pending pharmacist sign-off", from `clinical_review_status=pending_pharmacist`;
     - `allergy_class`: the class name, class source and formulary version;
     - `allergy_direct`: the ingredient mapping and formulary version.
   - The rule puts these in `issue.detail` (`citation`, `clinical_review_status`, `basis`).
7. **Truthful wording (B1, C3).**
   - `uncheckedSummary` is replaced. The run summary states `comparisons_made`, `unchecked_comparisons` and the per-reason counts.
   - It may say that every comparison was made only when `unchecked_comparisons == 0`. That sentence names the compared fields ("dose per administration and frequency") and links to the scope section.
   - The sources table shows:
     - `not stated`, `not recognised` or `not verifiable (<reason>)` for each field status;
     - the dose per administration as `3 mg × 2 = 6 mg`, or `3 mg (quantity not stated; stated amount used)`.
   - The `missing_field` title follows `field_status`: "Dose not stated", "Frequency not recognised", or "Dose could not be verified".
   - A `dose_mismatch` with `unverifiable=true` is titled "Dose not comparable (units)" and never uses "differs".
8. **C4, atomic writes.**
   - `pharma_runs` + `pharma_issues` + the `pharma.reconcile` audit row are committed in **one** transaction.
   - `pharma_issue_decisions` + the `pharma.issue.*` audit row are committed in one transaction.
   - `backend/app/audit.py` gains an **additive** way to write on a caller's connection. The existing `write_audit` signature and behaviour are unchanged, and the s0 tests pass.
   - The per-call gateway audit rows (s0) stay independent. They record calls that did happen.
9. **C5, versions.** Exact strings:

   | Constant | New value |
   |---|---|
   | `MOCK_RULES_VERSION` | `s5-mock-rules-1.2.0` |
   | `TEMPLATE_VERSION` | `template-1.1.0` |
   | `RULES_VERSION` | `s5-rules-2.1.0` |
   | `RULE_VERSIONS.dose_mismatch` | `1.2.0` |
   | `RULE_VERSIONS.missing_field` | `2.1.0` |
   | `RULE_VERSIONS.allergy_*` | `1.1.0` |
   | pipeline version | bumped |

   Each run and `results.json.versions` record them.
10. **C6, reassurance phrasing.** `validate_text` gains a reassurance lexicon (EN + TH), anchored to the issue type. Any hit falls back to the template with `fallback_reason="reassurance_phrase"`. The lexicon is at least:
    - generic: `no concern`, `nothing to worry`, `no action needed`, `safe to`, `ไม่มีปัญหา`, `ปลอดภัย`;
    - `dose_mismatch`: `doses match`, `same dose`, `dose is consistent`, `ขนาดยาตรงกัน`;
    - `frequency_mismatch`: `frequencies match`, `same frequency`, `ความถี่ตรงกัน`;
    - `allergy_*`: `not allergic`, `no allergy`, `tolerated`, `ไม่แพ้`;
    - `duplication_*`: `not a duplicate`, `no duplication`, `ไม่ซ้ำ`;
    - `missing_field`: `dose is stated`, `frequency is stated`, `complete`;
    - `omission`: `intentionally omitted`, `was stopped on purpose`.

    Every template for all 9 types still passes validation.
11. **Fixtures v3 and the surface-form suite.**
    - The fixture generator becomes `s5-fixtures-3.x`. Gold per entry gains `quantity`, `dose_status` and `frequency_status`.
    - The **same** patient split as manifest v2: the 32 test refs are unchanged and no patient changes split.
    - At least 10 test clean patients (at least 30 overall) carry an entry written in a quantity form. Its dose per administration equals the other sources' dose written a different way, e.g. `500 mg 2 tabs bid` vs `1000 mg bid`.
    - Clean lists stay fully specified: every entry is `resolved` and `recognised`.
    - A new seeded **surface-form suite** (`inject.py`, separate from the 9-type suite so that S5R-A05 stays as it is) produces `slices/s5/eval/injection_log_surface.jsonl`.
    - One case is one patient × one form, with exactly one injected change and at most one case per (patient, form). Each log line gains `form` and `lang`.
    - The manifest is re-frozen as v3, with the test refs, the fixture sha256 and the suite seed/generator version. It is committed **before** any v1.2 test-split evaluation.

    | Form | Injection | Expected result | test ≥ | all ≥ |
    |---|---|---|---|---|
    | SF-NXM | quantity N in `NxM` changed in one source (EN and TH lines) | `dose_mismatch` | 10 | 30 |
    | SF-TABS | `N tab(s)/cap(s)` differs (EN) | `dose_mismatch` | 10 | 30 |
    | SF-MED | `N เม็ด/แคปซูล` differs (TH) | `dose_mismatch` | 10 | 30 |
    | SF-FRAC | fractional quantity (`1/2`, `½`, `ครึ่งเม็ด`, `1.5`) vs whole | `dose_mismatch` | 10 | 30 |
    | SF-EQUIV | same dose per administration, different written form | **no** `dose_mismatch`, no `missing_field(dose)` | 10 | 30 |
    | SF-VAR | variable regimen | `missing_field(dose)`, `field_status=unverifiable`, `variable_regimen` | 10 | 30 |
    | SF-LIQ | liquid concentration + volume | `missing_field(dose)`, `unverifiable`, `liquid_volume` | 10 | 30 |
    | SF-MULTI | two or more strengths in one entry | `missing_field(dose)`, `unverifiable`, `multiple_strengths` | 10 | 30 |
    | SF-FREQ | frequency-like text the mock cannot map | `missing_field(frequency)`, `field_status=not_recognised` | 10 | 30 |

    - Bilingual forms (NXM, FRAC, VAR, LIQ, MULTI, FREQ) have at least 3 EN and at least 3 TH cases on test.
    - A match means the same type, the same ingredient set, and the injected source in `conflicting_sources`, plus the expected `field_status`/reason where the table gives one.
12. **Reporting.**
    - `results.json` keeps `label` = System Evaluation on synthetic data, not clinical performance.
    - It adds `surface_forms[form].{test,all}.{cases,detected,recall,ci95_exact,ci95}` and `summary[]` lines.
    - Every recall line **leads with** the Clopper–Pearson 95% interval, followed by the patient-level bootstrap CI (1000 resamples, fixed seed), e.g. `recall 1.00 (Clopper–Pearson 95% 0.89–1.00; bootstrap 1.00–1.00), n=32`.
    - `make pharma-eval` prints the same lines.

## Out of scope

- Drug–drug interactions, dose-range, renal/hepatic and route checks. They are stated on the page, not built.
- A new discrepancy type: unverifiable doses ride on `missing_field`, as in §4. Any threshold change: recall ≥ 0.95 and false alerts ≤ 0.10 stay.
- Converting liquid volumes or variable regimens into a comparable dose. The mock declares them unverifiable.
- The gateway contract version, s0 audit semantics, real/MIMIC data, TMT/ATC codes, and external providers.
- Expert pharmacist precision review (Proposal 3.6, later).

## Acceptance

Thresholds apply to the frozen `test` split **and** to all patients; both are reported.

| ID | Criterion | Threshold | How measured |
|---|---|---|---|
| S5R2-A01 | All S5 and S5R items still pass | S5-A01..A18 and S5R-A01..A11 pass, as amended here (A02 reads `pharma.extract.v2`; A03 includes the new fields; A10 manifest reads v3). The builder report carries evidence per ID | `make test`, `make pharma-eval`, `make e2e-pharma`; per-ID checklist |
| S5R2-A02 | `make test` green | Exit 0, 0 failed, 0 errors, 0 skip/xfail on pharma tests, offline; s0 suite passes | `make test` from a clean clone of `factory/s5r2` |
| S5R2-A03 | Quantity-based dose mismatches detected | `Warfarin 3 mg 2 tabs od` vs `Warfarin 3 mg 1 tab od` → 1 `dose_mismatch` (6 mg vs 3 mg). `เมทฟอร์มิน 500 มก. 2x2` vs `เมทฟอร์มิน 500 มก. 1x2` → 1 `dose_mismatch` (1000 vs 500 mg). `Warfarin 3 mg od` vs `Warfarin 3 mg 2 tabs od` → `dose_mismatch` (stated-amount convention). `3 mg 1/2 tab` vs `3 mg 1 tab` → `dose_mismatch`. 4/4 | pytest `test_rule_dose_quantity_mismatch[warfarin_en\|metformin_th_2x2\|stated_amount\|fraction]` |
| S5R2-A04 | Equal dose per administration is not an alert | `Metformin 500 mg 2 tabs bid` vs `Metformin 1000 mg bid` → 0 `dose_mismatch`, 0 `missing_field`; SF-EQUIV ≥ 0.95 of cases with no dose issue, on test and all | pytest `test_rule_dose_quantity_equivalent`; `results.json.surface_forms.SF-EQUIV` |
| S5R2-A05 | Quantity extraction exact | 100% of the enumerated forms in "Required test cases" give the gold `quantity` (incl. 0.5 and 1.5); `Warfarin 3 mg od` gives `quantity=null` (0 defaulted 1s); a fraction is never read as an integer | pytest `test_extract_quantity_forms[...]` |
| S5R2-A06 | Unverifiable regimens are explicit | For each of variable (EN, TH), liquid (EN, TH), multi-strength, ambiguous quantity: `dose_value=null`, `dose_status=unverifiable` with the right reason; 1 `missing_field(dose)` issue with `field_status=unverifiable`, also when the entry is in 1 source only; 0 `dose_mismatch` from that entry; `unchecked_comparisons` rises by exactly the number of cross-source pairs holding the entry; `unchecked_by_reason` sums to `unchecked_comparisons`. 100% of enumerated cases | pytest `test_unverifiable_dose_explicit[...]`, `test_unchecked_by_reason_sums`, `test_missing_never_agreement[...]` (S5R-A08 grid × field_status) |
| S5R2-A07 | Surface-form suite size and freeze | ≥ 10 test and ≥ 30 all cases for each of the 9 forms; ≤ 1 case per (patient, form); bilingual forms ≥ 3 EN and ≥ 3 TH on test; log byte-identical from seed; manifest v3 test refs = v2 refs (32/32) and 0 split changes; the commit freezing manifest v3 precedes or equals the first commit with v1.2 test metrics; `results.json` manifest sha = committed sha | pytest `test_surface_form_counts`, `test_surface_form_one_per_patient_form`, `test_surface_form_reproducible`, `test_manifest_v3_same_split`, `test_results_manifest_matches`; `git log` order in builder report |
| S5R2-A08 | Surface-form recall | Point recall ≥ 0.95 per detection form (NXM, TABS, MED, FRAC, VAR, LIQ, MULTI, FREQ) on test and all, each with Clopper–Pearson and bootstrap 95% CI; extra non-injected issues per surface case ≤ 0.10 | `results.json.surface_forms`; pytest `test_eval_thresholds` |
| S5R2-A09 | 9-type metrics still hold on v3 fixtures | Recall ≥ 0.95 for each of the 9 types on test and all; clean false alerts ≤ 0.10 (every issue and notice); extra issues per injected case ≤ 0.10; extraction field accuracy ≥ 0.98 on test incl. `quantity`, `dose_status`, `frequency_status`; clean entries 100% `resolved`/`recognised` | `results.json.{recall,clean_false_alerts,extra_issues_per_injected_case,extraction}`; pytest `test_eval_thresholds`, `test_clean_fixtures_fully_specified` |
| S5R2-A10 | Results label and CI order | `label` unchanged (System Evaluation, synthetic); 100% of `summary[]` recall lines start the interval text with "Clopper–Pearson" before "bootstrap" | pytest `test_eval_summary_leads_with_exact` |
| S5R2-A11 | Page never claims a comparison that did not happen | With `unchecked_comparisons > 0` (each reason): 0 occurrences of the every-comparison sentence and of `all doses`, `every dose`, `doses match`; per-reason counts shown. With 0 unchecked: the sentence names "dose per administration" and "frequency". `not recognised` / `not stated` / `not verifiable (…)` rendered per field status; dose shown as `3 mg × 2 = 6 mg`; `dose_mismatch unverifiable=true` title contains no "differs" | Vitest `pharma-page.test.tsx` (`unchecked wording[...]`, `field status labels`, `dose per administration`) |
| S5R2-A12 | C1: discontinued entries | A `new_order` entry with `discontinue_intent=true` and no dose or no frequency → 0 `missing_field` issues for it; an active entry with the same text still raises 1 | pytest `test_rule_missing_field_skips_inactive` |
| S5R2-A13 | C2: scope limits and allergy basis visible | Scope section contains "drug–drug interaction", "dose range", "renal", "hepatic", "route" as not checked, before and after a run; each allergy subtype renders its basis; cross-reactivity renders the row citation and "pending pharmacist sign-off" (3/3 subtypes) | pytest `test_allergy_issue_basis`; Vitest `scope limits`, `allergy basis[direct\|class\|cross_reactivity]`; Playwright `e2e/pharma.spec.ts` |
| S5R2-A14 | C3: unrecognised frequency label | 5/5 enumerated forms → `frequency_code=null`, `frequency_status=not_recognised`, `missing_field(frequency)` with `field_status=not_recognised`, page label "not recognised"; `Amlodipine 5 mg` alone → `not_stated` | pytest `test_extract_frequency_not_recognised[...]`; Vitest `field status labels` |
| S5R2-A15 | C4: single-transaction writes | With the audit insert forced to raise: reconcile → 0 new `pharma_runs` and 0 `pharma_issues` rows, non-2xx; decision → 0 `pharma_issue_decisions` rows, non-2xx, and a retry then succeeds (no 409). Happy path still writes exactly 1 decision + 1 audit row; s0 `write_audit` tests unchanged and passing | pytest `test_reconcile_atomic_with_audit`, `test_decision_atomic_with_audit`, `test_decision_audit` |
| S5R2-A16 | C5: versions bumped | Exact strings in Scope §9 present in code, in every run and in `results.json.versions`; pipeline calls only `pharma.extract.v2`; a v2 output missing any new field → `schema_invalid` → `source_unreadable`, run `incomplete` | pytest `test_versions_bumped`, `test_extract_v2_schema_required_fields`, `test_pipeline_uses_gateway` |
| S5R2-A17 | C6: reassurance phrasing rejected | For each of the 9 types, ≥ 1 EN and ≥ 1 TH (where the lexicon has one) reassurance phrase → `template_fallback`, `fallback_reason="reassurance_phrase"`, issue set unchanged; 9/9 templates pass validation | pytest `test_phrasing_rejects_reassurance[type-lang]`, `test_templates_pass_validation`, `test_phrasing_cannot_change_issues` |
| S5R2-A18 | Browser, accessibility, claim hygiene | Playwright on 3105/8105: fixture `demo-quantity` shows the warfarin and Thai metformin `dose_mismatch` with `× 2`; `demo-unverifiable` shows three "Dose could not be verified" issues and a non-zero unchecked count; scope section visible; 0 serious/critical axe violations; 0 colour literals; 0 `diagnos\|prescrib\|treat` in UI copy | `make e2e-pharma` (`e2e/pharma.spec.ts`, `e2e/pharma-a11y.spec.ts`); Vitest; s0 `test_repo_hygiene` |

## Required test cases

Backend (`make test`), new or changed. Enumerated inputs are fixed; expected values are gold.

- `test_extract_quantity_forms[...]`:

  | Input | Expected |
  |---|---|
  | `Warfarin 3 mg 2 tabs od` | qty 2, q24h |
  | `Warfarin 3 mg 1 tab od` | 1 |
  | `เมทฟอร์มิน 500 มก. 2x2` | 2, q12h |
  | `เมทฟอร์มิน 500 มก. 1x2` | 1 |
  | `Metformin 500 mg 2 tablets bid` | 2 |
  | `Paracetamol 500 mg 2 เม็ด วันละ 3 ครั้ง` | 2, q8h |
  | `Warfarin 3 mg 1/2 tab od` | 0.5 |
  | `วาร์ฟาริน 3 มก. ครึ่งเม็ด วันละ 1 ครั้ง` | 0.5 |
  | `Warfarin 2 mg ½ เม็ด od` | 0.5 |
  | `Warfarin 1 mg 1.5 tabs od` | 1.5 |
  | `Warfarin 3 mg od` | `null` |

- `test_extract_unverifiable_forms[...]`:

  | Input | Reason |
  |---|---|
  | `Warfarin 3 mg od except 1.5 mg on Sunday` | `variable_regimen` |
  | `วาร์ฟาริน 3 มก. วันละ 1 เม็ด ยกเว้นวันอาทิตย์ครึ่งเม็ด` | `variable_regimen` |
  | `Warfarin 3 mg alternating with 1.5 mg daily` | `variable_regimen` |
  | `Paracetamol syrup 250 mg/5 ml 10 ml q6h prn` | `liquid_volume` |
  | `พาราเซตามอล น้ำเชื่อม 120 มก./5 มล. 5 มล. ทุก 6 ชั่วโมง` | `liquid_volume` |
  | `Warfarin 3 mg + 1 mg od` | `multiple_strengths` |
  | `Warfarin 3 mg and 2 mg tabs od` | `multiple_strengths` |
  | `Metformin 500 mg 2 tabs 1x2` | `ambiguous_quantity` |

  Each case also expects `dose_value=null`.
- `test_extract_frequency_not_recognised[q4h|every_other_day|3_times_a_week|วันเว้นวัน|สัปดาห์ละ_1_ครั้ง]`, plus a `not_stated` control.
- `test_rule_dose_quantity_mismatch[...]`, `test_rule_dose_quantity_equivalent`, `test_unverifiable_dose_explicit[variable_en|variable_th|liquid_en|liquid_th|multi_strength|ambiguous_quantity|single_source]`, `test_unchecked_by_reason_sums`.
- `test_missing_never_agreement[...]`: the S5R-A08 grid × `field_status ∈ {not_stated, not_recognised, unverifiable}`.
- `test_rule_missing_field_skips_inactive`, `test_allergy_issue_basis[direct|class|cross_reactivity]`.
- `test_reconcile_atomic_with_audit`, `test_decision_atomic_with_audit`.
- `test_versions_bumped`, `test_extract_v2_schema_required_fields`.
- `test_phrasing_rejects_reassurance[type-lang]`, `test_templates_pass_validation`.
- `test_surface_form_counts`, `test_surface_form_one_per_patient_form`, `test_surface_form_reproducible`, `test_manifest_v3_same_split`, `test_results_manifest_matches`, `test_eval_thresholds` (9 types + 9 forms, test and all), `test_eval_summary_leads_with_exact`.
- All other S5 and S5R tests unchanged and passing.

Web (Vitest `pharma-page.test.tsx`):

- `scope limits` (before and after run)
- `allergy basis[direct|class|cross_reactivity]`
- `unchecked wording[zero|not_stated|not_recognised|unverifiable]`
- `field status labels`
- `dose per administration`
- `unverifiable dose_mismatch title`

Browser (`make e2e-pharma`): `e2e/pharma.spec.ts` gains the `demo-quantity` and `demo-unverifiable` flows. These are demo fixtures only and are not in any eval split. `e2e/pharma-a11y.spec.ts` still passes.

## Clinical risks

| Risk | Mitigation |
|---|---|
| Two-fold (or larger) dose error hidden by a dropped quantity, e.g. warfarin | Dose per administration = strength × quantity (A03). Enumerated quantity forms are exact (A05). Surface-form recall ≥ 0.95 with Clopper–Pearson reported (A08). |
| A fraction misread as a whole number (`1/2 tab` → 2) | Exact fraction parsing is required, and the tests assert 0.5/1.5 (A05). Unresolvable forms become `unverifiable`, never a guess. |
| Liquid, variable or multi-strength regimen passes silently | Dose null + `unverifiable` → `missing_field(dose)` issue, even in a single source. Counted in `unchecked_comparisons` (A06). The page says "could not be verified" (A11). |
| Stated-amount convention (quantity not stated = the stated amount is the dose per administration) masks a real difference | The convention is shown per source (`dose_basis`) and on the page. It fires in the safe direction (3 mg vs 3 mg × 2 → mismatch). Pharmacist sign-off is needed before non-synthetic use (Decisions). |
| Page over-claims coverage (interactions, dose range, renal/hepatic, route) | A scope section is always visible (A13). The comparison sentence only appears at 0 unchecked (A11). |
| Model phrasing reassures ("doses match", "no concern") | A type-anchored lexicon falls back to the template (A17). Phrasing cannot change issues (S5-A07). |
| A decision or run without an audit row, or the reverse | Single transaction; a forced audit failure leaves 0 rows (A15). |
| Mock rules tuned on test | Manifest v3 is frozen before v1.2 test metrics, with the split unchanged (A07). Forms are tuned on `dev`. Results are labelled System Evaluation. |
| Unseen real-world wordings not in the pattern set are misread as resolved | The residual risk is stated in `results.json` notes. The page says a fixed pattern set is read. Real-data use needs pharmacist review first. |

## Run commands

```bash
make test                                   # all unit/contract tests incl. pharma, offline
make pharma-eval                            # 9-type + surface-form suites -> slices/s5/eval/{results.json,injection_log.jsonl,injection_log_surface.jsonl}
make dev API_PORT=8105 WEB_PORT=3105        # API http://127.0.0.1:8105, web http://127.0.0.1:3105/pharmacist/reconcile
make e2e-pharma                             # Playwright pharma specs against 3105/8105
```

## Decisions needed (none blocking this slice)

- **Project owner:** confirm that unverifiable doses ride on `missing_field` with a `field_status` field, instead of a 10th issue type. This slice changes no owner-defined threshold.
- **Pharmacist:** sign off the stated-amount convention and the unverifiable reasons before any non-synthetic use. Carried over from S5/S5R: cross-reactivity rows, `duplication_relevant` classes, `missing_field` severity placement.
- **Integration-auditor awareness:** `pharma.extract.v1` → `v2` is a pharma-local task schema bump, with no change to the gateway contract version.
