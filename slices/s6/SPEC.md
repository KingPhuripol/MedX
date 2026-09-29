# Slice s6 — Care suggestion with abstention (physician)

- Owner (Gantt): ธัญรดา (row "พัฒนาระบบเสนอแนวทางการดูแล")
- Source of truth: `docs/PROPOSAL.md` (v8). Sections used:
  - 1.3.1 "ระบบเสนอแนวทางการดูแล": when more data arrives (labs, images) the system summarises the patient, suggests tests or information to collect next, and suggests initial care-pathway options **for the physician to consider**. It states the data it used and the data still missing, and **abstains when required data is incomplete**. The Clinical Dashboard lets the user confirm, edit or reject and records who acted and when.
  - 1.3.4: no diagnosis, no treatment or prescribing orders, synthetic data only, research prototype.
  - 3.2.1 / Table 3.1: Reasoning Node outputs `CareSuggestion`. The Red-flag Node is mandatory. The Human Checkpoint is mandatory.
  - 3.2.2: when a Reasoning required input is not in the snapshot, the node abstains and returns the missing list.
  - 3.6 / Table 3.2: label (3) is the tests ordered after decision time, plus expert rating. Abstention is reported as coverage plus accuracy on answered cases versus an always-answer system. 95% CI from a patient-level bootstrap. Without expert review the result is a **System Evaluation**, not clinical performance.
- Builds on (already on this branch): s0 (auth, roles, gateway, append-only audit), s1r (`data_factory` v1.1.1, `make data`/`make audit`), s2/s2r (`casegraph.data.CareSuggestion`, `RedFlagScreening`, `banner_for`), s4 (`app.triage.redflags` rf-1.1.0), s8/s8r (`eval/`), t1 (MedX theme).
- Tier 0 only: CPU, synthetic, offline, deterministic. No external provider. Ports **8106 / 3106**.
- Status: PLAN.

## Design decisions fixed by this spec

1. **Red-flag input is reused, not rebuilt.** The care service never computes, changes or ranks red flags. For s1r snapshots, `care/redflag_adapter.py` maps structured items only (Demographics → `age`, `sex`; each Vitals param → `vital.*` fact with the item's `available_at_time`) to s4 `IntakeFact`s and calls `app.triage.redflags.evaluate` (rf-1.1.0, unchanged). Consciousness: `A` → `avpu=A`, `new_confusion=false`; `C` → `new_confusion=true` only; `V|P|U` → `avpu` of the same letter. No symptom facts are produced (no NLP in this slice), so symptom-based rules are `not_evaluable` and the screening status is `partially_evaluated` with the INCOMPLETE banner. That is the honest state and it must be shown. The result is expressed as `casegraph.data.RedFlagScreening` fields (`status`, `performed`, `banner` via `banner_for`, `rules_evaluated`, `rules_not_evaluated`, `missing_inputs`) plus the s4 `alerts[]`.
2. **The shared `CareSuggestion` type is not changed.** The care API returns a local, richer `CareAssessment`. Each suggested assessment also carries a projection that validates as `casegraph.data.CareSuggestion` (`items` = ranked item codes, `red_flag_screening` = carried status, `input_refs` = sorted union of evidence refs). Richer fields in the shared type need a joint Research/Innovation decision (D3).
3. **The care engine is independent of the gold.** `app/care/**` must not import `data_factory`, read `data_factory/templates/**`, `journey.json` or `gold/**`, or see the complaint template id. Its rule tables are written from the **dev** split only.

## Scope

1. **Gold extension** (`data_factory`, `GENERATOR_VERSION = "1.2.0"`). This is committed **before** any file under `backend/app/care/rules/`.
   - New templates:
     - `next_info_codes.json`: a closed vocabulary of `NI-*` codes, each with `display_th`, `display_en`, `kind ∈ {ask, observe, lab, imaging, ecg}`, and a LOINC code for labs.
     - `care_pathways.json`: a closed vocabulary of `CP-*` pathway options, each named after its source guideline pathway (for example "chest-pain evaluation pathway"). An option is **not** a disposition, a diagnosis or a treatment.
     - `care_next_info.json`: for every complaint template id and every red-flag rule id, either `{next_info: [NI…], pathway: CP…, source_refs: […]}` or `{no_sourced_workup: true, reason}`.
     - `care_required_inputs.json`: the canonical, ordered list of required inputs, each with a source ref: `demographics.age`, `demographics.sex`, `chief_complaint`, `duration`, `allergy_status`, and `vitals.{rr,spo2,on_oxygen,temp_c,sbp,hr,consciousness}` (the NEWS 2012 parameter set, `RCP-NEWS-2012`). Proposal 1.3.1 / s3 is the source for the intake fields.
   - Candidate sources. The builder verifies every PMID/URL and adds it to `references.json` with an `accessed` date. Nothing is invented. A template with no verified source gets `no_sourced_workup`.
     - Acute chest pain: Gulati 2021 (PMID 34709879).
     - FAST / stroke: Powers 2019 (PMID 31662037).
     - Thunderclap headache: Perry 2013 (PMID 24065011).
     - Anaphylaxis: Cardona WAO 2020 (PMID 33204386).
     - qSOFA / NEWS red flags: Evans SSC 2021 (PMID 34599691) and RCP-NEWS-2012.
     - Fever with cough: Metlay ATS/IDSA 2019 (PMID 31573350).
     - RLQ pain: Di Saverio WSES 2020 (PMID 32295644).
     - Dysuria: an IDSA cystitis guideline (verify).
   - New gold key per decision-time row, `care`:
     - `required_inputs_missing`: canonical order, exact strings.
     - `expected_action ∈ {suggest, abstain}`: `abstain` iff the missing list is non-empty.
     - `next_info`: the set of codes. It is the template items plus the fired-rule items, **minus** anything already resulted or observed in `snapshot_T`.
     - `next_info_sources`: map from code to ref ids.
     - `pathway`.
     - `evaluable`: false when `no_sourced_workup` applies, or when `next_info` is empty.
     - `reason`.
     - `ordered_after_T`: lab codes whose LabSeries `event_time` is after T. This is the proposal 3.6(3) proxy.
   - Invariants:
     - Every `inputs/**` file is byte-identical to the v1.1.1 output at the default seed.
     - Existing gold keys are unchanged except `label_version`.
     - The audit bans every `care` key from inputs.
     - `DATACARD.md` and `gold/README.md` describe the new labels as synthetic reference labels, not expert-reviewed.
2. **Care engine** (`backend/app/care/`: `models.py`, `snapshot.py`, `redflag_adapter.py`, `engine.py`, `mock_rules.py`, `rules/care_rules_v1.json` with a pinned sha256 and `CARE_RULES_VERSION`).
   - **Input.** Only `inputs/<split>/<case_id>/snapshot_T{1,2}.json`, validated with `casegraph.evidence_adapter`. As defence, any item with `available_at_time > as_of` is rejected (`error`, never silently dropped).
   - **Order.** Red-flag screening runs first. Then the required-input check. Then exactly one gateway call.
   - **Required-input check.** It runs before the gateway call. Field status is tri-state: `known`, `unknown` or `missing`. `unknown` counts as missing and is never read as negative. If anything is missing, the result is `status=abstained` with `missing_information` in the canonical order, no summary conclusions, no next-info and no pathway options, and **0 gateway calls**.
   - If red-flag screening is `unavailable` (the adapter or engine errored), the result is `abstained` with `missing_information` containing `red_flag_screening`.
   - **Gateway task.** `care.suggest.v1`, `data_class=synthetic`, through `app.gateway.service.invoke_audited`. The deterministic rule-based mock is registered in `app.gateway.mock_tasks` with a version. The mock matches the patient-turn text and the structured items against `care_rules_v1.json`.
   - **Output** (`CareAssessment`). Keys are serialised in this order:
     1. `alerts`
     2. `red_flag_screening`
     3. `escalation_required`
     4. `status ∈ {suggested, abstained, error}`
     5. `case_summary[]`: short descriptive lines (stated complaint, duration, latest vitals, lab values with a reference-range flag, allergy status, medication count). Each line has `evidence_refs`.
     6. `next_information[]`: ranked, at most 5. Each entry has `code`, `display`, `evidence_refs`, `source_refs`. Items driven by an alert rank first.
     7. `pathway_options[]`: at most 3. Each has `code`, `evidence_refs`, `source_refs`.
     8. `missing_information[]`: always present. When suggested, it lists the optional inputs that are absent (for example no LabSeries yet, pregnancy status unknown). These are never read as negative.
     9. `uncertainty`: "MOCK baseline — not calibrated".
     10. `provider`, `model_version`, `contract_version`, `rules_version`, `request_sha256`, `as_of`, `decision_point`.
     11. `casegraph_projection`.
   - **Post-gateway validation (fail-safe).** Any of the following gives `status=error`, shows 0 items, and keeps the alerts and screening unchanged:
     - a code outside the vocabularies;
     - an item with no evidence ref;
     - a ref that is not in the snapshot, or whose `available_at_time > T`;
     - any provider attempt to set alerts, screening or escalation;
     - a provider `error`, `rejected` or timeout.
   - **Always-answer mode** (`abstain=False`). It is used only by the evaluation comparator: the same engine answers from whatever is available.
3. **API** (`/api/care`, physician only for read and write).
   - `GET /cases`: **dev-split** case ids and decision points only. The test split is never served.
   - `POST /cases/{case_id}/assess {decision_point: T1|T2}`: returns an immutable `CareAssessment` with `review_status=pending_review`.
   - `GET /assessments/{id}`.
   - `POST /assessments/{id}/confirm|edit|reject`. Every review body carries `acknowledged_alert_ids[]` and `screening_acknowledged: bool`, which is required when screening is not `evaluated`.
     - `edit` requires a `reason` and codes from the vocabularies. It is the only action allowed on an abstained assessment besides `reject`.
     - `reject` requires a `reason`.
   - `GET /cases/{case_id}/confirmed`: resolves against the newest assessment, with the s4 semantics.
   - The dataset path comes from `CARE_DATASET` (default `data/synthetic/v1`). If it is absent, the API returns 503 `dataset_missing: run make data`.
   - Storage: `care_assessments` and `care_reviews` with append-only triggers.
   - Audit actions:
     - `care.assess`: ids, `as_of`, status, codes, screening status, alert ids, provider/version, request hash.
     - `care.review.confirm|edit|reject`: reviewer id and role, UTC ts, the original suggestion, the final codes or null, acknowledged ids, `reason_sha256`.
     - `care.review.denied`.
   - Raw transcript or reason text never enters the audit log.
4. **Web** (`/physician/care` list, `/physician/care/[assessmentId]` review). MedX tokens from `web/app/theme.css` only, with no new colours.
   - The red-flag region (alerts, and the banner text `RED-FLAG SCREENING INCOMPLETE` or `NOT PERFORMED` with the lists of rules not evaluated) comes first in DOM and visual order. Alerts use `role="alert"`. Urgency is conveyed by heading, text and a glyph, never by colour alone.
   - Next come the summary, then next information (`<ol>`), then pathway options, then missing information. Every item shows its evidence refs with the available time.
   - Confirm stays disabled until every alert and the screening banner are acknowledged.
   - The abstained view shows the missing list and no suggestions.
   - The page is labelled "suggestion for physician review — research prototype".
5. **Evaluation** (`python -m app.care.evaluate --split dev|test` → predictions JSONL, then `python -m eval run`; `make care-eval SPLIT=…`).
   - Additive changes to `eval/`:
     - `selective_hit_at_k` (abstention-aware: `suggested=null` means abstain; hit@k over answered rows), added to `ABSTENTION_AWARE`.
     - `exact_binomial_ci`: Clopper–Pearson, reported next to the bootstrap CI when the bootstrap CI has zero width or more than 1% degenerate resamples. It is computed at patient level: a patient succeeds only if all its eligible decision points succeed. This is conservative and is labelled as such.
   - Metrics per split, each with a patient-level bootstrap 95% CI (eval defaults, seed 20260926):
     - `coverage` over all decision points;
     - `selective_hit_at_3` over answered `care.evaluable` rows;
     - comparator **always-answer** `hit_at_3` over all evaluable rows, and paired on the rows the system answered;
     - comparator **train-prior** (the static top-3 most frequent gold codes on the **train** split);
     - `hit_at_3` against `ordered_after_T` (proxy);
     - pathway top-1 accuracy.
   - Manifests: `slices/s6/eval/manifest_{dev,test}.json`, with the dataset `version` set to the v1.2.0 `tree_sha256` and thresholds predeclared.
   - Ledger: a slice-local ledger `slices/s6/eval/ledger/` (`python -m eval ledger init`). The test manifest is frozen and committed before the single test run. Results go to `slices/s6/eval/results_{dev,test}/`, labelled "System Evaluation on synthetic data — not clinical performance".
6. **Makefile**: add a `care-eval` target. `make dev` / `make e2e` run with `API_PORT=8106 WEB_PORT=3106`.

## Out of scope

- Symptom extraction from the transcript into red-flag facts (s3 → s4 wiring). Text rules stay `not_evaluable` here.
- Any change to red-flag rules, `casegraph` shared types or the executor, or the gateway contract version.
- Diagnosis, differential ranking, treatment, prescribing, dosing, orders, disposition or acuity levels.
- Imaging inputs (CXR/CT readers), and MIMIC or any real data.
- External or real providers, calibrated probabilities, and expert rating of the suggestions (proposal 3.6 sample rating: D1).
- Department suggestion (s4) and the Pharma Agent.

## Acceptance

"All splits" means train + dev + test, both decision points, at the default seed 20260926.

| ID | Criterion | Threshold | How measured |
|---|---|---|---|
| S6-A01 | Abstains whenever required inputs are missing | 100% of rows with gold `care.expected_action=abstain` (all splits) → `status=abstained`, 0 summary/next-info/pathway items, `missing_information` **exactly equal** (strings and order) to gold `required_inputs_missing`, 0 gateway calls. Plus 13/13 synthetic fixtures (12 each removing one of the 12 required inputs, 1 with allergy status `unknown`) → exactly that input listed | pytest `test_abstains_when_required_missing` (parametrized over dataset), `test_each_required_input_individually` |
| S6-A02 | No false abstention | 0 rows with gold `expected_action=suggest` return `abstained` (all splits) | pytest `test_no_false_abstention` |
| S6-A03 | Every item is backed by time-valid evidence | 100% of summary lines, next-info items and pathway options across all assessments (all splits) have ≥1 evidence ref; 100% of refs resolve to an item in `snapshot_T` with `available_at_time <= T`. A provider returning a future ref, an unknown id, or an item without refs → `status=error`, 0 items (3/3) | pytest `test_evidence_refs_time_valid`, `test_bad_refs_fail_safe[future\|unknown\|none]` |
| S6-A04 | Red-flag screening carried and shown above suggestions | 100% of assessments (suggested/abstained/error) carry `alerts` and `red_flag_screening` consistent with `banner_for`; JSON key order puts them before `status`. Fixtures for `evaluated`+alert, `partially_evaluated`, `not_evaluated`, `unavailable` (4/4) render the correct banner text. UI: the red-flag region precedes suggestions in DOM order and bounding-box y | pytest `test_screening_carried[4 states]`, `test_alerts_serialized_first`; Vitest `care-review.test.tsx`; Playwright `care.spec.ts` |
| S6-A05 | Model cannot alter urgency | For every red-flag case in dev, alerts, screening and `escalation_required` are byte-identical across provider modes ok/error/rejected/invalid/"tries to clear alerts" (5/5). Screening `unavailable` → `abstained` with `red_flag_screening` in the missing list | pytest `test_model_cannot_change_alerts`, `test_screening_unavailable_abstains` |
| S6-A06 | Through the gateway, fail-safe, isolated | Exactly 1 `gateway.invoke` audit row per suggested assessment, 0 per abstained, `data_class=synthetic`. Forced error/rejected/schema-invalid/timeout → `status=error`, 0 fabricated items (4/4). 0 imports of `gateway.adapters`, `httpx`, `requests`, `socket` in `app/care` (AST). s0/s4 tests pass unchanged | pytest `test_care_via_gateway`, `test_care_fail_safe[4]`, `test_care_provider_isolation` |
| S6-A07 | Reasoning-node type compatibility | 100% of suggested assessments' `casegraph_projection` validate as `casegraph.data.CareSuggestion` with items in rank order and matching `red_flag_screening`; `git diff main -- casegraph/` is empty | pytest `test_projection_is_care_suggestion`; checker diff |
| S6-A08 | Gold extension is sourced, additive and temporal | v1.2.0: all `inputs/**` file hashes equal v1.1.1 (100%); old gold keys equal except `label_version`; every complaint template and red-flag rule has a `care_next_info` entry; every `NI`/`CP` code used in gold has ≥1 ref with PMID (`^\d{7,8}$`) or `https://` URL and `accessed` date (checker spot-checks 100% of refs resolve to the stated title); every `evaluable=true` row has non-empty `next_info`; ≥1 case whose T1 and T2 `next_info` differ because a result became available | pytest `test_inputs_unchanged_vs_v111`, `test_care_gold_sources`, `test_care_gold_temporal`; checker lookup log |
| S6-A09 | Gold frozen before evaluation; no leakage | `git log`: the data_factory v1.2.0 commit precedes the first commit touching `backend/app/care/rules/`. `make data && make audit` prints `STEP leakage: PASS` and `STEP factory: PASS`; the audit fails on a planted `care` key in an input. The test manifest's freeze entry precedes the test run entry in the s6 ledger; exactly 1 test run for the evaluation id. With `journey.json`, `gold/` and `data_factory/templates` removed from a temp copy, care outputs are byte-identical. `app/care` has 0 imports of `data_factory` | `make audit`; pytest `test_audit_bans_care_gold_in_inputs`, `test_care_reads_snapshots_only`, `test_care_no_data_factory_import`; `python -m eval ledger verify --ledger-dir slices/s6/eval/ledger`; `git log` check |
| S6-A10 | Table 3.2 abstention metrics with CIs on dev and frozen test | `results_{dev,test}/results.json` contain coverage, selective hit@3, always-answer hit@3 (all evaluable + paired on answered), train-prior hit@3, ordered-after-T proxy hit@3 and pathway top-1, each with point + patient-level bootstrap 95% CI and `n_patients`, `n_decision_points`; exact interval present whenever the bootstrap CI has zero width or is `unstable`; `split_coverage` complete; label "System Evaluation" present | `make care-eval SPLIT=dev`, `make care-eval SPLIT=test`; results files checked by the checker |
| S6-A11 | Harness additions are correct | `selective_hit_at_k` equals a hand computation on 3 toy sets (exact); abstained rows never enter the answered set. `exact_binomial_ci` matches `scipy.stats.binomtest(x,n).proportion_ci(method="exact")` within 1e-9 on ≥10 `(x,n)` incl. `x=0` and `x=n`. All existing `eval/tests` pass unchanged | pytest `eval/tests/test_s6_additions.py` |
| S6-A12 | Selective hit@3 (mock baseline) | Dev: selective hit@3 point ≥ 0.80 (predeclared, gating) with ≥ 30 answered evaluable decision points (else reported as underpowered and returned to planner). Test: reported with CI, flagged "overfitting risk" if < 0.70 (non-gating). System vs train-prior and vs always-answer reported with paired difference (non-gating) | `results_dev/results.json` threshold cell; `results_test` |
| S6-A13 | Missing information always explicit | 100% of assessments have a `missing_information` list (empty list allowed only when nothing optional is absent). Suggested dev cases without a resulted LabSeries list it. 0 cases where an absent/unknown input is rendered as negative or normal | pytest `test_missing_information_explicit`, `test_unknown_not_negative` |
| S6-A14 | Physician confirm/edit/reject audited | For each of confirm/edit/reject: exactly 1 `care.review.*` row with reviewer id+role, UTC ts, original suggestion (status, codes, missing list, alert ids, screening status), final codes or null, acknowledged ids, `reason_sha256`. Review without acknowledging every alert, or without `screening_acknowledged` when screening ≠ evaluated → 409, 0 review rows (3 actions × 2 conditions). Second review → 409 + `care.review.denied`. Sentinel transcript/reason text in 0 audit rows. `care_*` tables reject UPDATE/DELETE. `/confirmed` is 404 `pending_review` before review and after reject, and reflects only the newest assessment | pytest `test_care_review_audit[3]`, `test_review_requires_ack[6]`, `test_double_review_409`, `test_care_audit_no_raw_text`, `test_care_tables_append_only`, `test_confirmed_only_after_review` |
| S6-A15 | Role enforcement and split exposure | Physician 2xx; nurse and pharmacist 403; no session 401 on every care endpoint; every denial audited. `GET /cases` returns 0 test-split or train-split case ids | pytest `test_care_role_matrix`, `test_cases_dev_only` |
| S6-A16 | Claim boundary | 0 matches (case-insensitive) of `diagnos`, `prescrib`, `treat`, `dose`, `dosage`, `วินิจฉัย`, `สั่งยา`, `ให้ยา`, `รักษา` in: every API response for all dev+test assessments (T1, T2), string values in `backend/app/care/rules/*.json` and `data_factory/templates/{next_info_codes,care_pathways}.json` display fields, and `web/app/physician/care/**`. Citations are shown by ref id only. Research disclaimer shown | pytest `test_care_claim_scan`; s0 `test_repo_hygiene`; Vitest assertion |
| S6-A17 | Theme tokens only; urgency not colour-only | t1 `theme.test.ts` passes with the new files (0 hard-coded colours, no new tokens). Banner and alert text asserted present in the DOM (not only styled). Axe: 0 serious/critical on both care pages at 1280×800 and 768×1024. Keyboard-only confirm flow works | Vitest `theme.test.ts`, `care-review.test.tsx`; Playwright `a11y.spec.ts` (care pages added), `care.spec.ts` |
| S6-A18 | Deterministic | Two assessments of the same snapshot are byte-identical excluding ids/timestamps; the dev predictions JSONL is byte-identical across two runs | pytest `test_care_deterministic`; checker `sha256sum` of two runs |
| S6-A19 | Physician page works end to end | On 8106/3106: physician1 logs in, opens a dev case with a vitals alert at T2, sees alerts + INCOMPLETE banner above suggestions, confirm disabled until acknowledgements, confirm succeeds and confirmed state shows. An abstained case shows the exact missing list, no suggestions, and supports edit/reject | Playwright `e2e/care.spec.ts`, `API_PORT=8106 WEB_PORT=3106` |
| S6-A20 | `make test` green | Exit 0, 0 failed, offline (sockets blocked); pytest + Vitest counts ≥ the pre-slice baseline plus the new tests | `make test` from a clean checkout |

## Required test cases

- `data_factory/tests/`: `test_inputs_unchanged_vs_v111`, `test_care_gold_sources`, `test_care_gold_temporal`, `test_audit_bans_care_gold_in_inputs`, `test_care_required_inputs_canonical`.
- `backend/tests/care/`:
  - `test_abstains_when_required_missing`, `test_each_required_input_individually`, `test_no_false_abstention`, `test_unknown_not_negative`, `test_missing_information_explicit`
  - `test_evidence_refs_time_valid`, `test_bad_refs_fail_safe[future|unknown|none]`, `test_snapshot_rejects_future_item`
  - `test_screening_carried[evaluated|partially_evaluated|not_evaluated|unavailable]`, `test_alerts_serialized_first`, `test_model_cannot_change_alerts`, `test_screening_unavailable_abstains`, `test_redflag_adapter_mapping` (A/C/V/P/U, nulls → not evaluable)
  - `test_care_via_gateway`, `test_care_fail_safe[error|rejected|invalid|timeout]`, `test_care_provider_isolation`, `test_projection_is_care_suggestion`
  - `test_care_reads_snapshots_only`, `test_care_no_data_factory_import`, `test_rules_hash_pinned_to_version`, `test_care_deterministic`
  - `test_care_review_audit[confirm|edit|reject]`, `test_review_requires_ack[...]`, `test_edit_requires_reason_and_valid_codes`, `test_double_review_409`, `test_care_audit_no_raw_text`, `test_care_tables_append_only`, `test_confirmed_only_after_review`, `test_care_role_matrix`, `test_cases_dev_only`, `test_care_claim_scan`
- `eval/tests/test_s6_additions.py`: selective hit@k hand examples, abstain rows excluded, Clopper–Pearson vs scipy, zero-width trigger.
- Web: Vitest `care-review.test.tsx` (red-flag region first, banner text for 4 states, confirm disabled until acks, abstained view, no claim terms); Playwright `care.spec.ts` and extended `a11y.spec.ts`.

## Clinical risks

| Risk | Mitigation |
|---|---|
| A care suggestion is read while an urgent red flag is hidden or looks "cleared" | Alerts and screening are computed before and independently of the provider, serialised and rendered first, and cannot be changed by the model (A04, A05). Review is blocked until alerts and the INCOMPLETE banner are acknowledged (A14). |
| Symptom red flags are not evaluated on s1r cases in this slice | Status `partially_evaluated` with the INCOMPLETE banner and the list of rules not evaluated on every case. It is never shown as passed (A04). s3→s4 wiring is decision D2. |
| Suggestions made on incomplete data look authoritative | Hard abstention on required inputs with the exact missing list (A01). `unknown` is treated as missing (A13). The uncalibrated label is shown. |
| Leakage of future data or gold into suggestions | Snapshot-only input, a reject-on-future defence, the evidence-ref time check, the gold-removed byte-identity test, no data_factory import (A03, A09). |
| Circular evaluation: the same team writes the gold templates and the engine rules | The gold is committed first. The engine is independent of template ids. The engine is tuned on dev only. There is one frozen test run. The train-prior baseline is reported. Results are labelled System Evaluation (A09, A10, A12). hit@3 is lenient (any one hit), and the report says so. |
| Output reads as a diagnosis or treatment order | Closed vocabularies of information-gathering items and guideline-named pathways only. Claim-term scan (A16). "Suggestion for physician review" labelling. Nothing is care-facing before confirmation (A14). |
| Unverified or misapplied guideline citations | The builder verifies every source and the checker spot-checks 100% (A08). Templates without a verified source are marked `no_sourced_workup` rather than guessed. Expert review is D1. |

## Run commands

```bash
make test
make data && make audit                                   # v1.2.0 dataset + leakage/factory audit
python -m eval ledger init --ledger-dir slices/s6/eval/ledger   # once, before any freeze
make care-eval SPLIT=dev                                  # -> slices/s6/eval/results_dev/
python -m eval freeze slices/s6/eval/manifest_test.json --ledger-dir slices/s6/eval/ledger   # commit, then:
make care-eval SPLIT=test                                 # single run -> slices/s6/eval/results_test/
make dev API_PORT=8106 WEB_PORT=3106                      # http://127.0.0.1:3106/physician/care
API_PORT=8106 WEB_PORT=3106 make e2e
```

## Decisions required (non-blocking for the build, blocking for any clinical claim)

1. **D1:** A clinical expert reviews the next-info vocabulary, the pathway options, the required-input list and the per-template gold, plus the proposal 3.6 expert rating sample. Until then the labels are synthetic reference labels only.
2. **D2:** Wiring s3 symptom extraction into s4 red-flag facts for s1r snapshots (Case Graph wiring slice), so that text rules are evaluated.
3. **D3:** A joint Research/Innovation decision on extending `casegraph.data.CareSuggestion` (per-item evidence refs, missing list, status) as a versioned contract change.
4. **D4:** The slice-local ledger `slices/s6/eval/ledger/` versus the main ledger policy (appends on `main` only). The integration owner re-freezes and re-runs on `main`, or accepts the slice ledger.
5. **D5:** The s8 owner (สุปรียา) reviews the additive `eval/` changes (`selective_hit_at_k`, `exact_binomial_ci`).
