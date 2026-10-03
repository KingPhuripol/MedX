# Slice cg-m1: multi-version assess. Every built version's alerts escalate, and every graph_id is linked (closes CONDITIONS M1)

- Owner (Gantt): ภูริณัฐ (Case Graph / backend triage).
- Branch: `factory/cg-m1`, base `f9dd06e` (merge of cg-t123).
- Source of truth: `docs/PROPOSAL.md` v9.6.
  - §1.3.1: Red-flag and the Human Checkpoint are mandatory in every graph.
  - §3.2.2: each data arrival creates a new graph version, and old versions are kept.
  - §3.2.3: the Executor records state, and outputs are replayable.
  - §1.3.4: no patient routing without staff confirmation.
  - The CLAUDE.md invariants also apply here. Urgent red flags trigger escalation. A failure means abstain or escalate. Every recommendation records the evidence behind it.
- Condition closed: `slices/CONDITIONS.md` § cg-t123, row **M1** (MEDIUM, gate "before any backend source of results/orders (CG-F3)").
- Status: PLAN. Tier 0 only: CPU, synthetic data, offline, mock gateway provider. No external calls, no real or MIMIC data.
- Claim boundary: this checks system behaviour on synthetic data. It says nothing about clinical performance.

## Problem

One `POST /api/triage/cases/{ref}/assess` can build several Case Graph versions. `casegraph_run.run_graph` loops over `next_stages(...)`. When a parent version exists and new results or orders arrived after its `T`, the loop builds e.g. `[T2@e1, T3@as_of]`. The first assess of a case has no parent, so it always builds exactly one T1.

Today the loop keeps only the **last** graph, which causes three gaps:

1. **Lost alerts.** `router.assess` reads `graph_id`, the screening block and `graph_alerts` from the last graph only. Suppose SpO2 85 is fresh at an intermediate version's `T` (vital window 60 min, `vital_freshness_v1.json`) but stale at `as_of`. The urgent alert is then raised and stored in that intermediate version, but `escalation_required` and the `triage.assess` audit row never see it.
2. **Unlinked versions.** Every version except the last is linked to no assessment.
3. **Lost versions on failure.** Suppose version k fails (compile or execute) after versions 1..k-1 were built. The handler catches the exception and logs `graph_id: null` and `graph_alert_rule_ids: []`. The built versions and their alerts disappear from the record. The case still escalates, which is correct.

## Scope

1. **`run_graph` exposes every graph it built in the call** (`backend/app/triage/casegraph_run.py`, only `run_graph` plus any new private helper).
   - Recommended design: add a keyword-only out-parameter, `run_graph(..., *, built: list[ExportedGraph] | None = None) -> ExportedGraph`.
     - Each executed version is appended to `built` in build order, immediately after `executor.run_sync` returns.
     - The return value stays the last graph, which is the compatible accessor.
     - The exception from a failing version still propagates unchanged.
   - Why this design: it keeps both existing tests unmodified. `test_i2_checkpoint::test_assess_graph_failure_fails_safe` monkeypatches `casegraph_run.run_graph` with `boom(*args, **kwargs)`, and `test_cg_t123_round5` uses the return value as the last graph.
   - An alternative design (e.g. a result object) is allowed only if M1d still holds with those two tests unmodified.
   - The failed version (spec possibly saved by `Executor.run`, no run recorded) is **not** in `built`. It is described by the error record (scope 3).
2. **Assess handler takes the union across every built version** (`backend/app/triage/router.py`, the `assess` function only).
   - `graph_alert_rule_ids` = sorted union of `rule_id`s from `casegraph_run.graph_alerts(g)` over every `g` in `built`.
   - `escalation_required` = engine `escalation_required` OR any built version raised ≥1 alert OR a graph failure occurred. A graph failure means the exception path, as today.
   - `graph_id` and `screening` stay the **last** built version's. This keeps the single-version behaviour and the review/checkpoint path (`_review` resumes `a.graph_id`).
   - On a failure, `graph_id` is `None` and `screening` is `unavailable_screening()`, exactly as today. No earlier version's checkpoint becomes the reviewable one.
3. **Structured per-version record (additive).**
   - `TriageAssessment` (`models.py`) gains `built_graphs: list[BuiltGraphRef] = []`. Default empty, so stored payloads without the field still validate.
   - `BuiltGraphRef` is a new `_Strict` model with these fields:
     - `graph_id`
     - `version`
     - `stage` (`"T1"|"T2"|"T3"|null`)
     - `T` (aware datetime)
     - `screening_status`
     - `alert_rule_ids` (sorted)
     - `escalation` (bool: `alert_rule_ids` non-empty)
   - It also gains `graph_alert_rule_ids: list[str] = []`, the union.
   - It may also gain `graph_failure: GraphFailure | None = None`, holding `{error_type, stage, version}` where they are known (a compile failure may have no version).
   - The `triage.assess` audit row adds:
     - `built_graphs`, the same list in the same order;
     - `graph_failure`.
   - The row keeps every existing key:
     - `graph_id` is still the last version's, or `null` on failure;
     - `graph_error` stays an `error_type` string;
     - `graph_alert_rule_ids` is now the union. With a single version it equals the old value.
     - `screening_status`.
   - Through `built_graphs[*].escalation` / `alert_rule_ids`, the response always shows that an earlier version in the same call escalated, even though the `screening` block is the latest version's.
4. **Fail-safe on a mid-loop failure.** The audit row still lists every version built before the failure, with each one's alerts. `graph_alert_rule_ids` is their union, not `[]`. `escalation_required` is True. `screening.status` is `unavailable`.
5. **Tests**: `backend/tests/triage/test_cg_m1_multiversion.py` (new). There is one allowed, listed edit to an existing test (see M1d).
6. **CONDITIONS.md**: mark M1 `CLOSED (cg-m1)` and cite the test names.

## Out of scope (scope fence)

- `casegraph_run.versions()`, `router.graph_versions()`, and anything only the graph-versions endpoint uses. The parallel slice **ui-dag** owns these (M1e).
- Web rendering of `built_graphs`. This is a follow-up for ui-dag/web. The existing `escalation_required` banner already shows the escalation. The field is additive, and `web/lib/triage.ts` types are not strict.
- `casegraph/` compiler, staged planner, executor, cache keys, red-flag rules or freshness windows. They are not changed.
- Which checkpoint a nurse resumes when the last version is T2/T3 (`human:physician`/`human:pharmacist` → `checkpoint_role_mismatch`). This is existing behaviour, and triage cases carry no results/orders today. Recorded as a risk.
- Requiring acknowledgement of graph-only alerts at review. `_review` checks engine `a.alerts` only, which is existing single-version behaviour. Recorded as a risk / follow-up.
- Escalating when a built version's Red-flag screening was `unavailable` but the graph ran. Today a single version with `screening_status != evaluated` does not force escalation. Changing that would alter M1d and is a separate safety decision, recorded below. `screening_status` is recorded per version so it stays visible.
- The parent pointer after a failed version, i.e. what the next call's parent is when a spec was saved but the run was not. Existing behaviour.

## Acceptance

| ID | Criterion | Threshold | How measured |
|---|---|---|---|
| M1a | **Union escalation.** In one assess that builds ≥2 versions, an urgent alert raised **only** in a non-last version sets `escalation_required=True`. Its rule id appears in the response `graph_alert_rule_ids`, in that version's `built_graphs[i].alert_rule_ids` with `escalation=true`, and in the audit row's `graph_alert_rule_ids`. The engine raised no alert and the last version raised none, so the graph union is the only cause. | 100% of patterns; **0 lost alerts** across all built versions over **≥5** multi-trigger patterns (P1–P5) | `test_cg_m1_multiversion.py::test_intermediate_alert_escalates[P1..P5]`. Oracle: for each pattern, load every built graph with `casegraph_run.load(graph_id)` and compute `⋃ graph_alerts`. Assert it equals the response and audit `graph_alert_rule_ids`, and that each version's set equals `built_graphs[i].alert_rule_ids`. The oracle does not use `versions()`. Also assert per pattern that `engine alerts == []` and that the last version's `alert_rule_ids == []` (or, for P5, a different rule id). |
| M1a-neg | **No over-escalation.** A multi-version assess where no version and no engine rule fires keeps `escalation_required=False`, with union `[]`. | 1 pattern (P0) | `::test_no_alert_any_version_does_not_escalate` |
| M1b | **Linkage.** The response `built_graphs` and the audit `built_graphs` list every graph built in the call, in build order, each with `graph_id`, `version`, `stage` and `T`. They equal the versions newly stored by that call, `latest_version` before → after. `graph_id` equals the last entry's `graph_id`. | 100% (all patterns P0–P5 plus single-version) | `::test_built_graphs_linked_in_order`. Compare against `stores.state.load_graph(graph_id_for(ref, v))` for each new v. |
| M1c | **Mid-loop failure.** The last version fails after ≥1 earlier version was built in the call. Test both a compile failure (`compile_stage` raises) and an execute failure (`Executor.run_sync` raises). The audit row lists the built versions' graph_ids and stages, `graph_alert_rule_ids` = their union, `graph_failure.error_type` is set, `graph_id` is null, `screening_status=="unavailable"` and `escalation_required` is True. The response shows the same. | 2/2 failure modes; built list non-empty and correct | `::test_last_version_failure_records_built_and_escalates[compile,execute]`. Inject by monkeypatching `casegraph_run.compile_stage` or the executor's `run_sync` to raise on the k-th call only. |
| M1c2 | A failure in a middle version (version 2 of a planned 3) records version 1 only. No later version is built, and the case escalates. | 1 case | `::test_middle_version_failure_stops_and_escalates` |
| M1d | **Single-version behaviour unchanged.** Every existing triage test passes. The **only** allowed edit to an existing test: in `test_department.py::test_assessment_deterministic`, `strip()` also excludes `built_graphs`, because it carries per-call graph_ids, just as `graph_id` is already excluded. `test_i2_checkpoint.py` and `test_cg_t123_round5.py` are unmodified. For a single-version assess, the audit row's pre-existing keys hold the same values as before. A `TriageAssessment` JSON stored without the new fields still loads. | 0 failures; ≤1 listed test edit | `pytest backend/tests/triage -q`. Check `git diff f9dd06e -- backend/tests` (only the strip edit plus the new file). Add `::test_single_version_audit_keys_unchanged` and `::test_legacy_payload_without_built_graphs_loads`. |
| M1e | **Scope fence.** No change to `casegraph_run.versions` or `router.graph_versions`, and nothing under `casegraph/`. | 0 changed lines in those functions/dir | `git diff f9dd06e -- casegraph/` is empty. Compare the two function bodies via `git diff` hunk headers, or AST-dump them, base vs head: they are identical. |
| M1f | `slices/CONDITIONS.md` M1 row is marked CLOSED and cites the test names. | present | `grep -n "M1" slices/CONDITIONS.md` |
| M1g | `make test` green. A known flaky web live-call (F8) is accepted only if it passes on rerun. | exit 0 | `make test`, logs in the checker report |

## Required test cases (synthetic, mock provider)

How to drive them: go through HTTP `POST /api/triage/cases/{ref}/assess`.

- Monkeypatch `app.triage.router.engine_cases` to return a `helpers.make_case(...)` whose S4 engine raises no alert. Give it a late fact (e.g. +130 min) so that `_check_as_of` accepts the later `as_of`.
- Monkeypatch `casegraph_run.evidence_from_case` to return injected Case Graph items (as `test_cg_t123_round5.py` does), anchored to the case's `T0`.
- First call at `T1 = T0` builds the parent T1. The second call, at `as_of`, builds the multi-version set under test. All alert numbers below concern the second call.
- Vitals freshness window is 60 min. "U@x" means an urgent SpO2 85 reading with event time T1+x, available at T1+x+1.

| Pattern | Triggers after T1 | as_of | Versions built (2nd call) | Expected alert-carrying version |
|---|---|---|---|---|
| P0 | lab@40, order@70; no urgent reading | +80 | T2@40, T3@80 | none |
| P1 | U@5; lab@40, order@70 | +80 | T2@40, T3@80 | T2 only (age 35 vs 75) |
| P2 | U@5; order@30, lab@40 | +80 | T3@30, T2@80 | T3 only (age 25 vs 75) |
| P3 | U@40; lab@20, order@50, lab@75 | +130 | T2@20, T3@50, T2@130 | middle T3 only (not yet available at 20, stale at 130) |
| P4 | U@5; lab+order same timestamp @40 | +110 | T2@40, T3@110 | T2 only (same-`e` pair) |
| P5 | U@5; lab@40; a second urgent rule in a reading available just before as_of; order@100 | +110 | T2@40, T3@110 | T2 = SpO2 rule, T3 = the other rule; union = both |

The builder may shift minutes. However, each pattern must keep its stated version sequence and alert placement, and each test must assert that sequence before checking the alert.

Other required tests:

- M1c ×2 (compile / execute failure on the last version, P1 timeline);
- M1c2;
- single-version audit keys unchanged;
- legacy payload loads;
- determinism. Two reruns of the same synthetic case give `built_graphs` equal except for `graph_id`/`version`, i.e. the same stages, statuses and rule ids.

## Clinical risks

- **R1 (addressed): a hidden intermediate urgent alert.** This is the core hazard. M1a requires the union to escalate, with 0 lost alerts.
- **R2: an urgent flag that disappears on screen.** The `screening` banner shows the latest version, which may read "0 of n fired" while an earlier version fired. Mitigation in this slice: `escalation_required=True` plus `built_graphs[*].escalation`. Rendering it in the web is a follow-up (ui-dag). Until then, a demo must not show the latest screening block alone as the case's red-flag status.
- **R3: graph-only alerts are not part of the acknowledgement gate** (`_review` checks engine alerts). This is existing behaviour, and multi-version widens it. Proposed follow-up condition **M1-F1** (needs a reviewer decision).
- **R4: screening `unavailable` inside a built version does not escalate.** This is existing single-version semantics. Decision required (safety reviewer): should any built version whose screening was NOT PERFORMED force escalation? Not changed here.
- **R5: role mismatch at review** when the last version is T2/T3. Unreachable today because triage cases have no results/orders. It must be resolved before CG-F3.
- All data is synthetic, Tier 0, mock provider, and nothing is sent externally. A nurse must still confirm before any routing (§1.3.4).

## Run commands

```bash
cd /Users/king_phuripol/AI-Engineer/01_Projects/Senior-Project/Full-Agent/.claude/worktrees/cg-m1
python3 -m pytest -q backend/tests/triage/test_cg_m1_multiversion.py
python3 -m pytest -q backend/tests/triage
git diff f9dd06e -- casegraph/                    # must be empty (M1e)
git diff f9dd06e -- backend/app/triage/casegraph_run.py backend/app/triage/router.py   # versions()/graph_versions() untouched
git diff f9dd06e --stat -- backend/tests          # new file + the one strip() edit only (M1d)
make test
```
