# Slice cg-t123: staged Case Graph versions (T1 nurse → T2 physician → T3 pharmacist)

- Owner (Gantt): ภูริณัฐ (task 12 Case Graph Compiler/Executor). Replay/Regenerate touch points: ธนาพล (task 13).
- Branch: `factory/cg-t123`, base `24a491b`.
- Source of truth: `docs/PROPOSAL.md` v9.6:
  - §3.2.1 / Table 3.1: node types and providers. Red-flag and Human Checkpoint are mandatory. The checkpoint reviewer is a nurse, a physician or a pharmacist.
  - §3.2.2: every new data arrival produces a new graph version and keeps the old one. The compiler adds Reader:CXR when a CXR arrives and adds the Pharma Agent when new physician orders arrive. A node whose inputs are unchanged reads its stored output. Figure 3.2 shows T1, T2 and T3.
  - §3.2.3: Output Store cache key, replay, regenerate.
  - §3.2.4: Pharma Agent inputs are the new orders, the prior medication list and the medication/allergy data from the conversation.
  - §3.5 / Figure 3.4: the three stages by role.
- Status: PLAN. Tier 0 only: CPU, synthetic data, offline, mock gateway provider. No GPU, no external API, no real/MIMIC/hospital data.
- Claim boundary: this is a system-behaviour check on synthetic data, not clinical performance. Staging rules, fixtures and gold come from the same authors, so agreement is circular. It shows that the compiler follows its own declared rules and nothing more.

## Problem today

`casegraph/` compiles one graph with one Human Checkpoint, which defaults to `human:nurse`. Pharma Agent is selected whenever any `MedicationList` exists, including a home list at intake. That contradicts §3.2.2/§3.2.4: Pharma should run only on new orders. The graph's Pharma uses `placeholder-pharma-0.2`. Physician care (`backend/app/care`) and pharmacist reconciliation (`backend/app/pharma`) run outside the graph.

**Planner finding (safety, must fix): a false cache hit.** The Red-flag node (rf-1.1.0) computes vital freshness and age from `T` (`triage_bridge.build_case(..., freshness=...)`). The node cache key (`store.cache_key`, `executor._run_node` input_hash) does not include `T`. Today's regenerate uses the same `T`, so the gap stays hidden. Staged versions have different `T`. A later version would therefore be served a Red-flag output whose vitals were fresh at the earlier `T` but are stale now. That is exactly the C1 hazard (stale vitals read as an all-clear).

## Scope

1. **Stage planner** (new module, e.g. `casegraph/stages.py`). It is pure, deterministic and fixed-rule, with no model call: `plan_stages(items, t1, horizon) -> list[StagePlan(stage, T, trigger_item_ids)]`.
   - `RESULT_TYPES = {LabSeries, CXRImage, CTVolume, MRIVolume}`. `ORDER = MedicationList with list_source == "new_order"`. Only items with `t1 < available_at_time <= horizon` are triggers.
   - The first version is always `T1` at `T = t1`, where `t1` is the nurse assessment time: the T1 `as_of` of the assess call, or `snapshot_T1.as_of` for data_factory cases.
   - For each distinct trigger time `e` in ascending order:
     - emit `T2@e` if any result is available at `e`;
     - then emit `T3@e` if any order is available at `e`;
     - when both occur at the same `e`, emit T2 first, then T3.
   - Items available at or before `t1` (historical labs, prior-encounter orders) are in the T1 snapshot but never trigger a version. Non-trigger arrivals (new vitals, transcripts, ConfirmedEvidence) never create a version on their own. They enter the next version's snapshot.
   - T3 can follow T1 directly. T2 can follow T3. Natural synthetic v1 data gives T1→T3→T2, because orders arrive at about t1+32 min and labs at about t1+60 min.
2. **Staged compile**, `compile_stage(snapshot, stage, config, version, parent_version)`. It builds on `build_draft`/`validate`; the validators are unchanged.

   | Stage | Readers | Red-flag | Reasoning | Pharma | Human Checkpoint |
   |---|---|---|---|---|---|
   | T1 | every Reader whose evidence type is in the snapshot | yes | `params.task="department"` (current behaviour) | no, even when a home/patient-reported list exists | `human:nurse` |
   | T2 | same rule (adds Reader:CXR / CT-MRI; Reader:Vitals/Labs re-reads with labs) | yes | `params.task="care"`; required inputs add the output of the triggering result's Reader | no | `human:physician` |
   | T3 | same rule | yes | **none** (decision P-1) | yes | `human:pharmacist` |

   - Pharma evidence = every `MedicationList` (`home_list`, `patient_reported`, `new_order`) plus `AllergyList`. Add `AllergyList` to the Pharma `evidence_types`.
   - Pharma's only `Findings` edge comes from Reader:Text, which carries the conversation's allergy and medication facts. Findings from other Readers are not wired to Pharma.
   - The Human Checkpoint also reads `ConfirmedResult` evidence (ConfirmedEvidence available at or before `T`) and lists it as `prior_confirmed` in its pending payload. Rejected results never re-enter, because `resume` appends nothing on reject.
   - `GraphSpec` gains `stage: "T1"|"T2"|"T3"|null` and `trigger_refs`. The export schema bumps to `casegraph-export/0.4`. 0.3 exports still import read-only with `stage=null`. Any other version raises.
   - Legacy `compile_graph` (no stage) keeps its current behaviour for the existing tests. The backend no longer uses it.
3. **Time-correct cache key.**
   - Every node body that reads `T` includes `T`, or the T-derived values it uses, in its input hash. Red-flag rf-1.1.0 must do this. Red-flag therefore re-executes in every version at 0 gateway calls (it is a rules node).
   - The builder checks Reader:Text, Reasoning and Pharma for `T` dependence. For each one it either proves T-independence with a test or adds `T` to that node's key.
4. **Staged run.** `build_versions(executor, items, t1, horizon, config)`:
   - compiles and executes each planned version in order;
   - sets `parent_version` to the previous version;
   - uses one StateStore namespace per encounter (case_id);
   - leaves stored versions insert-only (as today).

   A version is built even when an earlier checkpoint is still pending. Each checkpoint is resumed only by its own role (`Executor.resume` role check, unchanged).
5. **Real S5 Pharma provider (should).**
   - Register `app.pharma.pipeline.reconcile` (`rules_plus_model`) on the Pharma hook under `s5-pipeline-2.6.0`.
   - The hook signature becomes versioned (v2) and receives the medication lists, the AllergyList, the Reader:Text allergy/medication facts, `T`, `data_class` and an audited `invoke`. The v1 placeholder signature stays supported.
   - An adapter maps `MedicationList`/`AllergyList`/facts to `MedSnapshot` (`as_of = T`) and maps S5 issues to `MedicationIssues`, keeping the S5 `issue_signature` fields, rule id and conflicting sources.
   - Every S5 extract/phrase call goes through the node's gateway and is counted.
   - The default `ProviderConfig` Pharma assignment becomes S5.
   - If this cannot be completed in this slice, keep the hook and the placeholder. Record the gap in this SPEC's "Follow-ups" as `CG-F1`. A7b is then reported `NOT_DONE`, which does not fail the slice.
6. **Backend exposure** (no UI).
   - `backend/app/triage/casegraph_run.py`: `run_graph` compiles via `compile_stage`. Its stage comes from triggers newer than the latest version's `T`; with no trigger it inherits the parent stage, or T1 when there is no parent. Triage cases have no results or orders, so they stay `T1`/nurse and current behaviour is unchanged.
   - Add `versions(stores, case_ref)` and `GET /api/triage/cases/{case_ref}/graph-versions`. Per version the response returns `graph_id`, `version`, `parent_version`, `stage`, `T`, `trigger_refs`, `checkpoint_role`, `checkpoint_status`, `escalation`, `alert_rule_ids`, node ids with `cached` / `gateway_calls`, and `totals`.
   - Readable by nurse, physician and pharmacist. Every read is audited. Unknown cases return 404.
   - The endpoint returns the data only. No new page or component.

## Out of scope

- Any UI (UI-DAG rendering is a later slice).
- Backend confirm/edit/reject endpoints for physician and pharmacist checkpoints. `Executor.resume` covers them in tests.
- Wiring `backend/app/care` as the T2 Reasoning provider (follow-up `CG-F2`).
- Drug–drug interaction checks.
- Real imaging encoders. Reader:CXR uses the existing `enc2d-mock-0.1` through the mock gateway.
- Cross-encounter version chains for revisit patients.
- Clinical validation of the staging rules (D1).
- Any change to data_factory output or splits.

## Decisions made by the planner (owner may overrule)

- **P-1: T3 has no Reasoning node.**
  - Figure 3.2 says T3 reuses "all T2 nodes". The validator (`unreviewed_output`) would force a carried Reasoning output to reach the pharmacist checkpoint, so the pharmacist would see an AI suggestion that the physician may have edited or rejected.
  - Instead, T3 reuses the T2/T1 Readers through the cache and re-runs Red-flag. The physician-confirmed or edited result reaches the pharmacist as `prior_confirmed` ConfirmedEvidence.
  - If the owner wants the literal figure instead, the alternative is to carry Reasoning into T3 as a context-only cache hit, shown separately from `for_review`.
- **P-2: Red-flag re-executes in every version** (time-dependent). This replaces "re-runs only with new labs" because freshness depends on `T`.

## Acceptance

Gold stage lists are re-derived independently in the checker from `available_at_time` only, using the rule in Scope 1. Expected counts below come from the generator at seed 20260926 before any compiler code exists. `SYN` = `make data` output (`data/synthetic/v1`, seed 20260926). `F-*` = hand fixtures listed under required tests.

| ID | Criterion | Threshold | How measured |
|---|---|---|---|
| A1 | Staging rule: the emitted (stage, T, trigger set) list equals the gold list | 100% of lists. SYN horizon=`snapshot_T1.as_of`: 200/200 `[T1]`. SYN horizon=`snapshot_T2.as_of`: 180 `[T1,T3,T2]` + 20 `[T1,T2]`. All F-* fixtures, including F-CXR `[T1,T2,T3]`, F-T3ONLY `[T1,T3]`, F-SAME `[T1,T2,T3]` with equal T, F-PRE `[T1]` | `test_stage_plan_synthetic_v1` over all 3 splits (400 lists); `test_stage_plan_fixtures`; the checker's independent gold script |
| A2 | Each version validates; exactly 1 Human Checkpoint whose provider is `human:nurse`/`human:physician`/`human:pharmacist` for T1/T2/T3; exactly 1 Red-flag with a direct `Alerts` edge to that checkpoint; Pharma present iff T3; Reasoning `task` matches the stage (T1 department, T2 care, T3 none) | 100% of versions built in A1 | `test_stage_structure` iterates every version: `validate()` passes; node/edge assertions |
| A3a | Cache reuse: in versions k≥2, every node whose cache key was produced in an earlier version is `cached=True` with `gateway_calls=0`. Reader:Text is a cache hit in every version k≥2 when its evidence is unchanged. Version gateway calls = sum over non-cached nodes = audited count | 100% of nodes; audited count equals the export `totals.gateway_calls` for 100% of versions | `test_stage_cache_reuse`: gateways wrapped in a counting `LocalGateway` audit sink; per-version count before/after |
| A3b | No false cache hit: for every `cached=True` node, re-executing the body with an empty OutputStore at the same version yields the same `output_sha256` | 100% of cached nodes in F-* and 40 dev SYN cases; plus F-STALE: Red-flag at T3 reports a vital `stale` that was fresh at T1 | `test_no_false_cache_hit`, `test_red_flag_freshness_across_versions` |
| A4 | Temporal: every version has all `evidence.available_at_time <= T` and all `prior_confirmed.available_at_time <= T`. F-FUTURE (an order or result after the horizon) creates no version. A forged spec or `compile_stage` with a future item raises `GraphValidationError(future_evidence)`. F-LATECONFIRM (a T1 confirmation after T2's `T`) is absent from T2 | 100%; adversarial cases 3/3 rejected | `test_stage_temporal`; `scripts/temporal_leakage_audit.py <version_journey.json> --as-of <T>` exits 0 for every F-* version; `--dataset data/synthetic/v1` exits 0 |
| A5 | Immutability and replay: after T1 is built and resumed, the T1 `GraphSpec` JSON, snapshot items JSON, run JSON and its OutputStore entries are byte-identical after T2 and T3 are built. Re-saving any version raises `GraphVersionExists`. `replay(graph_id)` of each version makes 0 calls and reproduces every node `output_sha256` | 100% of versions; 0 replay calls | `test_stage_immutability`, `test_stage_replay` |
| A6 | Red-flag alerts cannot be suppressed: with hostile Reasoning (T2) and hostile Pharma (T3) providers (empty or "no alerts" outputs, errors, schema-invalid), the checkpoint `alerts` equals the Red-flag node output and `escalation=True` for every urgent rule | 0 lost alerts across F-RED at T1/T2/T3 × 3 hostile providers | Extend `casegraph/tests/test_executor.py::test_red_flag_escalates_regardless_of_reasoning` into `test_red_flag_not_suppressed_by_stage[T1,T2,T3]` |
| A7a | T3 Pharma inputs: evidence_refs include the `new_order`, `home_list` and `patient_reported` lists and the AllergyList; there is exactly one Findings edge, from Reader:Text; MedicationIssues reach the pharmacist checkpoint `for_review`. F-T3ONLY with no AllergyList reports allergy as missing/not_evaluated, never "no allergy" | 100% of T3 versions | `test_t3_pharma_inputs`, `test_t3_missing_allergy_not_negative` |
| A7b | (if Scope 5 is done) With S5 wired, the graph Pharma issue signatures (`issue_signature`) equal a direct `app.pharma.pipeline.reconcile` on the same `MedSnapshot`. Secondary, reported only: agreement with the SYN gold `medication_issues` | 100% equality on the 36 dev SYN T3 cases + F-T3ONLY; secondary reported as a count with no threshold | `test_s5_parity`; otherwise reported `NOT_DONE` and `CG-F1` recorded |
| A8 | Regression and backend: `make test` green (`web/tests/live-call.test.tsx` F8 may pass on a single rerun only). Existing casegraph/backend tests pass, and any test edited for the intended Pharma-selection change is listed in the PR body. Triage assess still yields T1/nurse. `GET /graph-versions` returns the A1 stage list for a staged synthetic case, 403 for unauthenticated or other roles, 404 for unknown cases, and an audit row per read | All green; list matches 100% | `make test`; `backend/tests/triage/test_cg_t123_versions.py` |

## Required test cases (synthetic only)

- **F-CXR** (Figure 3.2): transcript + vitals at t1. Then a CXRImage at t1+40 → T2: Reader:CXR is added, Reasoning(care) runs, physician checkpoint. Then a `new_order` at t1+70 → T3: Pharma, pharmacist checkpoint. Reader:Text and Reader:Vitals are cache hits in T2 and T3. Reader:CXR is a cache hit in T3.
- **F-T3ONLY**: no results; `new_order` at t1+30; no AllergyList; the conversation states an allergy → `[T1,T3]`.
- **F-SAME**: a LabSeries and a `new_order` share one `available_at_time` → T2 then T3 at the same T.
- **F-PRE**: a historical LabSeries and a prior-encounter `new_order` both available before t1 → `[T1]` only; T1 has no Pharma.
- **F-FUTURE**: an order or result after the horizon; a forged spec carrying it; `compile_stage` given it.
- **F-LATECONFIRM**: the T1 nurse confirmation is stamped after T2's `T` → it is absent from T2 and present in T3 if T3's `T` is later.
- **F-RED**: urgent vitals (RF-NEWS-SINGLE3) at t1, plus hostile providers (A6).
- **F-STALE**: VS1 is the only vitals; the T3 time is beyond the 60-min window → Red-flag T3 shows `stale` and screening `partially_evaluated` or `not_evaluated`.
- **Role guard**: `resume` on the T2 version with `nurse` or `pharmacist` raises `ResumeError`. `resume` on T3 with `physician` raises.
- **SYN**: every case at both horizons (A1); 40 dev cases for A3/A3b/A7b.

## Clinical risks

| Risk | Mitigation in this slice |
|---|---|
| Stale vitals served from cache as "fresh" in a later version (found in planning) | Scope 3 time-correct key; A3b and F-STALE |
| Pharmacist shown an unconfirmed or rejected AI suggestion as context | P-1: T3 has no Reasoning; only confirmed/edited ConfirmedEvidence is shown |
| Urgent alert at a pending earlier checkpoint hidden by a newer version | Red-flag runs in every version (A2, A6); the version list exposes every version's `checkpoint_status`, `escalation` and `alert_rule_ids` |
| Missing allergy read as "no allergy" | A7a: missing is `not_evaluated` (data rule 6) |
| Wrong role confirms a stage | `Executor.resume` role check per version (role guard test) |
| Stage misfire from historical results or orders | Triggers only after t1 (F-PRE) |
| Overclaim | Claim boundary above; MOCK label kept on all mock outputs; no performance numbers |

## Run commands

```bash
cd /Users/king_phuripol/AI-Engineer/01_Projects/Senior-Project/Full-Agent/.claude/worktrees/cg-t123
make data                                   # data/synthetic/v1, seed 20260926 (Tier 0)
PYTHONPATH=backend:. .venv/bin/python -m pytest -q casegraph/tests backend/tests/triage -k "stage or cg_t123 or t3 or replay or executor"
python3 scripts/temporal_leakage_audit.py --dataset data/synthetic/v1
make test
```

## Follow-ups

- `CG-F2`: T2 Reasoning provider = `backend/app/care` engine.
- `CG-F3`: physician and pharmacist review endpoints, and the UI-DAG rendering of `/graph-versions`.
- `CG-F1`: S5 Pharma wiring. Fill in here only if Scope 5 is not completed.
