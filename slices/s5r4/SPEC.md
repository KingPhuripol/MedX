# Slice s5r4 — Pharma Agent v1.4 (dose grammar rev 3, bounded adversarial scope)

- Owner (Gantt): ธัญรดา / ภูริณัฐ
- Source of truth: `docs/PROPOSAL.md` (v8) 3.2.4 (rules are primary; dose or frequency differences between sources are flagged for pharmacist review) and 3.6 / Table 3.2 (recall from synthetic error injection, patient-level bootstrap CIs, System Evaluation label).
- **This spec is a pointer.** The behaviour to build is `slices/s5r3/SPEC.md` **revision 3** (commits `5fb09a9`, `e8b7ebb`). Build it on top of the rev-2 code at `e6a354f`. Everything in `slices/s5/`, `s5r/`, `s5r2/` and `s5r3/SPEC.md` still applies. Where this file differs, this file wins. It adds only the **stopping rule** and the **residual-risk file**.
- Status: PLAN. All data is synthetic. Tier 0 only. No external provider. Servers, if started: API 8105, web 3105. Branch `factory/s5r4`.

## Scope

1. Implement s5r3 rev 3 in `backend/app/pharma/mock_rules.py`, in the reference parser `backend/tests/pharma_dose_reference.py`, and in the fuzz generator `backend/tests/pharma_dose_fuzz.py`:
   - **G1 INVISIBLE.** Any character in categories Cc/Cf/Co/Cs/Cn, or on the explicit list, is numeric-ish and never consumed.
   - **G1 SLASH-LIKE.** Every character whose Unicode name contains SOLIDUS or SLASH, plus U+2216, is numeric-ish everywhere. The only exception is an ASCII `/` consumed inside FRAC, S2 or L1.
   - **R1 anchor TAIL.** Covers rules (a), (b) and (c), the NEUTRAL set, and `a day|week|month`.
   - **Q4b closed follower list QF.**
   - **D1 markers** (daily total or divided dose, TH and EN): these give `per_unit_amount`.
   - **Version bumps:**
     - `MOCK_RULES_VERSION = "s5-mock-rules-2.2.0"`
     - `DOSE_GRAMMAR_VERSION = "s5-dose-grammar-1.2.0"`
     - `PIPELINE_VERSION = "s5-pipeline-2.4.0"`
     - `TEMPLATE_VERSION` and `RULES_VERSION` do not change.
2. Add the rev-3 tests listed in s5r3 "Required test cases":
   - probe suites I, SL, DT, D and QF;
   - `test_invisible_set` and `test_slash_like_set`;
   - the five new fuzz classes and the §F.5 closure properties;
   - `test_fuzz_catches_piecewise_stub` with 10 classes;
   - the amended constants tests.

   Write invisible characters in test sources as `\uXXXX` escapes, never as literal characters. Note that s5r3 `SPEC.md` line 438 contains a literal U+200B inside `เม็ดครึ่ง`.
3. Add a test that proves the fuzz has teeth against the old parser: `test_fuzz_catches_e6a354f`. It loads the `e6a354f` parser from a **frozen copy** at `backend/tests/legacy/mock_rules_e6a354f.py`, which is byte-identical to `git show e6a354f:backend/app/pharma/mock_rules.py`, with its sha256 pinned in the test. The test then runs the same harness over the same seed.
4. Write `slices/s5r4/RESIDUAL_RISK.md` (format in §R).

## Stopping rule (bounds the adversarial loop; set by the orchestrator)

The checker probes the **declared threat classes** and runs the fuzz harness:

- the declared classes are F1–F7 and P, H, U, V, W, I, SL, DT, D and QF, all from the s5r3 tables;
- the fuzz harness covers every s5r3 §F class.

It may also try its own new probes. Every finding is classified as exactly one of the following.

| Class | Definition | Outcome |
|---|---|---|
| **CONFORMANCE FAIL** | The implementation disagrees with s5r3 rev 3 as written. This covers any listed probe row that is not exact, any fuzz disagreement with the reference, and any closure-property violation. It applies whatever the input alphabet. | FAIL, back to the **builder** |
| **BLOCKER (spec gap)** | Both the implementation and the reference **resolve** a *plausibly typed* entry to a wrong value, dose or quantity (a MISREAD), and the input is outside any rule. | FAIL, back to the **planner** (rev 4) |
| **RESIDUAL** | The same kind of MISREAD, but on an entry that is **not** plausibly typed. | Recorded in `RESIDUAL_RISK.md`, pending pharmacist acceptance. **Not** a blocker |
| **SAFE** | The entry comes out `unverifiable` (any reason) or `not_stated`, including checker-invented probes where the checker would have preferred `resolved`. | Never a failure. The checker may add an alert-burden note |

**Plausibly typed** (closed and measurable): every character of the entry is in PLAUSIBLE, which is the union of:

- ASCII U+0020–U+007E;
- the Thai block U+0E00–U+0E7F;
- any `str.isspace()` character;
- `½ ¼ ¾ × – — µ ‘ ’ “ ” …`, which are common autocorrect or IME output.

An entry that contains any other code point is not plausibly typed. A MISREAD on such an entry is RESIDUAL unless it is a CONFORMANCE FAIL. The checker reports the out-of-set code points for every RESIDUAL finding.

## §R — `RESIDUAL_RISK.md` format

The file has one table row per risk, with these columns:

- `id`;
- `class`;
- example input (code points written as `<U+XXXX>`);
- observed output: status, value and quantity;
- why it is not plausibly typed, or why the text cannot tell the cases apart;
- found by: planner, checker or fuzz;
- status: `pending pharmacist acceptance`.

The file must contain:

- **RR-01, declared by the planner.** A daily total written with **no** D1 marker is read as per dose. Example: `เมทฟอร์มิน 1000 มก. วันละ 2 ครั้ง` meant as 1000 mg per day resolves as 1000 mg per dose, q12h. Reference: s5r3 D11, Out of scope, and Decisions.
- One row for **every** RESIDUAL finding from the checker round(s) of this slice. If there are none, the file says so explicitly.

The planner and builder may not mark any row accepted. Only a pharmacist or the owner can, recorded in `docs/DECISIONS.md`.

## Out of scope

- Everything that s5r3 declares out of scope, unchanged. That includes: no reading of unmarked daily totals, no new reason values, no new eval cases, no manifest change, no gateway or contract change, and no external provider.
- Grammar changes beyond rev 3. A spec-gap BLOCKER goes back to the planner. It is not patched by the builder.
- Homoglyph and rare-Unicode classes that are not plausibly typed. Record them; do not fix them.
- Accepting any residual risk. That needs a human decision.

## Acceptance

Thresholds apply to the frozen `test` split **and** to all patients. Report both.

| ID | Criterion | Threshold | How measured |
|---|---|---|---|
| S5R4-A01 | All prior items still pass | S5-A01..A18, S5R-A01..A11, S5R2-A01..A18 and S5R3-A01..A23 pass (S5R3-A19..A23 are measured by S5R4-A04..A09). The only amendments allowed are those s5r3 rev 3 lists: versions, the D1 entry in the table set, 10 stub classes, and rev-2 `test_pharma_s5r3.py` expectations only where an input falls under a rev-3 rule. The builder report lists each changed expectation → rev-3 rule. Any other changed expectation is a STOP | `make test`, `make pharma-eval`, `make e2e-pharma`; per-ID checklist in the builder report |
| S5R4-A02 | `make test` green | Exit 0; 0 failed, 0 errors, 0 skip/xfail in pharma tests; offline; the fuzz test takes ≤ 20 s, and each code-point sweep takes ≤ 5 s | `make test` from a clean clone of `factory/s5r4` |
| S5R4-A03 | Grammar table closed with D1 | `DOSE_GRAMMAR` IDs are exactly {S1,S2,S3,L1,R1,D1,Q1..Q7,T1,F1,F2,F3}. QF, NEUTRAL, the explicit INVISIBLE list and the D1 lexicon are each one constant. 0 deleted piecewise regex names. Every `resolved` trace has 0 unconsumed numeric-ish tokens | pytest `test_grammar_table_closed`, `test_no_piecewise_dose_regex`, `test_resolved_consumes_all_numeric_tokens` |
| S5R4-A04 | I-probes | 10/10 exact (status, reason, null dose/qty). I1 is `ambiguous_quantity`, never 1.5 | pytest `test_probe_invisible[I1..I10]` |
| S5R4-A05 | SL-probes | 11/11 exact, including the SL11 resolved control (3 mg, qty 0.5, q24h) and the listed Freq | pytest `test_probe_slash_like[SL1..SL11]` |
| S5R4-A06 | DT-probes | 15/15 exact, including 4 resolved controls DT12–DT15 with the listed Freq | pytest `test_probe_unit_tail[DT1..DT15]` |
| S5R4-A07 | D-probes | 12/12 exact status, reason and Freq. D11 and D12 stay resolved | pytest `test_probe_daily_total[D1..D12]` |
| S5R4-A08 | QF-probes | 12/12 exact. H1–H13, F4a and F4b are unchanged. Joined and spaced QF forms give identical output | pytest `test_probe_q4b_follower[QF1..QF12]`, `test_probe_half_hour`, `test_half_whitespace_equivalent` |
| S5R4-A09 | Computed sets | The INVISIBLE and SLASH-LIKE predicates equal the s5r3 §G1 definitions on 100% of code points 0..U+10FFFF. They contain the listed must-have code points (8 and 9) | pytest `test_invisible_set`, `test_slash_like_set` |
| S5R4-A10 | Unverifiable is visible | For I1, SL1, DT1, D1 and QF1 in a two-source snapshot: exactly 1 `missing_field(dose)` (`field_status=unverifiable`, reason) and 0 `dose_mismatch`; `unchecked_by_reason.unverifiable` +1 per pair | pytest `test_negative_raises_missing_dose[...]` (rev-3 cases) |
| S5R4-A11 | Fuzz: 0 misreads | ≥ 2000 phrases (seed 5303). Every production and every class, including `invisible`, `slash_like`, `dotted_tail`, `daily_total` and `q4b_follower`, has ≥ 20 phrases. Resolved ≥ 25%, unverifiable ≥ 25%, EN and TH quantity segments ≥ 30% each. **0** safety violations; 100% status and reason agreement; 100% reference check; 0 resolved quantity > 10 | pytest `test_dose_fuzz_vs_reference` |
| S5R4-A12 | Closure properties | Over every generated phrase, 0 `resolved` outputs for phrases that contain (a) an INVISIBLE character, (b) a SLASH-LIKE character other than a consumed U+002F in FRAC, S2 or L1, or (c) a D1 marker | assertions in `test_dose_fuzz_vs_reference` (§F.5) |
| S5R4-A13 | Tests have teeth | The harness finds ≥ 1 safety misread **in each** of `invisible`, `slash_like`, `dotted_tail`, `daily_total` and `q4b_follower` on the frozen `e6a354f` parser. The piecewise stub is caught in each of the 10 s5r3 §F.4 classes. The checker also reports ≥ 1 misread on `1c1f476` and `29d8b20` as in S5R3-A07 | pytest `test_fuzz_catches_e6a354f` (legacy copy, sha256 pinned), `test_fuzz_catches_piecewise_stub`; checker run with `git show <rev>:backend/app/pharma/mock_rules.py` |
| S5R4-A14 | Reference independent | `pharma_dose_reference.py` imports no `app.*` module (AST scan). It shares no regex literal with `mock_rules.py`. It computes INVISIBLE and SLASH-LIKE from `unicodedata` with its own code | pytest `test_reference_independent` |
| S5R4-A15 | Frequency unchanged | 100% of fixture entries and existing test inputs match the pinned `1c1f476` frequency table (only the s5r3 §4 Q5-fraction exception). Every rev-3 probe with a Freq column equals that Freq, which equals the frequency of the same entry with the D1, R1 or QF segment removed | pytest `test_frequency_unchanged`, `test_t1_r1_frequency_neutral` (SL, DT, D, QF) |
| S5R4-A16 | Versions | The exact strings `s5-mock-rules-2.2.0`, `s5-dose-grammar-1.2.0` and `s5-pipeline-2.4.0` appear in the code, in every run record and in `results.json.versions`. `template-1.3.0` and `RULES_VERSION` are unchanged | pytest `test_versions_bumped` (amended) |
| S5R4-A17 | Frozen data untouched | sha256 of `fixtures/patients.json`, `fixtures/test_manifest.json` (v3), `injection_log.jsonl` and `injection_log_surface.jsonl` equals `1c1f476`. The generators are byte-identical. 0 new eval cases | pytest `test_frozen_artifacts_unchanged`; `git diff 1c1f476 --stat` in the builder report |
| S5R4-A18 | Evaluation holds | Every `results.json` field except `versions` and `notes` equals `1c1f476`. That covers: recall ≥ 0.95 per each of 9 types and each surface form (test and all); clean false alerts ≤ 0.10; extra issues/case ≤ 0.10; extraction accuracy ≥ 0.98; label = System Evaluation | `make pharma-eval`; pytest `test_eval_thresholds`, `test_results_unchanged_except_versions` |
| S5R4-A19 | Clean fixtures use only grammar forms | 96/96 clean entries are `resolved` with the gold quantity. 0 of them hit R1, D1, a QF failure, INVISIBLE or an unconsumed SLASH-LIKE character. 100% of surface-suite `after` strings give their logged status and reason | pytest `test_clean_fixtures_grammar_only`, `test_surface_after_strings_expected` |
| S5R4-A20 | Labels, wording, UI | 7/7 reason labels in `phrasing.py` and `web/lib/pharma.ts`. `notes[0]` and the page scope say "could not be verified", not "may be misread". 0 serious or critical axe violations; 0 colour literals; 0 `diagnos\|prescrib\|treat` in UI copy | pytest `test_reason_labels_complete`, `test_results_notes_grammar`; Vitest `pharma-page.test.tsx`; `make e2e-pharma`; s0 `test_repo_hygiene` |
| S5R4-A21 | Stopping rule applied | The checker report classifies every finding as CONFORMANCE FAIL, BLOCKER, RESIDUAL or SAFE using the table above. It lists the non-PLAUSIBLE code points for each RESIDUAL. PASS requires **0 CONFORMANCE FAIL and 0 BLOCKER**. SAFE findings never fail the slice | checker report; the checker's PLAUSIBLE check is a script over each finding's code points |
| S5R4-A22 | Residual risk recorded | `slices/s5r4/RESIDUAL_RISK.md` exists in §R format. It contains RR-01 (unmarked daily total, example D11) and 1 row per checker RESIDUAL finding, or an explicit "none found". Every row has status `pending pharmacist acceptance`. 0 rows are marked accepted by an agent | file review by checker and reviewer; `grep -c "pending pharmacist acceptance"` ≥ number of rows |

## Required test cases

- New or extended in `backend/tests/test_pharma_s5r3.py` (or `test_pharma_s5r4.py`):
  - `test_probe_invisible`, `test_probe_slash_like`, `test_probe_unit_tail`, `test_probe_daily_total`, `test_probe_q4b_follower`, with rows exactly as in the s5r3 rev-3 tables;
  - `test_invisible_set` and `test_slash_like_set`;
  - `test_negative_raises_missing_dose` for I1, SL1, DT1, D1 and QF1;
  - `test_fuzz_catches_e6a354f`;
  - the amended `test_fuzz_catches_piecewise_stub` (10 classes), `test_grammar_table_closed` and `test_versions_bumped`;
  - `test_t1_r1_frequency_neutral`, extended to SL, DT, D and QF.
- Fuzz generator: the classes `invisible`, `slash_like`, `dotted_tail`, `daily_total` and `q4b_follower`, each ≥ 20 phrases, as specified in s5r3 §F.
- Every s5/s5r/s5r2/s5r3 test stays in place. Only the listed amendments are allowed.

## Clinical risks

| Risk | Mitigation |
|---|---|
| A hidden character or a slash look-alike turns a per-day total or a half-hour into a resolved per-dose value (e.g. 1.5 tablets of warfarin) | INVISIBLE and SLASH-LIKE are computed sets that are never consumed. There is a full code-point sweep and a fuzz closure property (A04, A05, A09, A12). |
| A divided daily total is read as per dose (a 2× overdose that looks like agreement) | D1 markers give `per_unit_amount` (A07). An **unmarked** total stays a residual risk (RR-01): declared, not accepted. It blocks any non-synthetic use until a pharmacist or the owner accepts it. |
| The adversarial loop never converges, so the slice never ships | The stopping rule bounds it. Only a plausibly typed MISREAD or a spec-conformance failure blocks. Exotic classes are recorded (A21, A22). |
| An exotic misread is recorded but then forgotten | `RESIDUAL_RISK.md` rows stay `pending pharmacist acceptance`. Pharmacist sign-off on the grammar (s5r3 Decisions) is needed before non-synthetic use. |
| The PLAUSIBLE set is too narrow, so a real keyboard or IME character is treated as exotic | The set is closed and written in this spec. The reviewer checks it against Thai Kedmanee, US keyboard and common autocorrect output. Widening it is a planner change. |
| More `missing_field(dose)` alerts (burden) | Clean fixtures are unchanged (A18, A19). Real-list alert volume must be measured with a pharmacist before non-synthetic use. |
| Tuning on the test split | 0 new eval cases; hashes are pinned; metrics are identical (A17, A18). |

## Run commands

```bash
cd /Users/king_phuripol/AI-Engineer/01_Projects/Senior-Project/Full-Agent-s5
make test                                                  # all tests incl. probes, sweeps, fuzz (offline)
cd backend && python -m pytest tests/test_pharma_s5r3.py -q -k "probe or fuzz or set"   # rev-3 focus
make pharma-eval                                           # results.json == 1c1f476 except versions/notes
make dev API_PORT=8105 WEB_PORT=3105                       # http://127.0.0.1:3105/pharmacist/reconcile
make e2e-pharma
git show e6a354f:backend/app/pharma/mock_rules.py | shasum -a 256   # must equal the pinned legacy-copy hash
```

## Decisions needed (none blocking this synthetic slice)

- **Pharmacist and owner:** accept or reject each `RESIDUAL_RISK.md` row, starting with RR-01. Record the decision in `docs/DECISIONS.md`. Until then, every row blocks non-synthetic use.
- **Pharmacist:** sign off on the rev-3 QF list, the NEUTRAL set and the D1 lexicon (carried over from s5r3), and on the PLAUSIBLE alphabet defined here.
