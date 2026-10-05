# Slice s2r — Case Graph core v1.1: red-flag `not_evaluated`

- Owner (Gantt): ภูริณัฐ / ธนาพล. This is a delta on `slices/s2/SPEC.md` at branch tip `edf8182`. Everything in S2 still applies unless this file changes it.
- Source of truth: `docs/PROPOSAL.md` (v8), sections 3.2.1 (Table 3.1: Red-flag inputs are `Findings, Vitals`, rules only, mandatory; Reasoning inputs include `Alerts`), 3.2.2 and 3.2.3.
- Trigger: an open HIGH blocker from clinical-safety-reviewer. When the Red-flag rule set cannot evaluate, it reports an all-clear.
- Status: PLAN. The planner wrote this. It is library-only: no UI and no HTTP routes.

## Defect evidence (reproduced by the planner on `edf8182` with the mock gateways)

| Input at T | `Alerts.status` | `missing_inputs` | Alerts | Checkpoint `escalation` |
|---|---|---|---|---|
| F3 (text only: Findings, no Vitals) | `evaluated` | `["Vitals"]` | `[]` | **false** |
| Text + Vitals with only `rr=30` (no rule's key present) | `evaluated` | `[]` | `[]` | **false** |
| Vitals `spo2=NaN, sbp=NaN` (accepted by `Vitals`) | n/a | n/a | `red_flag_rules` → `()` | n/a (silent) |

Root causes:
- `executor._red_flag` sets `evaluated` whenever Findings **or** Vitals exist. No placeholder rule reads Findings.
- `providers.red_flag_rules` does `continue` when a rule's vital key is absent.
- `Vitals.values` accepts non-finite floats, and every comparison against NaN is False.

S2-A18 passed only because its test covers the case where both inputs are absent.

## Scope

1. **Per-rule declarations** (`casegraph/providers.py`)
   - Each Red-flag rule declares `required_inputs`, for example `RF-PH-001 → ("Vitals.spo2",)`.
   - The rule-set version is bumped to `placeholder-redflag-0.2`. It stays labelled `PLACEHOLDER — not clinical`.
   - A rule is `evaluated` only if every one of its required inputs is present, finite, and inside the snapshot. Otherwise it is `not_evaluated` with the exact list of missing inputs.
   - Having Findings present never makes a rule evaluated unless that rule declares a Findings input. No placeholder rule declares one.
2. **`Alerts` v1.1** (`casegraph/data.py`)
   - `Alerts` gains `rule_results: tuple[RuleResult, ...]`. Each `RuleResult` has `rule_id`, `status ∈ {evaluated, not_evaluated}`, `missing_inputs`, `evaluated_on` (the evidence `item_id`s used) and `fired: bool | None`. `fired` is `None` whenever the rule is `not_evaluated`.
   - It also gains `rules_evaluated` and `rules_not_evaluated`, which are sorted rule id lists.
   - The overall `status` becomes one of `evaluated`, `partially_evaluated` or `not_evaluated`:
     - `evaluated` means every declared rule was evaluated.
     - `not_evaluated` means no rule was evaluated. This includes the case where the rule set is empty.
     - `partially_evaluated` covers everything else.
   - A model validator makes it **impossible to construct** `status="evaluated"` in any of these cases: `rule_results` is empty, any rule is `not_evaluated`, or `missing_inputs` is not empty.
   - `missing_inputs` is the sorted union over all rules, plus `Findings`/`Vitals` when that input type is absent or its producer errored.
3. **Finite values** (`casegraph/data.py`)
   - `Vitals.values` and `LabResult.value` reject NaN and ±inf with a typed validation error. The input is rejected; it is never read as a normal value.
   - The rule function also treats a non-finite value as missing, as defence in depth.
4. **Human Checkpoint payload** (`executor._checkpoint`)
   - A new top-level `red_flag_screening` block is always present, including when Red-flag errored. It holds:
     - `status ∈ {evaluated, partially_evaluated, not_evaluated, unavailable}`;
     - `performed: bool`, which is true only for `evaluated`;
     - `banner`;
     - `rules_evaluated`, `rules_not_evaluated` and `missing_inputs`.
   - The banner text is exact:
     - `RED-FLAG SCREENING NOT PERFORMED` for `not_evaluated` and `unavailable`;
     - `RED-FLAG SCREENING INCOMPLETE` for `partially_evaluated`;
     - `null` only for `evaluated`.
   - `escalation_reasons` accumulates. It is not an `elif` chain. A partial screen with an urgent alert therefore carries both `red_flag_partially_evaluated` and `urgent_red_flag`.
   - `escalation` is true for `not_evaluated`, `partially_evaluated` and `unavailable`.
5. **Downstream Reasoning** (`executor._reasoning`, `data.py`)
   - Reasoning may still run.
   - `CaseSummary`, `DepartmentSuggestion` and `CareSuggestion` each gain a **required** field `red_flag_screening`, which copies the upstream screening status (`unavailable` if Alerts is absent or errored). It has no default.
   - In the checkpoint payload, each `for_review` entry carries the same status, so a suggestion can never be shown as though screening passed.
   - Abstention behaviour from S2-A14 is unchanged.
6. **Export and inspect** (`casegraph/export.py`)
   - `SCHEMA_VERSION` becomes `casegraph-export/0.2`.
   - `ExportedGraph` gains a required graph-level `red_flag_screening` summary with the same fields as item 4. It has no default.
   - Importing a `0.1` export raises a typed version error. It never defaults to `evaluated`.
   - When the status is not `evaluated`, the **first** line after the graph header in `inspect` is `!! RED-FLAG SCREENING NOT PERFORMED missing=[...]` or `!! RED-FLAG SCREENING INCOMPLETE not_evaluated=[...] missing=[...]`.
   - The `red_flag` node line always shows `screening=<status>`.
   - The node-level `status=ok` keeps its S2 meaning: the body executed without error. It is never printed for `red_flag` without `screening=`.
7. **Other missing-as-negative paths** (sweep the planner found; the engineer must fix all of them and re-grep for more)
   - `_reasoning` does `output.get("care", [])`. A missing `care` key must become `schema_invalid`, not an empty care list. A missing `department` key must also become `schema_invalid`. An explicit `null` stays "no department proposed".
   - `pharma_rules` skips entries with no dose (`if d`), so a missing dose silently removes the dose-mismatch check. `MedicationIssues` gains `status ∈ {evaluated, partially_evaluated, not_evaluated}` and `checks_not_evaluated` (medication, check, missing), using the same construction invariant as `Alerts`.
   - The model-path Pharma currently emits `issues=()`. It must now emit `status=not_evaluated` for the structured rule checks.
   - `Vitals`/`LabResult` non-finite values are handled by Scope 3.
   - Any new finding goes into the sweep table in the PR and gets a test.
8. **Tests and version bump.** The S2 tests whose expected values change because of the rule-set or export version are updated in place, with a comment pointing to s2r. Their assertions must not be weakened or deleted.

## Out of scope

- The real clinical Red-flag rule set, thresholds, vital freshness windows and Findings-based rules. These need clinical review in a later slice.
- Real Pharma 3.2.4 logic, UI rendering of the banner (the web slice consumes the payload later), HTTP routes, and real models or data.
- Changing S2 node selection, provider policy, the cache-key recipe or replay semantics.
- The untracked `tests/e2e/s2/` directory in this worktree is not part of this slice and must not be modified. It is not in `testpaths`.

## Acceptance

All criteria are measured by pytest (sockets blocked) as part of `make test`.

| ID | Criterion | Threshold | How measured |
|---|---|---|---|
| S2R-A01 | All S2 acceptance items still pass | S2-A01…A24: 100% of the named S2 tests exist and pass. The only edits allowed are expected-value updates for rule-set/export version and the new fields. There are 0 deleted or skipped S2 tests: the count of S2 test functions is ≥ the count at `edf8182`. | `make test`, plus `git diff edf8182 -- casegraph/tests` reviewed. The S2 test-function count is compared by `pytest --collect-only -q`. |
| S2R-A02 | No vitals means `not_evaluated` with a missing list | F3 (text only) gives `Alerts.status == "not_evaluated"`, all 4 rules `not_evaluated`, `rules_evaluated == []`, `missing_inputs ⊇ {"Vitals"}` plus each rule's `Vitals.<key>`, `alerts == []`, and checkpoint `escalation is True` with `"red_flag_not_evaluated"` in its reasons. The same holds for CXR-only (no Findings, no Vitals) and for an errored Findings producer. | `test_red_flag_not_evaluated_without_vitals[text_only\|cxr_only\|findings_errored]` |
| S2R-A03 | Partial input gives per-rule status | With Vitals `{spo2: 97, hr: 80}` only: `rules_evaluated == [RF-PH-001, RF-PH-003]`, `rules_not_evaluated == [RF-PH-002, RF-PH-004]` with missing `Vitals.sbp` / `Vitals.temp_c` respectively, overall `partially_evaluated`, and `escalation is True` with `red_flag_partially_evaluated`. With `{spo2: 86, hr: 80}`, both `urgent_red_flag` and `red_flag_partially_evaluated` are present. With only `rr=30`, the result is `not_evaluated` (0/4 rules). | `test_red_flag_partial_per_rule[normal\|urgent\|no_rule_keys]` |
| S2R-A04 | Full input is the only way to `evaluated` | Exhaustive sweep over 2⁴ subsets of `{spo2, sbp, hr, temp_c}` × {Vitals item present/absent} × {Findings present/absent}, all with non-alarming values: `status == "evaluated"` ⇔ all 4 keys present. `escalation is False` occurs **only** when the status is `evaluated` with no urgent alert. There are 0 violating combinations. | `test_red_flag_status_truth_table` |
| S2R-A05 | Construction invariant | `Alerts(status="evaluated", …)` with empty `rule_results`, any `not_evaluated` rule, or a non-empty `missing_inputs` raises `ValidationError` (3/3). The same holds for `MedicationIssues` (3/3). | `test_alerts_cannot_claim_evaluated[empty\|rule_not_evaluated\|missing]`, `test_medication_issues_cannot_claim_evaluated[...]` |
| S2R-A06 | Human Checkpoint payload carries the flag | For `not_evaluated`, `partially_evaluated`, `unavailable` (Red-flag forced to error) and `evaluated` (F5), `payload["red_flag_screening"]` has the exact `status`, `performed`, `banner` string, rule lists and missing list. The block is present in 4/4 cases. `performed is True` only for `evaluated`. | `test_checkpoint_red_flag_screening_block[not_evaluated\|partial\|unavailable\|evaluated]` |
| S2R-A07 | Graph export and inspect carry the flag | The export has `schema_version == "casegraph-export/0.2"` and a graph-level `red_flag_screening` equal to the checkpoint block for all fixtures. export→import→export stays byte-identical. A `0.1` export, or a `0.2` export missing the field, fails import (2/2). `python -m casegraph inspect` on F3 exits 0, and its line 2 starts with `!! RED-FLAG SCREENING NOT PERFORMED`. The partial case prints `!! RED-FLAG SCREENING INCOMPLETE`. The `red_flag` line contains `screening=`. Replay of an s2r export reproduces the flag with 0 gateway calls. | `test_export_red_flag_screening`, `test_export_rejects_missing_screening[v0_1\|field_absent]`, `test_inspect_banner[not_evaluated\|partial]`, `test_replay_preserves_screening_flag` |
| S2R-A08 | Downstream Reasoning carries the flag | With `reasoning_required_inputs=("Findings<-ClinicalText",)` on F3, Reasoning is `ok`, its `CaseSummary`, `DepartmentSuggestion` and `CareSuggestion` each have `red_flag_screening == "not_evaluated"` (3/3), and each `for_review` entry carries it. On F5 the value is `evaluated`. Constructing any of the 3 types without the field raises `ValidationError`. | `test_reasoning_output_carries_screening_status`, `test_suggestion_requires_screening_field` |
| S2R-A09 | Static guard: no missing→all-clear path | An AST scan of `casegraph/` (tests excluded) passes all four checks. (a) Every `Alerts(`/`MedicationIssues(` call passes `status=` from the single aggregator `screening_status(rule_results)`, never a string literal. (b) The literal `"evaluated"` as a status value appears only inside that aggregator. (c) No `continue`, `.get(<key>, <default>)` or `in`-guard skip on vital or medication fields in rule bodies unless it records a `not_evaluated` result. (d) `escalation` is assigned only in `_checkpoint` as `bool(reasons)`. 0 violations. The test also **fails** when run against a fixture copy of the `edf8182` `_red_flag` body (mutation check). | `test_no_missing_input_maps_to_all_clear` (AST), `test_static_guard_catches_edf8182_pattern` |
| S2R-A10 | Non-finite values are never read as normal | `Vitals` with NaN, +inf or −inf in any key, and `LabResult` with non-finite `value`, raise `ValidationError` (3/3 per type). The rule function given a non-finite value via `model_construct` reports that rule as `not_evaluated`. | `test_non_finite_values_rejected[nan\|inf\|-inf]`, `test_rule_treats_non_finite_as_missing` |
| S2R-A11 | Other missing-as-negative paths closed | A Reasoning provider output without a `care` key → `status=error, reason=schema_invalid`, and likewise without a `department` key (2/2). An explicit `department: null` is accepted. The Pharma rules path with one entry missing a dose gives `checks_not_evaluated` containing that medication/`dose_mismatch` and status ≠ `evaluated`. The Pharma model path gives `status=not_evaluated`. | `test_reasoning_missing_keys_schema_invalid[care\|department]`, `test_pharma_missing_dose_not_evaluated`, `test_pharma_model_path_not_evaluated` |
| S2R-A12 | Placeholder labelling and version | `RULES_VERSIONS[RED_FLAG] == "placeholder-redflag-0.2"`. Every rule result and alert message is labelled `PLACEHOLDER — not clinical`. The cache key changes versus 0.1 for the same inputs. | `test_red_flag_rule_set_version_and_label` |
| S2R-A13 | Whole suite green, offline | `make test` exit 0: s0, S2 and s2r tests pass (0 failed/errors). Sockets are blocked. The casegraph suite runs in < 60 s on CPU. | `make test` in the worktree, output recorded in the PR |

## Required test cases

- `casegraph/tests/test_red_flag_screening.py` (new): A02–A06, A08, A10, A12.
- `casegraph/tests/test_export.py`: add A07.
- `casegraph/tests/test_static_guards.py` (new): A09.
- `casegraph/tests/test_executor.py`: add A11. Update the S2 A18 test for the new fields only. Its F5 case still asserts `evaluated` + `urgent_red_flag`.
  - F5 today has only `hr, sbp, spo2`, which would now correctly be `partially_evaluated`.
  - Add `temp_c=37.0` to F5 so that F5 is the full-input case, and note this in the fixture docstring.
  - This is the only fixture change allowed.
- `casegraph/tests/test_typed_data.py`: add A05 and A10.

Every named test in the acceptance table must exist and pass.

## Clinical risks

| Risk | Mitigation |
|---|---|
| Missing vitals are shown as "no red flags" (the blocker) | Per-rule status, an aggregator-only `evaluated`, and a construction invariant (A02–A05). A static guard with a mutation check stops regressions (A09). |
| A partial screen reads as complete | `partially_evaluated` plus a rule list, the `INCOMPLETE` banner and escalation (A03, A06, A07). |
| Suggestions look safe because screening "passed" | A required `red_flag_screening` field on every Reasoning output and on each `for_review` entry (A08). |
| NaN or corrupted sensor values silently compare as normal | Rejection at validation, and non-finite treated as missing in the rule (A10). |
| Absent fields in Reasoning or Pharma output become an empty list | `schema_invalid` and `not_evaluated` checks (A11). |
| Old exports without the flag are replayed as clear | Import fails for `0.1` and for exports missing the field (A07). |
| Escalating on `partially_evaluated` causes alert fatigue | This is accepted as the conservative default under the constitution ("missing required information → escalation"). Clinical-safety-reviewer must confirm it or propose a signed-off alternative. |
| Placeholder thresholds are mistaken for clinical rules | The version is bumped, the label is kept, and evaluation claims are prohibited (A12). |

## Run commands

```bash
cd /Users/king_phuripol/AI-Engineer/Workstreams/SeniorProject/Full-Agent-casegraph
make test                                                     # full suite (s0 + s2 + s2r), offline
.venv/bin/python -m pytest -q casegraph/tests                 # casegraph only (PYTHONPATH=.:backend via Makefile)
.venv/bin/python -m pytest -q casegraph/tests/test_red_flag_screening.py casegraph/tests/test_static_guards.py
.venv/bin/python -m pytest --collect-only -q casegraph/tests | tail -1   # S2R-A01 test count
.venv/bin/python -m casegraph inspect <graph.json>            # banner must appear on line 2 when not evaluated
```

## Decisions required

- **Clinical-safety-reviewer:** confirm that `partially_evaluated` escalates (the default here). Confirm the exact banner wording.
- **Clinical-safety-reviewer:** re-review this slice to close the HIGH blocker. The engineer who implements it must not review it.
- **None of these block implementation.** Bumping the export schema to `0.2` is internal to casegraph and has no external consumer yet (the backend and web do not import `Alerts`). Any later Model API Contract exposure must version it deliberately.
