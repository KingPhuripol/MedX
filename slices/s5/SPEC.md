# Slice s5 — Pharma Agent (medication reconciliation)

- Owner (Gantt): ธัญรดา / ภูริณัฐ
- Source of truth: `docs/PROPOSAL.md` (v8). Sections used:
  - 1.3.1: the agent compares medication lists from every source and raises issues for a pharmacist. It never edits orders. Rules are the primary checker and the model is supplementary.
  - 2.1.5: medication reconciliation (AHRQ/ASHP). Names are normalised to a standard code first (RxNorm, TMT).
  - 3.2.4: the three-step pipeline, duplication by ingredient or class (RxClass/ATC), and a Human Checkpoint. Drug–drug interaction (DDI) is out of scope.
  - 3.6 / Table 3.2: recall comes from synthetic error injection. Precision and recall are reported per issue type against a rules-only baseline, with 95% patient-level bootstrap CIs.
- Builds on s0: the Model Gateway (`backend/app/gateway`), auth/roles, and the append-only audit log.
- Status: PLAN. Written by the planner. All data is synthetic: `data_class="synthetic"` everywhere.

## Scope

All code lives in `backend/app/pharma/` (its own module). Local Pydantic models live in `pharma/models.py`. The shared casegraph types belong to S2, so this slice does not import or extend them beyond `casegraph.EvidenceItem` field names.

1. **Input `MedSnapshot`**
   - Fields: `patient_ref`, `as_of` (aware datetime), and `data_class` (required, no default).
   - `sources[]`: each entry has `source_type ∈ {home_list, patient_reported, new_order}`, `evidence_ref`, `available_at_time`, `provenance`, `version`, and `entries[]` of free text (EN/TH).
   - A `new_order` entry may carry `discontinue_intent` + `reason`.
   - `allergies[]`: each has `text`, `evidence_ref`, and `available_at_time`.
   - Items with `available_at_time > as_of` are excluded and counted in `excluded_future_items`.

2. **Step 1: extract.** Each present source makes one gateway call, task `pharma.extract.v1`. The output has, per entry:
   - `drug_name_raw`, `dose_value|null`, `dose_unit|null`, `route|null`, `frequency_code|null` (normalised, e.g. `q24h`, `q12h`, `q8h`, `prn`), `raw_span`.
   - Missing fields stay `null` and are never defaulted.
   - The default is a **deterministic rule-based mock** in `pharma/mock_rules.py`. It handles EN/TH patterns: `bid`, `1x2 pc`, `วันละ 2 ครั้ง`, `mg`/`มก.`, and so on.
   - The mock is registered through a small additive **task-handler hook in the gateway's MockProvider**. Unknown tasks keep the current hash-based behaviour, so the contract version is unchanged.
   - Pharma calls the gateway through the same in-process function that `/api/gateway/invoke` uses, so every call is audited by s0. Pharma never touches `gateway.adapters`.
   - The response is validated against a Pydantic schema.

3. **Step 2: normalise + rules (primary).**
   - `pharma/data/formulary.json` maps names (generic, EN brand, Thai brand, Thai script) to ingredient(s), then to class(es). Combination products map to several ingredients. Unmapped names raise an `unrecognised_drug` notice and are never dropped.
   - Rules are pure functions. Each has a `rule_id` and `rule_version`:
     - `duplication_ingredient`: two or more active `new_order` entries share an ingredient.
     - `duplication_class`: two or more active `new_order` entries with different ingredients share a class flagged `duplication_relevant`.
     - `dose_mismatch`: the same ingredient has a different dose across sources after unit conversion (mg/g/mcg). If units cannot be compared, the result is a mismatch with `unverifiable=true`. A missing dose in one source is not a match. It becomes a `missing_field` note on the issue.
     - `frequency_mismatch`: the same ingredient has a different `frequency_code` across sources.
     - `omission`: an ingredient appears in `home_list` or `patient_reported` but not in active `new_order` entries, and has no recorded `discontinue_intent`. If a same-class ingredient is ordered, the issue carries `possible_substitution=true`.
     - `allergy_direct`: an allergen maps to the same ingredient as an active order or a home med.
     - `allergy_class`: an allergen maps to the drug's class, e.g. penicillin allergy with amoxicillin.
     - `allergy_cross_reactivity`: the pair is in the curated `cross_reactivity.json`. Every row has a citation and `clinical_review_status: pending_pharmacist`.
   - Notices are shown and audited but are not discrepancy types:
     - `unrecognised_drug`
     - `allergy_unmapped`
     - `source_unreadable` (extraction failed)
     - `source_missing` (no `new_order` source). This gives one notice and zero omission issues.
     - `missing_field` (added by the builder after review, 2026-09-26): an active ingredient set appears in 2 or more source types and one entry's dose or frequency is not stated. One notice per entry and field, with source, `evidence_ref` and `raw_span`. A missing value is never read as agreement. The run also reports `unchecked_comparisons`. Whether these notices count toward the S5-A06 false-alert metric is an open human decision (see `docs/DECISIONS.md`); the A06 threshold is unchanged.
   - Severity order is fixed by rule: allergy_* > duplication_* > dose/frequency > omission > notices. Model output never changes this order.

4. **Step 3: phrase.** Each run makes one gateway call, task `pharma.phrase.v1`, with the typed issues. The mock is a deterministic template.
   - The output text is accepted only if all of these hold:
     - it names every conflicting source label and drug of the issue;
     - it contains no banned prescriptive phrase (`discontinue`, `stop`, `increase`, `decrease`, `change the dose to`, `prescribe`, `หยุดยา`, `เพิ่มขนาด`);
     - it passes schema validation.
   - Otherwise the result falls back to a deterministic template (`phrasing.source="template_fallback"`). The original model output is stored raw.
   - Phrasing can never add, drop, retype, or re-rank issues.

5. **Issue object**
   - Fields: `issue_id`, `run_id`, `type`, `severity`, `rule_id@version`, `ingredients[]`, and `conflicting_sources[]`.
   - `conflicting_sources[]` is required and non-empty. Each entry has `source_type`, `evidence_ref`, `available_at_time`, `raw_span`, and extracted fields. Mismatch, duplication and allergy issues have at least 2 sources; for allergy these are the allergy record and the medication source.
   - It also carries `phrasing{text, source, provider, model_version}` and `status ∈ {open, confirmed, dismissed}`.
   - It has **no** field for a replacement or edited order.

6. **Persistence and API** (pharmacist role only; others get 403, unauthenticated gets 401)
   - New tables `pharma_runs`, `pharma_issues`, `pharma_issue_decisions` are append-only (DB triggers, same pattern as `audit_events`). Issue status is derived from the decisions.
   - `GET /api/pharma/fixtures` returns synthetic patient refs, for dev/demo.
   - `POST /api/pharma/reconcile {snapshot | fixture_ref, mode: rules_only|rules_plus_model}` returns the run, with extraction per source, issues and notices, formulary/rule versions, and the gateway request hashes.
   - `GET /api/pharma/runs/{run_id}`
   - `POST /api/pharma/issues/{issue_id}/confirm` and `/dismiss {reason}`. The dismiss reason is required.
     - Each decision writes one decision row and one audit row: `action=pharma.issue.confirm|dismiss`, reviewer id and role, `ts_utc`, `run_id`, `issue_id`, `rule_id`, `reason_sha256`.
     - A second decision on the same issue returns 409.
   - `pharma.reconcile` audit details: `run_id`, `snapshot_sha256`, `formulary_version`, `rules_version`, `mode`, and the issue and notice counts. They contain no raw text.

7. **Offline formulary** (`pharma/data/`). See "Formulary licence decision" below.
   - At least 40 ingredients relevant to common OPD care: antihypertensives, statins, antidiabetics, PPIs, NSAIDs/analgesics, antibiotics incl. penicillins, cephalosporins and sulfonamides, anticoagulants, and so on.
   - At least 12 classes flagged `duplication_relevant`, at least 3 combination products, and at least 15 Thai brand or Thai-script aliases.
   - Each ingredient carries `rxcui` and `verified_on`, checked once against RxNav by the curator. Tests are offline.

8. **Fixtures and harness** (`pharma/fixtures/`, `pharma/eval/`)
   - At least 30 clean synthetic patients, split by patient into at least 20 `dev` and at least 10 `test`. The test split is frozen by a committed sha256 manifest.
   - Each patient has the 3 sources, an allergy list, and gold structured fields per entry.
   - At least 5 patients have documented intentional discontinuation, and at least 10 use Thai brand or Thai-script mentions.
   - `inject.py` (seeded) takes clean patients and injects exactly one discrepancy of each of the 8 types per case. That gives at least 30 cases per type, drawn from all splits, with a JSONL log line per case: `case_id, patient_ref, split, type, source, before, after, expected{type, ingredients, sources}`.
   - `run_eval.py` runs both modes and writes `slices/s5/eval/results.json` and `injection_log.jsonl`. The results include:
     - per-type recall with a 95% patient-level bootstrap CI (1000 resamples, fixed seed);
     - false alerts per clean list;
     - extra (non-injected) issues per injected case;
     - extraction field accuracy;
     - the equality check between the two modes.
   - A match means the same type, the same ingredient set, and the same injected source included in `conflicting_sources`.

9. **Pharmacist web page** at `/pharmacist/reconcile`, linked from `/pharmacist`
   - Flow: select a fixture patient, run, see issues sorted by severity, then confirm or dismiss (with a labelled reason field). Status persists after reload.
   - Markup: semantic `main`/`h1`/`section[aria-labelledby]`, an issue list as `ol > article`, and conflicting sources as a `table` with `caption` and `th scope`. A `role="status"` live region announces results. Allergy issues cannot be filtered out.
   - MedX theme (built in parallel): use only `var(--…)` tokens from `web/app/theme.css` once it lands. Hard-coded colours are not allowed. Until then, use neutral defaults via CSS variables with fallbacks.
   - Shows the NLM attribution statement and a "rules primary / model phrasing supplementary / mock" label on each phrasing.

10. **Ports**
    - Add `API_PORT ?= 8000` and `WEB_PORT ?= 3000` to the Makefile, and pass `API_ORIGIN` through. Defaults stay unchanged.
    - Playwright `baseURL` comes from env.
    - This slice runs on API 8105 and web 3105 only.

## Out of scope

- Drug–drug interactions and dose-range or renal/hepatic checking.
- Any order entry or order mutation. The agent only reads snapshots.
- MIMIC `medrecon` / `prescriptions` / `pyxis`, TMT release files, ATC data, and real or hospital data. Any external provider run.
- The S1 dataset (built in parallel; no dependency) and S2 Compiler/Executor integration. This slice exposes a callable `reconcile(snapshot)` for S2 to wrap later.
- Re-deciding an issue, pharmacist free-text editing of phrasing, and a patient-facing view.
- Expert pharmacist precision review. Proposal 3.6 plans it later; until then results are reported as **System Evaluation**, not clinical performance.

## Formulary licence decision

Checked against primary sources on 2026-09-26. Must also be recorded in `docs/DECISIONS.md` by the builder.

| Source | Finding (primary source) | Decision |
|---|---|---|
| RxNorm normalized names + RXCUI (SAB=RXNORM) | NLM-created content is public domain and may be freely distributed. NLM asks for acknowledgement. The *full* release contains proprietary sources and needs a UMLS licence. <https://www.nlm.nih.gov/research/umls/rxnorm/docs/termsofservice.html>. The Current Prescribable Content subset is "No license required; public domain". <https://www.nlm.nih.gov/research/umls/rxnorm/docs/prescribe.html> | **Use.** Commit ingredient names and RXCUIs from NLM content only. Do not commit any proprietary-source (non-RXNORM SAB) strings. |
| RxNav / RxClass APIs | Free to use with no licence (one SNOMED CT exception), at most 20 requests/s. Apps must display the NLM statement. RxClass's SNOMED CT content falls under the UMLS/SNOMED affiliate licence. <https://lhncbc.nlm.nih.gov/RxNav/TermsofService.html>, <https://lhncbc.nlm.nih.gov/RxNav/applications/RxClassIntro.html> | **Use at curation time only**, to verify RXCUIs. Do not commit SNOMED CT–derived class data. |
| Drug classes | RxClass class sources include FDA EPC, MED-RT (VA), MeSH, SNOMED CT, and ATC (from WHO). <https://lhncbc.nlm.nih.gov/RxNav/applications/RxClassIntro.html> | **Use FDA EPC / MED-RT class names** (US federal works) for the class mapping. The curator re-checks the MED-RT UMLS restriction level at <https://www.nlm.nih.gov/research/umls/sourcereleasedocs/current/MED-RT/index.html> and records it. |
| WHO ATC/DDD | "Copying and distribution for commercial purposes is not allowed. Changing or manipulating the material is not allowed." A reference to the WHOCC is required. <https://www.whocc.no/copyright_disclaimer/> | **Do not commit ATC codes.** A subset or remap could count as "manipulating". Proposal 3.2.4 allows RxClass *or* ATC, so EPC satisfies it. Revisit only with a human decision. |
| Thai Medicines Terminology (TMT) | Release files are login-gated (<https://this.or.th/service/tmt/download/>) and the site is "© สงวนลิขสิทธิ์" (all rights reserved). No public redistribution licence was found (<https://this.or.th/service/tmt/>). | **Do not commit TMT codes or release content.** Thai brand aliases are team-authored from public product labelling, with `alias_source` recorded. The `tmt_id` field is reserved as `null`. Using TMT needs a written permission from THIS plus a DECISIONS.md entry. |

Required attribution: "This product uses publicly available data from the U.S. National Library of Medicine (NLM), National Institutes of Health, Department of Health and Human Services; NLM is not responsible for the product and does not endorse or recommend this or any other product."

## Acceptance

Eval thresholds apply to the frozen `test` split **and** to all patients. Both are reported, with 95% bootstrap CIs.

| ID | Criterion | Threshold | How measured |
|---|---|---|---|
| S5-A01 | `make test` is green | Exit 0; 0 failed, 0 errors; offline (sockets blocked). The s0 suite still passes. | Run `make test` from a clean clone of `factory/s5` |
| S5-A02 | The three-step pipeline runs through the gateway | Per run: exactly 1 `pharma.extract.v1` call per present source and 1 `pharma.phrase.v1` call. Each call has an s0 gateway audit row. The default provider is `mock`. Identical snapshots give byte-identical issue sets. 0 imports of `gateway.adapters` in `pharma/`. | pytest `test_pipeline_uses_gateway`, `test_reconcile_deterministic`, `test_pharma_provider_isolation` |
| S5-A03 | Extraction accuracy (mock) | Field-level exact match of name, dose, unit, route and frequency against fixture gold is at least 0.98 on the test split. Null gold stays null (0 fabricated values). | `results.json.extraction`; pytest `test_extraction_fields` |
| S5-A04 | Normalisation to the code system | 100% of fixture mentions (generic, EN brand, Thai brand, Thai script) resolve to the gold ingredient RXCUI(s). 3/3 unknown names produce an `unrecognised_drug` notice and are not dropped. | pytest `test_normalise_fixture_mentions`, `test_unknown_drug_notice` |
| S5-A05 | Recall per discrepancy type on injected errors | Point estimate at least 0.95 for **each** of the 8 types, with at least 30 injected cases per type and the lower CI reported. | `make pharma-eval` produces `results.json.recall[type]`; pytest `test_eval_thresholds` reads it |
| S5-A06 | Precision / false alerts | On clean lists: mean false alerts per list at most 0.10, counting every issue and notice. On injected cases: mean extra non-injected issues per case at most 0.10. Per-type precision on the injected set is reported. | `results.json.clean_false_alerts`, `.precision[type]` |
| S5-A07 | Rules-only vs rules+model phrasing | Both modes are reported. Issue sets (type, rule_id, ingredients, sources, severity) are identical in 100% of cases. Recall and false alerts are reported per mode. | `results.json.modes`; pytest `test_phrasing_cannot_change_issues` |
| S5-A08 | Every issue lists its conflicting sources | 100% of issues across all eval runs have a non-empty `conflicting_sources` list, with at least 2 entries for mismatch, duplication and allergy. Each entry has `source_type`, `evidence_ref`, `available_at_time` and `raw_span`. 100% of accepted phrasings name every source label and drug. 3/3 cases fall back to the template: an invalid schema, a missing source name, and a banned phrase. | pytest `test_issue_sources_complete`, `test_phrasing_validation_fallback[schema|missing_source|banned_phrase]` |
| S5-A09 | Allergy detection incl. cross-reactivity | 5/5 positive cases detected with the correct subtype. At least 1 negative control gives 0 allergy issues. 1/1 unmapped allergen gives an `allergy_unmapped` notice. Every `cross_reactivity.json` row has a citation. The positives are:<br>• penicillin allergy with amoxicillin → `allergy_class`<br>• penicillin allergy with cephalexin → `allergy_cross_reactivity`<br>• sulfonamide-antibiotic allergy with a sulfamethoxazole combination → `allergy_class`<br>• aspirin/NSAID hypersensitivity with ibuprofen → `allergy_cross_reactivity`<br>• direct allergy via a Thai brand name → `allergy_direct`<br>The negative control is penicillin allergy with azithromycin. | pytest `test_allergy_cases` (parametrized), `test_cross_reactivity_citations` |
| S5-A10 | The agent has no code path that mutates orders | 4/4 checks pass:<br>(a) AST/grep: `pharma/` has 0 SQL UPDATE/DELETE and writes only to `pharma_*` tables and audit.<br>(b) The route inventory has only GET/POST on runs/issues/fixtures, and 0 routes on orders.<br>(c) The snapshot sha256 is unchanged after reconcile, confirm and dismiss.<br>(d) The Issue and Decision models have 0 order-edit fields. | pytest `test_no_order_mutation_static`, `test_pharma_route_inventory`, `test_snapshot_immutable`, `test_issue_model_has_no_order_fields` |
| S5-A11 | Pharmacist confirm/dismiss is audited | Pharmacist only: nurse and physician get 403 (2/2), unauthenticated gets 401. Each decision writes exactly 1 decision row and 1 audit row, with reviewer id, role, UTC `ts_utc`, `run_id`, `issue_id` and `rule_id`. Dismiss without a reason gives 422. A second decision gives 409. UPDATE/DELETE on the `pharma_*` tables raise (SQLite). 0 raw reason text in audit. | pytest `test_decision_roles`, `test_decision_audit`, `test_dismiss_requires_reason`, `test_decision_once`, `test_pharma_tables_append_only` |
| S5-A12 | Fails safe | 4/4 extraction failure modes (error, timeout, rejected, schema-invalid) each set that source to `extraction_failed`, add a `source_unreadable` notice, and set the run to `incomplete`, with no silent empty list. No `new_order` source gives 1 `source_missing` notice and 0 omission issues. A non-synthetic `data_class` through the external adapter is rejected with 0 outbound requests. | pytest `test_extract_fail_safe[...]`, `test_missing_new_order_source`, `test_pharma_non_synthetic_rejected` |
| S5-A13 | Only time-valid evidence is used | Items with `available_at_time > as_of` are excluded (0 in issues) and counted in `excluded_future_items`. | pytest `test_future_items_excluded` |
| S5-A14 | Formulary licence decision recorded | `docs/DECISIONS.md` has a dated entry with all the URLs in the table above. `formulary.json` metadata records the source per field, `verified_on`, and the NLM attribution. The committed data contains 0 ATC codes and 0 TMT codes. The attribution is visible on the pharmacist page. Formulary coverage minimums (§7) are met. | pytest `test_formulary_licence_and_coverage` (regex for ATC `^[A-Z]\d\d[A-Z]{2}\d\d$` and TMT id patterns); Vitest page test |
| S5-A15 | Fixtures and harness are valid | At least 30 clean patients with a split of at least 20 dev and at least 10 test. The test manifest sha256 matches. Every item has `available_at_time`, `provenance`, `version` and `data_class=synthetic`. At least 5 have documented discontinuation and at least 10 use Thai mentions. The injection log has 1 line per case, at least 30 per type, and is reproducible from the seed (byte-identical). | pytest `test_fixtures_valid`, `test_injection_reproducible` |
| S5-A16 | The pharmacist page works in a browser | Playwright on 3105 against 8105: log in as `pharmacist1`, open `/pharmacist/reconcile`, pick a fixture, and run. Issues render with allergy first and a sources table. Confirm 1 issue and dismiss 1 with a reason. The statuses persist after reload. Nurse gets the 403 page. | `make e2e-pharma` → `e2e/pharma.spec.ts` |
| S5-A17 | Accessibility, semantics and claim hygiene | 0 serious or critical axe violations on `/pharmacist/reconcile`. Semantic markup as in §9. Confirm and dismiss work with the keyboard only. 0 hex/rgb colour literals in the pharma page files. The disclaimer is present. 0 occurrences of `diagnos\|prescrib\|treat` in the UI copy. | `e2e/pharma-a11y.spec.ts`; Vitest `pharma-page.test.tsx`; s0 `test_repo_hygiene` |
| S5-A18 | Ports | The slice servers bind only to 127.0.0.1:8105 and 127.0.0.1:3105. The Makefile defaults are still 8000/3000. | e2e-tester `curl` on 8105/3105; pytest `test_makefile_port_defaults` |

## Required test cases

These are backend tests, run by `make test`:
- `test_pipeline_uses_gateway`
- `test_reconcile_deterministic`
- `test_pharma_provider_isolation`
- `test_extraction_fields`
- `test_normalise_fixture_mentions`
- `test_unknown_drug_notice`
- One rule unit test per type, with positive and negative cases:
  - `test_rule_duplication_ingredient`
  - `test_rule_duplication_class`
  - `test_rule_dose_mismatch` (incl. unit conversion, unverifiable, and missing dose)
  - `test_rule_frequency_mismatch` (incl. `bid` = `วันละ 2 ครั้ง` = `q12h`)
  - `test_rule_omission` (incl. discontinue_intent and possible_substitution)
  - `test_allergy_cases[...]`
- `test_cross_reactivity_citations`
- `test_phrasing_cannot_change_issues`
- `test_phrasing_validation_fallback[schema|missing_source|banned_phrase]`
- `test_issue_sources_complete`
- `test_no_order_mutation_static`
- `test_pharma_route_inventory`
- `test_snapshot_immutable`
- `test_issue_model_has_no_order_fields`
- `test_decision_roles`
- `test_decision_audit`
- `test_dismiss_requires_reason`
- `test_decision_once`
- `test_pharma_tables_append_only`
- `test_extract_fail_safe[error|timeout|rejected|schema_invalid]`
- `test_missing_new_order_source`
- `test_pharma_non_synthetic_rejected`
- `test_future_items_excluded`
- `test_formulary_licence_and_coverage`
- `test_fixtures_valid`
- `test_injection_reproducible`
- `test_eval_thresholds` (runs the harness in-process, then checks A05–A07)
- `test_makefile_port_defaults`

This is a web unit test, run by `make test`:
- `pharma-page.test.tsx`: landmarks, table caption and `th scope`, labelled reason, attribution, and no colour literals.

These are browser tests, run by `make e2e-pharma`:
- `e2e/pharma.spec.ts`
- `e2e/pharma-a11y.spec.ts`

## Clinical risks

| Risk | Mitigation |
|---|---|
| The agent is seen as changing or recommending therapy | There is no order-mutation path (A10). Banned prescriptive phrases fall back to a template (A08). The page states that issues are for pharmacist review. Claim hygiene is checked (A17). |
| A missed allergy or cross-reactivity | Rules are primary, and allergy issues get the highest severity and cannot be filtered out. The cross-reactivity table is cited and marked `pending_pharmacist` review (A09). An unmapped allergen raises a notice instead of silence. |
| Missing data is read as "no discrepancy" | Null fields are preserved. Extraction failure gives a `source_unreadable` notice and an `incomplete` run. A missing order source gives a notice, not a flood of omissions (A12). |
| Model phrasing distorts findings | The model cannot add, drop, retype or re-rank issues (A07). The phrasing must name every source, otherwise the template is used (A08). The raw output is stored. |
| Alert fatigue from false alerts | False alerts per clean list are at most 0.10 (A06). Intentional discontinuation and same-class substitution are handled. |
| Rules overfitted to the injector | The test split is frozen by hash and results are reported on test and all patients. Injection uses varied surface forms (Thai, brand, abbreviations). The results are labelled System Evaluation, not clinical performance. |
| Licence breach (TMT/ATC/SNOMED) | Only public-domain NLM and US federal class data is committed. A regex test enforces 0 ATC/TMT codes (A14). |
| Real patient data reaches an external API | Everything is `data_class=synthetic`. The s0 policy rejects non-synthetic data before any I/O (A12). |

## Run commands

```bash
make test                                   # all unit/contract tests incl. pharma, offline
make pharma-eval                            # inject + evaluate both modes -> slices/s5/eval/{results.json,injection_log.jsonl}
make dev API_PORT=8105 WEB_PORT=3105        # API http://127.0.0.1:8105, web http://127.0.0.1:3105/pharmacist/reconcile
make e2e-pharma                             # Playwright pharma specs against 3105/8105
```

## Decisions needed (none blocking)

- Whether to use TMT codes: this needs written permission from THIS plus a DECISIONS.md entry.
- Whether to use ATC codes: this needs a human decision under the WHOCC terms.
- Clinical sign-off of `cross_reactivity.json` and of the `duplication_relevant` classes by a pharmacist: needed before any non-synthetic use.
- Expert-reviewed precision sample (Proposal 3.6): planned for later, not part of s5.
