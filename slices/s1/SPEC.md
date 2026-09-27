# Slice s1 — Synthetic case factory v1

- Owner (Gantt task 21 "สร้างชุดผู้ป่วยจำลอง บทสนทนาจำลอง และเกณฑ์การประเมิน"): สุปรียา
- Source of truth: `docs/PROPOSAL.md` (v8). Sections used: 1.3.1 (required intake fields: chief complaint, duration, allergy history; Red-flag Node uses predeclared rules; Pharma Agent issue types), 1.3.2 (synthetic Thai role-play scripts, not MIMIC), 1.3.4 (adults 18+, simulated environment, no real patients), 2.1.4 and 3.4 (patient-level split before examples; `available_at_time` on every item; leakage audit), 2.1.5 and 3.2.4 (medication reconciliation from home list, Voice Agent report, and new order; synthetic error injection), 3.2.1 Table 3.1 (typed data: ClinicalText, Vitals, LabSeries, MedicationList), 3.2.2 (snapshot at decision time T; abstain when required data is missing), 3.6 (gold labels come from data not sent to the model; Pharma Agent recall via injection; coverage/abstention metric).
- Status: PLAN. Written by the planner. This is Tier 0 work (CPU, synthetic, deterministic). It needs no GPU and no external API.
- Claim boundary: this is a synthetic reference set for **system evaluation**. The labels are generated from rules. They are not clinical ground truth, and they have not been reviewed by clinical experts (PROPOSAL 3.6).

## Scope

1. **`data_factory/` package**
   - Entry point: `python -m data_factory generate --seed N --out DIR` and `--splits-only`.
   - It uses only the stdlib and pydantic. Randomness comes from one `random.Random(seed)`, with a child RNG per patient derived from `(seed, patient_ref)`.
   - It makes no wall-clock, `hash()`, set-order, network, or LLM calls. Text comes from templates only.
2. **Roster, then split, then cases (in that order)**
   - 180 synthetic patients (`SYNP-0001…`): 160 have one encounter and 20 have two, for **200 cases** (`SYNE-…`).
   - Patients are split 108/36/36 (train/dev/test) by seeded shuffle, and `splits.json` is written **before** any case is generated. Revisit patients test the rule that a patient belongs to exactly one split.
   - Scenario strata (red flag, missing info, medication issue types) are assigned after the split, so that each split gets its quotas.
3. **Typed evidence (extend `casegraph`, additive only)**
   - New abstract `TimedEvidence(EvidenceItem)` adds `item_id`, `encounter_ref`, and `observed_at` (all required). A validator enforces `event_time ≤ observed_at ≤ available_at_time`.
   - Concrete types, all `extra="forbid"`:
     - `ClinicalText` → `IntakeTranscript` (`language="th"`, `turns[]` of `{turn_index, speaker: nurse|patient, text, spoken_at}`).
     - `Demographics` (`age_years` 18–95, `sex`; no DOB, no name).
     - `Vitals` (`sbp, dbp, hr, rr, temp_c, spo2, consciousness (ACVPU), on_oxygen`). Each value is nullable, and a missing value stays `null`, never 0.
     - `LabSeries` (`results[]` of `{test, value, unit, ref_low, ref_high, collected_at, resulted_at}`).
     - `MedicationList` (`list_source: home_list | patient_reported | new_order`, `entries[]` of `{generic_name, atc_code, dose_value, dose_unit, frequency, route}`, and `derived_from` item_id for `patient_reported`).
     - `AllergyList` (`status: known | no_known_allergy | unknown`, `entries[]` of `{substance, atc_class, reaction}`).
   - The factory validator also requires `provenance == "synthetic"`. S0 fields and tests remain unchanged.
4. **Per-case timeline**
   - Arrival.
   - Prior-record items (home list, prior allergies), available before arrival.
   - Triage `Vitals`.
   - Thai nurse–patient `IntakeTranscript`: ≥6 turns, strictly increasing timestamps.
   - `patient_reported` MedicationList, derived from the transcript.
   - **T1** = intake complete (department suggestion point).
   - Physician `new_order` MedicationList, labs, and repeat vitals.
   - **T2** = pharmacist and physician review point.
   - Optional late items with `available_at_time > T2` (late lab results). These exist so the leakage audit is not vacuous.
   - Every case has ≥2 decision times. The input field `intake_point` is always `"front_door"`: ED/OPD disposition is gold only.
5. **Gold labels (separate tree, never in inputs), per case and decision time:**
   - `target_department` (code from the fixed list below);
   - `red_flags[]` (`rule_id` plus the triggering item_ids);
   - `required_fields` (`chief_complaint {code, th_text}`, `duration {value, unit}`, `allergy_status`, each value or `MISSING`);
   - `medication_issues[]` (only at T ≥ time the new order is available);
   - `expected_action`: `escalate` if any red flag, else `abstain` if any required field is missing, else `suggest`. This follows the product invariant that red flags take priority.
   - `gold/injection_log.jsonl` has one record per injected medication issue: `injection_id, case_id, issue_type, drugs, item_ids, list_sources, field, value_before, value_after`.
6. **Medication discrepancy injection** (AHRQ MATCH [2]; ASHP [3]; PROPOSAL 3.2.4)
   - Issue types: `duplicate_therapy` (same ATC level 4 across/within lists), `dose_mismatch`, `frequency_mismatch`, `omission` (home drug absent from new order), and `allergy_conflict` (ordered drug in the class of a documented allergy).
   - `allergy_conflict` is injected only when the allergy is documented and available at or before T2.
   - Clean control cases get no injection.
7. **Fixed department list** `data_factory/templates/departments.json`
   - Source: SIL-TH `cs-chi-clinic` v0.1.2 (canonical `https://terms.sil-th.org/core/CodeSystem/cs-chi-clinic`, sourced from สกส. CSOP OPServices).
   - Codes used: 01 อายุรกรรม, 02 ศัลยกรรม, 03 สูติกรรม, 04 นรีเวชกรรม, 06 โสต ศอ นาสิก, 07 จักษุ, 08 ศัลยกรรมกระดูก, 09 จิตเวช, 11 ทันตกรรม, 12 ฉุกเฉิน.
   - Excluded: 05 กุมารเวชกรรม (adults only), 10 รังสีวิทยา (a diagnostic service, not an intake destination), and 99 อื่น ๆ (not a usable label).
   - Red-flag cases map to 12. Other cases use the complaint-template → department map, which is a synthetic rule pending expert review.
8. **Red-flag rules** `data_factory/templates/red_flags.json`
   - Each rule has `rule_id`, a machine-checkable criterion, `source_ref`, and threshold values copied from the cited source:
     - `RF-QSOFA`: ≥2 of RR ≥22, SBP ≤100, altered mentation. Seymour 2016 JAMA, PMID 26903335.
     - `RF-NEWS-SINGLE3`: any single NEWS parameter scoring 3. Smith 2013 Resuscitation, PMID 23295778.
     - `RF-FAST`: sudden face/arm/speech deficit. Harbison 2003 Stroke, PMID 12511753.
     - `RF-ACUTE-CHEST-PAIN`: acute chest pain. Gulati 2021 Circulation, PMID 34709879.
     - `RF-THUNDERCLAP`: headache peaking instantly. Perry 2013 JAMA, PMID 24065011.
     - `RF-ANAPHYLAXIS`: skin/mucosal involvement plus respiratory compromise or reduced BP. Sampson 2006 JACI, PMID 16461139.
9. **Reference registry** `data_factory/templates/references.json`
   - Every clinical template must carry a `source_ref` that resolves here, with a PMID, DOI, or URL.
   - Clinical templates are complaint scenarios, red-flag rules, vitals bands, formulary/ATC entries (WHOCC ATC index; TMT [22] where used), allergy classes, the department map, and issue types.
10. **Output layout** (`data/synthetic/` is gitignored; outputs are regenerated, not committed)

    ```
    DIR/manifest.json            seed, generator_version, source_code_sha256, counts, sha256 per file, tree_sha256 (no wall-clock)
    DIR/DATACARD.md              synthetic / not clinical / not expert-reviewed / label rules
    DIR/splits.json              patient_ref -> train|dev|test
    DIR/inputs/<split>/<case_id>/journey.json          all input items (full timeline)
    DIR/inputs/<split>/<case_id>/snapshot_<T>.json     items with available_at_time <= T
    DIR/gold/<split>/<case_id>.json                    labels per decision time
    DIR/gold/injection_log.jsonl
    ```

    Serialization: JSON with UTF-8 and `ensure_ascii=False`, `sort_keys`, fixed separators, and an LF newline. Thai text is NFC. Times are ISO-8601 with `+07:00`.
11. **`scripts/temporal_leakage_audit.py`** (rebuilt, stdlib + casegraph)
   - `--dataset DIR` checks:
     - every snapshot item has `available_at ≤ T`;
     - each snapshot equals `filter(journey, T)` exactly;
     - no patient appears in more than one split, and case dirs agree with `splits.json`;
     - every item's `patient_ref` equals its case patient;
     - gold decision times equal snapshot Ts;
     - there are no gold keys or files under `inputs/`.
   - The legacy mode `<journey.json> --as-of ISO` still works.
   - It writes a JSON report and exits 0 only on PASS.
12. **Makefile**
   - `make data` (`SEED ?= 20260926`, `OUT ?= data/synthetic/v1`).
   - `make audit` runs, over `OUT`:
     - the leakage audit;
     - schema validation;
     - the gold-separation check;
     - the identifier scan;
     - the manifest hash check.
   - `make test` includes `data_factory/tests` (add it to `testpaths`).

## Out of scope

- Audio/TTS/ASR and the Voice Agent itself.
- The Pharma Agent, the Red-flag Node, and the department model.
- The Case Graph Compiler/Executor (S2).
- UI.
- Images (CXR/CT/MRI).
- MIMIC, PhysioNet, hospital, or any real data.
- LLM-generated text or any external API.
- Drug–drug interactions.
- TMT/RxNorm code mapping beyond ATC.
- Clinical expert review, which is recorded as a pending decision below.
- Metric computation and bootstrap CIs, which belong to the evaluation slices.

## Acceptance

Default seed is 20260926. "Cases" = 200 encounters. "Case×T" = every (case, decision time) pair.

| ID | Criterion | Threshold | How measured |
|---|---|---|---|
| S1-A01 | `make data` is byte-identical for the same seed | Two runs into clean dirs under `PYTHONHASHSEED=0` and `=12345` give identical `tree_sha256` and identical per-file bytes. A different seed gives a different `tree_sha256`. 0 wall-clock values in outputs. | `test_determinism_same_seed`, `test_different_seed_differs` (subprocess, tmp dirs) |
| S1-A02 | Dataset size and split ratio | Exactly 200 cases and 180 patients (20 with 2 encounters). Patient split exactly 108/36/36. Case share per split is within 60±3 / 20±3 / 20±3 %. | `test_counts_and_split_ratio` on `manifest.json` + tree walk |
| S1-A03 | Zero patient overlap | 0 patient_refs in more than 1 split. 20/20 revisit patients have both cases in the same split. 100% of items have `patient_ref` == case patient. | leakage audit `--dataset`; `test_revisit_same_split` |
| S1-A04 | Split made before case generation | `splits.json` from `--splits-only` is byte-identical to the full run's. Changing a scenario quota in config leaves `splits.json` unchanged. | `test_split_precedes_generation` |
| S1-A05 | 100% schema-valid with timing and provenance | 100% of input items validate as a concrete casegraph type (`extra=forbid`). 100% have tz-aware `event_time, observed_at, available_at_time`, plus `source, version, item_id, encounter_ref`, and `provenance=="synthetic"`. 100% satisfy `event_time ≤ observed_at ≤ available_at_time`. | `test_all_items_schema_valid`; `make audit` schema step |
| S1-A06 | Adult cohort, no DOB | 100% have `age_years` in 18–95. 0 DOB or name fields in any schema. | `test_adults_only`, `test_no_identity_fields` |
| S1-A07 | ≥2 decision times with growing snapshots | 100% of cases have ≥2 strictly increasing Ts. Snapshot(T2) ⊋ Snapshot(T1). `new_order` is absent from T1 in 100% of cases. T1 ≥ transcript `available_at_time`. | `test_decision_times`, `test_new_order_not_at_T1` |
| S1-A08 | Leakage audit passes on every case and T | PASS on 100% of case×T pairs (≥400). Every snapshot item has `available_at ≤ T`. Each snapshot equals `filter(journey,T)` exactly. Exit 0. | `make audit` → `audit_report.json`; `test_leakage_audit_passes_generated` |
| S1-A09 | Leakage audit detects planted faults | 5/5 planted faults give FAIL with non-zero exit: future item in snapshot; patient in 2 splits; `patient_ref` mismatch; gold key in an input file; gold T ≠ snapshot T. Legacy `--as-of` mode flags a future item (1/1). | `test_audit_detects_planted[...]` (parametrized, tmp copies) |
| S1-A10 | Leakage test is non-vacuous | ≥20% of cases contain ≥1 item with `available_at_time > max(T)`. 100% of those items are excluded from every snapshot. | `test_future_items_exist_and_excluded` |
| S1-A11 | Gold labels are never in input files | Gold lives only under `gold/`. 0 occurrences of gold keys (`target_department, red_flags, rule_id, required_fields, medication_issues, expected_action, injection_id, issue_type`) in `inputs/`. 0 of the 10 department display names in `inputs/`. 0 input references to `gold/` paths. | `test_gold_separation`; `make audit` gold-separation step |
| S1-A12 | Red-flag subset | ≥20% of cases overall **and** ≥20% in each split (target 25%). Each of the 6 rules is used ≥5 times. 100% of gold red flags have a `rule_id` that resolves to a registry entry with a PMID. ≥5 cases where the red flag first appears at T2 and is absent from T1 gold. | `test_red_flag_subset`, `test_red_flag_evolves_at_T2` |
| S1-A13 | Red-flag labels match inputs | An independent reference rule oracle over each snapshot reproduces gold `red_flags` on 100% of case×T pairs (0 FP, 0 FN). ≥20 near-miss negative cases (a value within one step of a threshold) have 0 red flags. | `test_red_flag_oracle_agrees`, `test_near_miss_negatives` |
| S1-A14 | Department labels are from the fixed cited list | 100% of gold departments are among the 10 listed codes. Every code has ≥5 cases. 100% of red-flag cases are labelled 12. `departments.json` cites the `cs-chi-clinic` URL and version. | `test_department_labels` |
| S1-A15 | Required intake fields and missing-info cases | 100% of cases have gold for chief complaint, duration, and allergy status. ≥15% of cases (≥30) miss ≥1 field. Each field is missing in ≥8 cases. ≥5 cases are both red-flag and missing-info. For present fields, the gold surface form appears in the transcript (100%). For missing fields, the slot is absent from the transcript and from every structured input at that T (100%; allergy `unknown` ≠ `no_known_allergy`). | `test_required_fields_gold`, `test_missing_info_really_missing` |
| S1-A16 | Expected-action precedence | 100% of case×T gold rows follow the rule: `escalate` iff a red flag is present; else `abstain` iff a field is missing; else `suggest`. | `test_expected_action_precedence` |
| S1-A17 | Medications from three sources | ≥85% of cases have medication data. 100% of those have `home_list`, `patient_reported`, and `new_order` lists (a list may be empty but present). 100% of entries have `generic_name`, `atc_code` present in the formulary, dose value and unit, a frequency code, and a route. | `test_medication_sources` |
| S1-A18 | Every issue type injected ≥10 times and logged | Each of the 5 issue types has ≥10 injections overall and ≥2 in the test split. Injection-log records = gold issues (1:1 by `injection_id`). ≥30% of medication-bearing cases are clean controls with 0 injections. | `test_injection_counts`, `test_injection_log_one_to_one` |
| S1-A19 | No unlogged discrepancies | An independent discrepancy oracle over the T2 snapshot finds exactly the logged set in 100% of cases (precision = recall = 1.0). | `test_medication_oracle_agrees` |
| S1-A20 | Thai intake dialogue well-formed | 100% of transcripts have ≥6 turns, speakers in {nurse, patient}, a nurse first turn, strictly increasing `spoken_at` in [arrival, T1], NFC text, and ≥70% Thai-script letters per turn (excluding digits and drug names). ≥20 distinct complaint templates are used. | `test_transcripts_wellformed` |
| S1-A21 | No real-looking personal identifiers | 0 hits across `inputs/`, `gold/`, and `data_factory/templates/` for: 13-digit Thai ID (with or without dashes); Thai/+66 phone numbers; email; honorific+name (นาย, นาง, นางสาว, น.ส., ด.ช., ด.ญ.); address tokens (บ้านเลขที่, หมู่ที่, ซอย, ถนน, ตำบล, อำเภอ, จังหวัด, แขวง, เขต) and 5-digit postcodes; HN/AN numbers. Scanner self-test detects 100% of planted positives (≥1 per pattern class). | `make audit` identifier step; `test_identifier_scan_clean`, `test_identifier_scanner_self_test` |
| S1-A22 | No real data sources | During generation, a `sys.addaudithook` records 0 `open` events outside `data_factory/` and `OUT`, and 0 `socket.*` events. 0 matches for `mimic`, `physionet`, or hospital data paths in `data_factory/**/*.py`. | `test_generator_reads_only_templates`, `test_no_real_data_refs` |
| S1-A23 | Clinical templates carry a source reference | 100% of template records (complaints, red-flag rules, vitals bands, formulary, allergy classes, department map, issue types) have a `source_ref` that resolves in `references.json` with a PMID, DOI, or URL. 0 unresolved. | `test_templates_have_source_ref` |
| S1-A24 | casegraph extension is backward compatible | S0 `casegraph/tests/test_types.py` passes unmodified. New types subclass `EvidenceItem`. There are still no `compile`/`execute` symbols. A missing `observed_at` gives a `ValidationError`. | pytest `casegraph/tests` |
| S1-A25 | `make test` still green; generation is fast | `make test` exits 0 with 0 failures, including the new `data_factory/tests`. `make data` completes in ≤30 s on a laptop CPU. | `make test`; timed `make data` |
| S1-A26 | Manifest integrity and data card | `manifest.json` has seed, generator version, source hash, counts, and per-file sha256. `make audit` fails on 1/1 tampered-file test. `DATACARD.md` states "synthetic, not for clinical use, not expert-reviewed, system evaluation only". | `test_manifest_detects_tamper`, `test_datacard_present` |

## Required test cases (`data_factory/tests/`, run by `make test`)

- **Determinism and split:**
  - `test_determinism_same_seed`
  - `test_different_seed_differs`
  - `test_counts_and_split_ratio`
  - `test_revisit_same_split`
  - `test_split_precedes_generation`
- **Schema:**
  - `test_all_items_schema_valid`
  - `test_adults_only`
  - `test_no_identity_fields`
- **Time:**
  - `test_decision_times`
  - `test_new_order_not_at_T1`
  - `test_future_items_exist_and_excluded`
- **Audit:**
  - `test_leakage_audit_passes_generated`
  - `test_audit_detects_planted[future_item|cross_split|patient_mismatch|gold_in_input|T_mismatch]`
  - `test_audit_legacy_as_of_mode`
- **Gold:**
  - `test_gold_separation`
  - `test_red_flag_subset`
  - `test_red_flag_evolves_at_T2`
  - `test_red_flag_oracle_agrees`
  - `test_near_miss_negatives`
  - `test_department_labels`
  - `test_required_fields_gold`
  - `test_missing_info_really_missing`
  - `test_expected_action_precedence`
- **Medication:**
  - `test_medication_sources`
  - `test_injection_counts`
  - `test_injection_log_one_to_one`
  - `test_medication_oracle_agrees`
- **Text and safety:**
  - `test_transcripts_wellformed`
  - `test_identifier_scan_clean`
  - `test_identifier_scanner_self_test`
  - `test_generator_reads_only_templates`
  - `test_no_real_data_refs`
  - `test_templates_have_source_ref`
- **Integrity:**
  - `test_manifest_detects_tamper`
  - `test_datacard_present`
- **Types:** `casegraph/tests/test_types.py`, unchanged, plus `casegraph/tests/test_evidence_types.py` for the new types.

The oracles (red-flag, discrepancy) are test-side reference checkers written separately from the generator's injection code. They must not import the generator's label functions.

## Clinical and validity risks

| Risk | Mitigation in this slice |
|---|---|
| Synthetic rule labels are later cited as clinical accuracy | Data card and claim boundary say "system evaluation, not clinical" (A26). Department map and thresholds are flagged for expert review (decision D1). |
| Thresholds miscopied from sources | Each rule carries a PMID and verbatim threshold values (A12, A23). The oracle is independent of the generator (A13). Expert check is pending (D1). |
| Lexical shortcuts: labels guessable from template phrasing rather than content | Near-miss negatives share complaint templates with red-flag cases (A13). Department names are banned from inputs (A11). `intake_point` is constant. |
| Leakage via future items or split crossing inflates later metrics | Patient split before generation (A04). Snapshot = filter by `available_at_time` (A08). Planted-fault sensitivity (A09) and non-vacuity (A10). |
| Missing treated as negative (e.g., unknown allergy read as none) | Distinct `unknown` vs `no_known_allergy`. `null` vitals are never 0. Missing-info truly absent (A15). |
| Label noise from accidental, unlogged medication discrepancies | Oracle equality with the injection log (A19). |
| Red-flag case yields a non-escalating gold action | Precedence rule tested on 100% of rows (A16). |
| Realistic-looking identifiers are mistaken for real people | No names/DOB/addresses. Opaque `SYNP-/SYNE-` refs. Identifier scan with self-test (A21). |
| Accidental use of MIMIC or hospital data | Audit hook on file and socket access. Code scan (A22). |

## Run commands

```bash
make data                      # SEED=20260926 OUT=data/synthetic/v1 (override: make data SEED=7 OUT=/tmp/x)
make audit                     # leakage audit + schema + gold separation + identifier scan + manifest hashes over OUT
python3 scripts/temporal_leakage_audit.py --dataset data/synthetic/v1
python3 scripts/temporal_leakage_audit.py data/synthetic/v1/inputs/test/<case_id>/journey.json --as-of 2030-01-05T10:00:00+07:00
make test                      # all pytest (backend, casegraph, data_factory) + web unit tests
```

## Decisions needed (none blocking the build)

- **D1:** Clinical expert review of the complaint → department map, the red-flag thresholds, and the Thai dialogue templates (PROPOSAL 1.3.2, 3.6). Until it is recorded in `docs/DECISIONS.md`, all s1 labels are "synthetic reference labels".
- **D2:** Generated data stays gitignored. Only the code, templates, and seed are committed. Committing a golden `tree_sha256` is optional. It would pin cross-machine determinism but must be updated deliberately on any generator change.
