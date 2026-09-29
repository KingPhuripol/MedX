# Slice int2: Integration: port S6 care onto the I2 Case Graph type system

- Owner (Gantt): ธัญรดา / ภูริณัฐ.
- Branch: `factory/int2` in the worktree `Full-Agent-i2`. It forks from `factory/i2` at ff65677 (this spec, first revision), whose parent c15ac93 holds merge 1c59c7f (`factory/int`: S6r, E1r2 and the posthoc projection fix, merged into the I2 wiring) plus the orchestrator's snapshot port. Diff baselines below are 1c59c7f unless stated.
- Source of truth: `docs/PROPOSAL.md` v8:
  - 3.2.1 / Table 3.1: typed data. The Red-flag node is mandatory, and its screening block is a typed output.
  - 3.4: time-valid evidence, no leakage.
  - 3.6 / Table 3.2: the S6 care result is a System Evaluation, and it is frozen.
  - The claim boundary applies.
- Governing specs: `slices/i2/SPEC.md` (the screening block, the MOCK label rule, one registry, one type system) and `slices/s6/SPEC.md` + `slices/s6r/SPEC.md` (frozen care behaviour and evaluation).
  - Where they meet, the rule is: I2 decides representation, and S6 decides behaviour and results.
- Tier 0 only: CPU, synthetic data, offline, mock provider. E2E ports are **8122 / 3122**.
- Status: PLAN (planner), revision 3 (2026-09-28).
  - Revision 2 changed no criterion's meaning. It fixed the branch line and defined "clean checkout" for INT2-A01.
  - Revision 3 answers four checker findings:
    - Scope 2's "gateway request unchanged" was unmeasured and false. It is redefined as normalised request parity (INT2-A17), and the change is acknowledged (D-int2-3).
    - The physician `case_summary` regression (`HR 83.0/min`) is now a failure: the text must match d423d15 (INT2-A07, INT2-A18).
    - INT2-A10 had a false premise. It now states the 2 stale v1 readings that were measured.
    - INT2-A14 no longer names `make e2e` as its measure, because that command fails on a pre-existing voice failure.
  - No approval is recorded or implied here.
  - No ledger line may be appended.
  - No S6 evaluation is re-run.

## Problem

After the merge, S6 care still builds the pre-I2 `RedFlagScreening`, which has 6 fields. It also calls `RedFlagScreening.from_alerts(None, <list>)`. As a result, every care assessment raises, and `make test` has 48 failed and 21 errors (`backend/tests/care/*`, `test_mock_registry.py::test_mock_label_every_task` and `voice/test_symptoms.py::test_no_data_factory_imports_in_product_code`).

The physician care page also renders two pre-I2 strings that I2 bans:
- "No red-flag rule fired…", which matches the I2 overclaim regex;
- "Red-flag screening evaluated every rule."

## Scope

1. **Care produces the I2 screening block** (`backend/app/care/redflag_adapter.py`, `models.py`, `engine.py`).
   - `CareResult.red_flag_screening` carries every `casegraph.data.RedFlagScreening` field, serialised as lists, plus `summary` (`RedFlagScreening.summary()`). The fields are: status, performed, banner, rules_evaluated, rules_not_evaluated, missing_inputs, rule_set_version, label, scope, n_declared, n_evaluated, n_not_evaluated, n_fired, readings, conflicts.
   - Every block (including `unavailable` and the snapshot-error path) is built by constructing and validating a `casegraph.data.RedFlagScreening`.
   - The `from_alerts(None, …)` call passes the rule-set **version** (`rf-1.1.0`), never the rule-id list.
   - `rule_set_version` is `rf-1.1.0`, taken from the S4 rule file and checked to equal `casegraph.data.RF_110`. A mismatch is `unavailable`.
   - `label` = `RULE_SET_LABELS["rf-1.1.0"]`.
   - `scope` = a care-specific constant `CARE_SCREENING_SCOPE`. It must:
     - name `rf-1.1.0` and 16 declared rules;
     - say that screening uses the latest structured vitals and demographics only;
     - say that symptom rules are **not evaluated** in care, because care does not read the transcript for red flags (S6 D2);
     - say that an unmentioned symptom is unknown, not absent.
   - It must **not** equal the I2 transcript scope (`RULE_SET_SCOPES["rf-1.1.0"]`), because that scope would claim symptom screening that care does not do. It must contain no CLAIMS term (`diagnos|prescrib|treat|dose|…`).
   - `conflicts` = the S4 `Snapshot.conflicts` (I2 C4), serialised.
2. **Behaviour stays frozen.**
   - Care keeps its own S6 fact mapping (`to_facts`: consciousness `C` gives `new_confusion=true` only; `test_redflag_adapter_mapping` stays unchanged). It keeps calling `redflags.evaluate` directly.
   - Care does **not** switch to `casegraph.triage_bridge` and does not consume Reader:Text symptom facts. That is D2, left for a later slice.
   - **Result parity.** For every S1r v1 and held-out decision point, the whole `CareResult` equals d423d15 except two fields: `red_flag_screening` (now the I2 block) and `request_sha256`. This covers:
     - alerts, `escalation_required`, status, reason, abstention and `missing_information`;
     - next-information and pathway codes, and evidence refs;
     - `provider`, `model_version`, `contract_version`;
     - the physician-visible `case_summary` text (INT2-A07).
   - **Case summary is physician-visible behaviour, so S6 decides it.** The I2 `Vitals` type holds `sbp`, `dbp`, `hr`, `rr` and `spo2` as floats. After the snapshot port, 442/560 DPs rendered text such as `HR 83.0/min` where d423d15 rendered `HR 83/min`.
     - The builder fixes `engine.summary` (care code, not fenced) so the text matches d423d15 exactly on 560/560 DPs.
     - A non-integral value is shown as recorded, never rounded (INT2-A18).
   - **Gateway request: the representation follows I2, the content is frozen.** This replaces revision 2's "the gateway request is unchanged", which was false on 442/442 gateway-calling DPs. Care serialises items through the I2 types (the c15ac93 snapshot port, kept by Scope 6). Rebuilding the retired S2r wire shape inside care would bring back a second evidence representation, which I2 removed. The request therefore differs from d423d15 **only** by the representation deltas measured on 560 DPs:
     - (a) `sbp`, `dbp`, `hr`, `rr` and `spo2` are floats with the same numeric value;
     - (b) every item gains `data_class: "synthetic"`;
     - (c) every `Vitals` item gains `new_confusion: null` and `capillary_glucose_mg_dl: null`;
     - (d) every transcript turn gains `ended_at: null` and `turn_id: null`.
   - Everything else in the request must be equal: task, data class, `as_of`, item set and order, every value, the alert context, the limits, and the number of calls per DP (0 or 1). INT2-A17 measures this under the normalisation N defined below the table.
   - Consequence: `request_sha256` differs on the 442 calling DPs. No frozen artifact contains it; it is present only in the runtime API/audit record. This is acknowledged as D-int2-3.
3. **Vital readings and stale inputs in the care block** (I2 C1, applied without changing any alert).
   - `readings` lists every mapped vital:
     - `value`;
     - `read_at` = the item's `event_time`;
     - `age_min = T - event_time`;
     - `window_min` from `casegraph/config/vital_freshness_v1.json`, loaded through `casegraph.triage_bridge.load_freshness`;
     - `fresh` and `item_id`.
   - **Asymmetric, conservative rule:**
     - A **fired** rule stays evaluated and fired whatever the age of its inputs. Staleness never removes or downgrades an alert.
     - A rule that did **not** fire and needs a stale vital is moved to `rules_not_evaluated`. Its missing input is `triage_bridge.stale_input(...)`, i.e. `vital.<k>:stale(read_at=…, age_min=…)`.
     - Status and counts are recomputed from the moved lists.
   - The web text for a stale care reading must not say "not used". It states that a normal stale value is not counted as screened and that an abnormal value still alerts.
   - This rule is a proposed default (D-int2-1).
4. **One registry, MOCK label.**
   - `care.suggest.v1` stays registered only through `app.gateway.mock_tasks.register(..., version=CARE_RULES_VERSION)`.
   - The provider's output carries `label: "MOCK — not clinical"`. The engine accepts the label (`OUTPUT_KEYS`) and does not render it as a suggestion.
   - The care result's `model_version` is `mock-0.1.0+care-rules-1.1.0`.
   - No care-local handler table.
5. **No `data_factory` import under `backend/`.** The care test fixtures (`backend/tests/care/conftest.py`, `test_s6r.py::heldout_root`) generate their datasets with the factory CLI in a subprocess (`python -m data_factory generate --seed … --out … [--heldout]`), as `casegraph/tests/conftest.py` does. The generated trees are byte-identical to before (`tree_sha256`).
6. **data_class.**
   - Keep the orchestrator's snapshot port (c15ac93): an item that declares a class other than `synthetic` rejects the snapshot.
   - In addition, the care dataset root must have a `manifest.json` whose `data_class` is `synthetic`. It is read with `casegraph.sources.s1r.manifest_data_class`. Otherwise the care API returns 503 `dataset_not_synthetic`, and `evaluate` exits non-zero, having written 0 files.
7. **Physician care pages render the I2 block.**
   - `web/lib/care.ts` `Screening` = the I2 type (reuse `web/lib/triage.ts` `Screening`).
   - `CareReview.tsx` renders `ScreeningBlock` (the shared I2 component) inside `redflag-section`, above the suggestion.
   - The alert list, the alert and screening acknowledgement checkboxes, and their labels are unchanged.
   - Remove "No red-flag rule fired on the data recorded so far." and "Red-flag screening evaluated every rule." When there are no alerts, the page says "No alert raised" (or equivalent) and points to the screening block.
   - `ScreeningBlock` may gain an optional prop for the care stale-reading text. `TriageReview` output is unchanged.
8. **Evidence and frozen artifacts.** The S6 recompute-vs-frozen question is settled by **comparing the frozen artifacts**. No test is pinned to d423d15. Details:
   - (a) A new test recomputes dev-0002 and test-0002 predictions/comparators in memory, writes nothing, and compares their sha256 with the committed files.
   - (b) A parity fixture `backend/tests/care/fixtures/s6_urgency_d423d15.json`. It records, per DP (v1 400 plus held-out 160):
     - alerts (rule ids and evidence refs), `escalation_required`, status, reason, `missing_information`, and the old 6 screening fields, all verbatim;
     - `result_sha256`: the sha256 of the canonical JSON of `CareResult.model_dump(mode="json")` minus `red_flag_screening` and `request_sha256`, written with `sort_keys=True, separators=(",", ":"), ensure_ascii=False` and no numeric normalisation;
     - `n_gateway_calls`;
     - `request_sha256_normalised`: N applied to each gateway request (null when there is no call).
     - It is generated by a committed script (`scripts/int2_dump_s6_urgency.py`) run in a temporary `git worktree` at d423d15.
     - The generating commit sha and the command are recorded in the file header.
     - The new engine must match it exactly (the 6 old screening fields are compared by name).

## Out of scope

- Care consuming Reader:Text symptom facts, the triage bridge mapping, or I2 freshness *dropping* alerts (D2, D-int2-1).
- Any change to `casegraph/`, `backend/app/triage/`, `backend/app/voice/`, `eval/`, `data_factory/`, the S4 rule file, the care rules (`care-rules-1.1.0`), the gateway contract or the export schema (`casegraph-export/0.3`).
- Re-running, re-freezing, re-rendering or retiring any S6/S6r/E1/I2 evaluation. No ledger appends.
- New metrics or clinical claims. Expert review stays D1.

## Acceptance

"v1" is S1r at seed 20260926 (400 DPs). "Held-out" is seed 20260927 `--heldout` (160 DPs). The overclaim regex is I2's: `/no red.?flags?|all clear|ไม่มี.*(สัญญาณอันตราย|red flag)/i`.

| ID | Criterion | Threshold | How measured |
|---|---|---|---|
| INT2-A01 | Build green | `make test` exits 0 with **0 failed, 0 errors**. The pytest collected count is ≥ 1466 (the count at c15ac93). The Vitest test count is ≥ the count at c15ac93. There are 0 new `skip`/`xfail` markers vs 1c59c7f. | `make test` in the worktree **and** in a clean checkout (see note A01); `git diff 1c59c7f -- '*.py' '*.ts' '*.tsx' \| grep -E '^\+.*(skip\|xfail)'` is empty |
| INT2-A02 | Data audit | `make data && make audit` prints `STEP leakage: PASS` and `STEP factory: PASS` | checker |
| INT2-A03 | Ledgers intact | `python -m eval ledger verify --git-history` exits 0. `python -m eval ledger verify --ledger-dir slices/s6/eval/ledger` exits 0. The line counts of every `**/ledger/*.jsonl` equal those at 1c59c7f. | ledger CLI; `wc -l` at both commits |
| INT2-A04 | E1 posthoc unchanged | `python -m eval.posthoc.e1_findings --check` prints `CHECK OK` | checker |
| INT2-A05 | Frozen artifacts untouched | `git diff 1c59c7f -- slices/s6/eval slices/s6r/eval eval/ledger eval/results eval/manifests` is empty | checker `git diff --stat` |
| INT2-A06 | S6 frozen predictions reproduce | The in-memory recompute of dev-0002 on v1 and test-0002 on held-out gives sha256(predictions JSONL) and sha256(comparator JSONL) equal to the committed `slices/s6/eval/{predictions,comparator}_{dev,test}_0002.jsonl` (4/4). 0 files are written under `slices/` during the test. | pytest `backend/tests/care/test_int2.py::test_s6_frozen_predictions_reproduce[dev_0002\|test_0002]` |
| INT2-A07 | Result parity with S6 (behaviour frozen) | For 560/560 DPs (v1 plus held-out):<br>(i) these equal the d423d15 fixture verbatim: alert rule ids and evidence refs, `escalation_required`, status, reason, `missing_information`, and the old screening fields (status, performed, banner, rules_evaluated, rules_not_evaluated, missing_inputs);<br>(ii) `result_sha256` equals the fixture. It is computed over the whole `CareResult` minus `red_flag_screening` and `request_sha256`, so it includes the `case_summary` text and refs, next-information, pathways, provider, `model_version` and `contract_version`.<br>The fixture header names commit d423d15 and lists its fields. The generating script is committed. | pytest `test_int2.py::test_urgency_parity_d423d15`, `test_result_parity_d423d15`. The checker reruns the script with `--check` against a fresh checkout of d423d15 (byte-identical). The checker's own probe `tests/e2e/int2_full_parity.py`, diffed between the two commits, shows only `red_flag_screening`, `request_sha256` and the A17 deltas |
| INT2-A08 | Care emits the I2 block | On all 560 DPs, plus the unavailable path and the snapshot-error path, `red_flag_screening` (minus `summary`) validates as `casegraph.data.RedFlagScreening` (100%), and: `rule_set_version == "rf-1.1.0"`; `n_declared == 16`; `n_evaluated + n_not_evaluated == 16`; `n_fired == len(alerts)`; `label == RULE_SET_LABELS["rf-1.1.0"]`; `scope == CARE_SCREENING_SCOPE`; `summary == RedFlagScreening.summary()`. `CARE_SCREENING_SCOPE` contains `rf-1.1.0`, `not evaluated` and `unknown, not absent`, is not equal to `RULE_SET_SCOPES["rf-1.1.0"]`, and has 0 CLAIMS matches. | pytest `test_int2.py::test_care_block_is_i2_screening`, `test_care_scope_honest` |
| INT2-A09 | Never "no red flags" | 0 overclaim-regex matches in: every care API response (assess, GET assessment, list) for all v1 dev and test DPs; the rendered `CareReview` in the 4 screening states; `web/components/CareReview.tsx` source. Without supplied symptom facts, 0/400 v1 care screens have status `evaluated`. | pytest `test_int2.py::test_care_never_no_red_flags_api`, `test_care_never_evaluated_without_symptoms`; Vitest `care-review.screening.test.tsx` |
| INT2-A10 | Stale vitals in care (C1 without alert loss) | Planted fixtures, one per mapped vital: hr, rr, sbp, dbp, spo2, temp_c, and consciousness (reported as the care-fact readings `avpu` / `new_confusion`): (i) a normal reading at age = window is evaluated and `fresh=true`; (ii) a normal reading at window + 1 s puts every non-fired rule that needs it in `rules_not_evaluated`, with the exact `stale_input` string, `fresh=false`, and status not `evaluated`; (iii) an abnormal reading at window + 1 s still fires the same alert, `escalation_required=true`, and the rule is in `rules_evaluated`. Every block lists read time and age for 100% of mapped vitals.<br>**Measured on real synthetic data:** the set of stale readings is **exactly** 2 on v1 and 0 on held-out:<br>- `SYNE-0002` T2 (as_of 2030-06-23T11:36:12+07:00): `new_confusion`, read from `SYNE-0002-VS1` at age 108.2 min, window 60;<br>- `SYNE-0053` T2 (as_of 2030-06-28T12:45:45+07:00): `avpu`, read from `SYNE-0053-VS1` at age 108.75 min, window 60.<br>Each is an older consciousness fact that the latest Vitals item (VS2) does not restate. RF-CONSC fires from VS2 in both cases. On these 2 DPs, `fresh=false` is shown, no rule is moved to `rules_not_evaluated` compared with d423d15, and the output is identical to d423d15 (A07). | pytest `test_int2.py::test_care_stale_boundary[vital]`, `test_care_stale_abnormal_still_alerts[vital]`, `test_care_readings_listed` (asserts the exact stale list above) |
| INT2-A11 | One registry and the MOCK label | `care.suggest.v1` is in `mock_tasks.registered()` with version `care-rules-1.1.0`. `test_mock_label_every_task` passes with a real care sample input (label `MOCK — not clinical`, model_version `mock-0.1.0+care-rules-1.1.0`). The care `model_version` equals that on 100% of suggested v1 DPs. The label never appears as a next-information or pathway item. `test_single_mock_registry` is unchanged except that it requires `care.suggest.v1`. | pytest `backend/tests/test_mock_registry.py`, `test_int2.py::test_care_mock_label` |
| INT2-A12 | No `data_factory` import under `backend/` or `casegraph/` | `backend/tests/voice/test_symptoms.py::test_no_data_factory_imports_in_product_code` passes **unchanged**. Care fixtures produce `tree_sha256` equal to v1 `manifest.json` (seed 20260926) and to `manifest_test_0002.json` `dataset.version` (held-out). | pytest; `test_int2.py::test_fixture_trees_match_recorded` |
| INT2-A13 | Synthetic only | A dataset whose manifest has no `data_class`, or a non-`synthetic` one, gives: API 503 `dataset_not_synthetic`; `evaluate` non-zero with 0 files written; 0 gateway calls. A snapshot item that declares `data_class: "real"` gives status `error` with reason `snapshot_item_not_synthetic` and 0 calls. | pytest `test_int2.py::test_care_refuses_non_synthetic[manifest\|item]` |
| INT2-A14 | Physician pages render the I2 block | Vitest `care-review.screening.test.tsx` covers 4 states: evaluated with 0 alerts shows "0 of 16 declared rules fired" and the scope; evaluated with alerts; partial shows the INCOMPLETE banner with role=alert; unavailable shows NOT PERFORMED. The scope, `rf-1.1.0` and the not-evaluated rules are visible, and the red-flag region precedes the suggestion in the DOM. Playwright `care.spec.ts` (existing tests unchanged, plus 1 new test on SYNE-0011 T2 on 8122/3122) passes: `screening-scope` contains `rf-1.1.0`; the page text has 0 overclaim matches; `screening-readings` lists the vitals. `a11y.spec.ts` passes. `web/tests/TriageReview.screening.test.tsx` passes unchanged.<br>**All Playwright specs except `voice-intake.spec.ts` pass** on 8122/3122.<br>`voice-intake.spec.ts` is fenced (voice) and fails before this slice. int2 must not change its outcome: every test in it that fails on int2 must also fail, with the same error class, on a c15ac93 checkout (non-temp path, the same ports). A voice test that fails on int2 but passes at c15ac93 fails A14. `git diff 1c59c7f -- web/e2e/voice-intake.spec.ts web/components/voice backend/app/voice` is empty. | `cd web && npm test`; `cd web && WEB_PORT=3122 API_PORT=8122 npx playwright test e2e/care.spec.ts e2e/a11y.spec.ts e2e/triage.spec.ts e2e/roles.spec.ts e2e/disclaimer.spec.ts e2e/health.spec.ts e2e/theme.spec.ts` (0 failed); `npx playwright test e2e/voice-intake.spec.ts` on int2 and on c15ac93, compared by the checker. `make e2e` is **not** the measure |
| INT2-A15 | Test-edit discipline, no safety loosening | Every modified pre-existing test file is in "Sanctioned test edits" below, with its reason. `git diff 1c59c7f` is **empty** for: `casegraph/tests/`, `backend/tests/triage/`, `backend/tests/voice/`, `web/tests/TriageReview.screening.test.tsx`, `eval/tests/`, `data_factory/tests/`, `backend/tests/care/test_engine.py`, `test_api.py`, `test_static.py`, `test_evaluate.py`. 0 `assert` lines are removed from any listed file except the replacements named below. | checker `git diff 1c59c7f --stat -- '**/tests/**' web/tests web/e2e` and a line review |
| INT2-A16 | Scope fence | `git diff 1c59c7f` is empty for `casegraph/`, `backend/app/triage/`, `backend/app/voice/`, `backend/app/gateway/`, `eval/`, `data_factory/`, `backend/app/care/rules/`. The export schema stays `casegraph-export/0.3`. | checker `git diff --stat` |
| INT2-A17 | Gateway request parity (normalised; representation per I2) | For 560/560 DPs, `n_gateway_calls` equals the fixture (442 DPs with 1 call, 118 with 0). For the 442 calling DPs, N(request) sha256 equals the fixture's `request_sha256_normalised` (442/442).<br>Sensitivity controls: N must **not** hide real changes. Each of the following changes the hash:<br>(a) one vital value +1;<br>(b) `new_confusion: true` on a Vitals item;<br>(c) `data_class: "real"` on an item;<br>(d) an added key with a non-null value;<br>(e) swapping 2 items;<br>(f) dropping one alert-context entry. | pytest `test_int2.py::test_gateway_request_parity_d423d15`, `test_request_normalisation_is_sensitive[a..f]`; fixture regenerated by the committed script at d423d15 (A07 `--check`) |
| INT2-A18 | Case summary display | The `case_summary` text is identical to d423d15 on 560/560 DPs (inside A07-ii). A planted Vitals item with `hr=83.5` and `spo2=94.5` renders `HR 83.5/min` and `SpO2 94.5%`: no rounding and no loss of recorded precision. `temp_c=37.0` renders `37.0 °C`, as at d423d15. A null value renders `not recorded`. | pytest `test_int2.py::test_case_summary_format` |

**Normalisation N (INT2-A17).** Take `GatewayRequest.model_dump(mode="json")` and apply these steps, in order:
1. Delete the top-level `request_id`, `created_at` and `requested_at` if present.
2. For each `inputs.items[i]`:
   - delete `data_class` **only if** it equals `"synthetic"`;
   - if `data_type == "Vitals"`, delete `new_confusion` and `capillary_glucose_mg_dl` **only if** they are null;
   - for each `turns[j]`, delete `ended_at` and `turn_id` **only if** they are null.
3. Replace every float with an integral value by the equal int. This is applied to both commits.
4. sha256 of `json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False)`.

N lives in `scripts/int2_dump_s6_urgency.py` and is shared with `test_int2.py`, as `row_of` is. Nothing else is removed or coerced. Any new key, any non-null value for these keys, and any changed value, order or count fails.

**Note A01 (clean checkout).** A clean checkout is `git clone --branch factory/int2 <worktree> <dir>`, where `<dir>` is **not** under `tempfile.gettempdir()` or `/tmp`. The S1r out-path guard (`data_factory/__main__.py`) deliberately allows the temp roots as scratch output. So, in a clone under a temp dir, 5 pre-existing `data_factory/tests/test_factory.py` guard tests fail by design: `test_out_path_guard[parent|absolute|symlink|repo_root]` and `test_make_data_rejects_out_of_tree`. `data_factory/` is fenced (A16), and this is not an int2 regression. A clone at such a path does not count as evidence for or against A01. It must be re-run at a non-temp path, for example next to the worktree.

## Sanctioned test edits (exhaustive; the builder lists each one in its result)

1. `backend/tests/care/conftest.py`: dataset generated through the factory CLI subprocess instead of `from data_factory.generate import generate`. Reason: I2-A06 bans `data_factory` imports under `backend/`. Same seed and same tree (A12).
2. `backend/tests/care/test_s6r.py::heldout_root`: the same change, with `--heldout`. No other line of the file changes.
3. `backend/tests/test_mock_registry.py`:
   - add a `care.suggest.v1` entry to `SAMPLE_INPUTS` (a minimal valid care input) and `import app.care.mock_rules`;
   - add `"care.suggest.v1"` to the required-task tuple of `test_single_mock_registry`.
   - Additive only.
4. `web/tests/care-review.test.tsx`:
   - the `screening()` fixture gains the I2 fields;
   - in "shows the banner text for screening %s", the `evaluated` branch asserts `screening-count` "0 of 16 declared rules fired" in place of `screening-evaluated`, and `rules-not-evaluated` becomes `screening-not-evaluated` (still asserting `RF-STROKE`).
   - Every other assertion is unchanged.

Anything else found necessary goes back to the planner. It is not edited silently.

## Required new tests

- `backend/tests/care/test_int2.py`:
  - `test_s6_frozen_predictions_reproduce[dev_0002|test_0002]`
  - `test_urgency_parity_d423d15`
  - `test_care_block_is_i2_screening`
  - `test_care_scope_honest`
  - `test_care_never_no_red_flags_api`
  - `test_care_never_evaluated_without_symptoms`
  - `test_care_stale_boundary[hr|rr|sbp|dbp|spo2|temp_c|consciousness]`
  - `test_care_stale_abnormal_still_alerts[same]`
  - `test_care_readings_listed`
  - `test_care_mock_label`
  - `test_fixture_trees_match_recorded`
  - `test_care_refuses_non_synthetic[manifest|item]`
  - `test_result_parity_d423d15`
  - `test_gateway_request_parity_d423d15`
  - `test_request_normalisation_is_sensitive[a|b|c|d|e|f]`
  - `test_case_summary_format`
- `backend/tests/care/fixtures/s6_urgency_d423d15.json` + `scripts/int2_dump_s6_urgency.py`. The fixture is regenerated at d423d15 with the added fields (`result_sha256`, `n_gateway_calls`, `request_sha256_normalised`). It is a new int2 file, not a sanctioned edit.
- `web/tests/care-review.screening.test.tsx` (4 states, overclaim regex, DOM order).
- `web/e2e/care.spec.ts`: 1 new test (A14).

## Clinical risks

| Risk | Mitigation |
|---|---|
| The care block copies the I2 scope and claims transcript symptoms were screened when care reads none (false reassurance) | Care-specific scope that states symptom rules are not evaluated (A08). 0 `evaluated` care screens without symptom facts (A09) |
| A stale normal vital is counted as screened (C1) | A non-fired rule on a stale vital becomes `not_evaluated` with read time and age (A10) |
| The physician summary shows `HR 83.0/min`, which implies precision that was never recorded; or a fix rounds a real `83.5` | Text parity with d423d15 (A07-ii) and the no-rounding unit (A18) |
| The request representation change hides a content change sent to a future real provider | The only allowed deltas are enumerated. N removes nothing else, and sensitivity controls prove it (A17) |
| The port silently drops or changes an alert or escalation | Staleness never removes a fired alert (A10 iii). 560/560 parity with d423d15 (A07). Frozen predictions reproduce (A06) |
| Two red-flag mappings (care vs I2 bridge: consciousness `C`, freshness drop) confuse reviewers | Scope text names care's inputs. Unification is D2/D-int2-1, not done silently |
| Removing the old care strings loses the "escalate now" cue | The alert list, the escalation text, and the acknowledgement gating are unchanged (existing Vitest and Playwright) |
| Test edits hide a regression | Exhaustive sanctioned list, frozen safety test files (A15), scope fence (A16) |

## Run commands

```bash
cd /Users/king_phuripol/AI-Engineer/01_Projects/Senior-Project/Full-Agent-i2
make test                                   # worktree
git clone -q --branch factory/int2 . ../int2-clean && (cd ../int2-clean && make test)   # clean checkout, NOT under a temp dir (note A01)
make data && make audit
python -m eval ledger verify --git-history
python -m eval ledger verify --ledger-dir slices/s6/eval/ledger
python -m eval.posthoc.e1_findings --check
git diff 1c59c7f --stat -- slices/s6/eval slices/s6r/eval eval/ledger eval/results eval/manifests   # empty
git diff 1c59c7f --stat -- casegraph backend/app/triage backend/app/voice backend/app/gateway eval data_factory backend/app/care/rules  # empty
git diff 1c59c7f --stat -- '**/tests/**' web/tests web/e2e                  # only sanctioned files + new tests
git worktree add /tmp/int2-d423d15 d423d15 && python scripts/int2_dump_s6_urgency.py --repo /tmp/int2-d423d15 --check backend/tests/care/fixtures/s6_urgency_d423d15.json
(cd web && npm test)
(cd web && WEB_PORT=3122 API_PORT=8122 npx playwright test e2e/care.spec.ts e2e/a11y.spec.ts e2e/triage.spec.ts e2e/roles.spec.ts e2e/disclaimer.spec.ts e2e/health.spec.ts e2e/theme.spec.ts)
# voice-intake (fenced, pre-existing failure): run on int2 and on a c15ac93 clone at a non-temp path; failure sets must match
(cd web && WEB_PORT=3122 API_PORT=8122 npx playwright test e2e/voice-intake.spec.ts)
# checker probe: full CareResult + gateway requests, diff between d423d15 and int2 (expect only A17 deltas, red_flag_screening, request_sha256)
PYTHONPATH=$PWD/backend:$PWD python tests/e2e/int2_full_parity.py '{"v1": "<v1 root>", "heldout": "<held-out root>"}'
```

## Decisions required (human)

- **D-int2-1:** the care stale-vital rule (fired alerts kept, non-fired rules become `not_evaluated`) differs from I2's Red-flag node, which drops stale facts entirely. Should care adopt I2 freshness, including dropping stale-abnormal alerts? This is a clinical decision (D1), and it would change S6 behaviour, so it needs a new evaluation id.
- **D-int2-2:** S6-A07 was measured as `git diff ef4a3d2 -- casegraph/` empty. It can no longer hold after I2 by design. It is re-baselined here to `git diff 1c59c7f -- casegraph/` empty (INT2-A16). Owner acknowledgement is required.
- **D-int2-3 (acknowledgement, non-blocking for the build):** the care gateway request now carries I2-typed items. The deltas are exactly (a)-(d) in Scope 2. Its `request_sha256` therefore differs from S6 on 442/442 calling DPs. No frozen artifact holds it. The gateway contract, the task and the mock output are unchanged (A06, A07, A17). The owner acknowledges that S6's "same request" statement is re-baselined to normalised parity.
- Open and unchanged: S6 D1 (expert review), D2 (symptom red-flag wiring into care), D3, D4; D-I2-1..5.
