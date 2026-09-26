# Slice s4 — Department suggestion + Red-flag + nurse confirm

- Owner (Gantt): ธัญรดา
- Source of truth: `docs/PROPOSAL.md` (v8). Sections used:
  - 1.3.1: Red-flag Node uses predefined rules and is mandatory. The Reasoning Node suggests a department. The nurse confirms it. The Human Checkpoint is mandatory. The dashboard records who acted and when.
  - 1.3.4: the system never sends a patient to a department without staff confirmation. It is a research prototype and uses synthetic data only.
  - 3.2.1 Table 3.1: `Red-flag Node: Findings, Vitals -> Alerts (rules)`. `Human Checkpoint -> ConfirmedResult`.
  - 3.2.2: when required data is missing, the node abstains and returns a missing-information list.
  - 3.5: the nurse confirms the suggested department.
  - 3.6 / Table 3.2: department accuracy. Abstention is measured as coverage plus accuracy on answered cases, compared with an "always answer" system. 95% CI comes from a patient-level bootstrap. Without expert review, results are reported as a **System Evaluation**.
- Builds on: s0 (auth/roles, Model Gateway, append-only `audit_events`).
- Does not depend on: s1 (dataset), s2 (casegraph types), or the MedX theme.
- Status: PLAN. The planner wrote this spec. Code lives in `backend/app/triage/` with local Pydantic models.

## Scope

1. **Intake model** (`triage/models.py`, local)
   - `IntakeFact {fact_id, kind, value, available_at_time, source, provenance, version}`.
   - Symptom facts are tri-state: `present | absent | unknown`. A missing symptom is never treated as absent.
   - `Vitals`: `hr`, `rr`, `sbp`, `dbp`, `spo2`, `temp_c`, `avpu (A|V|P|U)`, `new_confusion`, and optional `capillary_glucose_mg_dl`. Each vital carries its own `available_at_time`.
   - `Case` has `case_ref`, `data_class="synthetic"` and `facts[]`.
   - `Gold` is a **separate** model. The engine's input type cannot hold it.
   - **Snapshot at `as_of`:** only facts with `available_at_time <= as_of` are used, for both rules and the department suggestion.
2. **Red-flag engine** (`triage/redflags.py` + `triage/rules/redflag_rules_v1.json`)
   - Deterministic and declarative. There is no model in this path.
   - `RULESET_VERSION = "rf-1.0.0"`. The SHA-256 of the rules file is pinned next to the version. A test fails if the file changes without a version bump.
   - Each rule has: `id`, `name_en`, `name_th`, `condition`, `severity=escalate`, `rationale`, and `source {citation, pmid | url, accessed}`.
   - Output is `Alert {rule_id, ruleset_version, evidence_refs[fact_id], message_th/en}`.
   - Any alert sets `escalation_required=true`.
   - `not_evaluable[]` lists rules that could not be checked because their inputs are missing. It is shown to the nurse and is never counted as "no red flag".
   - Model or gateway output can never add, remove, or downgrade alerts.
   - Candidate rules follow. The builder must verify every PMID or URL on PubMed or at the publisher. Thresholds come from the source and are not tuned to fixtures. No thresholds are invented.

   | Rule | Trigger (adult) | Candidate source (verify) |
   |---|---|---|
   | RF-SPO2 | SpO2 <= 91% | NEWS2, RCP 2017 (single-parameter score 3), rcp.ac.uk |
   | RF-RR | RR <= 8 or >= 25 | NEWS2 |
   | RF-SBP | SBP <= 90 or >= 220 | NEWS2 |
   | RF-HR | HR <= 40 or >= 131 | NEWS2 |
   | RF-CONSC | AVPU != A, or new confusion | NEWS2; ESI Handbook v4 (AHRQ/ENA) |
   | RF-TEMP | Temp <= 35.0 °C | NEWS2 |
   | RF-QSOFA | >= 2 of: RR >= 22, SBP <= 100, altered mentation | Seymour et al., JAMA 2016 (PMID 26903335) |
   | RF-CHEST | Acute chest pain (goal: ECG within 10 min) | Gulati et al., AHA/ACC 2021 chest pain guideline (PMID 34709879) |
   | RF-STROKE | Sudden facial droop, arm/leg weakness, speech or vision disturbance | Powers et al., AHA/ASA 2019 (PMID 31662037) |
   | RF-THUNDER | Sudden severe ("worst ever") headache peaking within 1 h | Perry et al., JAMA 2013 Ottawa SAH rule (PMID 24065011) |
   | RF-ANAPH | Allergen exposure plus airway/breathing compromise or hypotension | Cardona et al., WAO 2020 (PMID 33204386) |
   | RF-SUICIDE | Suicidal ideation or self-harm | ESI Handbook; Joint Commission NPSG 15.01.01 (URL) |
   | RF-GIBLEED | Hematemesis or melena | Laine et al., ACG 2021 (PMID 33929377) |
   | RF-ECTOPIC | Female 15–50 with abdominal pain or vaginal bleeding, and pregnancy status positive **or unknown** | ACOG Practice Bulletin 193 (2018) |
   | RF-MENING | Fever plus neck stiffness or non-blanching rash | van de Beek et al., ESCMID 2016 (PMID 27062097) |
   | RF-HYPOGLY | Capillary glucose < 54 mg/dL | ADA Standards of Care, Glycemic Targets (level 2) |

3. **Department suggestion** (`triage/department.py`) via the s0 Model Gateway
   - Task: `triage.department.v1`, with `data_class=synthetic`.
   - **Gateway change (additive, backward-compatible):**
     - Extract the body of `/api/gateway/invoke` into `app.gateway.service.invoke(engine, provider, request, actor)`. The route and the triage module both call it, so each call is audited once.
     - Add `app.gateway.mock_tasks.register(task, fn)`. `MockProvider` dispatches registered tasks to `fn`. Unregistered tasks keep today's hash-based output.
     - No code outside `app/gateway/` imports `gateway.adapters`.
     - The s0 tests stay green unchanged.
   - The default mock is a deterministic keyword/rule baseline (`triage/baseline.py`, registered with the mock). It matches the Thai and English chief-complaint text and the present symptom facts against a versioned keyword table (`baseline_keywords_v1.json`). Scores are normalized to [0, 1].
   - Output: `DepartmentSuggestion`.
     - `status`: `suggested | abstained | error`.
     - `top3`: up to 3 entries `{code, label_th, label_en, score, evidence_refs[fact_id]}`.
     - `uncertainty`: `low | medium | high`, computed from the top-1 minus top-2 margin and the evidence count. It is labelled "MOCK baseline — not calibrated".
     - `missing_information[]`, `provider`, `model_version`, `contract_version`, `request_sha256`.
   - **Abstain** (no ranking is shown) in any of these cases:
     - any required field is missing: age, sex, chief complaint, onset/duration, and the vitals `hr`, `rr`, `sbp`, `spo2`, `temp_c`, `avpu`;
     - the gateway returns `rejected` or `error`, or its output fails the local schema;
     - no keyword evidence matched.
   - Red-flag evaluation always runs on the available facts, including when the department suggestion abstains.
   - **Fixed department list v1:** 10 codes, Thai-hospital adult OPD granularity. Each code has a MIMIC-IV `services` code so it lines up with the 3.6 proxy label.
     - The list and mapping are **provisional** until an expert confirms them.
     - There is no "ER" department. Urgency goes through the red-flag and escalation channel only, so an urgency signal is never hidden inside a ranking.

   | Code | Thai | English | MIMIC `services` |
   |---|---|---|---|
   | MED | อายุรกรรม | Internal medicine | MED, OMED |
   | CARD | อายุรกรรมหัวใจ | Cardiology | CMED |
   | NEURO | ประสาทวิทยา | Neurology | NMED |
   | SURG | ศัลยกรรมทั่วไป | General surgery | SURG, VSURG, TSURG, PSURG, CSURG |
   | ORTHO | ศัลยกรรมกระดูกและข้อ | Orthopedics | ORTHO, TRAUM |
   | URO | ศัลยกรรมระบบทางเดินปัสสาวะ | Urology | GU |
   | OBGYN | สูติ-นรีเวชกรรม | Obstetrics & gynecology | OBS, GYN |
   | EYE | จักษุ | Ophthalmology | EYE |
   | ENT | โสต ศอ นาสิก | ENT | ENT |
   | PSY | จิตเวช | Psychiatry | PSYCH |

4. **Assessment and review API** (`triage/router.py`, prefix `/api/triage`)
   - Read endpoints (nurse or physician; pharmacist gets 403):
     - `GET /cases`: fixture cases, listed by `case_ref` and chief complaint only.
     - `GET /assessments/{id}`.
     - `GET /cases/{case_ref}/confirmed`.
   - Nurse-only write endpoints (other roles get 403, no session gets 401):
     - `POST /cases/{case_ref}/assess {as_of}`. It returns an immutable `TriageAssessment {assessment_id, as_of, ruleset_version, alerts[], not_evaluable[], escalation_required, department, review_status="pending_review", confirmed_department=null}`. Alerts are serialized **before** the department section.
     - `POST /assessments/{id}/confirm {department_code ∈ top3, acknowledged_alert_ids[]}`.
     - `POST /assessments/{id}/edit {department_code ∈ fixed list, reason (required), acknowledged_alert_ids[]}`. This is also the only way to set a department on an abstained assessment.
     - `POST /assessments/{id}/reject {reason (required), acknowledged_alert_ids[]}`.
   - When `escalation_required` is true, any review that does not acknowledge **every** alert id gets 409 `alerts_not_acknowledged`.
   - A second review of the same assessment gets 409 `already_reviewed`.
   - Re-assessing creates a new assessment and never mutates an old one.
   - Storage: new tables `triage_assessments` and `triage_reviews`, both with append-only triggers like `audit_events`.
   - `GET /cases/{ref}/confirmed` returns only confirmed or edited results. If nothing is confirmed it returns 404 `pending_review`. This is the only care-facing read.
   - `/confirmed` resolves against the **newest assessment** for the case (by `as_of`, then `created_at`), never by review order. If that assessment is pending or rejected, it returns 404 `pending_review` with `newest_assessment {assessment_id, as_of, review_status, alert_rule_ids, escalation_required}`, so an older confirmed result never hides newer red flags.
5. **Audit** (via s0 `write_audit`)
   - Actions:
     - `triage.assess`: details include `assessment_id`, `case_ref`, `as_of`, `ruleset_version`, `alert_rule_ids`, dept status and top-3 codes/scores, `provider`, `model_version`, and `request_sha256`.
     - `triage.review.confirm|edit|reject`: details include the reviewer id and role, `ts_utc`, `assessment_id`, the **original suggestion** (status, top-3 codes/scores, missing information, alert rule ids), `final_department`, `acknowledged_alert_ids`, and `reason_sha256`.
     - `triage.review.denied`: written for every 403 or 409.
   - Raw chief-complaint and reason text never goes into the audit log.
6. **Fixtures** (`backend/app/triage/fixtures/cases_v1.json`)
   - 40 hand-written synthetic adult cases. They are committed in a **separate commit before the engine code**. The file hash is pinned in a test.
   - Composition:
     - >= 16 red-flag cases, covering every rule at least once, with >= 3 multi-rule cases;
     - >= 6 cases with a required field missing, of which >= 2 also carry a red flag;
     - >= 10 near-miss negatives, for example HR 125, SpO2 93, chest discomfort explicitly `absent`, or musculoskeletal pain;
     - >= 2 temporal cases, where the red-flag fact becomes available after the first `as_of`;
     - every department gold >= 3 times among complete cases;
     - Thai chief-complaint text in >= 20 cases.
   - Each case has `split: dev | holdout` (20 / 20). Keyword tuning may look only at `dev`.
7. **Evaluation** (`python -m app.triage.evaluate` → `slices/s4/eval/metrics_v1.json`)
   - Rule-level and case-level red-flag recall, false-positive rate (FPR) with the list of false-positive case ids, top-1 and top-3 accuracy, coverage, selective accuracy compared with "always answer", abstention rate on missing-field cases, and false abstention on complete cases.
   - Each metric is reported per split and overall, with a patient-level bootstrap 95% CI (1000 resamples, seed 20260926).
   - The results are labelled "System Evaluation on synthetic fixtures — not clinical performance".
8. **Nurse web page**
   - Pages:
     - `/nurse/triage`: case list.
     - `/nurse/triage/[assessmentId]`: review page.
   - Semantic markup:
     - `<main>`, `<h1>`/`<h2>` sections;
     - alerts in `<section aria-labelledby>` with `role="alert"`, placed **before** the department section in both DOM and visual order;
     - `<ol>` for the top-3, showing score, uncertainty, and evidence references;
     - the missing-information list;
     - `<form>` with labelled controls.
   - Confirm stays disabled until every alert's acknowledgement checkbox is checked.
   - An abstained assessment shows no ranking. Only edit (manual department) and reject are available.
   - Uses the existing globals only (the MedX theme lands in parallel). The page uses no claim terms ("diagnos", "prescrib", "treat") and no provider names.
9. **Makefile**
   - `make dev` and `make e2e` take `API_PORT` and `WEB_PORT`, with defaults unchanged. s4 runs on **8104/3104**.
   - Add a `triage-eval` target.

## Out of scope

- Voice Agent and intake capture. Intake is fixture JSON here.
- The s1 dataset and MIMIC data, including MIMIC `services` labels.
- The Case Graph Compiler/Executor and shared casegraph types (s2). The local models map onto them later.
- Care suggestions, the Pharma Agent, and the physician/pharmacist workflow.
- Pediatric or obstetric-specific triage scales, and ESI/MOPH acuity levels. Only escalation is output here. No local acuity mapping is invented.
- Any external or real provider call. Real or identifiable data.
- The MedX visual theme. Calibrated probabilities.

## Acceptance

| ID | Criterion | Threshold | How measured |
|---|---|---|---|
| S4-A01 | Red-flag recall on fixtures (hard gate) | Case-level recall = 1.00 (every case with a gold red flag gets >= 1 alert). Rule-level recall = 1.00 (every gold `(case, rule)` pair fires). Both hold on dev, holdout, and overall. | pytest `test_redflag_recall_is_total`; `metrics_v1.json` |
| S4-A02 | Red-flag false-positive rate reported | FPR (gold-negative cases with >= 1 alert) and per-rule extra alerts are reported with a 95% CI and the list of false-positive case ids. Non-gating, but every false positive needs a one-line justification in the metrics file. | `make triage-eval` output checked by the checker |
| S4-A03 | Every rule cites a clinical source | 16/16 rules have a non-empty `citation` plus a PMID (`^\d{7,8}$`) or an `https://` URL, and an `accessed` date. The checker verifies each PMID/URL resolves to the stated title (spot check 100%). | pytest `test_every_rule_has_source`; checker manual lookup log in PR |
| S4-A04 | Ruleset is versioned and pinned | Every assessment and audit row carries `ruleset_version`. Changing the rules file without a version bump fails the test. | pytest `test_ruleset_hash_pinned_to_version` |
| S4-A05 | Alerts take priority and cannot be downgraded | Alerts are computed before and independently of the gateway. A mock that returns "no urgency" or tries to set `alerts: []` leaves the alerts unchanged (0/16 red-flag cases lose an alert). Provider error still returns the full alerts. | pytest `test_model_cannot_suppress_alerts`, `test_alerts_survive_provider_error` |
| S4-A06 | Alert is shown above the suggestion and blocks silent acceptance | API: `alerts` is serialized before `department`. Confirm/edit/reject without acknowledging every alert id gives 409 and writes no review row (3/3 actions). UI: the alert region comes before the department section in DOM order and bounding-box y. Confirm is disabled until all acknowledgement boxes are checked. | pytest `test_review_requires_alert_ack[confirm\|edit\|reject]`; Vitest `triage-review.test.tsx`; Playwright `triage.spec.ts` |
| S4-A07 | Department accuracy (mock baseline) | Top-3 accuracy >= 0.80 on answered complete cases, overall. Top-1 and top-3 are reported per split with a 95% CI. Holdout top-3 is reported separately. If holdout falls below 0.70, it is flagged as overfitting risk (non-gating). | `make triage-eval`; pytest `test_department_top3_threshold` |
| S4-A08 | Abstention on missing required fields | 100% of missing-field cases give `status=abstained`, no top-3, and `missing_information` exactly equal to the gold missing list. Red-flag alerts still fire on those cases where gold says so. | pytest `test_abstains_when_required_missing` (parametrized over the fixtures) |
| S4-A09 | Coverage and selective accuracy reported (Table 3.2) | Coverage, accuracy on answered cases, and "always answer" accuracy are reported with CI. False abstention on complete cases is reported (target 0). | `metrics_v1.json` |
| S4-A10 | Missingness is preserved | `unknown` or missing symptoms are never treated as `absent`. RF-ECTOPIC fires when pregnancy status is unknown. Missing vitals appear in `not_evaluable`. | pytest `test_unknown_not_negative`, `test_not_evaluable_listed` |
| S4-A11 | Time-valid evidence only | For the temporal cases, the alert is absent at the early `as_of` and present at the later `as_of`. All `evidence_refs` have `available_at_time <= as_of` in 100% of assessments. Gold fields are unreachable from the engine input. | pytest `test_snapshot_as_of`, `test_evidence_refs_time_valid`, `test_gold_not_in_engine_input` |
| S4-A12 | Suggestion goes through the gateway and fails safe | Department calls go through `gateway.service.invoke` with `data_class=synthetic`, giving exactly 1 `gateway.invoke` audit row per assessment. A forced error, rejected, or schema-invalid provider gives `status=error` or `abstained` with 0 fabricated departments (3/3). The s0 tests pass unchanged. There are 0 `gateway.adapters` imports outside the gateway. | pytest `test_department_via_gateway`, `test_department_fail_safe[error\|rejected\|invalid]`; s0 `test_provider_isolation` |
| S4-A13 | Deterministic | Two identical assessments give byte-identical alerts and department output (excluding ids and timestamps). | pytest `test_assessment_deterministic` |
| S4-A14 | Review is audited with reviewer, time, and original suggestion | For each of confirm, edit, and reject: exactly 1 `triage.review.*` audit row with reviewer id and role, UTC ts, the original suggestion, the final department (or null), and the acknowledged alerts. A second review gives 409 plus a `triage.review.denied` row. Sentinel text from the chief complaint or reason appears in 0 audit rows. `triage_*` tables reject UPDATE and DELETE. | pytest `test_review_audit[confirm\|edit\|reject]`, `test_double_review_409`, `test_audit_no_raw_text`, `test_triage_tables_append_only` |
| S4-A15 | Nothing reaches care without confirmation | `GET /cases/{ref}/confirmed` gives 404 `pending_review` before a review and after a reject. It gives the department only after confirm or edit. The assess response always has `confirmed_department=null`. After re-assessment it reflects only the newest assessment (by `as_of`); a pending newer assessment yields 404 with its alerts, and reviewing an older snapshot later never overrides it. | pytest `test_confirmed_only_after_review`, `test_confirmed_not_stale_after_reassessment` (3 temporal fixtures x both review orders) |
| S4-A16 | Role enforcement | Write endpoints: nurse gets 2xx, physician and pharmacist get 403, no session gets 401. Read endpoints: pharmacist gets 403. Every denial is audited. | pytest `test_triage_role_matrix` |
| S4-A17 | Fixture set meets composition | 40 cases, `data_class=synthetic`, and every composition minimum in Scope 6. The fixture hash is pinned. The fixture commit precedes the engine commit in git history. | pytest `test_fixture_composition`; `git log` check by the checker |
| S4-A18 | `make test` green | Exit 0 with 0 failed. The s0 suite is included and unchanged in behavior. Offline (sockets blocked). | `make test` from a clean clone |
| S4-A19 | Nurse page works in a browser | On 8104/3104, nurse1 logs in and opens a red-flag case. Alerts are visible above the ranking. Confirm is disabled until acknowledgement, then confirm succeeds, and the confirmed state is shown. An abstained case shows the missing list and supports manual edit. 0 serious or critical axe violations. Works with the keyboard only. | Playwright `e2e/triage.spec.ts` + `e2e/a11y.spec.ts` (triage pages added), `API_PORT=8104 WEB_PORT=3104` |
| S4-A20 | Claim boundary | The research disclaimer is shown. Triage pages and API copy contain 0 claim terms. The UI labels the output "suggestion for nurse review". | s0 `test_repo_hygiene` (covers `web/app/**`) + Vitest assertion |

## Required test cases

- Backend (pytest, `backend/tests/triage/`):
  - `test_every_rule_has_source`
  - `test_ruleset_hash_pinned_to_version`
  - `test_redflag_recall_is_total`
  - one unit test per rule with a boundary value on each side, e.g. SpO2 91 fires and 92 does not
  - `test_model_cannot_suppress_alerts`
  - `test_alerts_survive_provider_error`
  - `test_unknown_not_negative`
  - `test_not_evaluable_listed`
  - `test_snapshot_as_of`
  - `test_evidence_refs_time_valid`
  - `test_gold_not_in_engine_input`
  - `test_abstains_when_required_missing`
  - `test_department_top3_threshold`
  - `test_department_via_gateway`
  - `test_department_fail_safe[error|rejected|invalid]`
  - `test_assessment_deterministic`
  - `test_review_requires_alert_ack[confirm|edit|reject]`
  - `test_edit_requires_reason_and_valid_code`
  - `test_confirm_code_must_be_in_top3`
  - `test_review_audit[confirm|edit|reject]`
  - `test_double_review_409`
  - `test_audit_no_raw_text`
  - `test_triage_tables_append_only`
  - `test_confirmed_only_after_review`
  - `test_confirmed_not_stale_after_reassessment`
  - `test_triage_role_matrix`
  - `test_fixture_composition`
  - `test_mock_task_registry_backward_compatible`
- Web (Vitest): `triage-review.test.tsx`
  - the alert section precedes the department section;
  - confirm is disabled until acknowledgement;
  - the abstained state shows the missing list and no ranking;
  - there are no claim terms.
- Browser (Playwright): `triage.spec.ts` and the extended `a11y.spec.ts`.

## Clinical risks

| Risk | Mitigation |
|---|---|
| A missed red flag delays emergency care | Deterministic rules with published thresholds. The recall hard gate is 1.00 (A01). Missing inputs are listed as `not_evaluable`, never read as "safe" (A10). Alerts are independent of the model and the gateway (A05). |
| Circular evaluation: the same author writes both rules and fixtures | Fixtures are committed and hash-pinned before the engine (A17). There is a holdout split (A07). Results are labelled System Evaluation. 100% recall on 40 cases is a regression gate, not evidence of clinical sensitivity. |
| Alert fatigue from over-firing, e.g. every chest pain | FPR and per-rule false positives are reported with justification (A02). Tuning thresholds against fixtures is prohibited. Threshold changes need a source and a version bump. |
| A department ranking is read as a disposition or diagnosis | There is no ER code. Urgency goes only through alerts. The copy says "suggestion for nurse review". Confirmation is required before anything is care-facing (A15, A20). |
| A nurse accepts a suggestion without seeing the alert | Alerts are placed above the suggestion. API and UI both block review until every alert is acknowledged (A06). |
| An uncalibrated mock score is read as a probability | The uncertainty label is coarse, marked "MOCK baseline — not calibrated". |
| Unverified citations | The checker must look up every PMID/URL (A03). The thresholds and department mapping stay provisional until clinical experts review them (proposal 3.6). |

## Run commands

```bash
make test                                   # full suite incl. s0 + s4, offline
make triage-eval                            # writes slices/s4/eval/metrics_v1.json
make dev API_PORT=8104 WEB_PORT=3104        # API http://127.0.0.1:8104, web http://127.0.0.1:3104/nurse/triage
API_PORT=8104 WEB_PORT=3104 make e2e        # Playwright incl. triage.spec.ts (never 8000/3000 for s4)
```

## Decisions required (non-blocking for the build, blocking for any clinical claim)

1. The department list v1 and its MIMIC `services` mapping need clinical expert confirmation. Proposal 3.6 says the mapping is "defined with experts".
2. The red-flag rule set and thresholds need clinical expert review. Until then they are a research prototype only.
3. The gateway refactor (`service.invoke`, `mock_tasks`) touches the s0 shared code. Coordinate with the other slices (s3/s5/s8) that may make the same change, so there is one merge owner.
4. Mapping to s2 casegraph types (`Alerts`, `DepartmentSuggestion`, `ConfirmedResult`) happens at integration. The local models are not a contract.
