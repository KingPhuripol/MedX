# Slice s5r4 — Pharma Agent v1.4 (dose grammar rev 5, final; bounded adversarial scope)

- Owner (Gantt): ธัญรดา / ภูริณัฐ
- Source of truth: `docs/PROPOSAL.md` (v8) 3.2.4 (rules are primary; dose or frequency differences between sources are flagged for pharmacist review) and 3.6 / Table 3.2 (recall from synthetic error injection, patient-level bootstrap CIs, System Evaluation label).
- **Base.** `slices/s5r3/SPEC.md` revision 3 (commits `5fb09a9`, `e8b7ebb`), plus rev 4 of this file (`e52489e`) as built up to `d2ff98c`. Everything in `slices/s5/`, `s5r/`, `s5r2/` and `s5r3/SPEC.md` still applies. Where this file differs, this file wins.
- **Revision 5 of this file.** It follows s5r4 checker round 2 on `d2ff98c`, which found 4 BLOCKER classes (B1–B4), 0 RESIDUAL, 0 CONFORMANCE FAIL, 1 alert-burden note and 1 minor item (`tests/e2e/s5r4_r2_classify_findings.py`, `s5r4_r2_sibling_sweep.py`). The orchestrator sent the B findings back as a rev 5 and says this is the **final** S5 grammar revision. Under the rev-4 stopping rule, the **owner** chooses between a rev 5 and recording BLOCKERs as residual risk. That choice is not recorded in `docs/DECISIONS.md` (see Decisions needed). Rev 5 only moves entries toward `unverifiable`, except for the P3 narrowing, which removes false alerts on drug names. Rev 5 fixes classes, not instances:
  1. **§C1 amendment: bare period words are not free text** (fixes B1). `day`, `days`, `week` and `month` leave `V_EN_FREE`, and `วัน` leaves `V_TH_FREE`. They are accepted only inside a closed list of frequency phrases. So `mg day`, `มก. วัน` and `mg po day` can no longer be silently ignored.
  2. **§P4 rewritten: the daily and multi-dose conflict is checked anywhere in the dose region** (fixes B2, B3, B4). Any once-daily statement in the dose region, written anywhere and in any closed form (`daily`, `qd`/`q.d.`, `od`, `every day`, `ทุกวัน`, q24h, once a day, `วันละ(1)ครั้ง`), plus any multi-dose statement (the rev-4 list **or ≥ 2 distinct time-of-day slots**) gives `per_unit_amount`. A vocabulary word in between (`po`, `with meals`, `รับประทาน` …) no longer defeats it.
  3. **§P3 narrowed** (alert-burden note). A name-region word fires only when it *is* one of a closed word list. A word that merely *starts with* `per` no longer fires, so `Perindopril` and `Perphenazine` resolve.
  4. **§D display rule** (minor). `drug_name_raw` ("Name read") may show the §N spelling. `raw_span` stays N1 + N5.
  5. **Version bumps:**
     - `MOCK_RULES_VERSION = "s5-mock-rules-2.4.0"`
     - `DOSE_GRAMMAR_VERSION = "s5-dose-grammar-1.4.0"`
     - `PIPELINE_VERSION = "s5-pipeline-2.6.0"`
     - `TEMPLATE_VERSION` (`template-1.3.0`) and `RULES_VERSION` do not change. No reason value is added.
- **Planner prototype (before writing).** Rev-5 rules were applied on top of `d2ff98c` with these results:
  - 0 of 1435 resolved existing inputs change (2083 unique fixture, eval-log, pinned and pre-rev-4 test strings, from `_existing_inputs()`);
  - 0 of 309 rev-3 and rev-4 probe rows change;
  - 0 of the 454 checker B-sibling phrases stay resolved;
  - 16 of 5000 fuzz phrases change. Each of the 16 holds two conflicting frequencies, for example `1×1 q6h … วันละ 1 ครั้ง`. P4 (d4) makes them `per_unit_amount`, and resolved fuzz phrases stay at 39%.
- Status: PLAN rev 5. All data is synthetic. Tier 0 only. No external provider, gateway change or contract change. Servers, if started: API 8105, web 3105. Branch `factory/s5r4`.

## Scope

1. Implement the rev-4 rules §N, §C1 and §P, which are already built and stay as they are, together with the rev-5 amendments below. Change `backend/app/pharma/mock_rules.py`, and make the same changes independently in `backend/tests/pharma_dose_reference.py`: it uses its own code and imports nothing from `app.*`.
2. Add four rev-5 fuzz classes (below) to `backend/tests/pharma_dose_fuzz.py`. Add the rev-5 tests to `backend/tests/test_pharma_s5r4.py`.
3. Freeze the rev-4 parser for the teeth test: `backend/tests/legacy/mock_rules_d2ff98c.py`, byte-identical to `git show d2ff98c:backend/app/pharma/mock_rules.py`, with its sha256 pinned. The legacy copies of `e6a354f` and `6b2a67a` stay.
4. `slices/s5r4/RESIDUAL_RISK.md` is written only by the planner (§R).

### §N — Normalisation (rev 4, unchanged)

Apply these steps in this order, exactly as written:

| Step | Rule |
|---|---|
| N1 | Unicode NFC (not NFKC) |
| N2 | U+0E4D, optionally followed by one tone mark (U+0E48–U+0E4B), then U+0E32 → that tone mark (if present) + U+0E33 |
| N3 | One left-to-right, non-overlapping pass of `([่-๋])([ัิ-ื])` → `\2\1` (a tone mark typed before an upper vowel moves after it) |
| N4 | U+0E40 U+0E40 → U+0E41 (`แ`) |
| N5 | Collapse each whitespace run (`str.isspace()`) to one ASCII space and trim |

The zero-width/format **removal list is empty**: every INVISIBLE character stays a never-consumed numeric-ish token. Homoglyphs, full-width letters, duplicated tone marks and misspellings are not corrected; C1 makes them unverifiable.

### §D — What the page shows (rev 5; decides the checker's minor item)

- `raw_span` and the audit record show the entry as entered, after N1 + N5 only.
- `drug_name_raw` ("Name read") is cut from the §N text, so it **may show the §N spelling**. N2–N4 only reorder or merge Thai marks, and the result renders the same as the typed text.
- No other field shows §N text. Test `test_name_read_uses_normalised_spelling`: for probe N12's name region and for a name with `<U+0E40><U+0E40>`, `drug_name_raw` equals the §N spelling and `raw_span` equals N1 + N5 of the input.

### §C1 — Closed free-text vocabulary (rev 4, amended in rev 5)

The rev-4 rules are unchanged: the dose region starts at the first numeric-ish token; consumed characters are blanked; the free text is casefolded; dotted abbreviations are compacted (`q.d.` → `qd`); a Thai run must segment greedily, longest-first, over `V_TH_FREE`; any other letter run must be in `V_EN_FREE`; a firing gives `unparsed_token`, the lowest reason in the order.

**Rev 5 changes** (`V_EN_FREE`, `V_TH_FREE` and `V_EN_PHRASES` are each exactly one constant):

```
V_EN_FREE    = od bd bid tid qid qd qod hs prn po ac pc daily nightly weekly monthly once twice thrice every other
               morning evening night bedtime noon before after with without meal meals food breakfast lunch dinner
               supper as needed when required for pain fever oral orally by mouth at in the take sc sl im iv
               (rev 4 minus: day days week month)
V_TH_FREE    = รับประทาน กิน ทาน อาหาร นอน มี อาการ ปวด ไข้ เว้น ให้ ก่อน หลัง พร้อม เช้า กลางวัน เที่ยง เย็น ค่ำ ตอน เวลา
               เมื่อ ทุก ทันที ต่อ แบ่ง รวม ทั้งหมด ทั้งวัน ทุกวัน วันเว้นวัน
               (rev 4 minus: วัน; plus: ทุกวัน วันเว้นวัน)
V_EN_PHRASES = every J day | every J other J day | every J week | every J other J week | every J month
               (J = one or more of: space - . _ ; whole-word match on the free text)
```

Before the Latin word check, each whole-word `V_EN_PHRASES` match in the free text is blanked. After that, a remaining `day`, `days`, `week`, `weeks`, `month` or `months`, or a Thai run that needs a bare `วัน` to segment, makes C1 fire. That run could be `วัน` on its own, `กินวัน` or `วันวัน`. Examples: `1000 mg day` → `unparsed_token`; `500 mg every other day` → resolved.

### §P — Per-unit and daily-total wording (rev 4, amended in rev 5)

- **P1 and P2** are unchanged from rev 4.
- **P3 (rev 5, narrowed).** In the drug-name region, the text before the first numeric-ish token, D1 fires on a Latin whole word, casefolded, **equal to** one of:

  ```
  P3_WORDS = per perday perdiem perdose perweek permonth perkg daily day days aday dose
  ```

  A word that only *starts with* `per` no longer fires. So `Perindopril 4 mg od` → 4 mg, and `Perphenazine 4 mg tid` → 4 mg. `Metformin per day 1000 mg bid` still gives `per_unit_amount`. The rev-3 D1 words (`divided`, `total`, `doses` …) still fire anywhere in the entry.
- **P4 (rev 5, replaces rev-4 P4).** D1 fires, giving `per_unit_amount`, when the **dose region** holds ≥ 1 DAILY statement **and** ≥ 1 MULTI statement. Position and the words between them do not matter.

  **DAILY** is any one of:

  | ID | Form |
  |---|---|
  | d1 | In the C1 free text, after casefold and dot compaction, and **not consumed by any production**: the whole word `daily`, `everyday`, `od` or `qd`; or a `V_EN_PHRASES` match `every J day`; or the substring `ทุกวัน`. So the `daily` inside an F2 `twice daily` is not a DAILY statement. |
  | d2 | An F1 match with interval 24 (`q24h`, `every 24 hours`, `ทุก 24 ชั่วโมง`). |
  | d3 | An F2 match with count 1 (`once`, `one time`, `1 time`) per `day` or `daily`. |
  | d4 | An F3 match `วันละ ␣? 1? ␣? ครั้ง`. |

  **MULTI** is either of:

  - **m1**, the rev-4 multi-dose list: `bd bid tid qid twice thrice` after dot compaction; F1 with 1–23 h; F2 with count ≥ 2 per day or daily; F3 `วันละ INT ครั้ง` with INT ≥ 2;
  - **m2 (new)**, ≥ 2 **distinct** slots from this closed table (one constant, `TIME_SLOTS`), found in the dose region. EN slot words are whole Latin words, casefolded; TH slot words are substrings.

  | Slot | EN words | TH substrings |
  |---|---|---|
  | AM | `morning` `breakfast` | `เช้า` |
  | MID | `noon` `midday` `lunch` | `กลางวัน` `เที่ยง` |
  | PM | `evening` `dinner` `supper` | `เย็น` `ค่ำ` |
  | HS | `night` `bedtime` `hs` | `นอน` |

  Frequency is unchanged by P4.
- **Why these are safe to add.**
  - A once-daily statement next to a multi-dose schedule means the strength could be a daily total, or the entry contradicts itself. Either way, no per-dose value may be chosen.
  - A lone `daily`, `ทุกวัน` or `once a day` with ≤ 1 slot stays resolved, as do the K controls.
  - A multi-slot schedule with no DAILY statement also stays resolved, per dose, for example `1 เม็ด เช้า-เย็น`. That is RR-01 territory: no marker.

## Stopping rule (bounds the adversarial loop; set by the orchestrator)

The checker probes the **declared classes** and runs the fuzz harness:

- the declared classes are F1–F7, P, H, U, V, W, I, SL, DT, D and QF (s5r3); N, M, PU and K (rev 4); and B and K (rev 5, below);
- it runs the checker's B-sibling sweep;
- the fuzz harness covers every class.

It may add its own probes. For each finding it records the **meaning a pharmacist reads from the displayed text** and the non-PLAUSIBLE code points. Each finding gets exactly one class:

| Class | Definition | Outcome |
|---|---|---|
| **CONFORMANCE FAIL** | The implementation disagrees with this spec: a listed probe row, the reference in the fuzz, or a closure property. This applies whatever the alphabet. | FAIL → **builder** |
| **BLOCKER** | The implementation and the reference both `resolve` an entry to a value, unit or quantity different from that meaning (a MISREAD). The entry is fully in PLAUSIBLE, is plausibly typed in EN or TH, and is **not** in a declared residual class (RR-01, RR-07). | FAIL. Rev 5 is final, so the orchestrator takes the finding to the **owner**. The owner decides between a spec change and recording it for pharmacist acceptance. No agent may downgrade it. |
| **RESIDUAL** | A MISREAD on an entry with ≥ 1 code point outside PLAUSIBLE; **or** a MISREAD inside RR-01 or RR-07; **or** a newly found exotic class that is not plausibly typed (rare Unicode, homoglyphs beyond the listed sets) | Listed in the checker report in §R row format. The **planner** appends the rows to `RESIDUAL_RISK.md`. **Not** a blocker, and **not** sent back to the planner as a spec revision |
| **SAFE** | `unverifiable` (any reason) or `not_stated`, including a result the checker would have preferred `resolved` | Never a failure. The checker may add an alert-burden note, which goes to the pharmacist review list, not to a spec revision |

PLAUSIBLE is unchanged:

- ASCII U+0020–U+007E;
- Thai U+0E00–U+0E7F;
- `str.isspace()` characters;
- `½ ¼ ¾ × – — µ ‘ ’ “ ” …`.

## §R — `RESIDUAL_RISK.md`

The columns are: `id` | class | example input (`<U+XXXX>` for code points) | observed output (status, value, quantity) | why it is residual | found by | status. Every row has the status `pending pharmacist acceptance`. Only a pharmacist or the owner can accept a row, and the decision is recorded in `docs/DECISIONS.md`.

- **RR-01** (unchanged). It covers **only** a bare `NUM UNIT` that meets all four conditions:
  - no D1 word or P2–P4 trigger;
  - no R1 trigger, including the P1 keys;
  - no SLASH-LIKE character;
  - no C1 firing.

  The writer meant a daily total. Example: `เมทฟอร์มิน 1000 มก. วันละ 2 ครั้ง`. It also covers `1000 มก. เช้า-เย็น`, where there is a schedule but no DAILY statement. A per-unit wording, and any wording with a DAILY statement plus a MULTI statement, is not RR-01.
- **RR-02 to RR-07** are unchanged.
- **Rev-4 round:** the checker report lists no RESIDUAL finding. The planner records "none found (rev-4 round)" in this revision's commit.
- **Who writes rows, and when.** The checker never writes under `slices/`. After each checker round, and before merge, the **planner** appends one row per RESIDUAL finding in the report, or "none found (rev-5 round)". This is a docs-only commit and needs no rebuild. The reviewer checks that the rows match the report 1:1.

## Out of scope

- Everything s5r3 and rev 4 declare out of scope, including:
  - reading unmarked daily totals (RR-01);
  - reading the name region beyond D1 and P3 (RR-07);
  - new reason values, eval cases, manifest, gateway or contract changes;
  - external providers.
- Widening `V_EN_FREE`, `V_TH_FREE`, `V_EN_PHRASES`, `P3_WORDS` or `TIME_SLOTS` beyond this file. That is a planner change and needs pharmacist sign-off.
- Removing an invisible character, or spelling correction beyond N2–N4.
- Accepting any residual risk. That needs a human decision.
- Any further grammar revision. After rev 5, a finding that is not a plausibly typed MISREAD goes to `RESIDUAL_RISK.md`, not to the planner.

## Acceptance

Thresholds apply to the frozen `test` split **and** to all patients. Report both.

| ID | Criterion | Threshold | How measured |
|---|---|---|---|
| S5R4-A01 | All prior items still pass | S5-A01..A18, S5R-A01..A11, S5R2-A01..A18 and S5R3-A01..A23 pass. Allowed amendments: the rev-5 versions (A16); the rev-5 vocabulary constants (A03, A14); and fuzz expectations for phrases that fall under a rev-5 rule (§C1, P3, P4), each listed in the builder report with its rule. Any other changed expectation is a STOP. | `make test`, `make pharma-eval`, `make e2e-pharma`; per-ID checklist in the builder report |
| S5R4-A02 | `make test` green | Exit 0; 0 failed, 0 errors, 0 skip/xfail in pharma tests; offline; fuzz test ≤ 20 s; each code-point sweep ≤ 5 s | `make test` from a clean clone of `factory/s5r4` |
| S5R4-A03 | Grammar closed | `DOSE_GRAMMAR` IDs are exactly {S1,S2,S3,L1,R1,D1,C1,Q1..Q7,T1,F1,F2,F3}. Each of these is one constant: QF, NEUTRAL, the INVISIBLE list, the D1 lexicon, `V_EN_FREE`, `V_TH_FREE`, `V_EN_PHRASES`, P1 keys, `P3_WORDS`, the P4 DAILY words, the P4 MULTI words, `TIME_SLOTS` and the §N step table. 0 deleted piecewise regex names. Every `resolved` trace has 0 unconsumed numeric-ish tokens, 0 C1 firings and 0 D1 matches (P4 included) | pytest `test_grammar_table_closed`, `test_no_piecewise_dose_regex`, `test_resolved_consumes_all_numeric_tokens` |
| S5R4-A04 | Rev-3 probe tables unchanged | F1–F7/P 15/15, H 13/13, U 12/12, V 6/6, W 5/5, I 10/10, SL 11/11, DT 15/15, D 12/12, QF 12/12: exact status, reason, dose, quantity and listed Freq | existing `test_probe_*` suites |
| S5R4-A05 | Rev-4 probe tables unchanged | N 13/13, M 11/11, PU 11/11, K1–K8 8/8 exactly as in rev 4 (rows below) | `test_probe_normalise`, `test_probe_free_text`, `test_probe_per_unit_words`, `test_probe_controls` |
| S5R4-A06 | B-probes (rev 5) | B1–B24 24/24 exact status and reason (table below); 0 resolved | pytest `test_probe_rev5_blockers[B1..B24]` |
| S5R4-A07 | K-controls (rev 5) | K9–K19 11/11 resolved with exact value, unit, quantity and listed Freq | pytest `test_probe_controls[K9..K19]` |
| S5R4-A08 | B-sibling sweep | All 454 phrases of the checker's sibling generator (classes B1_en_day 60, B1_th_wan 10, B2_en_word_daily 297, B2_th_word_thukwan 24, B3_en_daily_times 15, B3_th_thukwan_times 12, B4_qd_multi 36; built from the heads, words and schedules in `tests/e2e/s5r4_r2_sibling_sweep.py`, copied into the test) give **0 `resolved`** in both the implementation and the reference | pytest `test_rev5_sibling_sweep` |
| S5R4-A09 | Neutral on existing data | 100% of `_existing_inputs()` strings, the ≥ 2000 of rev 4, give the same status, reason, value, unit, quantity and frequency as at `d2ff98c`. The only exception is inputs whose name-region word is affected by P3 narrowing, and they must be listed; the planner prototype expects 0. §N identity and idempotence still hold | pytest `test_rev5_neutral_on_existing` (compares with the frozen `d2ff98c` copy), `test_normalise_identity_on_existing`, `test_normalise_idempotent` |
| S5R4-A10 | Unverifiable is visible | In a two-source snapshot, each of I1, SL1, DT1, D1, QF1, M1, M6, PU1, N6, **B1, B6, B12, B16** gives exactly 1 `missing_field(dose)` (`field_status=unverifiable`, reason) and 0 `dose_mismatch`. `unchecked_by_reason.unverifiable` rises by 1 per pair | pytest `test_negative_raises_missing_dose[...]` |
| S5R4-A11 | Fuzz: 0 misreads | ≥ 2000 phrases (seed 5303). Every production and every class has ≥ 20 phrases: rev-3 classes, rev-4 `th_normalise`, `th_misspelt`, `unknown_word`, `per_unit_word`, and rev-5 `bare_period`, `daily_anywhere`, `daily_slots`, `daily_abbrev`. Resolved ≥ 25%, unverifiable ≥ 25%, EN and TH quantity segments ≥ 30% each. **0** safety violations; 100% status and reason agreement with the reference; 0 resolved quantity > 10 | pytest `test_dose_fuzz_vs_reference` |
| S5R4-A12 | Closure properties | Over every generated phrase: 0 `resolved` when the phrase contains (a) an INVISIBLE character, (b) an unconsumed SLASH-LIKE character, (c) a D1/P marker, (d) a C1 firing, (e) a bare period word outside `V_EN_PHRASES`/`ทุกวัน`/`วันเว้นวัน`/`ทั้งวัน`/`กลางวัน` in the dose-region free text, or (f) a DAILY and a MULTI statement, all per the reference. (g) Every `th_normalise` phrase has the same output as its canonical spelling | assertions in `test_dose_fuzz_vs_reference` |
| S5R4-A13 | Tests have teeth | The harness finds ≥ 1 safety misread in each rev-3 class on frozen `e6a354f`, in each rev-4 class on frozen `6b2a67a`, and in **each rev-5 class** (`bare_period`, `daily_anywhere`, `daily_slots`, `daily_abbrev`) on frozen `d2ff98c`. The piecewise stub is caught in each of the 10 s5r3 §F.4 classes | pytest `test_fuzz_catches_e6a354f`, `test_fuzz_catches_6b2a67a`, `test_fuzz_catches_d2ff98c` (each legacy copy sha256-pinned), `test_fuzz_catches_piecewise_stub` |
| S5R4-A14 | Reference independent | `pharma_dose_reference.py` imports no `app.*` module (AST scan) and shares no regex literal with `mock_rules.py`. It computes INVISIBLE, SLASH-LIKE, §N, C1 and P4 with its own code. Its `V_EN_FREE`, `V_TH_FREE`, `V_EN_PHRASES`, `P3_WORDS`, DAILY/MULTI words and `TIME_SLOTS` equal the implementation's and the lists in this file | pytest `test_reference_independent`, `test_vocab_sets_match_spec` (extended) |
| S5R4-A15 | Frequency unchanged | 100% of fixture entries and existing test inputs match the pinned `1c1f476` frequency table (only the s5r3 §4 Q5-fraction exception). Every probe with a Freq column equals that Freq | pytest `test_frequency_unchanged`, `test_t1_r1_frequency_neutral` (extended to B and K9–K19) |
| S5R4-A16 | Versions | The exact strings `s5-mock-rules-2.4.0`, `s5-dose-grammar-1.4.0` and `s5-pipeline-2.6.0` appear in the code, in every run record and in `results.json.versions`. `template-1.3.0` and `RULES_VERSION` are unchanged | pytest `test_versions_bumped` (amended) |
| S5R4-A17 | Frozen data untouched | sha256 of `fixtures/patients.json`, `fixtures/test_manifest.json` (v3), `injection_log.jsonl` and `injection_log_surface.jsonl` equals `1c1f476`. The generators are byte-identical. 0 new eval cases | pytest `test_frozen_artifacts_unchanged`; `git diff 1c1f476 --stat` in the builder report |
| S5R4-A18 | Evaluation holds | Every `results.json` field except `versions` and `notes` equals `1c1f476`: recall ≥ 0.95 for each of the 9 types and each surface form (test and all); clean false alerts ≤ 0.10; extra issues/case ≤ 0.10; extraction accuracy ≥ 0.98; label = System Evaluation | `make pharma-eval`; pytest `test_eval_thresholds`, `test_results_unchanged_except_versions` |
| S5R4-A19 | Clean fixtures use only grammar forms | 96/96 clean entries are `resolved` with the gold quantity. 0 of them hit R1, D1, P1–P4, a QF failure, C1, INVISIBLE or an unconsumed SLASH-LIKE character. 100% of surface-suite `after` strings give their logged status and reason | pytest `test_clean_fixtures_grammar_only`, `test_surface_after_strings_expected` |
| S5R4-A20 | Labels, wording, UI | 7/7 reason labels in `phrasing.py` and `web/lib/pharma.ts`. `notes[0]` and the page scope say "could not be verified". 0 serious or critical axe violations; 0 colour literals; 0 `diagnos\|prescrib\|treat` in UI copy. §D: the "Name read" test passes | pytest `test_reason_labels_complete`, `test_results_notes_grammar`, `test_name_read_uses_normalised_spelling`; Vitest `pharma-page.test.tsx`; `make e2e-pharma`; s0 `test_repo_hygiene` |
| S5R4-A21 | Stopping rule applied | The checker report puts every finding in one class of the table above and records its meaning and non-PLAUSIBLE code points. PASS requires **0 CONFORMANCE FAIL and 0 BLOCKER**; SAFE and RESIDUAL never fail the slice. Round-1 items (HT1–9, DD1–5, PD1–6) and round-2 items (B1a–B4b, AB1) are re-run: 0 BLOCKER, and AB1 (`Perindopril 4 mg od`) is resolved | checker report plus `tests/e2e/s5r4_classify_findings.py` and `s5r4_r2_classify_findings.py` |
| S5R4-A22 | Residual risk recorded | `RESIDUAL_RISK.md` is in §R format. It holds RR-01..RR-07, "none found (rev-4 round)", and 1 row per rev-5 checker RESIDUAL finding appended by the planner (or "none found (rev-5 round)"). It also declares the unmarked daily-total risk (RR-01). Every row is `pending pharmacist acceptance`; 0 are accepted | reviewer compares it 1:1 with the checker report; `grep -c "pending pharmacist acceptance"` equals the number of rows |

### Rev-4 probe rows (A05; unchanged)

N1–N13, M1–M11, PU1–PU11 and K1–K8 are exactly as committed in rev 4 (`e52489e`, "Rev-4 probe tables"). The table is in `backend/tests/test_pharma_s5r4.py` (`N_PROBES`, `M_PROBES`, `PU_PROBES`, `K_PROBES`), and rev 5 changes 0 rows.

### Rev-5 probe tables

A dash in the Freq column means frequency is not asserted. `UT` is `unverifiable` / `unparsed_token`; `PUA` is `unverifiable` / `per_unit_amount`.

| Probe | Input | Expected | Freq | Rule |
|---|---|---|---|---|
| B1 | `Metformin 1000 mg day` (B1a) | UT | – | C1 |
| B2 | `Metformin 1000 mg day, bid` (B1b) | UT | q12h | C1 |
| B3 | `Metformin 500 mg 2 tabs day bid` (B1c) | UT | q12h | C1 |
| B4 | `เมทฟอร์มิน 1000 มก. วัน` (B1d) | UT | – | C1 |
| B5 | `เมทฟอร์มิน 1000 มก. วัน วันละ 2 ครั้ง` (B1e) | UT | q12h | C1 |
| B6 | `Metformin 1000 mg po daily bid` (B2a) | PUA | – | P4 d1+m1 |
| B7 | `Metformin 1000 mg oral daily, bid` (B2b) | PUA | – | P4 |
| B8 | `Metformin 500 mg 2 tabs po daily bid` (B2c) | PUA | – | P4 |
| B9 | `Metformin 1000 mg with meals daily q12h` (B2d) | PUA | – | P4 d1+m1(F1) |
| B10 | `เมทฟอร์มิน 1000 มก. รับประทานทุกวัน วันละ 2 ครั้ง` (B2e) | PUA | q12h | P4 |
| B11 | `เมทฟอร์มิน 1000 มก. กินทุกวัน วันละ 2 ครั้ง` (B2f) | PUA | q12h | P4 |
| B12 | `Metformin 1000 mg daily morning, evening` (B3a) | PUA | – | P4 d1+m2 |
| B13 | `Metformin 1000 mg daily, before breakfast, before dinner` (B3b) | PUA | – | P4 m2 |
| B14 | `เมทฟอร์มิน 1000 มก. ทุกวัน เช้า เย็น` (B3c) | PUA | q12h | P4 m2 |
| B15 | `เมทฟอร์มิน 1000 มก. ทุกวัน เช้า-เย็น` (B3d) | PUA | q12h | P4 m2 |
| B16 | `Metformin 1000 mg qd bid` (B4a) | PUA | – | P4 d1 |
| B17 | `Metformin 1000 mg q.d., bid` (B4b) | PUA | – | P4 d1 |
| B18 | `Metformin 1000 mg od bid` | PUA | – | P4 d1 |
| B19 | `Metformin 1000 mg q24h bid` | PUA | – | P4 d2 |
| B20 | `Metformin 1000 mg once daily, bid` | PUA | – | P4 d3 |
| B21 | `เมทฟอร์มิน 1000 มก. วันละครั้ง เช้า เย็น` | PUA | – | P4 d4+m2 |
| B22 | `Metformin 1000 mg po day` | UT | – | C1 |
| B23 | `เมทฟอร์มิน 1000 มก. รับประทาน วัน วันละ 2 ครั้ง` | UT | q12h | C1 |
| B24 | `เมทฟอร์มิน 500 มก. 2 เม็ด ทุกวัน เช้า ก่อนนอน` | PUA | – | P4 m2 (AM+HS) |
| K9 | `Alendronate 70 mg weekly` | 70 mg, resolved | – | control |
| K10 | `Alendronate 70 mg every week` | 70 mg, resolved | – | `V_EN_PHRASES` |
| K11 | `Metformin 500 mg every day` | 500 mg, resolved | q24h | `V_EN_PHRASES`, 0 MULTI |
| K12 | `เมทฟอร์มิน 500 มก. 1 เม็ด ทุกวัน` | 500 mg, qty 1, resolved | – | DAILY, 0 MULTI |
| K13 | `เมทฟอร์มิน 500 มก. 1 เม็ด หลังอาหารเช้า ทุกวัน` | 500 mg, qty 1, resolved | – | 1 slot |
| K14 | `เมทฟอร์มิน 500 มก. 1 เม็ด เช้า-เย็น` | 500 mg, qty 1, resolved | q12h | 0 DAILY (RR-01 shape) |
| K15 | `Metformin 500 mg daily at bedtime` | 500 mg, resolved | q24h | 1 slot |
| K16 | `Perindopril 4 mg od` (AB1) | 4 mg, resolved | q24h | P3 narrowed |
| K17 | `Perphenazine 4 mg tid` | 4 mg, resolved | q8h | P3 narrowed |
| K18 | `เมทฟอร์มิน 500 มก. วันเว้นวัน` | 500 mg, resolved | – | `V_TH_FREE` |
| K19 | `Metformin 500 mg daily with breakfast` | 500 mg, resolved | q24h | 1 slot |

## Required test cases

- `backend/tests/test_pharma_s5r4.py` (extended):
  - `test_probe_rev5_blockers`, and `test_probe_controls` extended with K9–K19, rows exactly as above;
  - `test_rev5_sibling_sweep` (A08);
  - `test_rev5_neutral_on_existing` (A09);
  - `test_name_read_uses_normalised_spelling` (§D);
  - `test_fuzz_catches_d2ff98c`;
  - the amended `test_grammar_table_closed`, `test_vocab_sets_match_spec`, `test_versions_bumped` and `test_t1_r1_frequency_neutral`;
  - the A10 list added to `test_negative_raises_missing_dose`.
- Fuzz generator, four rev-5 classes, each with ≥ 20 phrases and the controls that must resolve:
  - `bare_period`: `day/days/week/month/วัน` after the anchor and after 1–2 vocabulary words, with and without a MULTI;
  - `daily_anywhere`: DAILY forms d1–d4, with 0–2 vocabulary words (`po`, `oral`, `take`, `with meals`, `pc`, `รับประทาน`, `กิน`, `ทาน`, `ให้`, `หลังอาหาร`) before or after, plus an m1 MULTI;
  - `daily_slots`: DAILY plus 2–3 distinct `TIME_SLOTS` words, EN and TH, joined by space, `,`, `-` or nothing (TH);
  - `daily_abbrev`: `qd`, `q.d.`, `QD`, `od`, `o.d.` with an m1 MULTI.
- Write every non-ASCII invisible, homoglyph, full-width or mis-ordered Thai code point in test sources as a `\uXXXX` escape.
- Every s5/s5r/s5r2/s5r3/s5r4 test stays in place. Only the A01 amendments are allowed.

## Clinical risks

| Risk | Mitigation |
|---|---|
| `mg day`, `มก. วัน` or `mg po day` (the slash or `per` dropped) is read per dose, a 2× overdose when the total is split bid | Bare period words are out of the C1 vocabulary (A06 B1–B5, B22–B23; A08; A12e) |
| A route, verb or meal word between the dose and `daily`/`ทุกวัน`, or a daily written `qd`/`od`/q24h/once a day, hides a daily total given bid | P4 checks DAILY and MULTI anywhere in the dose region (A06 B6–B21; A08; A12f) |
| A split schedule written as time-of-day slots (`เช้า เย็น`, `morning evening`, `breakfast dinner`) is not seen as multi-dose | P4 m2 counts distinct slots (B12–B15, B21, B24) |
| Alert burden: a drug name starting with `per` is always unverifiable, which trains users to ignore the flag | P3 is narrowed to whole words (K16, K17). The remaining alert-burden cases (M11: brand after the dose; `every week` phrasing outside the list) need pharmacist review before non-synthetic use |
| A daily total written with no marker at all (`1000 มก. วันละ 2 ครั้ง`, `1000 มก. เช้า-เย็น`) is read per dose (RR-01) | Declared, not accepted. It blocks non-synthetic use until a pharmacist or the owner accepts it (§R) |
| The adversarial loop does not converge before the 8–9 Oct presentation | Rev 5 is final. After rev 5, only a plausibly typed MISREAD outside RR-01/RR-07 blocks, and the owner decides on it. Everything else is RESIDUAL or SAFE |
| Tuning on the test split | 0 new eval cases; hashes pinned; metrics identical (A17, A18). Rev-5 lists come from the checker's BLOCKER classes. The fixture check is a no-change check (A09), not a fit |

## Run commands

```bash
cd /Users/king_phuripol/AI-Engineer/01_Projects/Senior-Project/Full-Agent-s5
make test                                                  # all tests incl. probes, sweeps, fuzz (offline)
cd backend && ../.venv/bin/python -m pytest tests/test_pharma_s5r4.py tests/test_pharma_s5r3.py -q   # grammar focus
make pharma-eval                                           # results.json == 1c1f476 except versions/notes
make dev API_PORT=8105 WEB_PORT=3105                       # http://127.0.0.1:3105/pharmacist/reconcile
make e2e-pharma
git show d2ff98c:backend/app/pharma/mock_rules.py | shasum -a 256   # must equal the pinned rev-4 legacy-copy hash
.venv/bin/python tests/e2e/s5r4_r2_sibling_sweep.py        # checker's B-sibling sweep: expect 0 resolved
.venv/bin/python tests/e2e/s5r4_r2_classify_findings.py    # round-2 findings re-run: 0 BLOCKER, AB1 resolved
```

## Decisions needed (none block this synthetic slice)

- **Owner:** confirm the rev-5 route for B1–B4. The rev-4 stopping rule gave this choice to the owner, and the orchestrator requested it; there is no entry in `docs/DECISIONS.md` yet. Also decide on any rev-5 BLOCKER, which means either a further spec change or recording the finding for pharmacist acceptance.
- **Pharmacist and owner:** accept or reject each `RESIDUAL_RISK.md` row, and record the decision in `docs/DECISIONS.md`. Until then, every row blocks non-synthetic use.
- **Pharmacist:** sign off on:
  - §N and the rev-5 vocabulary (`V_EN_FREE`, `V_TH_FREE`, `V_EN_PHRASES`);
  - `P3_WORDS`, the P4 DAILY/MULTI rule and `TIME_SLOTS`;
  - the rev-3 items: QF, NEUTRAL, the D1 lexicon and PLAUSIBLE.
