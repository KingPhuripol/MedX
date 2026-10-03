# Slice cg-l3: Pharma gate-semantics version in every Pharma output, plus a golden test that forces a version bump (closes CONDITIONS L3)

- Owner (Gantt): ภูริณัฐ (Case Graph). Branch: `factory/cg-l3`, base `28ac4d2` (cg-l2 merge).
- Source of truth: `docs/PROPOSAL.md` §3.2.3 (Output Store cache key = node type, provider, model version, params, input hash; replay reads stored outputs) and §3.2.4 (Pharma sends issues to the pharmacist through the Human Checkpoint). CLAUDE.md says the executed DAG is the inspectable artifact, so a Pharma output must say which gate policy produced it.
- Condition being closed: `slices/CONDITIONS.md` → `cg-t123` → **L3** (gate: "before cg-t123 output is cited as evidence"). See also `docs/DECISIONS.md` 2026-10-04 ("Residual (tracked under L3)").
- Status: PLAN. Tier 0 only: CPU, synthetic data, offline, mock providers. No GPU, no external API, no real patient data.
- Claim boundary: this slice adds an audit field and a regression tripwire on synthetic cases. It does not measure clinical performance. A golden file covers a fixed corpus and is not a proof that behaviour is unchanged outside that corpus.

## Problem today (verified on `28ac4d2`)

- `casegraph/executor.py:82` `PHARMA_GATES_VERSION = "cg-pharma-gates-8"` appears only in `hashed["pharma_gates"]` (`_run_node`, line 260), so it lives only inside the input hash and cache key. `MedicationIssues` (`casegraph/data.py:658`) has no version field. A stored run or a 0.3/0.4 export therefore cannot show which gate policy produced its Pharma output. Example: under gates ≤6, superseded rows show `used=True` (the L2 residual).
- Versions 4 to 8 were each bumped by hand. Nothing fails when gate or `fact_use` behaviour changes without a bump.
- Backend `casegraph_run.versions()` node data (`backend/app/triage/casegraph_run.py:155`) lists only `id/type/provider/status/cached/gateway_calls`, with no outputs. The version cannot appear there unless `versions()` is edited, and `versions()` belongs to ui-dag and is outside this slice's scope. That work is recorded below as follow-up **L3-F1**.
- Planner probe (scratch script, not committed): corpus = (7 `FIXTURES_STAGED` + the first 8 dev SYN cases sorted by case id, S1r seed 20260926) × 17 `VARIANTS`. It gave 204 Pharma outputs, all at T3 with status `ok`: `partially_evaluated` 176, `evaluated` 28, `not_evaluated` **0**. Fact uses were `used` 348, `not_used` 59, `partial` 5, `superseded` 30. The output-hash digest was identical under `PYTHONHASHSEED=1` and `777`, and the run took about 5 s. The staged sweep alone never yields `not_evaluated`, so anchor cases are required for L3c (Scope 4).

## Decisions taken in this SPEC

- **D1: field.** Add `gates_version: str | None = None` to `MedicationIssues`. `None` (JSON `null`) means "produced before cg-l3; gate semantics not recorded". The code never fills this field with a guessed value. Every Pharma output built by the executor, on both the rules path and the model path, sets it to `executor.PHARMA_GATES_VERSION`, read **at call time** from the module global so tests can monkeypatch it.
- **D2: bump to `cg-pharma-gates-9`.** The new field changes the Pharma output bytes (`output_sha256`). If the version stayed at 8, a persistent Output Store entry computed at `28ac4d2` (gates-8, no field) would be served from cache under the new code, and L3a would fail. This follows the same rule as gates-4 to 8: Pharma output bytes change ⇒ bump. Add the comment `# 9: MedicationIssues carries gates_version (L3)`. No gate decision changes. L3g checks this.
- **D3: version is not in exports at graph level.** It stays inside the Pharma node output (`nodes[].output.MedicationIssues.gates_version`), which every 0.4 export and stored run already carries. Export schema stays `casegraph-export/0.4`, so no export version bump is needed.
- **D4: other node bodies (auditor L1).** Red-flag, Reader:*, Reasoning and Vitals/Labs reader get **no** semantics-version mechanism in this slice. Reasons:
  1. Their behaviour is chosen by provider plus `model_version` (for example `rf-1.1.0`, `placeholder-redflag-0.2`, reader versions), which is already in the cache key.
  2. `git log 28ac4d2 -- casegraph/executor.py` shows that every executor change since cg-t123 round 5 (cg-l1, cg-l2) touched Pharma only.
  3. Adding a field to `Alerts` changes a schema that `import_graph` validates strictly and that backend and web read, and both are in ui-dag scope.

  The gap stays open as tracked condition **L3-N1**: executor-side logic in a non-Pharma body, including `triage_bridge` and the Reasoning abstain logic, can change without a key change, and a persistent Output Store would then serve stale outputs. A stale Red-flag output is the safety-relevant case. Gate: whichever comes first of (a) the next change to a non-Pharma node body or to `triage_bridge`, (b) any demo or evaluation run that reuses an Output Store directory across code revisions, (c) CG-F3. Interim rule: demo and evaluation runs start from a fresh Output Store.

## Scope

1. **Model.** `casegraph/data.py::MedicationIssues` gains `gates_version: str | None = None` with a one-line comment. No other model change. A dict with no `gates_version` key (legacy) validates with `gates_version is None`.
2. **Executor.** Both `MedicationIssues(...)` constructions in `Executor._pharma` (rules path, `executor.py:641`, and model path, `:666`) pass `gates_version=PHARMA_GATES_VERSION`. Bump the version to `cg-pharma-gates-9` (D2). Nothing else in `_pharma`, the gates, `fact_use`, the hashing or the cache key changes.
3. **Golden tripwire** in new `casegraph/tests/pharma_golden.py`, a helper module importable by tests and runnable as `python -m casegraph.tests.pharma_golden`.
   - `build_corpus()` returns one entry per Pharma node across every built version. The key is `"<variant>|<case>|<stage>|v<version>"` (anchors use `"anchor|<name>|..."`). Each entry holds:
     - `input_sha256` = `sha256_json` of `{node provider, model_version, params, [evidence item_id, sha256] for the node's evidence_refs, sorted [src id, edge data_type, src status, src output_sha256] of its in-edges}`. This deliberately leaves out `PHARMA_GATES_VERSION`.
     - `output_sha256` (as exported).
     - `semantic_sha256` = `sha256_json` of the output with `MedicationIssues.gates_version` removed.
     - `status`.
     - per-`use` counts of `conversation_fact_use`.
   - The S1r dataset is generated in a temp dir by subprocess `python -m data_factory generate --seed 20260926`, as `conftest.s1r_dataset` does. The helper never imports `data_factory`, because the isolation guard forbids that import.
   - Corpus (frozen, `corpus_id = "cg-l3-corpus-1"`):
     - (a) 7 `FIXTURES_STAGED` × every key of `test_cgt123_conversation_meds.VARIANTS`, applied exactly as that sweep applies them.
     - (b) the first 8 dev SYN case ids in sorted order × every VARIANT. The ids are written into the golden file.
     - (c) anchor `model_path`: `test_executor.py::test_pharma_model_path_not_evaluated` setup (F1, `project_model`/`proj-mock-0.1`), which gives `not_evaluated`.
     - (d) anchor `placeholder_api1`: the `s2_config()` placeholder-pharma-0.2 duplicate/dose case from `test_executor.py`, which gives `partially_evaluated`.
   - `compare(golden, current) -> Report` classifies every key in this order:
     - `version_mismatch`: golden `pharma_gates_version` ≠ current `PHARMA_GATES_VERSION`.
     - `key_drift`: the key set differs, or the SYN subset ids or `corpus_id` differ.
     - `input_drift`: same key, different `input_sha256`.
     - `semantics_changed_without_bump`: same key, same `input_sha256`, different `output_sha256`, same version.
     - `ok`.
   - CLI: `--check` (default) prints the report and exits 1 on any non-ok class. `--write [--accept-input-drift]` rewrites the golden file and **refuses** (exit 2, golden file untouched) when the current version equals the golden version and any entry is `semantics_changed_without_bump`. `input_drift` entries are written only with `--accept-input-drift`. On every write, the helper prints the keys whose `semantic_sha256` changed so the reviewer sees what the bump changed.
   - Golden file `casegraph/tests/golden/pharma_gates_golden.json`. It stores sorted keys, `indent=2`, `pharma_gates_version`, `corpus_id`, `s1r_seed`, `syn_subset`, the exact regenerate command, and `entries`. It is generated once at gates-9 and committed.
4. **Tests** in new `casegraph/tests/test_cgl3_pharma_golden.py` (names fixed; see the acceptance table). Update `test_cgl2_fact_use.py:92` from `== "cg-pharma-gates-8"` to `"cg-pharma-gates-9"`. The monotonic check in `test_cgl1_unparseable_time.py` must still pass unchanged.
5. **Legacy fixtures** in `casegraph/tests/fixtures/legacy_28ac4d2/`, produced by **main code at `28ac4d2`** in a throwaway `git worktree`, plus a committed generator script `make_legacy.py` whose docstring gives the exact commands:
   - (i) `export_0_4_T3.json`: the F-CXR T3 export with a S5 Pharma node.
   - (ii) `export_0_3_unstaged.json`: an unstaged `s2_config()` graph with a placeholder Pharma node, re-serialised as 0.3 using the recipe in `test_cg_t123_integrity.py::test_export_schema_0_4_and_legacy_0_3_import`.
   - (iii) `outputs/`: the OutputStore entry files (`<cache_key>.json`) for every node of (i) and (ii).

   Files are committed byte-for-byte as generated.
6. **CONDITIONS.** In `slices/CONDITIONS.md`:
   - Mark the L3 row `CLOSED (cg-l3, <date>)` with `cg-pharma-gates-9` and the test names below.
   - Add **L3-N1** (D4, LOW, gate as in D4).
   - Add **L3-F1** (LOW, gate: ui-dag build): ui-dag renders `MedicationIssues.gates_version` in the Pharma panel or the graph-versions node data. `null` is rendered as "recorded before cg-l3 (gates ≤8): render fact use from `use`, never `used`".

## Out of scope

- `backend/app/triage/casegraph_run.py` (`versions()`), `backend/app/triage/router.py` (`graph_versions`), `web/` (ui-dag); `research/`; `docs/` (the orchestrator records the closure in `docs/DECISIONS.md` at merge).
- Any change to gate decisions, supersession or tie rules, `use`/`reason` selection, statuses, checks, issues, KNOWN `[]` semantics. A pharmacist must still sign off these rules; that condition is unchanged.
- Rewriting stored outputs or exports. Replay never alters evidence. Legacy outputs keep no `gates_version` key.
- Export schema version bump, `s5-pipeline-2.6.0` bump, and versioning of non-Pharma bodies (L3-N1).

## Acceptance

| ID | Criterion | Threshold | How measured |
|---|---|---|---|
| L3a | Every Pharma output built on this branch carries `gates_version == PHARMA_GATES_VERSION`, on both the rules path and the model path, and also when served from cache | 100% of non-null Pharma outputs over the full golden corpus (≥200 entries incl. both anchors); a second `build_versions` on the same store (cache hits, `cached=True`) also 100%; `PHARMA_GATES_VERSION == "cg-pharma-gates-9"` | `test_cgl3_pharma_golden.py::test_every_pharma_output_carries_gates_version`, `::test_cached_pharma_output_carries_gates_version` |
| L3a-legacy | Legacy outputs made by `28ac4d2` still load, replay and re-export unchanged | For each of `export_0_4_T3.json` and `export_0_3_unstaged.json`: `import_graph` succeeds; the Pharma output has no `gates_version` key and `MedicationIssues.model_validate(...)` gives `gates_version is None`; `replay()` from the committed OutputStore (copied to tmp), both from the `ExportedGraph` and via a fresh `SQLiteStateStore` after `save_run(text)`, makes 0 gateway calls and 0 node executions (bodies monkeypatched to raise); `to_json(replayed) == text` byte-identical | `::test_legacy_28ac4d2_replays_byte_identical[0.4-T3,0.3-unstaged]`, `::test_legacy_medication_issues_has_null_gates_version` |
| L3b-1 | The golden file matches the current code | `compare()` returns only `ok` for every key | `::test_pharma_golden_matches` |
| L3b-2 | A planted gate change without a version bump FAILS | A monkeypatched gate that drops one `missing_inputs` token (e.g. wrap `Executor._conversation_allergy_gaps` to drop its first gap) leaves every affected Pharma node `status="ok"` (a silent change, not an error). `compare()` then reports ≥1 `semantics_changed_without_bump` and 0 `input_drift`, and `--write` exits 2 and leaves the golden file byte-identical | `::test_golden_detects_planted_gate_change` |
| L3b-3 | A version bump without regeneration FAILS | Monkeypatching `PHARMA_GATES_VERSION="cg-pharma-gates-next"` makes `compare()` report `version_mismatch` (and `--check` exits 1) | `::test_golden_detects_version_bump_without_regen` |
| L3b-4 | Regenerating with the documented helper after a bump PASSES | Under the bumped version, with and without the planted change: `--write` to a tmp golden path exits 0, prints the changed-`semantic_sha256` key list (non-empty with the planted change, empty without), and `compare()` against the new file is all `ok` | `::test_regenerate_after_bump_passes[plain,planted]` |
| L3b-5 | Input drift is reported separately from a semantics change | A golden copy with one entry's `input_sha256` altered: that key is `input_drift`, not `semantics_changed_without_bump`; `--write` without `--accept-input-drift` exits 2 | `::test_input_drift_is_reported_separately` |
| L3b-6 | The corpus is deterministic | Two fresh builds give identical entries; `--check` in two subprocesses with `PYTHONHASHSEED=0` and `=1` both exit 0 | `::test_corpus_is_deterministic` |
| L3c | Corpus coverage | Pharma `status`: ≥1 each of `evaluated`, `partially_evaluated`, `not_evaluated`. Fact `use`: ≥1 each of `used`, `partial`, `not_used`, `superseded`. ≥200 entries. `syn_subset` has 8 ids equal to the golden file's ids | `::test_golden_corpus_coverage` (reads the committed golden file and the live build) |
| L3d | Decision on non-Pharma bodies recorded | SPEC D4 present; `slices/CONDITIONS.md` has L3-N1 (tracked, gate stated) and L3-F1 (ui-dag) | checker reads both |
| L3g | No behaviour change other than the added field | For 100% of golden-corpus keys: `semantic_sha256` at branch head == `output_sha256` at `28ac4d2` (same keys, same count) | checker's independent differential: run the corpus builder on a `git worktree` of `28ac4d2` (copy the helper in, version field absent) and on head; report counts |
| L3h | Existing behaviour kept | 100% of pre-existing casegraph tests pass; the only edit to an existing test is the gates-8→9 constant in `test_cgl2_fact_use.py` | `pytest -q casegraph`; `git diff 28ac4d2 -- casegraph/tests/test_*.py` shows only that edit outside the new files |
| L3i | L3 recorded closed | The L3 row says `CLOSED (cg-l3, <date>)`, `cg-pharma-gates-9`, and the test names from L3a–L3c, and documents how to regenerate (`python -m casegraph.tests.pharma_golden --write`) | checker reads the row |
| L3e | Scope fence | `git diff --name-only 28ac4d2...HEAD` ⊆ `casegraph/**`, `slices/CONDITIONS.md`, `slices/cg-l3/**` | checker runs the command |
| L3f | Full suite green | `make test` recipe exits 0 (pytest + web + mobile). The known flaky web live-call F8 is accepted only if it passes on one rerun; any other failure fails L3f. New golden tests add ≤60 s | the recipe run directly (see run commands) |

## Required test cases (synthetic, offline)

- Golden corpus `cg-l3-corpus-1` as defined in Scope 3: 7 fixtures plus 8 dev SYN cases, × 17 VARIANTS, plus anchors `model_path` (`not_evaluated`) and `placeholder_api1` (`partially_evaluated`).
- Planted change (L3b-2): drop one conversation-allergy gap. Expected: silent `ok` outputs, ≥1 hash change, detected as `semantics_changed_without_bump`.
- Planted bump (L3b-3): `cg-pharma-gates-next`. Expected: `version_mismatch`.
- Planted input drift (L3b-5): one `input_sha256` altered in a tmp golden copy.
- Legacy: `export_0_4_T3.json` and `export_0_3_unstaged.json` plus their OutputStore entries, all made by `28ac4d2`.
- Stale-cache negative: Pharma built at gates-8 (monkeypatched) and then rebuilt at gates-9 on the same store is `cached=False` with a different `cache_key` and now carries `gates_version` (inside `::test_cached_pharma_output_carries_gates_version`).

## Clinical risks

- **R1 (legacy misread):** a reviewer or UI reads `used=True` on a superseded row from a gates ≤6 output. Mitigation: legacy outputs carry `gates_version=null`, which marks them as pre-cg-l3. L3-F1 requires ui-dag to label null and render from `use`.
- **R2 (false assurance):** the golden file only covers its corpus. A gate change that affects no corpus case passes the tripwire. Mitigation: the corpus uses every property VARIANT and all statuses and uses (L3c). The tripwire adds to review and the property sweep; it does not replace them. Do not cite it as proof of unchanged behaviour.
- **R3 (silencing a regression by bumping):** a developer bumps the version and regenerates to hide an unintended change. Mitigation: the helper prints every key whose `semantic_sha256` changed; the bump is a visible diff to `PHARMA_GATES_VERSION` and to the golden file; the reviewer must check that list against the intended change.
- **R4 (stale cache):** without D2 a gates-8 entry with no version field would be served. The bump prevents this, as the stale-cache negative test shows.
- **R5 (non-Pharma stale outputs, L3-N1):** a stale Red-flag output could hide a newly fired alert if executor-side Red-flag logic changes without a rule-set bump. This condition stays open with a gate and an interim rule (a fresh Output Store for every demo or evaluation run).
- **R6 (unchanged, human):** a pharmacist must still sign off the supersession, ties and KNOWN `[]` rules before any clinical use.

## Run commands

Worktrees have no `.venv` or `node_modules`, so use the main checkout's (no install, no network).

```bash
cd /Users/king_phuripol/AI-Engineer/01_Projects/Senior-Project/Full-Agent/.claude/worktrees/cg-l3
MAIN=/Users/king_phuripol/AI-Engineer/01_Projects/Senior-Project/Full-Agent
PY="env PYTHONPATH=backend:. $MAIN/.venv/bin/python"
$PY -m pytest -q casegraph/tests/test_cgl3_pharma_golden.py
$PY -m casegraph.tests.pharma_golden --check            # tripwire report; exit 1 on any non-ok class
# Regenerate (ONLY after a deliberate PHARMA_GATES_VERSION bump, or with reviewed input drift):
$PY -m casegraph.tests.pharma_golden --write [--accept-input-drift]
# Legacy fixtures (once, by the builder): see casegraph/tests/fixtures/legacy_28ac4d2/make_legacy.py docstring
#   git worktree add /tmp/cg-28ac4d2 28ac4d2 && (cd /tmp/cg-28ac4d2 && PYTHONPATH=backend:. $MAIN/.venv/bin/python <path>/make_legacy.py --out <fixture dir>)
$PY -m pytest -q casegraph
# L3f = the `make test` recipe run directly. Do not run `make test` here: make would pip-install into the main venv.
ln -sfn $MAIN/web/node_modules web/node_modules; ln -sfn $MAIN/mobile/node_modules mobile/node_modules
$PY -m pytest -q -rs
(cd web && npm test) && (cd mobile && npm test && npm run typecheck)
rm web/node_modules mobile/node_modules   # symlinks are not ignored by .gitignore; never commit them
git diff --name-only 28ac4d2...HEAD
```
