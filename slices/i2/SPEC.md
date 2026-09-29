# Slice i2: Case Graph wiring (Voice and Triage as graph nodes) and closing the carried HIGH conditions

- Owner (Gantt): ภูริณัฐ / ธนาพล
- Branch: `factory/i2`, base `28d14c4` (`factory/int` with s1r, s2r, s3, s4, s8r, s9r merged).
- Source of truth: `docs/PROPOSAL.md` v8:
  - 3.1: the Voice Agent is outside the graph; its transcript and extracted facts enter the graph as ClinicalText.
  - 3.2.1 / Table 3.1: node types. Red-flag and Human Checkpoint are mandatory nodes.
  - 3.2.2: snapshot at T; the graph is validated before it runs; Reasoning abstains when required data is missing.
  - 3.2.3: Output Store, replay, regenerate.
  - 3.5: nurse confirms the suggested department.
  - Table 3.2, rows "Case Graph" and "Replay and Regenerate".
- Status: PLAN (planner). Tier 0 only: CPU, synthetic data, offline, mock provider. No GPU, no external API, no real/MIMIC/hospital data.
- Claim boundary: all numbers are **"System Evaluation on synthetic data — not clinical performance"**. Rules, fixtures, extractor lexicon and gold share authors, so the results are circular. The comparison uses one deterministic mock model. It measures graph structure (typed extraction, mandatory red-flag screening, abstention, call count, time). It does not measure model reasoning.
- Research question (Table 3.2 "Case Graph"): with the same mock model, how does the Case Graph compare with one prompt over the whole snapshot? Metrics: department-suggestion accuracy, model calls and time.
  - Predeclared expectation: accuracy is equal on DPs where both arms answer. The Case Graph abstains on `NOT_EVALUABLE` DPs, and the single prompt answers them. The Case Graph makes more model calls.

## Scope

1. **One evidence type system.**
   - `casegraph.data` is the only evidence hierarchy. Every class derives from `data.Evidence`, and `data_class` stays required.
   - Move S1's concrete types into it:
     - `IntakeTranscript` (a ClinicalText family member);
     - `Demographics`;
     - `Vitals` with named, nullable, finite fields: `sbp`, `dbp`, `hr`, `rr`, `temp_c`, `spo2`, `consciousness`, `on_oxygen`, and optional `capillary_glucose_mg_dl`;
     - `LabSeries`, `MedicationList` (entries), `AllergyList`.
   - Retire `casegraph/evidence.py`. Retire the S2 dict-valued `Vitals` (update the placeholder rules to match).
   - S3 `IntakeEvidence` is replaced by unified types:
     - the transcript becomes `IntakeTranscript`;
     - session facts become a new ClinicalText-family type `VoiceIntakeFacts`.
   - Loader `casegraph.sources.s1r`:
     - reads only `inputs/<split>/<case>/snapshot_T*.json`;
     - sets `data_class` from `manifest.json`, never by default;
     - is lossless (every source field is kept).
   - Bump the export schema to `casegraph-export/0.3`. `0.2` still raises `ExportVersionError`.
2. **One mock task registry.**
   - Merge `app.gateway.adapters.mock.register_task` / `register_mock_task` and `app.gateway.mock_tasks` into one registry: `register(task, fn, *, version)`.
   - Re-registering a task with a different handler raises.
   - MOCK label rule: every mock output carries `label: "MOCK — not clinical"`, and `model_version` is `mock-0.1.0+<version>`.
   - S3 `voice.intake_extract` and S4 `triage.department.v1` register there, and so do the new tasks below. S4's strict output parser must accept the label.
3. **Reader:Text provider = S3 voice extraction.**
   - Input: `IntakeTranscript`.
   - Behaviour: runs S3 extraction (chief complaint, duration, allergy) plus a new symptom extractor (`backend/app/voice/symptoms.py`, mock task `voice.symptom_extract.v1`) over the patient turns.
   - Output: `Findings` with typed `facts`. Each fact has `name`, `state` (present | absent | unknown), `onset` (sudden | gradual | unknown), `duration`, and `evidence_turns` with every cited turn's `spoken_at <= T`.
   - The fact names are exactly the S4 `symptom.*` names used by rf-1.1.0: `acute_chest_pain`, `sudden_facial_droop`, `sudden_limb_weakness`, `sudden_speech_disturbance`, `sudden_vision_disturbance`, `thunderclap_headache`, `allergen_exposure`, `airway_breathing_compromise`, plus any other rf-1.1.0 symptom the lexicon covers.
   - An onset-qualified fact is `present` only when a concept term and a sudden-onset term occur in the same patient turn.
   - A symptom the patient never mentions yields **no fact (unknown), never `absent`**. `absent` requires an explicit denial in a patient turn, and that turn is cited.
   - Every lexicon term has a `source_ref` (rule citation). The lexicon is written from rule definitions and tuned on the **train** split only. It must not import `data_factory`.
   - `VoiceIntakeFacts` (S4 author fixtures, live S3 sessions with no transcript) passes through with 0 calls. When a transcript is present, it is always the source.
4. **Red-flag node provider = S4 engine rf-1.1.0**, replacing `placeholder-redflag-0.2` in the default `ProviderConfig`.
   - An adapter builds the S4 `Case` from snapshot Demographics, Vitals and Reader:Text Findings, following e1 mapping v1 for vitals and demographics:
     - consciousness `C` becomes `avpu=A` plus `new_confusion=true`;
     - `null` becomes no fact;
     - `on_oxygen` is UNMAPPABLE and is listed.
   - **Freshness.** Per-vital windows live in `casegraph/config/vital_freshness_v1.json`, labelled "PROPOSED — pending clinical sign-off (D1)". Proposed values:

     | Vital | Window | Basis |
     |---|---|---|
     | hr, rr, sbp, dbp, spo2, temp_c, avpu/new_confusion | 60 min | RCP NEWS2 (2017) Chart 4: a medium score or a single parameter scoring 3 requires minimum 1-hourly monitoring, so an older reading cannot represent the current state of a patient near an urgent threshold |
     | capillary_glucose_mg_dl | 60 min | Same basis. Low confidence; flagged for D1 |

     - The age of a reading is `T - event_time`.
     - A reading with age greater than its window is stale. A stale reading contributes no fact. The rule that needs it is `not_evaluated`, with missing input `vital.<k>:stale(read_at=<event_time>, age_min=<n>)`.
   - **Screening block.** `RedFlagScreening` carries these fields:
     - `rule_set_version`;
     - `label`: the rules-file status, "provisional … pending clinical expert review";
     - `scope`: "rf-1.1.0: 16 declared rules over vitals within their freshness windows and symptoms mentioned in the intake transcript; an unmentioned symptom is unknown, not absent";
     - `n_declared`, `n_evaluated`, `n_not_evaluated` and `n_fired`;
     - per-vital `readings` (value, `read_at`, age, fresh/stale).
   - Screening is **never rendered as "no red flags"**. An evaluated screen with 0 alerts reads "0 of 16 declared rules fired", with the scope. A partial screen shows the INCOMPLETE banner.
   - The Alerts rule results must equal the declared rule set of `rule_set_version` exactly.
   - `import_graph` re-validates every Alerts output and checks `output_sha256 == sha256_json(output)` for every node.
5. **Reasoning node's DepartmentSuggestion = S4 `department.suggest`.**
   - The S4 structure is kept: status, top3, uncertainty, `missing_information`.
   - It abstains per S4 `REQUIRED_FIELDS` with 0 gateway calls.
   - The S2 `department: str | None` type is retired. CaseSummary and CareSuggestion stay mock.
6. **S4 `as_of` bound and same-timestamp conflicts.**
   - The `/api/triage/cases/{ref}/assess` endpoint (the only place the bound applies) rejects a request with 422, and audits the rejection, when either:
     - `as_of > latest available_at_time + AS_OF_SKEW`; the proposed default is 5 min, configurable (D-I2-2);
     - `as_of < earliest available_at_time` (the floor).
   - When facts of one kind share the latest `available_at_time` and have different values:
     - Kinds with a direction resolve to the worst value:
       - spo2 and glucose: min;
       - avpu: U>P>V>A;
       - new_confusion: true;
       - symptom: present>unknown>absent;
       - pregnancy: positive>unknown>negative.
     - For hr, rr, sbp, dbp and temp_c, every tied value is evaluated, and a leaf is true if any tied value hits.
     - For any other kind (sex, age, chief complaint, onset), the conflict is flagged. The department suggestion then abstains with `conflict:<kind>`.
     - Every conflict is recorded in `conflicts[]` and shown at the checkpoint.
   - Across different timestamps, S4 latest-wins is unchanged and is reported (D-I2-3).
7. **Human Checkpoint = the existing nurse endpoints.**
   - `/assess` compiles and runs the Case Graph (Human Checkpoint provider `human:nurse`) and stores the link between the assessment and the graph.
   - `/assessments/{id}/confirm|edit|reject` are the only path that resumes the checkpoint:
     - alert acknowledgement is still required;
     - confirm and edit append `ConfirmedEvidence` at confirmation time;
     - reject appends nothing.
8. **Pharma node hook.**
   - The Pharma Agent provider is resolved through a named hook, which by default is the S2 placeholder `placeholder-pharma-0.2`, labelled PLACEHOLDER.
   - S1r `MedicationList` entries map to the placeholder's inputs.
   - A provider registered on the hook runs with no change to the executor. The S5 swap is a follow-up slice.
9. **Runs and the Table 3.2 comparison** (harness in top-level `eval_i2/`, accepted by the orchestrator on 2026-09-28 in place of `eval/adapters/i2/`; the E1 `eval/adapters` allowlist is unchanged).
   - **Arm A (Case Graph):** compile and execute every S1r case×T through the Executor, then replay.
   - **Arm B (single prompt):**
     - one gateway call per DP, task `casegraph.single_prompt.v1`, with the whole snapshot serialized;
     - its mock handler composes the **same registered handler versions** as Arm A (S3 extraction, symptom extraction, S4 baseline rank);
     - it has no graph-only steps: no Red-flag node, no required-input gate, no freshness check, no checkpoint.
   - **Gold** is E1-style. It uses e1 mapping v1:
     - departments go to the E-space (11 and 12 are excluded);
     - S1r rules map to S4 rules; RF-NEWS-AGG5 is UNMAPPABLE.
   - **Reuse and ledger.** If `eval/exact.py` and the e1 mapping exist on `factory/int` at build start, reuse them. Otherwise add them at the same paths with e1's definitions, and record that in the result. Ledger freeze and run follow the exception dated 2026-09-27 in `docs/DECISIONS.md` on `main`.
   - **Metrics per split:**
     - **Suggestion accuracy:** top-1 (primary) and top-3 over evaluable DPs with a mappable gold. An abstention counts as wrong.
     - **Coverage and selective top-1** over that population plus the `NOT_EVALUABLE` DPs.
     - **Model calls per DP:** mean, total, and per node.
     - **Wall time per DP:** median and p95. Measured in-process with arms alternated per DP. It reflects orchestration overhead, not model latency, and is stored in a separate `timing.json`.
     - **Paired differences:** patient-cluster bootstrap (2000 resamples, seed 20260926). Clopper-Pearson is used when degenerate (e1 rule).
     - **Red-flag recall per S1r rule, Arm A:** point, x/n, n_patients, Wilson and Clopper-Pearson.
     - **False alerts:** per S4 rule on gold-negative DPs and on text near-miss DPs.
     - A list of missed gold red flags, with the reason (e.g. `latest_wins`, `unmentioned`, `unmappable`).
     - Arm B produces no red-flag output by design. That row is `null` with the reason, and no comparison is claimed.
   - **Ordering and run limits:**
     - Iterate on train and dev only, never on test outputs.
     - Freeze `i2-cg-vs-sp-{dev,test}-v1`, then run final dev and test once each.
     - The test split is compiled and executed only inside the frozen run.
10. **Conditions bookkeeping.** Mark each row in the `slices/CONDITIONS.md` section "Must close in the Case Graph wiring slice" as closed, with its test names and commit. The TriageReview web view renders the screening block (scope item 4).

## Out of scope

- The S5 Pharma Agent (hook only), CT/MRI/CXR readers, and the real 27B model or any external provider. The provider-swap row of Table 3.2 is also out of scope.
- Clinical validation of freshness windows, rules, lexicon or mapping (D1).
- Changing rf-1.1.0 thresholds or the department list.
- Latest-wins vs worst-in-window across timestamps: this is a clinical decision, and it is only reported here.
- CareSuggestion accuracy. The mock proposes no care items, and S1r has no care gold; this is listed as not evaluated.
- Any real, MIMIC or hospital data.

## Acceptance

"DP" means one case×T. S1r at seed 20260926 has 240/80/80 DPs in train/dev/test, and 108/36/36 patients. "Text rules" means RF-CHEST, RF-STROKE, RF-THUNDER and RF-ANAPH.

| ID | Criterion | Threshold | How measured |
|---|---|---|---|
| I2-A01 | Every "Case Graph wiring" row of CONDITIONS.md is closed by a named, passing test | 6/6 rows closed, each with ≥1 passing test from the Required tests list. 0 rows open or waived without a DECISIONS entry. | `pytest` over the listed tests; checker reads CONDITIONS.md |
| I2-A02 | One evidence type system | `casegraph/evidence.py` is absent. 0 `EvidenceItem` subclasses outside `casegraph.data` (the S3 `IntakeEvidence` is removed). 100% of items in all 400 S1r snapshots validate as `casegraph.data` types with 0 errors. The S1r loader is lossless: every source field round-trips; only `data_class` is added, from the manifest. S3 `finish` output validates. | `test_one_evidence_type_system`, `test_s1r_snapshot_loads_lossless`, `test_s3_finish_evidence_loads` |
| I2-A03 | One mock registry and the MOCK label rule | Exactly 1 handler table; `register_task`/`register_mock_task` are removed. Re-registering with a different handler raises. 100% of outputs of every registered task carry the MOCK label and a versioned `model_version`. S3 and S4 tests pass unchanged in behaviour. | `test_single_mock_registry`, `test_mock_label_every_task`, the S3/S4 suites |
| I2-A04 | S1r compiles and executes | Train and dev before the freeze (320 DPs); test inside the frozen run (80 DPs). 100% compile. 0 `GraphValidationError`. 0 node `error` status. 100% have Red-flag and Human Checkpoint nodes. Reader:Text is present iff the snapshot has a transcript. The graph-shape histogram is reported. | `python -m casegraph run-s1r` summary; `test_s1r_compile_execute` (small generated dataset) |
| I2-A05 | Time validity inside the graph | 100% of evidence refs have `available_at_time <= T`. 100% of Findings facts cite turns with `spoken_at <= T`. A planted future item and a planted future turn are excluded (2/2). | `test_graph_time_valid`, `test_planted_future_excluded` |
| I2-A06 | Reader:Text emits symptom facts correctly | Unit transcripts (≥3 positive paraphrases per text rule, ≥2 of them without `ทันที`; ≥3 near-miss negatives per rule family; ≥2 explicit denials; ≥2 transcripts that mention no target symptom) give the expected facts in 100% of cases. Unmentioned symptoms yield 0 `absent` facts. 100% of lexicon terms have `source_ref`. 0 `data_factory` imports under `backend/` and `casegraph/`. | `test_symptom_extract_*`, `test_unmentioned_is_unknown`, `test_lexicon_sources`, import scan |
| I2-A07 | Text red flags are evaluable end to end, and red-flag recall is reported | On dev, each text rule fires on ≥1 gold-positive DP (4/4). Per-S1r-rule recall (7 rules, AGG5 `null`/unmappable) is reported on dev and frozen test, with x/n, n_patients, Wilson, Clopper-Pearson (the reported interval when degenerate) and bootstrap. Also reported: false alerts per S4 rule on gold-negative DPs and on text near-miss DPs, and the list of missed gold red flags with reasons. Predeclared outcome target, reported as PASS/FAIL and not gating: text-rule recall = 1.00 each, and 0 text-rule alerts on text near-miss DPs. | `i2_summary.json`; `test_i2_summary_complete` |
| I2-A08 | The Red-flag node runs rf-1.1.0 | 100% of Red-flag outputs have `rule_set_version=rf-1.1.0` and 16 rule results. The `RF-PH-*` rules are unreachable from the default config. Parity: on all S4 author fixtures (dev + holdout), the node's alerts and not-evaluable sets equal `redflags.evaluate` on the same `Case` (100%). | `test_red_flag_node_rf110`, `test_placeholder_rules_unreachable`, `test_red_flag_parity_s4_fixtures` |
| I2-A09 | Freshness windows (S2r HIGH) | Every S4 vital has a window, a source and the pending label. For each vital: a reading at age = window is evaluated, and one at window + 1 s is `not_evaluated` with `read_at` and age in the missing input. The checkpoint payload lists the read time and age of every vital (100%). | `test_vital_freshness_boundary[each vital]`, `test_freshness_config_cited`, `test_checkpoint_shows_reading_times` |
| I2-A10 | The screening block never overclaims (S2r HIGH) | 100% of exports have `rule_set_version`, `label`, `scope` and the counts. 0 matches of `/no red.?flags?\|all clear\|ไม่มี.*(สัญญาณอันตราย\|red flag)/i` in any inspect output, API response or web render over all dev graphs. Web (Vitest) covers 4 states: evaluated with 0 alerts, evaluated with alerts, partial, and unavailable. An evaluated screen with 0 alerts renders "0 of 16 declared rules fired". | `test_never_no_red_flags`, `TriageReview.screening.test.tsx` |
| I2-A11 | `as_of` is bounded (S4 HIGH) | latest + skew → 201. latest + skew + 1 s → 422 `as_of_beyond_evidence`. earliest → 201. earliest − 1 s → 422 `as_of_before_evidence`. 100% of rejections are audited. | `test_as_of_ceiling`, `test_as_of_floor`, `test_as_of_rejection_audited` |
| I2-A12 | Same-timestamp conflicts (S4 MEDIUM) | For every conflict class (min, ordinal, bidirectional any-hit, flag-and-abstain) the result is correct (100%). Results do not depend on fact order: all permutations give an identical output. `conflicts[]` is present and shown at the checkpoint. | `test_same_timestamp_worst[...]`, `test_conflict_order_invariant` |
| I2-A13 | Alerts invariant and import validation (S2r MEDIUM) | An Alerts output with a missing, extra or duplicate rule id is rejected (3/3). `import_graph` rejects a tampered node output, a tampered `output_sha256` and an invalid Alerts object (3/3). | `test_alerts_equals_declared_rules`, `test_import_revalidates` |
| I2-A14 | Reasoning DepartmentSuggestion is S4's | On S4 author fixtures, the Reasoning output equals `department.suggest` on the same Case (100%). An abstention makes 0 gateway calls and lists `missing_information`. | `test_reasoning_equals_s4_department`, `test_reasoning_abstain_no_call` |
| I2-A15 | The Human Checkpoint is the nurse endpoints | `/assess` runs the graph. After confirm or edit, the graph's checkpoint status matches the action, and `ConfirmedEvidence` is appended at `confirmed_at >= T`. Reject appends nothing. Unacknowledged alerts → 409. A non-nurse → 403. 0 other code paths call `Executor.resume` (grep test). The S4 review tests pass. | `test_checkpoint_via_triage_endpoints`, `test_single_resume_path`, S4 suite |
| I2-A16 | Pharma hook | By default the hook resolves to the S2 placeholder, with the PLACEHOLDER label. A test provider registered on the hook is used with 0 executor changes. It runs on 100% of S1r DPs that have a MedicationList, with 0 errors. | `test_pharma_hook_default`, `test_pharma_hook_swap` |
| I2-A17 | Replay and regenerate (Table 3.2) | Replay covers 100% of executed graphs (train, dev; test inside the frozen run): 0 gateway calls, 0 node executions, and identical `output_sha256` on every node. A no-cache rerun reproduces 100% of node output hashes. Regenerate after bumping the Reasoning `model_version` re-executes only Reasoning and the Human Checkpoint; the count is reported. | `test_replay_zero_calls`, `run-s1r --replay --no-cache` summary |
| I2-A18 | The Case Graph vs single-prompt table is frozen and complete | `i2-cg-vs-sp-{dev,test}-v1` are frozen; the freeze commit is a strict ancestor of the test-run commit. Exactly 1 run per test `evaluation_id`. `python -m eval ledger verify --git-history` exits 0. Dev and test each report: top-1, top-3, coverage, selective top-1, calls per DP, median and p95 time, and paired differences with CIs. Both arms use identical handler versions (manifest). On DPs where both arms answer, top-3 lists are identical in 100% of DPs. | ledger CLI; `git merge-base --is-ancestor`; `test_arms_matched`; `i2_summary.json` |
| I2-A19 | Labelling and claims | 100% of tables carry "System Evaluation on synthetic data — not clinical performance" and the circularity note. 0 claim terms ("diagnos", "clinically validated", "superior") outside the banners. | `test_i2_labels` |
| I2-A20 | Reproducible | Re-running dev and test against a tmp ledger copy gives identical sha256 for every result file except `timing.json`. | `test_i2_byte_reproducible` (small dataset); checker rerun |
| I2-A21 | Mock only, and the build is green | 0 non-mock providers in manifests and configs. `make test` exits 0 with 0 failures. `make data && make audit` exits 0 with both STEP lines PASS. Prior slice tests pass; any modified test is listed with its reason. | `make test`; `make data && make audit` |

## Required tests (all run by `make test`)

- **By condition:**
  - C1 (stale vitals): `test_vital_freshness_boundary[*]`, `test_freshness_config_cited`, `test_checkpoint_shows_reading_times`
  - C2 (performed overclaims): `test_red_flag_node_rf110`, `test_placeholder_rules_unreachable`, `test_never_no_red_flags`, `TriageReview.screening.test.tsx`
  - C3 (as_of): `test_as_of_ceiling`, `test_as_of_floor`, `test_as_of_rejection_audited`
  - C4 (same-timestamp): `test_same_timestamp_worst[min|ordinal|bidirectional|flag]`, `test_conflict_order_invariant`
  - C5 (Alerts/import): `test_alerts_equals_declared_rules`, `test_import_revalidates`
  - C6 (registry/types): `test_single_mock_registry`, `test_mock_label_every_task`, `test_one_evidence_type_system`, `test_s1r_snapshot_loads_lossless`, `test_s3_finish_evidence_loads`
- **Wiring:**
  - `test_s1r_compile_execute`
  - `test_graph_time_valid`
  - `test_planted_future_excluded`
  - `test_symptom_extract_*`
  - `test_unmentioned_is_unknown`
  - `test_lexicon_sources`
  - `test_red_flag_parity_s4_fixtures`
  - `test_reasoning_equals_s4_department`
  - `test_reasoning_abstain_no_call`
  - `test_checkpoint_via_triage_endpoints`
  - `test_single_resume_path`
  - `test_pharma_hook_default`
  - `test_pharma_hook_swap`
  - `test_replay_zero_calls`
- **Evaluation:**
  - `test_arms_matched`
  - `test_i2_summary_complete`
  - `test_i2_labels`
  - `test_i2_byte_reproducible`
  - amended `test_eval_isolation` / adapter allowlist (e1 carve-out)

## Clinical risks

- **False reassurance** from unmentioned symptoms read as absent. Mitigation: unknown by default; the scope text is on every screen. Consequence: nearly every screen is `partially_evaluated` (for example, RF-HYPOGLY has no glucose in S1r). Report the status distribution and flag banner fatigue for D1.
- **Freshness windows are not clinically validated.** A window that is too long passes stale normal vitals. The values are pending sign-off (D-I2-1).
- **Latest-wins** can hide an earlier abnormal reading in the same encounter. Misses caused by it are listed (`latest_wins`), and the clinical decision is D-I2-3.
- **An `as_of` ceiling that is too tight** blocks late assessment, and the nurse must re-measure. This is the safe direction.
- **Lexicon overfit and shared authorship** with the S1r templates can inflate recall. Mitigations: train-only tuning, the near-miss families, and an explicit circularity label. Negation is limited to explicit denials.
- **Tiny n:** about 2 patients and 4 DPs per text rule on dev. The intervals are wide, and no rule-level claim is made.
- **Mock comparison:** differences come from structure, not reasoning. Arm B's missing red-flag output must not be presented as a safety result.
- **Consciousness `C`** mapped to `new_confusion` follows the e1 convention and needs D1 confirmation.

## Run commands

```bash
make test
make data && make audit                      # S1r at seed 20260926 -> data/synthetic/v1
python -m casegraph run-s1r --dataset data/synthetic/v1 --splits train,dev            # A04/A05/A17
python -m casegraph run-s1r --dataset data/synthetic/v1 --splits train,dev --replay --no-cache
make eval-i2-dev                             # unfrozen dev iteration
python -m eval freeze eval/manifests/i2/i2-cg-vs-sp-{dev,test}-v1.json   # commit: eval(ledger): freeze i2-*
make eval-i2-dev && make eval-i2-test        # once each; commit: eval(ledger): run i2-*
python -m eval ledger verify --git-history
```

## Decisions required (human)

- **D-I2-1:** freshness window values (60 min proposed, RCP NEWS2 2017 Chart 4). Clinical sign-off (D1).
- **D-I2-2:** `AS_OF_SKEW` of 5 min and the evidence-based floor.
- **D-I2-3:** latest-wins vs worst-in-window across timestamps (reported only in this slice).
- **D-I2-4:** confirm the policy "unmentioned = unknown, only an explicit denial = absent".
- **D-I2-5:** export schema bump to `casegraph-export/0.3` (architecture contract), and ledger sequencing with e1: one appender at a time, so i2 merges `factory/int` before its freeze.
