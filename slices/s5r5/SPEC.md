# Slice s5r5 — Pharma Agent v1.5 (dose grammar rev 5, final round)

- Owner (Gantt): ธัญรดา / ภูริณัฐ
- Source of truth: `docs/PROPOSAL.md` (v8) 3.2.4 (rules are primary; dose or frequency differences between sources go to the pharmacist) and 3.6 / Table 3.2 (recall from synthetic error injection, patient-level bootstrap CIs, System Evaluation label).
- **Authority:** `docs/DECISIONS.md`, entry "2026-09-28 — S5 Pharma: final dose-grammar round (rev 5), then close" (owner, commit `8f3d558` on this branch). That entry settles the s5r4 "Decisions needed" item on the rev-5 route.
- **This file is a pointer. It adds no rules.** The spec is `slices/s5r4/SPEC.md` **revision 5, commit `86ccf86`**, used exactly as written: §N, §C1 (bare period words only inside the closed phrase lists), §P (P3 whole-word list, P4 DAILY + MULTI anywhere in the dose region → `per_unit_amount`, `TIME_SLOTS`), §D (`drug_name_raw` may show the §N spelling; `raw_span` stays N1 + N5), the probe tables, required tests, run commands and versions. Everything in `slices/s5/`, `s5r/`, `s5r2/` and `s5r3/SPEC.md` still applies through it. Where this file and rev 5 differ, only the **closing rule** below changes rev 5.
- **Base:** `d2ff98c`. The branch already holds rev-5 build commits `cbb879b`, `55c0a62`, `b3c9659`, `7c90a0a` and `444ca3e`. The builder checks them against rev 5 and fixes only what does not conform.
- Status: PLAN. All data is synthetic. Tier 0 only. No external provider, gateway change or contract change. Servers, if started, use API 8105 and web 3105. Branch `factory/s5r5`.

## Scope

1. Build rev 5 of `slices/s5r4/SPEC.md` (`86ccf86`) on top of `d2ff98c`:
   - `backend/app/pharma/mock_rules.py` and its own copy in `backend/tests/pharma_dose_reference.py` (which imports nothing from `app.*`);
   - the four rev-5 fuzz classes in `backend/tests/pharma_dose_fuzz.py`;
   - the rev-5 tests in `backend/tests/test_pharma_s5r4.py`;
   - `backend/tests/legacy/mock_rules_d2ff98c.py`, with its sha256 pinned;
   - the versions `s5-mock-rules-2.4.0`, `s5-dose-grammar-1.4.0` and `s5-pipeline-2.6.0`.
2. Run one checker round and one reviewer round against rev 5.
3. Apply the closing rule. The planner updates `slices/s5r4/RESIDUAL_RISK.md` and the slice closes.

## Out of scope

- Any new rule, vocabulary word, production, reason value or probe expectation. Rev 5 is final. This file does not change `slices/s5r4/SPEC.md`.
- Another grammar revision (no rev 6 and no s5r6 grammar slice) before the 8–9 Oct Proposal presentation.
- Reading unmarked daily totals (RR-01) or name-region modifiers (RR-07).
- New eval cases, and changes to the manifest, gateway, Model API contract or providers.
- Accepting any residual row. Only a pharmacist or the owner can do that, recorded in `docs/DECISIONS.md`.

## Closing rule (owner decision 2026-09-28; replaces the rev-5 outcome column for this round only)

The checker classifies every finding with the s5r4 stopping-rule table (CONFORMANCE FAIL / BLOCKER / RESIDUAL / SAFE). It records the meaning a pharmacist would read and the code points that are not PLAUSIBLE.

- **CONFORMANCE FAIL** means the code disagrees with rev 5: a listed probe row, the reference in the fuzz, a closure property, the sibling sweep or a listed test. It goes back to the **builder**. This is the only loop-back.
- **Every other finding** is written by the **planner** into `slices/s5r4/RESIDUAL_RISK.md` under "Checker RESIDUAL findings, rev-5 round", one §R-format row each, with status `pending pharmacist acceptance`. Other findings are BLOCKER, RESIDUAL, SAFE alert-burden notes, and spec errata where rev 5 itself is ambiguous or inconsistent. Each row keeps its original class in the `class` column, so a BLOCKER row reads "BLOCKER (plausibly typed MISREAD) — recorded under owner decision 2026-09-28". If there are none, the planner writes "none found (rev-5 round)". This is a docs-only commit.
- No agent may drop a finding or change its class. A BLOCKER row still blocks all non-synthetic use until a pharmacist or the owner accepts it.
- After that commit and a reviewer verdict that is not FAIL, the slice closes.

## Acceptance

Thresholds apply to the frozen `test` split **and** to all patients. Report both.

| ID | Criterion | Threshold | How measured |
|---|---|---|---|
| S5R5-A01 | Rev-5 core items pass | S5R4-A01..A13 pass as written in `86ccf86`, 13/13. This covers prior items (A01), `make test` (A02), grammar closed (A03), rev-3/rev-4 probe tables (A04, A05), B1–B24 24/24 not resolved with the exact reason (A06), K9–K19 11/11 resolved with exact values (A07), 454/454 sibling phrases not resolved in both implementation and reference (A08), 100% neutral on `_existing_inputs()` vs `d2ff98c` (A09), the A10 `missing_field(dose)` list, fuzz ≥ 2000 phrases with 0 misreads and 100% agreement with the reference (A11), closure properties (a)–(g) (A12), and teeth on frozen `e6a354f`/`6b2a67a`/`d2ff98c` for every class (A13) | the pytest names in `slices/s5r4/SPEC.md` A01–A13; per-ID checklist with evidence in the builder report |
| S5R5-A02 | Rest of rev 5 passes | S5R4-A14..A20 pass, 7/7: reference independence (A14), frequency unchanged (A15), versions (A16), frozen data (A17), evaluation (A18), clean fixtures use only grammar forms (A19), labels/wording/UI including §D "Name read" (A20) | pytest names in `slices/s5r4/SPEC.md` A14–A20; Vitest `pharma-page.test.tsx`; `make e2e-pharma` |
| S5R5-A03 | `make test` green | Exit 0. 0 failed, 0 errors, 0 skip/xfail in pharma tests. Runs offline. Fuzz test ≤ 20 s; each code-point sweep ≤ 5 s | `make test` from a clean checkout of `factory/s5r5` |
| S5R5-A04 | No new rules | `git diff 86ccf86 -- slices/s5r4/SPEC.md` is empty. `DOSE_GRAMMAR` IDs, `V_EN_FREE`, `V_TH_FREE`, `V_EN_PHRASES`, `P3_WORDS`, P4 DAILY/MULTI and `TIME_SLOTS` equal the rev-5 lists exactly. The reason enum has 7 values | `git diff`; pytest `test_vocab_sets_match_spec`, `test_grammar_table_closed`, `test_reason_labels_complete` |
| S5R5-A05 | Versions | The exact strings `s5-mock-rules-2.4.0`, `s5-dose-grammar-1.4.0` and `s5-pipeline-2.6.0` appear in the code, every run record and `results.json.versions`. `template-1.3.0` and `s5-rules-2.1.0` are unchanged | pytest `test_versions_bumped` |
| S5R5-A06 | Frozen v3 data unchanged | The sha256 of `backend/app/pharma/fixtures/patients.json`, `backend/app/pharma/fixtures/test_manifest.json` (v3), `slices/s5/eval/injection_log.jsonl` and `slices/s5/eval/injection_log_surface.jsonl` equals `1c1f476`. The generators are byte-identical. 0 new eval cases | pytest `test_frozen_artifacts_unchanged`; `git diff 1c1f476 --stat -- backend/app/pharma/fixtures slices/s5/eval` shows only `results.json` |
| S5R5-A07 | Recall and false-alert thresholds hold | For each of the 9 discrepancy types and each surface form, test split and all patients: recall ≥ 0.95. Clean false alerts per list ≤ 0.10. Extra issues per case ≤ 0.10. Extraction accuracy ≥ 0.98. Label = System Evaluation. Every `results.json` field except `versions` and `notes` equals `1c1f476` | `make pharma-eval`; pytest `test_eval_thresholds`, `test_results_unchanged_except_versions` |
| S5R5-A08 | 0 conformance failures | The checker report lists **0 CONFORMANCE FAIL** against rev 5, across every probe table, the fuzz vs the reference, closure properties (a)–(g), the sibling sweep and the listed tests. Round-1 items (HT1–9, DD1–5, PD1–6) and round-2 items (B1a–B4b, AB1) are re-run: B1a–B4b are not `resolved`, and AB1 `Perindopril 4 mg od` is resolved at 4 mg, q24h | checker report; `tests/e2e/s5r4_classify_findings.py`, `s5r4_r2_classify_findings.py`, `s5r4_r2_sibling_sweep.py`, plus the checker's rev-5 round script(s) under `tests/e2e/s5r5_*` |
| S5R5-A09 | Every other finding recorded | Every checker finding that is not a CONFORMANCE FAIL has exactly 1 row in `RESIDUAL_RISK.md` under "rev-5 round". The rows are in §R format, keep the original class, and match the report 1:1. If there are none, the file says "none found (rev-5 round)". The "Pending the rev-5 checker round" placeholder is gone | reviewer compares the rows 1:1 with the checker report |
| S5R5-A10 | Residual rows stay pending | RR-01..RR-07 are still listed, with their text unchanged from `86ccf86`. Every row says `pending pharmacist acceptance`, and 0 rows are accepted | `git diff 86ccf86 -- slices/s5r4/RESIDUAL_RISK.md` shows only additions under "rev-5 round"; `grep -c "pending pharmacist acceptance"` equals the row count |
| S5R5-A11 | Slice closes, no further revision | After the RESIDUAL_RISK commit, 0 commits change `slices/s5r4/SPEC.md` or add a grammar spec. Product-code changes after the checker round only fix CONFORMANCE FAILs, and each one names the probe or test it fixes | `git log 8f3d558..HEAD -- slices/ backend/app/pharma/`; reviewer verdict |
| S5R5-A12 | Claim boundary and safety wording | Pharma UI copy contains 0 matches of `diagnos\|prescrib\|treat`. Page scope and `notes[0]` say "could not be verified". 0 serious or critical axe violations. 0 colour literals outside `web/app/theme.css` | covered by S5R4-A20 tests, `make e2e-pharma` (`pharma-a11y.spec.ts`) and s0 `test_repo_hygiene` |

## Required test cases

- Those listed in `slices/s5r4/SPEC.md` "Required test cases" (rev 5): `test_probe_rev5_blockers[B1..B24]`, `test_probe_controls[K1..K19]`, `test_rev5_sibling_sweep`, `test_rev5_neutral_on_existing`, `test_name_read_uses_normalised_spelling`, `test_fuzz_catches_d2ff98c`, the amended `test_grammar_table_closed`, `test_vocab_sets_match_spec`, `test_versions_bumped` and `test_t1_r1_frequency_neutral`, and the A10 rows in `test_negative_raises_missing_dose`. The four fuzz classes `bare_period`, `daily_anywhere`, `daily_slots` and `daily_abbrev` must have ≥ 20 phrases each.
- Every s5, s5r, s5r2, s5r3 and s5r4 test stays in place. Only the S5R4-A01 amendments are allowed.
- Checker: re-run the rev-4 round-1 and round-2 scripts, then add rev-5 probes named `tests/e2e/s5r5_*`. These are not committed under `slices/`. For every finding, the checker records its meaning, class and any code points that are not PLAUSIBLE.

## Clinical risks

| Risk | Mitigation |
|---|---|
| A plausibly typed misread (BLOCKER) is found and recorded rather than fixed | The owner decided this on 2026-09-28. The row keeps the BLOCKER label and blocks non-synthetic use until a pharmacist or the owner accepts it. The finding is not dropped or reclassified |
| Rev-5 build drifts from the spec, for example a vocabulary word added or dropped | S5R5-A04 compares exactly with the rev-5 lists. The reference is written independently (S5R4-A14) |
| Fixing a conformance failure changes eval results or tunes on the test split | Frozen hashes (A06). `results.json` must equal `1c1f476` except `versions`/`notes` (A07). 0 new eval cases |
| Unmarked daily totals (RR-01) and name-region modifiers (RR-07) are still read per dose | Declared, not accepted. Shown in `RESIDUAL_RISK.md` as pending pharmacist acceptance (A10) |
| Alert burden from `unverifiable` (e.g. AB2 `Warfarin 3 mg 1 tab od (Coumadin)`) | These count as SAFE, so they are recorded as rows for pharmacist review and never loop back as a grammar change |

## Run commands

```bash
cd /Users/king_phuripol/AI-Engineer/Workstreams/SeniorProject/Full-Agent-s5
make test
cd backend && ../.venv/bin/python -m pytest tests/test_pharma_s5r4.py tests/test_pharma_s5r3.py -q && cd ..
make pharma-eval                                     # results.json == 1c1f476 except versions/notes
make dev API_PORT=8105 WEB_PORT=3105                 # http://127.0.0.1:3105/pharmacist/reconcile
make e2e-pharma
git show d2ff98c:backend/app/pharma/mock_rules.py | shasum -a 256   # equals the pinned legacy-copy hash
git diff 86ccf86 -- slices/s5r4/SPEC.md             # must be empty
git diff 1c1f476 --stat -- backend/app/pharma/fixtures slices/s5/eval
.venv/bin/python tests/e2e/s5r4_r2_sibling_sweep.py     # 0 resolved
.venv/bin/python tests/e2e/s5r4_r2_classify_findings.py # B1a-B4b not resolved, AB1 resolved
```

## Decisions needed (none block this synthetic slice)

- **Pharmacist and owner:** accept or reject every `RESIDUAL_RISK.md` row, including RR-01..RR-07 and any rev-5 round rows (BLOCKER rows first). Record each decision in `docs/DECISIONS.md`.
- **Pharmacist:** sign off on the rev-5 vocabularies (`V_EN_FREE`, `V_TH_FREE`, `V_EN_PHRASES`, `P3_WORDS`, P4 DAILY/MULTI, `TIME_SLOTS`), as listed in the 2026-09-28 decision.
