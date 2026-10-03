# Slice cg-l6: the cg-t123 acceptance check runs in `make test` (closes CONDITIONS L6)

- Owner (Gantt): ภูริณัฐ (Case Graph) / checker. Branch `factory/cg-l6`, base `28ac4d2`.
- Source of truth: `docs/PROPOSAL.md` §3.2.2–3.2.4 (compiler builds the Typed DAG from data available at assessment time; executor records every node output for Replay/Regenerate; Output Store cache key; Pharma compares orders/lists/allergies for pharmacist review) and §3.6 (system behaviour is tested on synthetic data). CLAUDE.md: red flags take priority and trigger escalation; evidence must be reproducible, not a one-off script output.
- Condition: `slices/CONDITIONS.md` → `cg-t123` → **L6** (LOW): `tests/e2e/cgt123_inprocess_check.py` is not in `make test` (pyproject `testpaths` excludes `tests/e2e`), so the A1–A7b evidence is never re-checked and can rot silently.
- Tier 0 only: CPU, synthetic data (seed 20260926), offline, mock gateways. No product-code change. Not a clinical-performance claim: these are structural correctness checks of staged versions.

## Baseline (planner, measured on `28ac4d2`, this machine)

`python -m data_factory generate --seed 20260926 --out <tmp>/v1` (0.3 s), then `python tests/e2e/cgt123_inprocess_check.py <tmp>/v1 <scratch> <out.json>` (3.8 s wall): all of A1..A7b PASS. Two runs give byte-identical JSON (no paths or timestamps in it). Reference values:

| Metric | Reference value |
|---|---|
| A1 | `lists=400`; `counts_T1={"T1":200}`; `counts_T2={"T1/T3/T2":180,"T1/T2":20}`; `mismatch=[]`; `adversarial_cases=11`, `adversarial_mismatch=[]`; `fixture_mismatch=[]` (7 `FIXTURES_STAGED`) |
| A2 | `versions=131`, `bad=[]` |
| A3a | `nodes=657`, `bad=[]` |
| A3b | `cached_nodes_checked=127`, `bad=[]`, `fstale_t1_fresh_t3_stale=true`, `fstale_t3_screening="not_evaluated"` |
| A4 | `future_evidence_in_versions=[]`, `f_future_versions=1`, `adversarial_issues=[]`, `lateconfirm_absent_t2=true`, `lateconfirm_present_t3=true`, `leakage_audit_version_failures=[]`, `leakage_audit_dataset_rc=0` |
| A5 | t1 spec/items/run/outputs identical = true ×4, `resave_issues=[]`, `replay_calls=0`, `replay_issues=[]`, `role_guard_issues=[]` |
| A6 | `runs=36`, `lost=[]` |
| A7a | `t3_versions=41`, `bad=[]` |
| A7b | `parity_checked=37`, `parity_bad=[]`; secondary gold agreement `NOT_MEASURABLE` (never cited) |

Other committed probes on `28ac4d2`: `cgt123_allergy_probe.py` 80 combos / 0 bad / 71 gap combos (1.4 s); `cgt123_h1_probe.py` 16 combos / 0 bad (0.6 s); `test_cgl1_checker.py` 12 passed + `cgm1_independent_check.py` 4 passed (pytest, 1.2 s together); `cgl2_differential.py` + `cgl2_diff_compare.py` are a two-tree differential against base `c6a7a92`.

## Scope

1. **Refactor `tests/e2e/cgt123_inprocess_check.py` into importable functions.** No work at import time: no `sys.argv` read, no `mkdir`, no `main()` call at module level. One entry point, e.g. `run_check(dataset: Path, scratch: Path) -> dict`, returns the same result dict the script writes today. No module-global mutable state survives between calls (`R`, `CASES`, `BUILT` become locals or a per-call context), so two calls in one process are independent. The `temporal_leakage_audit.py` subprocess path is resolved from the repo root (not the cwd). The pharma `reconcile` spy is always restored (keep `try/finally`). A thin `if __name__ == "__main__":` wrapper keeps the CLI and its stdout lines. Gold stays independent: it is still re-derived from raw `journey.json` fields only, never from `casegraph.stages`. Every `pass` expression keeps its current conditions (none removed or loosened).
2. **New pytest module** `casegraph/tests/test_cgl6_cgt123_acceptance.py` (name may differ; must be under `casegraph/tests/`). It loads the check by file path (`importlib`; `tests/` is not a package) or by import, uses the existing session fixture `s1r_dataset` (seed 20260926, generated into tmp; `data/synthetic` is gitignored and must not be required) and `tmp_path` as scratch, and asserts:
   - every metric A1, A2, A3a, A3b, A4, A5, A6, A7a, A7b is PASS and `errors` is absent;
   - the exact reference values in the Baseline table (counts are pinned with `==`, not `>=`). A legitimate change to a count needs a reasoned edit to this test in the same commit.
3. **Planted regressions (permanent tests).** At least two, each applied by `monkeypatch` to a product code path the check exercises (never by editing the check or its thresholds):
   - `planner`: the stage planner seen by the check drops or reorders a stage → A1 FAIL and the pytest assertion helper raises;
   - `alert`: the Human Checkpoint pending payload loses an urgent Red-flag alert or `escalation` becomes False → A6 FAIL and the helper raises.
   Each planted test also asserts the unaffected metric it does not target is still computed (the run did not just crash: `errors` absent).
4. **Other probes (L6d).** For each of `cgt123_allergy_probe.py`, `cgt123_h1_probe.py`, `test_cgl1_checker.py`, `cgm1_independent_check.py`, `cgl2_differential.py`, `cgl2_diff_compare.py` decide `make test` vs manual evidence and record it (one line in the probe's module docstring + the L6 row). Planner recommendation (builder may differ with a stated reason):
   - `cgt123_allergy_probe.py`, `cgt123_h1_probe.py`: **in make test** (offline, deterministic, < 2 s). Same refactor pattern (importable function + `__main__`); pytest asserts 80 combos / 0 bad / 71 gap combos and 16 combos / 0 bad. The h1 probe's `reader_text.read_clinical_text` patch must be via `monkeypatch` or `try/finally` so it never leaks into other tests.
   - `test_cgl1_checker.py`, `cgm1_independent_check.py`: **in make test** if collectable without changing product code or `backend/tests/conftest.py` (12 + 4 tests must be collected and pass). If `cgm1_independent_check.py` cannot get its backend fixtures inside the fence, keep it manual and say so.
   - `cgl2_differential.py`, `cgl2_diff_compare.py`: **manual evidence** (they compare two git trees against a fixed base `c6a7a92`; not a regression test of one tree; L2 behaviour is already in `casegraph/tests/test_cgl2_fact_use.py`).
   - Live/browser probes (`i2_*`, `s5r4_*`, `s5r5_*`, `s6_*`, `*.cjs/.ts/.mjs`) are not in this decision and are not touched.
5. **Close L6** in `slices/CONDITIONS.md`: `CLOSED (cg-l6, <date>)` with the pytest node ids and the probe dispositions.

## Out of scope

- Any product code: `casegraph/*.py` (non-test), `casegraph/sources/`, `backend/app/`, `web/`, `mobile/`, `data_factory/`, `scripts/`. Parallel slices own `casegraph/data.py`, executor Pharma output and a golden file (cg-l3), `backend/app/triage/casegraph_run.py` / `router.graph_versions` and `web/` (ui-dag).
- Changing any acceptance definition of cg-t123, any gold rule, or any existing casegraph test.
- Other cg-t123 conditions (M1-R*, L3, L5, L9, N2, C3, C5).
- A `slow` marker: none exists and the expected cost (~5 s) does not need one. If one is added it must not deselect the test under `make test`.

## Acceptance

| ID | Criterion | Threshold | How measured |
|---|---|---|---|
| L6a | `make test` (pytest part) runs the cg-t123 acceptance check and asserts A1–A7b PASS with the reference values | Collected under the repo pytest config; passes; asserts all 9 metrics PASS and every Baseline value with `==` (A1 400 lists, `{"T1":200}`, `{"T1/T3/T2":180,"T1/T2":20}`, 11 adversarial + 7 fixtures 0 mismatch; A2 131/0; A3a 657/0; A3b 127/0 + F-STALE flags; A4 all clean, `f_future_versions=1`; A5 all true, `replay_calls=0`; A6 36/0; A7a 41/0; A7b 37/37) | `pytest --collect-only -q` lists the test; `pytest -q casegraph/tests/test_cgl6_*.py` passes; checker reads the assertions against the Baseline table |
| L6a-R | The test fails on a real regression | ≥2 planted regressions (`planner` → A1 FAIL, `alert` → A6 FAIL) each make the metric FAIL and the shared assertion helper raise `AssertionError`; both are permanent passing tests (`pytest.raises`) | `pytest -q casegraph/tests/test_cgl6_*.py -k planted`; checker additionally plants one regression of their own choosing (e.g. a cache key change → A3a) by local edit, sees the main test FAIL, then reverts |
| L6b | CLI unchanged | `python tests/e2e/cgt123_inprocess_check.py <dataset> <scratch> <out>` exit 0; the 9 stdout status lines identical; `out.json` equal (`json.load` dict equality) to the output of the `28ac4d2` script on the same seed-20260926 dataset | checker runs both commits (`git worktree add <tmp> 28ac4d2`) and compares |
| L6c | Runtime | Added wall time of the new tests under the pytest part of `make test` < 90 s (target < 60 s); report the number | `pytest -q --durations=0 casegraph/tests/test_cgl6_*.py` (+ any probe wrappers); report sum and the full pytest-part wall time before vs after |
| L6d | Every listed probe has a recorded disposition | 6/6 probes (Scope 4) have a docstring line `make test: <test id>` or `manual evidence: <reason>`, matching the L6 row; every `make test` probe's tests are collected and pass with the Baseline counts; every refactored probe CLI still runs and gives the Baseline counts | `grep -n "make test:\|manual evidence:" tests/e2e/<probe>`; `pytest --collect-only -q`; checker runs each probe CLI |
| L6e | Scope fence: no product code changed | `git diff --name-only 28ac4d2...HEAD` ⊆ `tests/e2e/**`, `casegraph/tests/**` (new files only; existing casegraph test files unchanged), `pyproject.toml`, `Makefile`, `slices/CONDITIONS.md`, `slices/cg-l6/**` | checker runs the command and `git diff --diff-filter=M --name-only 28ac4d2...HEAD -- casegraph/tests` (must be empty) |
| L6f | L6 recorded closed | L6 row: `CLOSED (cg-l6, <date>)`, the pytest node ids for the check, the planted-regression tests and each probe wrapper, and the per-probe dispositions | checker reads the row |
| L6g | Full suite green | The `make test` recipe exits 0 (pytest + web Vitest + mobile Vitest/tsc). Known flaky web live-call F8 accepted only if it passes on one rerun; any other failure fails L6g | recipe run directly (see Run commands) |
| L6h | No check weakened, gold still independent | Each `pass` expression in the refactored check has the same conditions as `28ac4d2`; `gold()` imports nothing from `casegraph.stages`/`casegraph.staged`; the probes' `ok`/`bad` rules unchanged | checker diffs the expressions (`git diff 28ac4d2 -- tests/e2e/`) and greps imports |
| L6i | Hermetic and split-safe | Tests need no `data/synthetic/` (pass with it absent); `git status --porcelain` empty after the run (all writes under tmp); the S1r dataset dir is unchanged by the run (file hash list before == after); the test split is only loaded and planned (A1), never compiled or executed; no `gold/` file is read; sockets stay disabled | checker moves `data/synthetic` aside if present, runs the tests, compares `find <dataset> -type f | xargs shasum` before/after, greps the check for `gold/` and for `"test"` split use outside A1 |
| L6j | Order independence | New tests pass alone, together, and in reverse order; the planted tests do not contaminate the main test (no leaked monkeypatch/spy) | `pytest -q casegraph/tests/test_cgl6_*.py`; each test alone by node id; planted tests listed before the main test by explicit node ids; full `pytest -q` |

## Required test cases (synthetic, offline)

- `test_cgt123_acceptance_reference_values`: seed-20260926 S1r (`s1r_dataset`) + `tmp_path` scratch; asserts the full Baseline table.
- `test_planted_planner_regression_fails` (A1) and `test_planted_alert_suppression_fails` (A6): monkeypatched product path; metric FAIL; helper raises.
- Probe wrappers per L6d (allergy 80/0/71, h1 16/0; cgl1 12 + cgm1 4 collected if in make test).
- Negative control for the helper: a result dict with one metric `pass=False` (or a count off by one) makes the helper raise (pure unit test, no build).

## Clinical risks

- **R1 (the gap being closed):** without CI, a change could hide an urgent red-flag alert behind a later version (A6), let future evidence into a version (A4), or serve a stale cached output after evidence changed (A3a/A3b, F-STALE), and nobody would notice. After this slice these fail `make test`.
- **R2 (false comfort):** pinned counts on one synthetic seed prove structural behaviour only, not clinical correctness. Do not cite this test as clinical performance or Pharma accuracy; A7b secondary gold agreement stays `NOT_MEASURABLE`.
- **R3 (weakening by refactor):** a refactor that loosens a `pass` rule or lets gold derive from the planner would turn the check into a tautology. Guarded by L6b (identical JSON), L6h and the planted regressions.
- **R4 (merge interaction):** cg-l3 (Pharma output) and ui-dag (`casegraph_run.py`) land in parallel. If either changes a pinned count or breaks `cgm1_independent_check.py`, that slice must fix or justify it; this slice must not relax the assertion to absorb it.

## Run commands

Worktrees have no `.venv`/`node_modules`; use the main checkout's. Do not run `make test` in the worktree: `requirements.lock` is newer than `$MAIN/.venv/.installed`, so make would re-run pip into the main venv (network, mutates main).

```bash
cd /Users/king_phuripol/AI-Engineer/01_Projects/Senior-Project/Full-Agent/.claude/worktrees/cg-l6
MAIN=/Users/king_phuripol/AI-Engineer/01_Projects/Senior-Project/Full-Agent
export PYTHONPATH=backend:.
$MAIN/.venv/bin/python -m pytest -q --durations=0 casegraph/tests/test_cgl6_*.py
# L6b: CLI on this branch vs 28ac4d2 (same dataset)
T=$(mktemp -d); $MAIN/.venv/bin/python -m data_factory generate --seed 20260926 --out $T/v1
$MAIN/.venv/bin/python tests/e2e/cgt123_inprocess_check.py $T/v1 $T/s_head $T/head.json
git worktree add $T/base 28ac4d2 && (cd $T/base && PYTHONPATH=backend:. $MAIN/.venv/bin/python tests/e2e/cgt123_inprocess_check.py $T/v1 $T/s_base $T/base.json)
python3 -c "import json,sys;a,b=(json.load(open(f)) for f in sys.argv[1:]);sys.exit(a!=b)" $T/head.json $T/base.json && echo SAME
git worktree remove $T/base
# L6g: the make test recipe, run directly
ln -sfn $MAIN/web/node_modules web/node_modules; ln -sfn $MAIN/mobile/node_modules mobile/node_modules
$MAIN/.venv/bin/python -m pytest -q -rs && (cd web && npm test) && (cd mobile && npm test && npm run typecheck)
```
