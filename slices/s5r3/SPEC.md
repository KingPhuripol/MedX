# Slice s5r3 — Pharma Agent v1.3 (strict dose grammar, fail-safe on anything else)

- Owner (Gantt): ธัญรดา / ภูริณัฐ
- Source of truth: `docs/PROPOSAL.md` (v8) 3.2.4 (the model extracts name, dose and frequency; rules are primary; flag dose **or frequency** differences between sources for pharmacist review), 3.6 / Table 3.2 (recall from synthetic error injection, 95% patient-level bootstrap CIs, System Evaluation label). Decisions: `docs/DECISIONS.md` 2026-09-26 (formulary licence) and 2026-09-27 (evaluation definitions).
- **Delta** on `slices/s5/SPEC.md`, `slices/s5r/SPEC.md` and `slices/s5r2/SPEC.md` at branch tip `1c1f476`. Everything in those files still applies unless this file replaces it. Where they conflict, this file wins.
- Trigger: three s5r2 check rounds each found a new dose form that `backend/app/pharma/mock_rules.py` misread as a resolved value (F1–F7 below). The extractor matches pieces of the text and ignores the rest, so every unseen form is a new silent misread. This slice replaces piecewise matching with a **closed grammar**: anything the grammar does not consume makes the dose `unverifiable`.
- Status: PLAN. All data is synthetic (`data_class="synthetic"`). Tier 0 only. No external provider. Servers, if started: API 8105, web 3105.

## Scope

1. **One closed grammar table.** Dose, quantity and every numeric token in the entry are read by the tokeniser (§G1) and the productions (§G2). Nothing else reads them. `mock_rules.py` holds the productions in **one** table, `DOSE_GRAMMAR`, keyed by the production IDs in §G2. The piecewise regexes are deleted: `DOSE_RE`, `QTY_RE`, `_QTY_NUM`, `_MIXED_RE`, `_STRAY_NUM_BEFORE_RE`, `_QTY_WORD_RE` and `TIMES_RE` as a dose reader. The frequency code mapping (`FREQ_PATTERNS`, `EVERY_RE`, `NON_DAILY_RE`, `FREQ_LIKE_RE`) stays. Its numeric tokens are consumed only by productions F1–F3.
2. **Resolution rule.** The whole entry is tokenised. The dose is `resolved` only if all of the following hold:
   - every numeric-ish token (§G1) is consumed by exactly one production;
   - no production that makes the dose unverifiable fired;
   - exactly one distinct strength (S1 value and unit) is read.

   If no strength is read and no numeric-ish token is left over, the dose is `not_stated`. In every other case the dose is `unverifiable`, with `dose_value`, `dose_unit` and `quantity` all `null`. The reason is the first one that applies, in this order: `variable_regimen` > `liquid_volume` > `multiple_strengths` > `range` > `ambiguous_quantity` > `unparsed_token`.
3. **Reason enum widened.** `UnverifiableReason` gains `range` and `unparsed_token`. This is additive, and the task name stays `pharma.extract.v2`. There is a label for each reason in both `backend/app/pharma/phrasing.py` and `web/lib/pharma.ts`:
   - `range`: "a range or alternative between two amounts"
   - `unparsed_token`: "a dose form this checker does not read"

   Downstream behaviour is unchanged from s5r2 §4. An unverifiable dose raises `missing_field(dose)` with `field_status=unverifiable` and the reason. It never produces or suppresses a `dose_mismatch`, and it is counted in `unchecked_comparisons` / `unchecked_by_reason.unverifiable`.
4. **Frequency is unchanged**, with one exception. For every input in the fixtures and in the existing tests, `frequency_code` and `frequency_status` stay as they are at `1c1f476`. The exception is Q5 with a fractional N (`½x1`, `1/2x2`): it now yields the code of M, the same as an integer N.
5. **Property/fuzz test and reference parser** (§F).
6. **Versions:**

   | Constant | Value |
   |---|---|
   | `MOCK_RULES_VERSION` | `s5-mock-rules-2.0.0` |
   | `DOSE_GRAMMAR_VERSION` (new) | `s5-dose-grammar-1.0.0` |
   | `TEMPLATE_VERSION` | `template-1.2.0` (new reason labels) |
   | pipeline version | `s5-pipeline-2.2.0` |

   `RULES_VERSION` and `RULE_VERSIONS` do not change. Every run and `results.json.versions` record all of these, including `dose_grammar`.
7. **Truthful residual-risk wording.**
   - `results.json.notes[0]` and the page scope section say that the dose is read by a fixed, listed grammar and that any other form is shown as "could not be verified".
   - They drop the words "may be misread as resolved".
   - They keep the caveat that a grammar-valid phrase can still be clinically wrong. For example, a dispensed count written as `2 tabs` is still read as 2 tablets per dose.
8. **Frozen data untouched.** The following stay byte-identical to `1c1f476`: `fixtures/patients.json`, `fixtures/test_manifest.json` (v3), `injection_log.jsonl`, `injection_log_surface.jsonl` and the generators. This slice adds **no** evaluation cases. The probe and fuzz strings are unit-test inputs and belong to no split. If a later slice needs new eval cases, they go in manifest v4, frozen before any evaluation.

### G1 — Tokeniser (normalise, then classify)

- **Normalise:**
  - NFC (not NFKC, so `½` survives);
  - collapse whitespace;
  - casefold Latin;
  - `×` becomes `x`;
  - the dot in Thai `มก.` / `มล.` / `ชม.` is part of the lexeme.

  Thai digits `๐–๙`, full-width digits and superscripts are **not** converted.
- **Token classes:**
  - `NUM`: ASCII digits, optionally `.` plus digits. The value is exact (`Fraction`).
  - `UFRAC`: any other character that has a Unicode numeric value (`½ ¼ ¾ ⅓ ⅛ ๑ ２ …`).
  - Latin words.
  - Thai lexemes, matched longest-first from a closed lexicon: `เม็ด แคปซูล ครึ่ง ครั้งละ วันละ สัปดาห์ละ อาทิตย์ละ เดือนละ ครั้ง ทุก ชั่วโมง ชม. มก. มิลลิกรัม กรัม ไมโครกรัม ยูนิต มล. และ หรือ ถึง หนึ่ง สอง สาม สี่ ห้า หก เจ็ด แปด เก้า สิบ`. Other Thai text is `OTHER`.
  - Symbols: `/ ⁄ . , - – — ~ x + &`.
- **Numeric-ish tokens.** Each of these must be consumed:
  - `NUM` and `UFRAC`;
  - EN number words `one two three four five six seven eight nine ten half once twice thrice`;
  - the TH number words in the lexicon, including `ครึ่ง`;
  - strength `UNIT` tokens (§G2 S1);
  - quantity words `QW` = `tab tabs tablet tablets cap caps capsule capsules เม็ด แคปซูล`;
  - any symbol or connector (`to or and ถึง หรือ และ`) that is adjacent to a `NUM`, `UFRAC` or number word, ignoring whitespace.

  An unconsumed connector from `- – — ~ to or and ถึง หรือ และ` that sits between two numeric-ish tokens gives the reason `range`. Every other unconsumed numeric-ish token gives `unparsed_token`.
- **Joined and spaced forms are equivalent.** `␣?` below means optional whitespace, so `3mg`, `2tabs` and `ครั้งละ2เม็ด` are read the same as their spaced forms.

### G2 — Productions (the complete, closed list)

Value constraints:

- `INT` has no leading zero.
- `QV` is a quantity value `v` with `0 < v ≤ 10` and `4v` an integer.
- `FRAC` is `1/2`, `1/4`, `3/4` (spaces around `/` allowed), or `UFRAC ∈ {½, ¼, ¾}`.

A value that breaks a constraint means the production does not match. Its tokens are then left unconsumed, which gives `unparsed_token`.

| ID | Form (EN / TH) | Examples | Result |
|---|---|---|---|
| S1 | `NUM ␣? UNIT`. UNIT ∈ `mg g gm mcg µg ug unit units u iu ml มก. มก มิลลิกรัม กรัม ไมโครกรัม ยูนิต มล. มล`. NUM > 0 and not preceded by `/` | `3 mg`, `3mg`, `500 มก.`, `15 ml` | strength (value, canonical unit) |
| S2 | `NUM / NUM ␣? UNIT` (combination) | `875/125 mg` | consumed; dose not read (`not_stated`, s5 gold kept) |
| S3 | ≥ 2 S1 with distinct (value, unit), with or without a joiner `+ , & and และ` | `3 mg + 1 mg`, `3 mg and 2 mg` | `multiple_strengths` |
| L1 | `NUM ␣? MASS / NUM? ␣? VOL`, optionally followed by `NUM ␣? VOL` | `250 mg/5 ml 10 ml`, `120 มก./5 มล. 5 มล.` | `liquid_volume` |
| Q1 | `QV ␣? QW` (INT or decimal) | `2 tabs`, `2tabs`, `1.5 เม็ด`, `3 แคปซูล` | quantity = QV |
| Q2 | `FRAC ␣? QW` | `1/2 tab`, `½ เม็ด` | 0.25 / 0.5 / 0.75 |
| Q3 | Mixed number: `INT (␣ \| ␣?-␣? \| ␣?and␣? \| ␣?และ␣?) FRAC ␣? QW`, or `INT ␣? UFRAC ␣? QW` | `1 1/2 tab`, `1-1/2 tab`, `1 and 1/2 tab`, `1และ1/2 เม็ด`, `1½ tab` | INT + FRAC |
| Q4 | TH half: `ครึ่ง ␣? (เม็ด\|แคปซูล)`, or `INT ␣? (เม็ด\|แคปซูล) ครึ่ง` | `ครึ่งเม็ด`, `1 เม็ดครึ่ง`, `2เม็ดครึ่ง` | 0.5; INT + 0.5 |
| Q5 | `N ␣? x ␣? M`. N ∈ {INT, decimal, FRAC} within the QV bounds; M ∈ {1,2,3,4}; no QW follows | `2x2`, `1x1 หลังอาหารเช้า`, `½x1`, `1/2x2` | quantity = N; frequency code of M (q24h/q12h/q8h/q6h) |
| Q6 | `ครั้งละ ␣? (Q1\|Q2\|Q3\|Q4)` | `ครั้งละ2เม็ด`, `ครั้งละ ครึ่งเม็ด` | value of the inner production |
| Q7 | `วันละ ␣? (Q1\|Q2\|Q3\|Q4)` | `วันละ 1 เม็ด`, `วันละครึ่งเม็ด` | value ≤ 1: quantity = value. Value > 1: `ambiguous_quantity` (a daily total, not a per-dose amount) |
| F1 | `q ␣? INT ␣? (h\|hr\|hrs\|hour\|hours)`, `every INT (h\|hr\|hrs\|hour\|hours)`, `ทุก ␣? INT ␣? (ชั่วโมง\|ชม.)` | `q6h`, `q4h`, `every 8 hours`, `ทุก 6 ชั่วโมง` | numbers consumed; code by the existing mapping (6/8/12/24), otherwise `not_recognised` |
| F2 | `(INT\|one\|two\|three\|four) (time\|times) (a\|per)? (day\|daily\|week\|weekly\|month\|monthly)`, or `(once\|twice\|thrice) (a\|per)? (day\|daily\|week\|weekly\|month\|monthly)`. `time`/`times` is **required** after a numeral, so `2 daily` is never read as a frequency | `twice daily`, `four times daily`, `3 times a week`, `twice weekly` | consumed; existing mapping (non-daily → `not_recognised`) |
| F3 | `(วันละ\|สัปดาห์ละ\|อาทิตย์ละ\|เดือนละ) ␣? INT? ␣? ครั้ง` | `วันละ 3 ครั้ง`, `วันละครั้ง`, `สัปดาห์ละ 1 ครั้ง` | consumed; existing mapping |

Conflicts:

- Two or more quantity productions (Q1–Q7) with **distinct** values give `ambiguous_quantity`, e.g. `2 tabs 1x2`. Equal values stay resolved, e.g. `1 tab 1x2`.
- Two S1 with equal (value, unit) stay resolved.
- Variable-regimen keywords (s5r2 §2) are checked before all productions and win.

Nothing else consumes a numeric-ish token. The following are always unverifiable:

- a bare number;
- a bare quantity word;
- a number word used as a quantity (`one tab`, `สองเม็ด`);
- an invalid or unlisted fraction (`1/0`, `3/2`, `⅓`);
- a Thai digit;
- `.5`, `1,000`;
- a trailing stray digit;
- `x2` with no N;
- any range.

### F — Property/fuzz test and reference parser

- **Reference parser.** `backend/tests/pharma_dose_reference.py` is written only from §G1–§G2 and uses a different technique from the implementation: a hand-written token scanner, not the `DOSE_GRAMMAR` table. It imports nothing from `app.pharma`. Given a text, it returns `(dose_status, dose_value, dose_unit, quantity)`.
- **Generator.** Seeded (`seed=5303`), standard library only, and at least **2000** phrases per run. Each phrase is `[drug name EN|TH] + [strength segment] + [quantity segment] + [frequency segment] + [tail]`. The joiner between segments is drawn from `{"", " ", "  "}`. Segment alphabet:
  - valid instances of every production S1–F3 (EN and TH);
  - adversarial segments:
    - ranges with `- – — ~ to or and ถึง หรือ และ`;
    - bare numbers, trailing stray digits, `.5`, `1,000`, `0`, `12`, `30`;
    - `1.3`, `3/2`, `1/0`, `2/3`, `⅓`, `๑`;
    - EN and TH number words;
    - bare QW, `x2`, `2x`, `2x5`;
    - duplicated or conflicting quantities;
    - `q4-6h`, `1-2 times daily`;
    - L1, S2 and S3 segments, and variable-regimen words.
- **Strata, checked in the test:**
  - ≥ 25% of phrases reference-`resolved` and ≥ 25% reference-`unverifiable`;
  - every production and every adversarial class appears ≥ 20 times;
  - EN and TH quantity segments are each ≥ 30%.
- **Assertions:**
  1. **Safety:** 0 phrases where the implementation returns `resolved` and either the reference is not `resolved` or `(dose_value, dose_unit, quantity)` differs.
  2. **Non-degeneracy:** `dose_status` agrees with the reference on 100% of phrases.
  3. **Reference check:** for phrases built from exactly one valid quantity production, the reference value equals the value the generator built.
  4. **Teeth:** the same harness, run on a stub piecewise parser defined in the test, finds ≥ 1 misread. The stub drops the whole part of a mixed number and reads the upper end of a range.

  Each failure prints the phrase and both outputs.

## Out of scope

- Converting ranges, liquids or variable regimens into a comparable dose, and any new discrepancy type or threshold change.
- Frequency-grammar redesign beyond the numeric consumption in F1–F3.
- Thai-digit or number-word **reading**. Both stay unverifiable.
- Applying the grammar as a verifier over a non-mock extraction provider. This is needed before any external extraction provider is enabled, and is recorded as a decision below.
- DDI, dose-range, renal or hepatic and route checks, real or MIMIC data, TMT/ATC, the gateway contract version, and s0 audit semantics.
- New eval cases or any manifest change.

## Acceptance

Thresholds apply to the frozen `test` split **and** to all patients, and both are reported.

| ID | Criterion | Threshold | How measured |
|---|---|---|---|
| S5R3-A01 | All prior items still pass | S5-A01..A18, S5R-A01..A11 and S5R2-A01..A18 pass, with these amendments only: S5R2-A16 reads the §6 version strings; the existing tests listed under "Amended expectations" change only the reason string. Any other changed prior expectation is a STOP, and the spec goes back to the planner | `make test`, `make pharma-eval`, `make e2e-pharma`; per-ID checklist in the builder report |
| S5R3-A02 | `make test` green | Exit 0, 0 failed, 0 errors, 0 skip/xfail on pharma tests, offline; the fuzz test runs in the default suite in ≤ 20 s | `make test` from a clean clone of `factory/s5r3` |
| S5R3-A03 | Grammar is one closed table | The `DOSE_GRAMMAR` IDs equal {S1, S2, S3, L1, Q1..Q7, F1, F2, F3} exactly; 0 occurrences of the deleted regex names in `backend/app/pharma/`; every `resolved` parse trace has 0 unconsumed numeric-ish tokens | pytest `test_grammar_table_closed`, `test_no_piecewise_dose_regex`, `test_resolved_consumes_all_numeric_tokens` |
| S5R3-A04 | F1–F7 probes: 0 misreads | 15/15 probe strings (table below) give exactly the listed result. Each result is the correct value or `unverifiable`, never another number | pytest `test_probe_f1_f7[...]` |
| S5R3-A05 | Every production reads exactly | 100% of the positive cases (≥ 2 per production, EN and TH where the form exists) give the gold (value, unit, quantity); the s5r2 `QUANTITY_FORMS`, `QUANTITY_FORMS_REGRESSION` and `QUANTITY_FORMS_REGRESSION_2` sets still pass unchanged | pytest `test_grammar_positive[...]` plus the existing s5r2 tests |
| S5R3-A06 | Anything else is unverifiable, visibly | 100% of the adversarial cases give `unverifiable` with the listed reason and null dose/quantity. In a two-source snapshot each gives 1 `missing_field(dose)` (`field_status=unverifiable`, reason), 0 `dose_mismatch`, and `unchecked_by_reason.unverifiable` rises by the number of pairs | pytest `test_grammar_negative[...]`, `test_negative_raises_missing_dose[range\|unparsed_token\|ambiguous_quantity]` |
| S5R3-A07 | Fuzz: 0 misreads | ≥ 2000 phrases; strata as in §F; 0 safety violations; 100% `dose_status` agreement; reference check 100%; teeth stub caught (≥ 1) | pytest `test_dose_fuzz_vs_reference`, `test_fuzz_catches_piecewise_stub`; the checker also runs the harness on the `1c1f476` parser (`git show 1c1f476:backend/app/pharma/mock_rules.py`) and reports ≥ 1 misread |
| S5R3-A08 | Reference is independent | `pharma_dose_reference.py` imports no `app.*` module (AST scan) and shares no regex literal with `mock_rules.py` | pytest `test_reference_independent` |
| S5R3-A09 | Frozen data untouched | sha256 of `patients.json`, `test_manifest.json`, `injection_log.jsonl` and `injection_log_surface.jsonl` equals `1c1f476`; manifest stays v3; 0 new eval cases | pytest `test_frozen_artifacts_unchanged` (hashes pinned in the test); `git diff 1c1f476 --stat` in the builder report |
| S5R3-A10 | Evaluation still holds | Every `results.json` field except `versions` and `notes` equals `1c1f476`. In particular: recall ≥ 0.95 for each of the 9 types and each surface form, on test and all, with Clopper–Pearson then bootstrap CI; clean false alerts ≤ 0.10; extra issues per case ≤ 0.10; extraction accuracy ≥ 0.98; `label` = System Evaluation | `make pharma-eval`; pytest `test_eval_thresholds`, `test_results_unchanged_except_versions` |
| S5R3-A11 | Clean fixtures use only grammar forms | 100% of entries in every clean patient (96/96) parse `resolved`, with 0 unconsumed numeric-ish tokens and the gold quantity; 100% of the surface-suite `after` strings give their logged expected status and reason | pytest `test_clean_fixtures_grammar_only`, `test_surface_after_strings_expected` |
| S5R3-A12 | Frequency unchanged | For 100% of fixture entries and of the inputs in existing pharma tests, `frequency_code`/`frequency_status` equal the `1c1f476` output (pinned table); the only allowed change is the §4 Q5-fraction exception | pytest `test_frequency_unchanged` |
| S5R3-A13 | New reasons labelled end to end | `UnverifiableReason` = the 6 values; 6/6 have a label in `phrasing.py` and in `web/lib/pharma.ts`; the page renders `not verifiable (a range or alternative between two amounts)`; the template passes validation for `range` and `unparsed_token` | pytest `test_reason_labels_complete`, `test_templates_pass_validation`; Vitest `field status labels[range\|unparsed_token]` |
| S5R3-A14 | Versions and wording | The §6 strings are present in code, in every run and in `results.json.versions`; `notes[0]` and the scope section contain "could not be verified" and not "may be misread"; 0 `all doses`/`every dose` claims; 0 serious/critical axe violations; 0 colour literals; 0 `diagnos\|prescrib\|treat` in UI copy | pytest `test_versions_bumped` (amended), `test_results_notes_grammar`; Vitest `scope limits`; `make e2e-pharma`; s0 `test_repo_hygiene` |

### F1–F7 probe table (S5R3-A04)

Each input is prefixed by the drug and strength shown.

| Probe | Input | Expected |
|---|---|---|
| F1 | `Warfarin 3 mg 1 1/2 tab od` | qty 1.5, dose 3 mg, resolved |
| F2 | `เมทฟอร์มิน 500 มก. ครั้งละ2เม็ด วันละ2ครั้ง` | qty 2, q12h, resolved |
| F3a | `Warfarin 3 mg 1-1/2 tab od` | qty 1.5 |
| F3b | `Warfarin 3 mg 1 and 1/2 tab od` | qty 1.5 |
| F4a | `วาร์ฟาริน 3 มก. 1 เม็ดครึ่ง วันละ 1 ครั้ง` | qty 1.5 |
| F4b | `วาร์ฟาริน 3 มก. 2เม็ดครึ่ง วันละ 1 ครั้ง` | qty 2.5 |
| F5a | `วาร์ฟาริน 3 มก. 1-2 เม็ด วันละ 1 ครั้ง` | unverifiable, `range` |
| F5b | `Paracetamol 500 mg 1-2 tabs q4-6h prn` | unverifiable, `range` |
| F6a | `Warfarin 3 mg ½x1` | qty 0.5, q24h |
| F6b | `Warfarin 3 mg 1/2x2` | qty 0.5, q12h |
| F7 | `Warfarin 3 mg 1/2 od` | unverifiable, `unparsed_token` |
| P1 | `Warfarin 3 mg 3 od` | unverifiable, `unparsed_token` (misread as 3 mg at `1c1f476`) |
| P2 | `Warfarin 3 mg 2 tabs x 2` | unverifiable, `unparsed_token` |
| P3 | `Aspirin 81 mg 1x1 หลังอาหารเช้า 1` | unverifiable, `unparsed_token` |
| P4 | `Paracetamol 500 mg 1 tab or 2 tabs prn` | unverifiable, `range` |

## Required test cases

- `test_grammar_positive[...]`: ≥ 2 per production, as in the §G2 examples, plus:
  - `3mg 2tabs od` → 3 mg × 2;
  - `วาร์ฟาริน 3 มก. ครั้งละ ครึ่งเม็ด` → 0.5;
  - `Metformin 500 mg 1 tab 1x2` → 1, q12h (equal quantities);
  - `Augmentin 875/125 mg bid` → `not_stated` (S2).
- `test_grammar_negative[...]`, with the reason for each:

  | Input | Reason |
  |---|---|
  | `Warfarin 3 mg ⅓ tab od` | `unparsed_token` |
  | `Warfarin 3 mg .5 tab od` | `unparsed_token` |
  | `Warfarin 3 mg 3/2 tab od` | `unparsed_token` |
  | `วาร์ฟาริน 3 มก. ๑ เม็ด` | `unparsed_token` |
  | `Warfarin 3 mg half tab od` | `unparsed_token` |
  | `Paracetamol 1,000 mg q6h` | `unparsed_token` |
  | `Paracetamol 500 mg 30 tabs` | `unparsed_token` (QV > 10) |
  | `Metformin 500 mg x2` | `unparsed_token` |
  | `Metformin 500 mg 2x5` | `unparsed_token` |
  | `Warfarin 3 mg 2 x1 tab` | `unparsed_token` |
  | `Warfarin 3 mg tab od` | `unparsed_token` |
  | `Paracetamol 500-1000 mg q6h` | `range` |
  | `Paracetamol 500 mg 1 ถึง 2 เม็ด` | `range` |
  | `Paracetamol 500 mg 1 หรือ 2 เม็ด` | `range` |
  | `Warfarin 3 mg 1–2 tabs` (en dash) | `range` |
  | `Warfarin 3 mg 1~2 tabs` | `range` |
  | `เมทฟอร์มิน 500 มก. วันละ 2 เม็ด` | `ambiguous_quantity` (Q7 > 1) |
  | `Metformin 500 mg 2 tabs 1x2` | `ambiguous_quantity` |
  | `Warfarin 3 mg 0 tab od` | `unparsed_token` |
- `test_probe_f1_f7[...]` (the table above), `test_negative_raises_missing_dose[...]`.
- `test_grammar_table_closed`, `test_no_piecewise_dose_regex`, `test_resolved_consumes_all_numeric_tokens`.
- `test_dose_fuzz_vs_reference`, `test_fuzz_catches_piecewise_stub`, `test_reference_independent`.
- `test_frozen_artifacts_unchanged`, `test_results_unchanged_except_versions`, `test_clean_fixtures_grammar_only`, `test_surface_after_strings_expected`, `test_frequency_unchanged`.
- `test_reason_labels_complete`, `test_results_notes_grammar`, and `test_versions_bumped` (amended).
- Web (Vitest `pharma-page.test.tsx`): `field status labels[range|unparsed_token]`; `scope limits` includes the grammar sentence.
- Browser: `make e2e-pharma` unchanged and passing. The `demo-quantity` and `demo-unverifiable` flows show the same issues as at `1c1f476`.

### Amended expectations (existing tests; only the reason string changes)

Every one of these still asserts `unverifiable`, a null dose and quantity, and `missing_field(dose)` where it did before.

| Test | Input | Old reason | New reason |
|---|---|---|---|
| `test_extract_range_or_unknown_quantity_is_unverifiable` | `ครั้งละ 1-2 เม็ด`, `1-2 tabs`, `1 to 2 tabs`, `1 or 2 tabs`, `1/2-1 tab`, `½-1 tab`, `1-2x2` | `ambiguous_quantity` | `range` |
| same | `one tab`, `สองเม็ด`, `1/0 tab`, `1.5 เม็ดครึ่ง` | `ambiguous_quantity` | `unparsed_token` |
| `test_extract_stray_number_before_quantity_is_unverifiable` | `1 0.5 tab` | `ambiguous_quantity` | `unparsed_token` |
| `test_range_quantity_raises_missing_dose_not_silent_pass` | `ครั้งละ 1-2 เม็ด` | `ambiguous_quantity` | `range` |

## Clinical risks

| Risk | Mitigation |
|---|---|
| An unseen dose form is read as a wrong resolved value, as happened in F1–F7 | A closed grammar: every numeric-ish token must be consumed, otherwise the dose is `unverifiable` → `missing_field(dose)` (A03, A06). ≥ 2000-phrase fuzz against an independent reference with 0 misreads (A07), with teeth shown on the old parser. |
| The grammar and the reference parser share one misunderstanding of the spec | Different technique, no shared code or regex (A08). The generator-label check covers single productions (§F.3). The checker reviews the §G2 table against the reference. |
| Grammar-valid text that is clinically something else, e.g. a dispensed count (`2 tabs` meant as a pack) or a strength inside a drug name | QV ≤ 10 bound. A digit in a name is `unparsed_token`, which is fail-safe. The residual risk is stated in `results.json.notes` and on the page (§7). Pharmacist review is needed before non-synthetic use. |
| More `missing_field(dose)` alerts on real lists (alert burden) | Clean synthetic lists are unchanged (A10, A11). Real-list alert volume must be measured with pharmacist review before non-synthetic use. Labelled System Evaluation. |
| The hyphen mixed number `1-1/2` is read as 1.5, but a writer meant a range | Only a proper fraction after an INT is read as mixed. `INT-INT`, `FRAC-INT`, en dash and `~` are always `range`. Needs pharmacist sign-off (below). |
| A Thai number word inside other Thai text (e.g. inside a drug name) is taken as a stray number | This is fail-safe: the dose becomes `unverifiable`, never a wrong value. 0 collisions in the current formulary and fixtures (A11). |
| A reason label is missing, so the template crashes or the page is blank | A13 checks 6/6 labels in backend and web. |
| Tuning on the test split | 0 new eval cases, frozen artifacts pinned by hash (A09). Metrics must be identical (A10). |

## Run commands

```bash
make test                                   # unit/contract tests incl. grammar, probes, fuzz (offline)
make pharma-eval                            # results.json must match 1c1f476 except versions/notes
make dev API_PORT=8105 WEB_PORT=3105        # API http://127.0.0.1:8105, web http://127.0.0.1:3105/pharmacist/reconcile
make e2e-pharma                             # Playwright pharma specs against 3105/8105
cd backend && python -m pytest tests/test_pharma_s5r3.py -q   # this slice only
```

## Decisions needed (none blocking this slice)

- **Pharmacist:** sign off the §G2 grammar before any non-synthetic use. This covers the hyphen mixed number (`1-1/2`), `วันละ N เม็ด` with N > 1 as `ambiguous_quantity`, and the QV ≤ 10 bound. Carried over from earlier slices: the stated-amount convention and the unverifiable reasons.
- **Innovation Lead + Safety Reviewer:** before an external or model extraction provider is enabled, decide whether the pipeline re-checks every provider-`resolved` dose against this grammar and downgrades a disagreement to `unverifiable`. The recommendation is yes.
- **Integration-auditor awareness:** the `pharma.extract.v2` reason enum is widened additively. There is no task-name or gateway-contract change.
