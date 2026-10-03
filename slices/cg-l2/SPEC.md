# Slice cg-l2: ConversationFactUse — a superseded fact is not reported as used (closes CONDITIONS L2)

- Owner (Gantt): ภูริณัฐ (Case Graph). Branch: `factory/cg-l2`, base `f9dd06e` (cg-t123 merge).
- Source of truth: `docs/PROPOSAL.md` §3.2.3 (Output Store cache key = node type, provider, model version, params, input hash; replay reads stored output), §3.2.4 (Pharma compares new orders with the prior list, the conversation's medications and the allergy history, for pharmacist review). CLAUDE.md: the inspectable artifact is the executed DAG, so its per-input "used" record must be accurate.
- Condition being closed: `slices/CONDITIONS.md` → `cg-t123` → **L2** (gate: before UI-DAG renders `conversation_fact_use`). `docs/DECISIONS.md` 2026-10-03 accepted L2 "for this slice only".
- Status: PLAN. Tier 0 only: CPU, synthetic data, offline, mock providers. No GPU, no external API, no real patient data.
- Claim boundary: a correctness fix to a structured audit field on synthetic cases. Not clinical performance. The supersession rule itself still needs pharmacist sign-off (standing human condition, unchanged).

## Problem today (verified on `f9dd06e`)

`casegraph/data.py::ConversationFactUse` has two fields that can disagree: `used: bool` and `use: Literal["used","partial","not_used","superseded"]`. `casegraph/executor.py::_conversation_fact_use` sets `used=use in ("used","superseded")` for medications and `used=reason is None` for allergy facts, so every `use="superseded"` row has `used=True`. Pharma never read that fact. A consumer reading `used` shows a patient's replaced UNKNOWN allergy statement as "used".

Planner probe (scratch plugin over the existing property sweep, 13 VARIANTS × FIXTURES_STAGED + dev SYN): `use="superseded"` occurs only for `allergy_status` (tz_allergy 6, old_allergens_partial 1, tie_allergens 1), always with `used=True`. **No superseded `allergens` or `current_medications` row and no superseded UNKNOWN/REFUSED row is exercised by the sweep today**, so new variants are required for L2c to be meaningful.

Note: `FIXTURES_STAGED` has **7** fixtures (F-CXR, F-FUTURE, F-PRE, F-RED, F-SAME, F-STALE, F-T3ONLY), not 9. Dev SYN contributes ≥40 cases (asserted in the test).

## Scope

1. **Model (one place).** In `ConversationFactUse`, `used` is derived from `use` by a single `model_validator`: `used = (use == "used")`. Callers stop passing `used`. If `used` is passed explicitly and disagrees with `use`, construction raises `ValidationError` (reject, not silent override, so a future code bug fails loudly). A consistent explicit value is accepted, so `model_dump()` → `model_validate()` round-trips. Same validator also enforces the reason contract: `use in {partial, not_used}` ⇒ `reason` is a non-empty string; `use in {used, superseded}` ⇒ `reason is None`.
2. **Executor.** `_conversation_fact_use` constructs rows without `used` (or with the derived value). No change to how `use` or `reason` is chosen, to supersession, ordering, ties, gates, `missing_inputs`, `status`, checks or issues.
3. **Gate version.** Bump `PHARMA_GATES_VERSION` in `casegraph/executor.py` from `cg-pharma-gates-5` to `cg-pharma-gates-6`, with a one-line comment: "6: ConversationFactUse.used is False for superseded (L2)". Pharma output bytes change, so an Output Store entry computed under gates-5 must never be served.
4. **Tests (invariant keyed on `use`).**
   - `casegraph/tests/test_cgt123_conversation_meds.py::_check_property`: replace the `if not u["used"]` rule with: `use in {partial, not_used}` ⇒ `used is False`, `reason in missing_inputs`, `status != "evaluated"`; `use == "superseded"` ⇒ `used is False`, `reason is None`, and no `missing_inputs` entry names that fact's `evidence_ref`; `use == "used"` ⇒ `used is True`, `reason is None`.
   - Add VARIANTS that produce every superseded kind: `sup_allergy_unknown` (older UNKNOWN `allergy_status` → later KNOWN `present` + KNOWN allergens), `sup_allergy_refused` (older REFUSED `allergy_status` → later KNOWN `absent`), `sup_allergens_unknown` (older UNKNOWN `allergens` → later KNOWN list), `sup_meds_unknown` (older UNKNOWN meds → later KNOWN `["warfarin"]`). The sweep keeps a counter and asserts ≥1 `superseded` row per kind (`allergy_status`, `allergens`, `current_medications`) across the variants that target it.
   - `casegraph/tests/test_cgt123_round5.py::test_superseded_older_non_known_allergy_fact_is_marked_superseded`: expected becomes `[("UNKNOWN","superseded",False,None), ("KNOWN","used",True,None)]`.
   - `casegraph/tests/test_cgt123_conversation_meds.py::test_superseded_unknown_is_not_an_open_input`: also assert the UNKNOWN med row is `use="superseded", used=False, reason=None`.
5. **Close L2** in `slices/CONDITIONS.md` (row text: `CLOSED (cg-l2, <date>)`, gates-6, and the test names below).

## Out of scope

- Any change to `use`/`reason` selection, the supersession/tie rules, KNOWN `[]` semantics, or Pharma gates (pharmacist sign-off pending; unchanged).
- Other cg-t123 conditions (M1, L1, L3, L5, L6, L9, N2, C3, C5). L3 (golden gate test, version visible in exports) stays OPEN.
- Rewriting already-stored outputs or exports. Stored gates-5 Pharma outputs replay byte-identically (replay must not alter evidence); see risk R2.
- Parallel-slice files: `backend/app/triage/casegraph_run.py`, `backend/app/triage/router.py` (ui-dag, cg-m1), `web/` (ui-dag), `research/data/ctrate/` (ctrate-r1). Also `docs/` (the orchestrator records the L2 closure in `docs/DECISIONS.md` at merge).
- `s5-pipeline-2.6.0` is not bumped (pinned by S5 tests; same reason as R5-1).

## Acceptance

| ID | Criterion | Threshold | How measured |
|---|---|---|---|
| L2a | `ConversationFactUse.used == (use == "used")` for every constructed value, enforced by one validator; an inconsistent explicit `used` is rejected; reason contract enforced | 4/4 `use` values constructed without `used` give the derived value; 4/4 inconsistent explicit `used` raise `ValidationError`; 4/4 consistent explicit values and `model_dump`→`model_validate` round-trip; `partial`/`not_used` with `reason=None` and `used`/`superseded` with a reason raise; `grep -n "used=" casegraph/executor.py` shows no `ConversationFactUse(... used=...)` computing `used` from anything but `use` | new `casegraph/tests/test_cgl2_fact_use.py::test_used_is_derived_from_use[used,partial,not_used,superseded]`, `::test_inconsistent_used_is_rejected[...]`, `::test_reason_contract[...]`, `::test_round_trip` |
| L2b | Superseded fact: an older UNKNOWN or REFUSED `allergy_status` / `allergens` (and UNKNOWN `current_medications`) replaced by a strictly later KNOWN fact is `use="superseded", used=False, reason=None`; it adds no `missing_inputs` entry; Pharma `status` and `missing_inputs` are identical to the same case **without** the older fact | 4/4 cases (allergy_status UNKNOWN, allergy_status REFUSED, allergens UNKNOWN, meds UNKNOWN): row values exact; `missing_inputs` contains no token with the fact's `evidence_ref` or `=UNKNOWN`/`=REFUSED` for that kind; `(status, missing_inputs)` equal with vs without the older fact | updated `test_cgt123_round5.py::test_superseded_older_non_known_allergy_fact_is_marked_superseded`, updated `test_cgt123_conversation_meds.py::test_superseded_unknown_is_not_an_open_input`, new `test_cgl2_fact_use.py::test_superseded_is_not_a_gap[allergy_status-UNKNOWN,allergy_status-REFUSED,allergens-UNKNOWN,current_medications-UNKNOWN]` |
| L2c | Property over all VARIANTS × (7 `FIXTURES_STAGED` + all dev SYN cases, ≥40) holds with the `use`-keyed rule, and actually exercises superseded rows | 0 violations; 17/17 variants pass (13 existing + 4 new); superseded rows ≥1 for each of `allergy_status`, `allergens`, `current_medications`; `checked >= 20` and `len(cases) >= 40` per variant still asserted | `pytest casegraph/tests/test_cgt123_conversation_meds.py -k no_pharma_output` |
| L2d | Gate version bumped; cache never serves gates-5 output | `PHARMA_GATES_VERSION == "cg-pharma-gates-6"`; `test_pharma_input_hash_carries_the_gate_semantics_version` passes; a Pharma node built under gates-5 then rebuilt under gates-6 on the same store is `cached=False` with a different `cache_key` | `test_cgt123_round5.py::test_pharma_input_hash_carries_the_gate_semantics_version`, new `test_cgl2_fact_use.py::test_gates_6_constant_and_no_stale_hit` |
| L2g | No other behaviour change: only `used` on superseded rows differs from base | Over the full L2c sweep (13 existing variants) the Pharma `MedicationIssues` at `f9dd06e` and at branch head differ **only** in `conversation_fact_use[i].used` True→False on rows with `use=="superseded"`; `status`, `missing_inputs`, `check_results`, `issues`, `use`, `reason`, row order identical; Red-flag/checkpoint outputs identical | checker's independent differential script run on both commits (`git worktree` of `f9dd06e`), reports counts of changed rows by kind |
| L2h | All cg-t123 behaviour kept (A1–A8, rounds 1–5, L8/N1) | 100% of existing casegraph tests pass with only the two expected edits listed in Scope 4 | `pytest -q casegraph` (baseline: `test_cgt123_conversation_meds.py` + `test_cgt123_round5.py` = 53 passed on `f9dd06e`) |
| L2e | Scope fence | `git diff --name-only f9dd06e...HEAD` ⊆ `casegraph/**`, `slices/CONDITIONS.md`, `slices/cg-l2/**` | checker runs the command |
| L2i | L2 recorded closed | `slices/CONDITIONS.md` L2 row says CLOSED with slice id, date, `cg-pharma-gates-6` and the test names from L2a–L2d | checker reads the row |
| L2f | Full suite green | `make test` recipe exit 0 (pytest + web + mobile). Known flaky web live-call F8 is accepted only if it passes on one rerun; any other failure fails L2f | the `make test` recipe run directly with the main checkout's venv and node_modules (see run commands) |

## Required test cases (synthetic, offline)

- `SYN-L2-AS-UNK`: AllergyList `known`; conv c1 at T1−30 min `allergy_status=UNKNOWN`; c2 at T1−15 `allergy_status=KNOWN present`, `allergens=KNOWN ["penicillin"]`; new order at T1+30 → T3. Expect c1 row `superseded/False/None`; no `conversation.allergy_status=UNKNOWN` in `missing_inputs`.
- `SYN-L2-AS-REF`: as above with c1 `REFUSED`, c2 `KNOWN absent`.
- `SYN-L2-AL-UNK`: c1 `allergens=UNKNOWN`, c2 `allergy_status=KNOWN present` + `allergens=KNOWN ["sulfa"]`.
- `SYN-L2-MED-UNK`: c1 `meds=UNKNOWN`, c2 at T1−10 `meds=KNOWN ["warfarin"]`.
- Each case is also built without c1; `(status, missing_inputs)` must be equal (L2b).
- Negative controls (must stay gaps): same-time UNKNOWN vs KNOWN (tie) stays `not_used`, `used=False`, reason `:same_time_conflict` in `missing_inputs`; newest UNKNOWN stays `not_used` with `conversation.<kind>=UNKNOWN`; older KNOWN allergens with an unparseable entry stays `partial`/`not_used` (round 5 B1-r5).

## Clinical risks

- **R1 (the fix):** a reviewer or UI reading `used` sees a replaced UNKNOWN allergy statement as evidence Pharma relied on. After the fix `used=False`; the row stays visible with `use="superseded"` so the reviewer still sees that the patient once said "unknown".
- **R2 (residual, stored data):** Pharma outputs and exports produced under gates-5 keep `used=True` on superseded rows when replayed (replay never rewrites stored evidence). UI-DAG must render from `use`, not `used`, or show the gate version. Recorded in the L2 closure row; L3 (gate version visible in exports) remains the tracking condition.
- **R3 (over-correction):** the fix must not turn a real gap into "not a gap". Superseded must never be assigned to a newest fact, a same-time conflict, or an unparseable KNOWN allergens fact. Guarded by the L2b negative controls and L2g (no `use`/`reason`/`status` change).
- **R4 (unchanged, human):** the supersession rule itself (later KNOWN closes earlier UNKNOWN/REFUSED) still needs pharmacist sign-off before any clinical use.

## Run commands

Worktrees have no `.venv` or `node_modules`; use the main checkout's (no install, no network).

```bash
cd /Users/king_phuripol/AI-Engineer/01_Projects/Senior-Project/Full-Agent/.claude/worktrees/cg-l2
MAIN=/Users/king_phuripol/AI-Engineer/01_Projects/Senior-Project/Full-Agent
PYTHONPATH=backend:. $MAIN/.venv/bin/python -m pytest -q casegraph/tests/test_cgl2_fact_use.py \
  casegraph/tests/test_cgt123_conversation_meds.py casegraph/tests/test_cgt123_round5.py
PYTHONPATH=backend:. $MAIN/.venv/bin/python -m pytest -q casegraph
# L2f = the `make test` recipe, run directly. Do not run `make test` here: the worktree's requirements.lock is newer
# than $MAIN/.venv/.installed, so make would re-run pip install into the main venv (network + mutates main checkout).
ln -sfn $MAIN/web/node_modules web/node_modules; ln -sfn $MAIN/mobile/node_modules mobile/node_modules
PYTHONPATH=backend:. $MAIN/.venv/bin/python -m pytest -q -rs
(cd web && npm test) && (cd mobile && npm test && npm run typecheck)
rm web/node_modules mobile/node_modules   # symlinks are NOT covered by `node_modules/` in .gitignore; never commit them
git diff --name-only f9dd06e...HEAD
```
