# Slice cg-l1: conversation facts with an unparseable time fail closed (closes CONDITIONS cg-t123 L1)

- Owner (Gantt): ภูริณัฐ (Case Graph). Branch `factory/cg-l1`, base `f9dd06e`.
- Source of truth: `docs/PROPOSAL.md` §3.2.4 (Pharma Agent inputs include the conversation's medication/allergy data) and CLAUDE.md data rules 2, 3 and 6 (every item has `available_at_time`; nothing after `T`; missing is never negative).
- Status: PLAN. Tier 0 only: CPU, synthetic, offline, mock gateway. No real data, no external API.
- Claim boundary: defence-in-depth for a path that is unreachable today (`IntakeValue.available_at_time` is `AwareDatetime`). It shows the Pharma gates fail closed on crafted input and nothing about clinical performance.

## Problem

`casegraph/conversation_meds.py::parse_ts` maps a missing or unparseable `available_at_time` to `datetime.min`, so the fact sorts oldest. The results:

- An UNKNOWN/REFUSED `allergy_status`, `allergens` or `current_medications` fact with a bad time loses `newest()` to any valid fact.
- The medication supersede rule (`parse_medication_facts`) marks it `superseded`, so it is no longer an open input. That is the unsafe direction (rule 6).
- A KNOWN fact with a bad time reaches the S5 adapter (`pharma_s5.py`). There `MedSource`/`AllergyRecord.available_at_time` is `AwareDatetime`, so the Pharma node can end as `error` with no structured reason.
- `order_key`/`same_time_conflict` raise `KeyError` when the key is missing.

## Scope

1. **Shared helper** (`casegraph/conversation_meds.py`). Add one public helper, e.g. `time_problem(fact) -> str | None`, that returns `conversation.<kind>:unparseable_time` when `available_at_time` is missing, `None`, not a `str`/`datetime`, or not ISO-parseable. It never raises. Valid behaviour stays as it is: a naive value is still read as UTC, and aware values compare as instants.
2. **Ordering fails closed.**
   - `newest()` never returns a bad-time fact while it is choosing among facts. It returns `None` when no fact of the kind has a valid time.
   - `ordered()` and `order_key()` are total and deterministic and never raise on a bad-time fact.
   - `same_time_conflict()` never raises and never treats a bad-time fact as being at the same instant as another fact.
3. **Supersede rule** (`parse_medication_facts`):
   - A bad-time fact is never `superseded`, whatever its state.
   - A bad-time KNOWN fact never supersedes another fact.
   - A bad-time fact gets `problem = "conversation.current_medications:unparseable_time"` and `names = ()`, so S5 `_conversation_sources` never reads it.
4. **Gates** (`executor._conversation_allergy_gaps`, `_conversation_medication_gaps`):
   - Every kind with at least one bad-time fact adds an `allergy_conversation` or `medication_conversation` gap row carrying `conversation.<kind>:unparseable_time`. This holds for any state.
   - The row's status is `not_evaluated`, and the token appears in `MedicationIssues.missing_inputs`.
   - The existing `:unparseable` (bad value) token is not reused for a bad time.
5. **Provider input** (`executor._pharma`): bad-time facts are not handed to the provider hook (`PharmaInput.facts`), because they cannot be placed at or before `T`. They are still passed to every gate and still listed in `conversation_*_facts`. The Pharma node ends `ok` with the structured gap, never `error` and never `evaluated`.
6. **Bump** `PHARMA_GATES_VERSION` in `casegraph/executor.py` from `cg-pharma-gates-5` to `cg-pharma-gates-6`. A one-line merge conflict with cg-l2 is expected.
7. **CONDITIONS**: mark cg-t123 L1 CLOSED in `slices/CONDITIONS.md` and list the test names and the commit. Add follow-up `L1-F1` as described under Out of scope.

## Out of scope (scope fence)

- `casegraph/data.py` (`ConversationFactUse`) and the `Executor._conversation_fact_use` function belong to the parallel slice cg-l2. Do not edit them.
  - Medication `fact_use` picks up the new reason through `parse_medication_facts.problem` with no edit (it becomes `use=not_used`, reason `...:unparseable_time`).
  - For `allergy_status`/`allergens`, a bad-time fact may still be labelled `superseded`/`used` in `fact_use`. Record this as follow-up **L1-F1** in CONDITIONS, gated to "with or after cg-l2 merge": `fact_use` must report it as `not_used` with reason `conversation.<kind>:unparseable_time`.
  - Tests in this slice must not assert on allergy-kind `fact_use` rows for bad-time facts.
- `backend/`, `web/`, `research/data/ctrate/`, `casegraph/pharma_s5.py`, `casegraph/triage_bridge.py`, schemas and export versions.
- Making the path reachable. `IntakeValue.available_at_time` stays `AwareDatetime`.
- Facts with a valid time after `T`. Those are already handled by the snapshot/temporal rules.

## Acceptance

`BAD` = the bad-time set {key missing, `None`, `""`, `"not-a-time"`, `"2026-02-30T10:00:00+00:00"`, `12345`}. "Staged" = `build_versions(...)[-1]` at T3. "Unstaged" = `compile_graph` + `run_sync` (as `_unstaged` in `test_cgt123_round5.py`). Crafted facts are injected by monkeypatching `Executor._conversation_facts` to overwrite `available_at_time` on the targeted fact, using a fresh Executor/OutputStore per case so there is no cache hit from an unpatched run.

| ID | Criterion | Threshold | How measured |
|---|---|---|---|
| L1a | A non-KNOWN (UNKNOWN, REFUSED) fact of each kind (`allergy_status`, `allergens`, `current_medications`) with a BAD time, next to a valid KNOWN fact of the same kind, is never superseded or overruled. Pharma `status != "evaluated"`, the node status is `ok`, and `missing_inputs` contains `conversation.<kind>:unparseable_time`. For meds, the bad fact's `ConversationMeds.superseded is False` | 3 kinds × 2 states × 6 BAD × {staged, unstaged} = 72/72 | `test_cgl1_nonknown_bad_time_never_superseded[kind-state-bad-staged]` plus the helper unit test `test_cgl1_parse_medication_facts_bad_time_not_superseded` |
| L1b | A KNOWN fact with a BAD time never wins `newest()` over a valid fact of the kind, never supersedes a valid non-KNOWN fact, and is itself a gap (token in `missing_inputs`, Pharma `!= "evaluated"`). It is not handed to the provider: no S5 `patient_reported` source and no `evaluated_on` cites its ref, and no S5 `AllergyRecord` comes from it. The cases include a bad-time KNOWN `allergy_status="absent"` next to a valid `present`, and a bad-time KNOWN `["warfarin"]` next to a valid older UNKNOWN meds fact (whose `=UNKNOWN` gap must remain) | 3 kinds × 6 BAD × {staged, unstaged} = 36/36 | `test_cgl1_known_bad_time_never_newest[kind-bad-staged]`, `test_cgl1_known_bad_time_not_sent_to_provider` |
| L1c | Helper contract: `time_problem`, `order_key`, `ordered`, `newest`, `same_time_conflict` and `parse_medication_facts` never raise on any BAD value (including a missing key). `newest` returns `None` when every fact is bad-time. Order is deterministic under input permutation. A single bad-time fact alone is a gap | 0 exceptions; same result over all permutations of a 4-fact mixed list | `test_cgl1_helpers_total_on_bad_time[bad]`, `test_cgl1_order_permutation_invariant` |
| L1d | Valid-timestamp behaviour is unchanged. All existing casegraph tests pass with the existing test files unmodified, including the cgt123 property test over all `VARIANTS` and the round-5 tz/tie tests. `tests/e2e/cgt123_inprocess_check.py` reports A1–A7b with the same pass status as on base `f9dd06e` | 100% pass; `git diff f9dd06e -- casegraph/tests` adds new files only; the A1–A7b statuses from the in-process check are identical on base and branch | `PYTHONPATH=backend:. .venv/bin/python -m pytest -q casegraph/tests`; the in-process check run on both revisions and the JSON statuses diffed |
| L1e | `PHARMA_GATES_VERSION == "cg-pharma-gates-6"`. A Pharma output cached under `-5` is not served for a `-6` run | 1 assertion + 1 cache-miss test | `test_cgl1_gates_version_bumped` (asserts the value and that the Pharma input hash differs from a run with `-5` monkeypatched) |
| L1f | Scope fence: the diff touches only `casegraph/conversation_meds.py`, `casegraph/executor.py` (not `_conversation_fact_use`), new files under `casegraph/tests/`, `slices/CONDITIONS.md` and `slices/cg-l1/` | 0 other paths; 0 changed lines inside `_conversation_fact_use` | `git diff --name-only f9dd06e...HEAD`; `git diff -U0 f9dd06e...HEAD -- casegraph/executor.py` hunks checked against the function's line range |
| L1g | CONDITIONS updated: L1 marked CLOSED with the test names and commit; follow-up L1-F1 (allergy-kind `fact_use` for bad-time facts, after cg-l2) recorded | Both rows present | Checker reads `slices/CONDITIONS.md` |
| L1h | `make test` green | All suites pass. Web `live-call.test.tsx` F8 may pass on a single rerun only, and that rerun must be reported | `make test` log |

## Required test cases (synthetic, new file `casegraph/tests/test_cgl1_unparseable_time.py`)

- **Helper unit tests on crafted dicts:** each BAD value, the missing key, a mixed list of 4 facts (valid KNOWN, valid UNKNOWN, bad KNOWN, bad UNKNOWN) in all 24 permutations, and a list where every fact is bad-time.
- **Gate unit tests:** call `Executor._conversation_allergy_gaps(latest, facts)` and `_conversation_medication_gaps(facts, (), 2)` directly with crafted facts, and assert the exact `unparseable_time` row.
- **End to end:**
  - Base the items on `staged_fixtures.base` + `conv_meds` + `order` (as in `test_cgt123_round5.py`), with the AllergyList `status="known"` so the record gates alone do not already make Pharma not-evaluated. For the L1b allergy case, use `status="no_known_allergy"`.
  - Run staged (T3) and unstaged.
  - Assert Pharma node status `ok`, `MedicationIssues.status != "evaluated"`, the token in `missing_inputs`, and a `not_evaluated` row of the right check.
- **Control:** the same items with valid times give the base-revision output (a bad time must be what flips the result).

## Clinical risks

| Risk | Mitigation |
|---|---|
| A patient's "I don't know / won't say" about allergies or medications is hidden by a valid "none" statement because its time is garbled | L1a: a bad-time non-KNOWN fact is never superseded and is an explicit gap |
| A garbled-time "no allergy" overrides a later "allergic to penicillin" | L1b: a bad-time KNOWN fact never wins `newest()` and is itself a gap |
| The Pharma node crashes (`error`) and the pharmacist sees no structured reason | Scope 5: bad-time facts are kept out of the provider, and the node ends `ok` + `not_evaluated` with a token |
| `fact_use` still labels an allergy-kind bad-time fact `superseded` until cg-l2 merges | Not safety-silent: the gate token keeps Pharma `!= evaluated`. Tracked as L1-F1 |
| Pharmacist sign-off on supersession rules is still pending (cg-t123 human condition) | Unchanged. This slice adds no clinical rule, only fail-closed handling |

## Run commands

```bash
cd /Users/king_phuripol/AI-Engineer/01_Projects/Senior-Project/Full-Agent/.claude/worktrees/cg-l1
PYTHONPATH=backend:. .venv/bin/python -m pytest -q casegraph/tests/test_cgl1_unparseable_time.py
PYTHONPATH=backend:. .venv/bin/python -m pytest -q casegraph/tests
make data && PYTHONPATH=backend:. .venv/bin/python tests/e2e/cgt123_inprocess_check.py data/synthetic/v1 <scratch> <out.json>
git diff --name-only f9dd06e...HEAD
make test
```
