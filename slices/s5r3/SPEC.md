# Slice s5r3 — Pharma Agent v1.3 (strict dose grammar, fail-safe on anything else)

- Owner (Gantt): ธัญรดา / ภูริณัฐ
- Source of truth: `docs/PROPOSAL.md` (v8) 3.2.4 (the model extracts name, dose and frequency; rules are primary; flag dose **or frequency** differences between sources for pharmacist review), 3.6 / Table 3.2 (recall from synthetic error injection, 95% patient-level bootstrap CIs, System Evaluation label). Decisions: `docs/DECISIONS.md` 2026-09-26 (formulary licence) and 2026-09-27 (evaluation definitions).
- **Delta** on `slices/s5/SPEC.md`, `slices/s5r/SPEC.md` and `slices/s5r2/SPEC.md` at branch tip `1c1f476`. Everything in those files still applies unless this file replaces it. Where they conflict, this file wins.
- Trigger: three s5r2 check rounds each found a new dose form that `backend/app/pharma/mock_rules.py` misread as a resolved value (F1–F7 below). The extractor matched pieces of the text and ignored the rest, so every unseen form was a new silent misread. This slice replaces piecewise matching with a **closed grammar**: anything the grammar does not consume makes the dose `unverifiable`.
- **Revision 2 (after checker round 1 on `29d8b20`).** Changes from revision 1:
  - T1: Thai half-hour time expressions. `ครึ่ง` + `ชั่วโมง`/`ชม.`/`นาที` was being read as half a tablet.
  - R1: a strength or quantity followed by `/`, `per` or `ต่อ` (mg/day, mg/kg, มก./วัน, มก.ต่อวัน) is now unverifiable with the new reason `per_unit_amount`. The L1 liquid form is the only exception.
  - The QV ≤ 10 bound now applies to Q3/Q4.
  - G1 now writes down the whitespace rule and the undotted-unit word-only rule.
  - Version strings are bumped.
- Status: PLAN rev 2. All data is synthetic (`data_class="synthetic"`). Tier 0 only. No external provider. Servers, if started: API 8105, web 3105.

## Scope

1. **One closed grammar table.** Dose, quantity and every numeric token in the entry are read by the tokeniser (§G1) and the productions (§G2). Nothing else reads them. `mock_rules.py` holds the productions in **one** table, `DOSE_GRAMMAR`, keyed by the production IDs in §G2.
   - The piecewise regexes are deleted: `DOSE_RE`, `QTY_RE`, `_QTY_NUM`, `_MIXED_RE`, `_STRAY_NUM_BEFORE_RE`, `_QTY_WORD_RE`, and `TIMES_RE` as a dose reader.
   - The frequency code mapping stays: `FREQ_PATTERNS`, `EVERY_RE`, `NON_DAILY_RE` and `FREQ_LIKE_RE`. Its numeric tokens are consumed only by productions F1–F3.
2. **Resolution rule.** The whole entry is tokenised. The dose is `resolved` only if all of these hold:
   - every numeric-ish token (§G1) is consumed by exactly one production;
   - no production or conflict that makes the dose unverifiable fired (R1, S3, L1, Q7 > 1, or a §G2 conflict);
   - exactly one distinct strength (S1 value and unit) is read.

   If no strength is read and no numeric-ish token is left over, the dose is `not_stated`. In every other case it is `unverifiable`, with `dose_value`, `dose_unit` and `quantity` all `null`. The reason is the first that applies, in this order: `variable_regimen` > `liquid_volume` > `multiple_strengths` > `per_unit_amount` > `range` > `ambiguous_quantity` > `unparsed_token`.
3. **Reason enum widened** to 7 values. `UnverifiableReason` gains `range`, `unparsed_token` and `per_unit_amount`. The change is additive, and the task name stays `pharma.extract.v2`. Each reason has a label in `backend/app/pharma/phrasing.py` (`UNVERIFIABLE_WORDS`) and in `web/lib/pharma.ts`:
   - `range`: "a range or alternative between two amounts"
   - `unparsed_token`: "a dose form this checker does not read"
   - `per_unit_amount`: "an amount per day, per weight or per other unit, not per dose"

   Downstream behaviour is unchanged from s5r2 §4. An unverifiable dose raises `missing_field(dose)` with `field_status=unverifiable` and the reason. It never produces or suppresses a `dose_mismatch`, and it is counted in `unchecked_comparisons` / `unchecked_by_reason.unverifiable`.
4. **Frequency is unchanged.** For every input in the fixtures and existing tests, `frequency_code` and `frequency_status` stay as they are at `1c1f476`. The one exception is Q5 with a fractional N (`½x1`, `1/2x2`), which now yields the code of M, the same as an integer N. R1 and T1 do not change frequency.
5. **Property/fuzz test and reference parser** (§F).
6. **Versions** (revision 2 bumps every constant that was introduced at `00cf648`):

   | Constant | Value |
   |---|---|
   | `MOCK_RULES_VERSION` | `s5-mock-rules-2.1.0` |
   | `DOSE_GRAMMAR_VERSION` | `s5-dose-grammar-1.1.0` |
   | `TEMPLATE_VERSION` | `template-1.3.0` |
   | pipeline version | `s5-pipeline-2.3.0` |

   `RULES_VERSION` and `RULE_VERSIONS` do not change. Every run and `results.json.versions` records all of these, including `dose_grammar`.
7. **Truthful residual-risk wording.**
   - `results.json.notes[0]` and the page scope section say the dose is read by a fixed, listed grammar and that any other form is shown as "could not be verified". The words "may be misread as resolved" are dropped.
   - The caveat stays that a grammar-valid phrase can still be clinically wrong. For example, `2 tabs` written for a dispensed count is still read as 2 tablets per dose.
8. **Frozen data untouched.** These stay byte-identical to `1c1f476`:
   - `fixtures/patients.json`;
   - `fixtures/test_manifest.json` (v3);
   - `injection_log.jsonl` and `injection_log_surface.jsonl`;
   - the generators.

   This slice adds **no** evaluation cases. Probe and fuzz strings are unit-test inputs and belong to no split. If a later slice needs new eval cases, they go in manifest v4, frozen before any evaluation.

### G1 — Tokeniser (normalise, then classify)

- **Normalise.** NFC (not NFKC, so `½` survives), then casefold Latin, and `×` becomes `x`. Thai digits `๐–๙`, full-width digits and superscripts are **not** converted.
- **Whitespace rule.**
  - Whitespace is any character for which Python `str.isspace()` is true. Each run is collapsed to one ASCII space.
  - Whitespace only separates tokens and carries no other meaning. Every `␣?` in §G2 means "zero or one space". A production matches the same text with or without that space. This includes the space **before and after `ครึ่ง`** in Q4a, Q4b and T1: `1 เม็ดครึ่ง`, `1 เม็ด ครึ่ง`, `ครึ่งชั่วโมง` and `ครึ่ง ชั่วโมง` are each read the same way as their other spacing.
  - The only required space is `␣` in Q3 `INT ␣ FRAC`. Joining would change the digit tokens: `11/2` is the tokens `11 / 2`, not `1 1/2`.
  - Zero-width characters (U+200B, U+200C, U+200D, U+2060, U+FEFF) are **not** whitespace. They are `OTHER` tokens and break any production they fall inside, so the result is fail-safe.
- **Token classes:**
  - `NUM`: ASCII digits, optionally followed by `.` and digits. The value is exact (`Fraction`).
  - `UFRAC`: any other character with a Unicode numeric value (`½ ¼ ¾ ⅓ ⅛ ๑ ２ …`).
  - Latin words.
  - Thai lexemes, matched longest-first from this closed lexicon: `เม็ด แคปซูล ครึ่ง ครั้งละ วันละ สัปดาห์ละ อาทิตย์ละ เดือนละ ครั้ง ทุก ชั่วโมง ชม. นาที ต่อ มก. มก มิลลิกรัม กรัม ไมโครกรัม ยูนิต มล. มล และ หรือ ถึง หนึ่ง สอง สาม สี่ ห้า หก เจ็ด แปด เก้า สิบ`.
    - **Word-only rule.** The undotted `มก` and `มล` are lexemes only when the characters on **both** sides are not Thai: start or end of text, a space, a digit, Latin text or punctuation. Otherwise they are part of the surrounding `OTHER` text. For example, `5 มกราคม` (January) and `5 มลพิษ` are not units, and `มล` inside `แอมลอดิปีน` is not a unit. The dotted `มก.` and `มล.` carry their own boundary.
    - `ต่อ` is matched as a prefix, so `ต่อวัน` gives `ต่อ` + `วัน`. Over-matching it can only make a dose unverifiable (R1), never resolved.
    - Other Thai text is `OTHER`.
  - Symbols: `/ ⁄ . , - – — ~ x + &`.
- **Numeric-ish tokens.** Each of these must be consumed:
  - `NUM` and `UFRAC`;
  - EN number words `one two three four five six seven eight nine ten half once twice thrice`;
  - the TH number words in the lexicon, including `ครึ่ง`;
  - strength `UNIT` tokens (S1);
  - quantity words `QW` = `tab tabs tablet tablets cap caps capsule capsules เม็ด แคปซูล`;
  - any symbol or connector (`to or and ถึง หรือ และ`) next to a `NUM`, `UFRAC` or number word, ignoring whitespace.

  An unconsumed connector from `- – — ~ to or and ถึง หรือ และ` between two numeric-ish tokens gives `range`. Any other unconsumed numeric-ish token gives `unparsed_token`.

### G2 — Productions (the complete, closed list)

Value constraints:

- `INT`: no leading zero.
- `FRAC`: `1/2`, `1/4` or `3/4` (spaces around `/` allowed), or a `UFRAC` in {`½`, `¼`, `¾`}.
- `QV` bound: **the final quantity of every quantity production Q1–Q7** must satisfy `0 < v ≤ 10` with `4v` a whole number. This covers:
  - Q1's number;
  - Q3's INT + FRAC;
  - Q4b's INT + ½;
  - Q5's N;
  - the inner value of Q6/Q7.

  A value that breaks a constraint means the production does **not** match. Its tokens stay unconsumed, which gives `unparsed_token`. For example, `30 1/2 tabs` and `12 เม็ดครึ่ง` are `unparsed_token`, not 30.5 or 12.5.

`TW` (time word) is text directly after `ครึ่ง␣?` that **starts with** `ชั่วโมง`, `ชม` (dotted or not), `ช.ม.` or `นาที`, or a next token that is an EN word in {`h hr hrs hour hours min mins minute minutes`}.

| ID | Form (EN / TH) | Examples | Result |
|---|---|---|---|
| S1 | `NUM ␣? UNIT`. UNIT ∈ `mg g gm mcg µg ug unit units u iu ml มก. มก มิลลิกรัม กรัม ไมโครกรัม ยูนิต มล. มล` (undotted forms under the G1 word-only rule). NUM > 0 and not preceded by `/` | `3 mg`, `3mg`, `500 มก.`, `3 มก`, `15 ml` | strength (value, canonical unit) |
| S2 | `NUM / NUM ␣? UNIT` (combination) | `875/125 mg` | consumed; dose not read (`not_stated`, s5 gold kept) |
| S3 | ≥ 2 S1 with distinct (value, unit), with or without a joiner `+ , & and และ` | `3 mg + 1 mg`, `3 mg and 2 mg` | `multiple_strengths` |
| L1 | `NUM ␣? MASS ␣? / ␣? NUM? ␣? VOL`, optionally followed by `NUM ␣? VOL`. MASS = the mass units of S1; VOL = `ml มล. มล` | `250 mg/5 ml 10 ml`, `120 มก./5 มล. 5 มล.`, `50 mcg/ml` | `liquid_volume` |
| **R1** | `(UNIT \| QW) ␣? (/ \| ⁄ \| per \| ต่อ) ␣? X`, where X is the next token of any kind, **unless** the UNIT and `/` begin an L1 match | `1000 mg/day`, `1000 มก./วัน`, `1000 มก.ต่อวัน`, `1000 มก. ต่อ วัน`, `5 mg/kg`, `500 mg per day`, `2 tabs/day`, `2 เม็ด/วัน`, `100 units/ml` | `per_unit_amount`. The amount is per day, weight or another unit, not per dose |
| Q1 | `QV ␣? QW` (INT or decimal) | `2 tabs`, `2tabs`, `1.5 เม็ด`, `3 แคปซูล` | quantity = QV |
| Q2 | `FRAC ␣? QW` | `1/2 tab`, `½ เม็ด` | 0.25 / 0.5 / 0.75 |
| Q3 | Mixed number: `INT (␣ \| ␣?-␣? \| ␣?and␣? \| ␣?และ␣?) FRAC ␣? QW`, or `INT ␣? UFRAC ␣? QW`. Total within the QV bound | `1 1/2 tab`, `1-1/2 tab`, `1 and 1/2 tab`, `1และ1/2 เม็ด`, `1½ tab` | INT + FRAC |
| Q4a | `ครึ่ง ␣? (เม็ด\|แคปซูล)` | `ครึ่งเม็ด`, `ครึ่ง แคปซูล` | 0.5 |
| Q4b | `INT ␣? (เม็ด\|แคปซูล) ␣? ครึ่ง`, where the `ครึ่ง` is **not** followed by `␣? TW`. Total within the QV bound | `1 เม็ดครึ่ง`, `2เม็ดครึ่ง`, `1 เม็ด ครึ่ง ก่อนนอน` | INT + 0.5 |
| Q5 | `N ␣? x ␣? M`. N ∈ {INT, decimal, FRAC} within the QV bound; M ∈ {1,2,3,4}; no QW follows | `2x2`, `1x1 หลังอาหารเช้า`, `½x1`, `1/2x2` | quantity = N; frequency code of M (q24h/q12h/q8h/q6h) |
| Q6 | `ครั้งละ ␣? (Q1\|Q2\|Q3\|Q4a\|Q4b)` | `ครั้งละ2เม็ด`, `ครั้งละ ครึ่งเม็ด` | value of the inner production |
| Q7 | `วันละ ␣? (Q1\|Q2\|Q3\|Q4a\|Q4b)` | `วันละ 1 เม็ด`, `วันละครึ่งเม็ด` | value ≤ 1: quantity = value. Value > 1: `ambiguous_quantity` (a daily total) |
| **T1** | `ครึ่ง ␣? TW` (Thai half-hour or half-minute time expression) | `ก่อนอาหารครึ่งชั่วโมง`, `ครึ่ง ชม.`, `ครึ่งชม`, `ครึ่งนาที` | `ครึ่ง` and TW consumed as **time, never a quantity**. No quantity and no frequency |
| F1 | `q ␣? INT ␣? (h\|hr\|hrs\|hour\|hours)`, `every INT (h\|hr\|hrs\|hour\|hours)`, `ทุก ␣? INT ␣? (ชั่วโมง\|ชม.)` | `q6h`, `every 8 hours`, `ทุก 6 ชั่วโมง` | numbers consumed; code from the existing mapping (6/8/12/24), otherwise `not_recognised` |
| F2 | `(INT\|one\|two\|three\|four) (time\|times) (a\|per)? (day\|daily\|week\|weekly\|month\|monthly)`, or `(once\|twice\|thrice) (a\|per)? (day\|daily\|week\|weekly\|month\|monthly)`. `time`/`times` is required after a numeral | `twice daily`, `3 times a week`, `2 times per day` | consumed; existing mapping (non-daily → `not_recognised`). The `per` inside F2 is not R1, because it follows `time(s)`, not a UNIT or QW |
| F3 | `(วันละ\|สัปดาห์ละ\|อาทิตย์ละ\|เดือนละ) ␣? INT? ␣? ครั้ง` | `วันละ 3 ครั้ง`, `วันละครั้ง` | consumed; existing mapping |

Conflicts:

- **Half-hour against half-tablet.** A `ครึ่ง` that starts a T1 match may also be the `ครึ่ง` of a Q4b, that is, preceded by `INT ␣? (เม็ด|แคปซูล) ␣?`. In that case the entry is `ambiguous_quantity`. Examples: `1 เม็ดครึ่งชั่วโมงก่อนอาหาร` and `ครั้งละ 1 เม็ด ครึ่ง ชม. ก่อนอาหาร`. Such text reads as either "1 tablet, half an hour before" or "1½ tablets, … hour", so neither value is chosen.
  - A T1 that cannot complete a Q4b is only a time expression. Examples:
    - `1 เม็ด ก่อนอาหารครึ่งชั่วโมง` is quantity 1;
    - `ครึ่งเม็ด ครึ่งชั่วโมงก่อนอาหาร` is quantity 0.5;
    - `1 เม็ดครึ่ง ครึ่งชั่วโมงก่อนอาหาร` is quantity 1.5.
- Two or more quantity productions (Q1–Q7) with **distinct** values give `ambiguous_quantity`, e.g. `2 tabs 1x2`. Equal values stay resolved, e.g. `1 tab 1x2`.
- Two S1 with equal (value, unit) stay resolved.
- Variable-regimen keywords (s5r2 §2) are checked before all productions and win.

Nothing else consumes a numeric-ish token. The following are always unverifiable:

- a bare number;
- a bare quantity word;
- a number word used as a quantity (`one tab`, `สองเม็ด`);
- an invalid or unlisted fraction (`1/0`, `3/2`, `⅓`);
- a Thai digit, `.5` or `1,000`;
- a trailing stray digit;
- `x2` with no N;
- a quantity above 10;
- any range;
- any per-unit amount other than L1.

### F — Property/fuzz test and reference parser

- **Reference parser.** `backend/tests/pharma_dose_reference.py` is written only from §G1–§G2. It uses a hand-written token scanner, not the `DOSE_GRAMMAR` table, and imports nothing from `app.pharma`. It returns `(dose_status, dose_value, dose_unit, quantity, reason)`. Revision 2 adds R1, T1, the conflict rule and the QV bound on Q3/Q4b to it.
- **Generator.** Seeded (`seed=5303`), standard library only, **≥ 2000** phrases per run. Each phrase is `[drug name EN|TH] + [strength] + [quantity] + [frequency] + [tail]`. Segments are joined by one of `{"", " ", "  "}`. The segment alphabet is:
  - valid instances of every production (EN and TH);
  - the revision-1 adversarial classes: ranges (`- – — ~ to or and ถึง หรือ และ`), bare or stray numbers, `.5`, `1,000`, `0`, `12`, `30`, `1.3`, `3/2`, `1/0`, `2/3`, `⅓`, `๑`, number words, bare QW, `x2`, `2x`, `2x5`, conflicting quantities, `q4-6h`, `1-2 times daily`, L1/S2/S3, variable-regimen words, and Thai unit prefixes;
  - **new in revision 2:**
    - `th_half_time`: `ครึ่ง` + each TW, with and without a space, placed both directly after `INT เม็ด` (the conflict case) and elsewhere in the tail;
    - `per_unit`: UNIT or QW + `/ ⁄ per ต่อ` + {`day d kg dose วัน กก. ครั้ง ml`}, with and without spaces, plus L1 look-alikes that must stay `liquid_volume`;
    - `qv_over`: Q3/Q4b/Q5 totals in (10, 40].
- **Strata, checked in the test:**
  - ≥ 25% of phrases reference-`resolved` and ≥ 25% reference-`unverifiable`;
  - every production and every adversarial class appears ≥ 20 times;
  - EN and TH quantity segments are each ≥ 30%.
- **Assertions:**
  1. **Safety.** 0 phrases where the implementation returns `resolved` and either the reference is not `resolved` or `(dose_value, dose_unit, quantity)` differs.
  2. **Agreement.** `dose_status` and `reason` agree with the reference on 100% of phrases.
  3. **Reference check.** For phrases built from exactly one valid quantity production, the reference value equals the value the generator built.
  4. **Teeth.** The same harness, run on a stub piecewise parser defined in the test, finds ≥ 1 misread **in each** of these classes: mixed number, range, `th_half_time`, `per_unit` and `qv_over`.

  Each failure prints the phrase and both outputs.

## Out of scope

- Converting ranges, liquids, per-unit amounts (mg/kg, mg/day) or variable regimens into a comparable dose. No new discrepancy type or threshold change.
- Reading time expressions other than T1, such as `30 นาที`, `1 hr before meals` or `half an hour`. Their numbers remain unconsumed, so the dose stays `unparsed_token` (fail-safe).
- Frequency-grammar redesign beyond the numeric consumption in F1–F3.
- Thai-digit or number-word **reading**. Both stay unverifiable.
- Applying the grammar as a verifier over a non-mock extraction provider (see Decisions).
- DDI, dose-range, renal or hepatic and route checks, real or MIMIC data, TMT/ATC, the gateway contract version, and s0 audit semantics.
- New eval cases or any manifest change.

## Acceptance

Thresholds apply to the frozen `test` split **and** to all patients, and both are reported.

| ID | Criterion | Threshold | How measured |
|---|---|---|---|
| S5R3-A01 | All prior items still pass | S5-A01..A18, S5R-A01..A11 and S5R2-A01..A18 pass. The only amendments: S5R2-A16 reads the §6 version strings, and the tests under "Amended expectations" change only the reason string. Any other changed prior expectation is a STOP, and the spec goes back to the planner | `make test`, `make pharma-eval`, `make e2e-pharma`; per-ID checklist in the builder report |
| S5R3-A02 | `make test` green | Exit 0, 0 failed, 0 errors, 0 skip/xfail on pharma tests, offline; the fuzz runs in the default suite in ≤ 20 s | `make test` from a clean clone of `factory/s5r3` |
| S5R3-A03 | Grammar is one closed table | `DOSE_GRAMMAR` IDs equal {S1, S2, S3, L1, R1, Q1, Q2, Q3, Q4, Q5, Q6, Q7, T1, F1, F2, F3} exactly (Q4 covers Q4a/Q4b); 0 occurrences of the deleted regex names in `backend/app/pharma/`; every `resolved` parse trace has 0 unconsumed numeric-ish tokens | pytest `test_grammar_table_closed`, `test_no_piecewise_dose_regex`, `test_resolved_consumes_all_numeric_tokens` |
| S5R3-A04 | F1–F7 probes: 0 misreads | 15/15 probe strings (table below) give exactly the listed result: the correct value or `unverifiable`, never another number | pytest `test_probe_f1_f7[...]` |
| S5R3-A05 | Every production reads exactly | 100% of positive cases give the gold (value, unit, quantity). There are ≥ 2 per production, EN and TH where the form exists. The s5r2 `QUANTITY_FORMS`, `QUANTITY_FORMS_REGRESSION` and `QUANTITY_FORMS_REGRESSION_2` sets still pass unchanged | pytest `test_grammar_positive[...]` plus the existing s5r2 tests |
| S5R3-A06 | Anything else is unverifiable, visibly | 100% of negative cases give `unverifiable` with the listed reason and a null dose and quantity. In a two-source snapshot each gives 1 `missing_field(dose)` (`field_status=unverifiable`, reason) and 0 `dose_mismatch`, and `unchecked_by_reason.unverifiable` rises by the number of pairs | pytest `test_grammar_negative[...]`, `test_negative_raises_missing_dose[range\|unparsed_token\|ambiguous_quantity\|per_unit_amount]` |
| S5R3-A07 | Fuzz: 0 misreads | ≥ 2000 phrases; strata as in §F; 0 safety violations; 100% status and reason agreement; reference check 100%; the stub is caught in each of the 5 classes. The checker also runs the harness on the `1c1f476` parser and on the `29d8b20` parser and reports ≥ 1 misread for each. On `29d8b20` the misreads must include ≥ 1 `th_half_time`, ≥ 1 `per_unit` and ≥ 1 `qv_over` | pytest `test_dose_fuzz_vs_reference`, `test_fuzz_catches_piecewise_stub`; checker run with `git show <rev>:backend/app/pharma/mock_rules.py` |
| S5R3-A08 | Reference is independent | `pharma_dose_reference.py` imports no `app.*` module (AST scan) and shares no regex literal with `mock_rules.py` | pytest `test_reference_independent` |
| S5R3-A09 | Frozen data untouched | sha256 of `patients.json`, `test_manifest.json`, `injection_log.jsonl` and `injection_log_surface.jsonl` equals `1c1f476`; the manifest stays v3; 0 new eval cases | pytest `test_frozen_artifacts_unchanged` (hashes pinned); `git diff 1c1f476 --stat` in the builder report |
| S5R3-A10 | Evaluation still holds | Every `results.json` field except `versions` and `notes` equals `1c1f476`, including: recall ≥ 0.95 for each of the 9 types and each surface form (test and all, Clopper–Pearson then bootstrap CI); clean false alerts ≤ 0.10; extra issues per case ≤ 0.10; extraction accuracy ≥ 0.98; `label` = System Evaluation | `make pharma-eval`; pytest `test_eval_thresholds`, `test_results_unchanged_except_versions` |
| S5R3-A11 | Clean fixtures use only grammar forms | 100% of entries in every clean patient (96/96) parse `resolved` with 0 unconsumed numeric-ish tokens and the gold quantity; 0 clean entries hit R1 or T1; 100% of surface-suite `after` strings give their logged expected status and reason | pytest `test_clean_fixtures_grammar_only`, `test_surface_after_strings_expected` |
| S5R3-A12 | Frequency unchanged | For 100% of fixture entries and existing pharma test inputs, `frequency_code`/`frequency_status` equal the `1c1f476` output (pinned table). The only allowed change is the §4 Q5-fraction exception. All T1 and R1 probes give the same frequency as the same entry with the T1/R1 segment removed | pytest `test_frequency_unchanged`, `test_t1_r1_frequency_neutral` |
| S5R3-A13 | Reasons labelled end to end | `UnverifiableReason` has exactly the 7 values; 7/7 have a label in `phrasing.py` and `web/lib/pharma.ts`; the page renders `not verifiable (a range or alternative between two amounts)` and `not verifiable (an amount per day, per weight or per other unit, not per dose)`; the template passes validation for `range`, `unparsed_token` and `per_unit_amount` | pytest `test_reason_labels_complete`, `test_templates_pass_validation`; Vitest `field status labels[range\|unparsed_token\|per_unit_amount]` |
| S5R3-A14 | Versions and wording | The §6 strings appear in code, in every run and in `results.json.versions`; `notes[0]` and the scope section contain "could not be verified" and not "may be misread"; 0 `all doses`/`every dose` claims; 0 serious/critical axe violations; 0 colour literals; 0 `diagnos\|prescrib\|treat` in UI copy | pytest `test_versions_bumped` (amended), `test_results_notes_grammar`; Vitest `scope limits`; `make e2e-pharma`; s0 `test_repo_hygiene` |
| S5R3-A15 | Thai half-hour is time, never a half tablet | 13/13 H-probes (table below) give exactly the listed result; 0 cases where `ครึ่ง` + TW adds 0.5 to a quantity; spaced and joined variants give identical output | pytest `test_probe_half_hour[...]`, `test_half_whitespace_equivalent` |
| S5R3-A16 | Per-unit amounts are unverifiable | 12/12 U-probes give exactly the listed result; every R1 case is `per_unit_amount` with a null dose, 1 `missing_field(dose)` and 0 `dose_mismatch` in a two-source snapshot; L1 cases stay `liquid_volume` | pytest `test_probe_per_unit[...]`, `test_negative_raises_missing_dose[per_unit_amount]` |
| S5R3-A17 | QV bound on every quantity production | 6/6 V-probes give exactly the listed result; 0 resolved quantities > 10 over all probe, positive and fuzz outputs | pytest `test_probe_qv_bound[...]`; assertion inside `test_dose_fuzz_vs_reference` |
| S5R3-A18 | Undotted units are word-only | 5/5 W-probes give exactly the listed result | pytest `test_probe_undotted_unit[...]` |

### F1–F7 probe table (S5R3-A04), unchanged from revision 1

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
| P1 | `Warfarin 3 mg 3 od` | unverifiable, `unparsed_token` |
| P2 | `Warfarin 3 mg 2 tabs x 2` | unverifiable, `unparsed_token` |
| P3 | `Aspirin 81 mg 1x1 หลังอาหารเช้า 1` | unverifiable, `unparsed_token` |
| P4 | `Paracetamol 500 mg 1 tab or 2 tabs prn` | unverifiable, `range` |

### H-probes: Thai half-hour (S5R3-A15)

| Probe | Input | Expected |
|---|---|---|
| H1 | `วาร์ฟาริน 3 มก. 1 เม็ด ก่อนอาหารครึ่งชั่วโมง` | 3 mg, qty 1, resolved |
| H2 | `วาร์ฟาริน 3 มก. 1 เม็ด ก่อนอาหาร ครึ่ง ชั่วโมง` | 3 mg, qty 1, resolved |
| H3 | `วาร์ฟาริน 3 มก. 1 เม็ดครึ่งชั่วโมงก่อนอาหาร` | unverifiable, `ambiguous_quantity` |
| H4 | `วาร์ฟาริน 3 มก. 1 เม็ด ครึ่งชั่วโมงก่อนอาหาร` | unverifiable, `ambiguous_quantity` |
| H5 | `วาร์ฟาริน 3 มก. 1 เม็ด ครึ่ง ชม. ก่อนอาหาร` | unverifiable, `ambiguous_quantity` |
| H6 | `วาร์ฟาริน 3 มก. ครั้งละ 1 เม็ดครึ่งชั่วโมงก่อนอาหาร` | unverifiable, `ambiguous_quantity` (via Q6) |
| H7 | `วาร์ฟาริน 3 มก. วันละ 1 เม็ด ครึ่งชม ก่อนอาหาร` | unverifiable, `ambiguous_quantity` (via Q7) |
| H8 | `วาร์ฟาริน 3 มก. 1 เม็ดครึ่งนาที` | unverifiable, `ambiguous_quantity` |
| H9 | `วาร์ฟาริน 3 มก. ครึ่งเม็ด ครึ่งชั่วโมงก่อนอาหาร` | 3 mg, qty 0.5, resolved |
| H10 | `วาร์ฟาริน 3 มก. 1 เม็ดครึ่ง ครึ่งชั่วโมงก่อนอาหาร` | 3 mg, qty 1.5, resolved |
| H11 | `วาร์ฟาริน 3 มก. 1 เม็ดครึ่ง ก่อนนอน` | 3 mg, qty 1.5, resolved (Q4b still works) |
| H12 | `วาร์ฟาริน 3 มก. 1 เม็ด ครึ่ง ก่อนนอน` | 3 mg, qty 1.5, resolved (whitespace before `ครึ่ง` allowed) |
| H13 | `วาร์ฟาริน 3 มก. 1 เม็ด ก่อนอาหารครึ่ง hr` | 3 mg, qty 1, resolved |

### U-probes: per-unit amounts (S5R3-A16)

| Probe | Input | Expected |
|---|---|---|
| U1 | `Metformin 1000 mg/day` | `per_unit_amount` |
| U2 | `เมทฟอร์มิน 1000 มก./วัน` | `per_unit_amount` |
| U3 | `เมทฟอร์มิน 1000 มก.ต่อวัน` | `per_unit_amount` |
| U4 | `เมทฟอร์มิน 1000 มก. ต่อ วัน` | `per_unit_amount` |
| U5 | `Gentamicin 5 mg/kg q24h` | `per_unit_amount`, frequency q24h unchanged |
| U6 | `Enoxaparin 1 mg / kg bid` | `per_unit_amount`, frequency q12h unchanged |
| U7 | `Metformin 500 mg per day` | `per_unit_amount` |
| U8 | `Metformin 500 mg 2 tabs/day` | `per_unit_amount` |
| U9 | `เมทฟอร์มิน 500 มก. 2 เม็ด/วัน` | `per_unit_amount` |
| U10 | `Metformin 500-1000 mg/day` | `per_unit_amount` (precedes `range`) |
| U11 | `Paracetamol syrup 250 mg/5 ml 10 ml prn` | `liquid_volume` (L1 exception, unchanged) |
| U12 | `Metformin 500 mg 2 times per day` | 500 mg, resolved, q12h (the F2 `per` is not R1) |

### V-probes: QV bound (S5R3-A17)

| Probe | Input | Expected |
|---|---|---|
| V1 | `Warfarin 3 mg 30 1/2 tabs` | `unparsed_token` |
| V2 | `Warfarin 3 mg 30 ½ tab` | `unparsed_token` |
| V3 | `Warfarin 3 mg 10 1/2 tab` | `unparsed_token` (10.5 > 10) |
| V4 | `วาร์ฟาริน 3 มก. 12 เม็ดครึ่ง` | `unparsed_token` |
| V5 | `Warfarin 3 mg 9 1/2 tab` | 3 mg, qty 9.5, resolved |
| V6 | `Warfarin 3 mg 12x2` | `unparsed_token` |

### W-probes: undotted units (S5R3-A18)

| Probe | Input | Expected |
|---|---|---|
| W1 | `วาร์ฟาริน 3 มก 1 เม็ด` | 3 mg, qty 1, resolved |
| W2 | `Paracetamol syrup 120 มก/5 มล 5 มล` | `liquid_volume` |
| W3 | `แอมลอดิปีน 5 มก. 1 เม็ด วันละครั้ง` | 5 mg, qty 1, resolved (`มล` inside the name is not a unit) |
| W4 | `Warfarin 3 mg 1 tab เริ่ม 5 มกราคม` | `unparsed_token` (`5` is unconsumed, not 5 mg) |
| W5 | `ยา 5 มลพิษ 1 เม็ด` | `unparsed_token` (`5` is unconsumed, not 5 ml) |

## Required test cases

- `test_grammar_positive[...]`: ≥ 2 per production (the §G2 examples), plus:
  - `3mg 2tabs od` gives 3 mg × 2;
  - `วาร์ฟาริน 3 มก. ครั้งละ ครึ่งเม็ด` gives 0.5;
  - `Metformin 500 mg 1 tab 1x2` gives 1 with q12h;
  - `Augmentin 875/125 mg bid` gives `not_stated`;
  - H1, H9, H10, U12, V5.
- `test_grammar_negative[...]`: the revision-1 table stays. It reuses the reason list in `slices/s5r3/SPEC.md@02ed203`, which is listed again here for completeness:
  - `⅓ tab`, `.5 tab`, `3/2 tab`, `๑ เม็ด`, `half tab`, `1,000 mg`, `30 tabs`, `x2`, `2x5`, `2 x1 tab`, bare `tab`, `0 tab`: `unparsed_token`;
  - `500-1000 mg`, `1 ถึง 2 เม็ด`, `1 หรือ 2 เม็ด`, `1–2 tabs`, `1~2 tabs`: `range`;
  - `วันละ 2 เม็ด`, `2 tabs 1x2`: `ambiguous_quantity`.

  Revision 2 adds H3–H8, U1–U10, V1–V4, V6 and W4–W5.
- Probe suites: `test_probe_f1_f7[...]`, `test_probe_half_hour[...]`, `test_probe_per_unit[...]`, `test_probe_qv_bound[...]`, `test_probe_undotted_unit[...]`.
- `test_half_whitespace_equivalent`: for each of H1–H12, the variants with 0 and with 1 space before `ครึ่ง`, and between `ครึ่ง` and TW or QW, give identical output. It also checks that a U+200B inside `เม็ด​ครึ่ง` gives `unparsed_token`, not 1.5.
- `test_t1_r1_frequency_neutral`, `test_negative_raises_missing_dose[range|unparsed_token|ambiguous_quantity|per_unit_amount]`.
- `test_grammar_table_closed` (amended set), `test_no_piecewise_dose_regex`, `test_resolved_consumes_all_numeric_tokens`.
- `test_dose_fuzz_vs_reference` (new classes, reason agreement, 0 resolved > 10), `test_fuzz_catches_piecewise_stub` (5 classes), `test_reference_independent`.
- `test_frozen_artifacts_unchanged`, `test_results_unchanged_except_versions`, `test_clean_fixtures_grammar_only`, `test_surface_after_strings_expected`, `test_frequency_unchanged`.
- `test_reason_labels_complete` (7), `test_results_notes_grammar`, `test_versions_bumped` (amended).
- Web (Vitest `pharma-page.test.tsx`): `field status labels[range|unparsed_token|per_unit_amount]`, and `scope limits` includes the grammar sentence.
- Browser: `make e2e-pharma` unchanged and passing. The `demo-quantity` and `demo-unverifiable` flows show the same issues as at `1c1f476`.

### Amended expectations (existing tests; only the reason string or this slice's own constants change)

Each of these still asserts `unverifiable`, a null dose and quantity, and `missing_field(dose)` where it did before.

| Test | Input | Old | New |
|---|---|---|---|
| `test_extract_range_or_unknown_quantity_is_unverifiable` | `ครั้งละ 1-2 เม็ด`, `1-2 tabs`, `1 to 2 tabs`, `1 or 2 tabs`, `1/2-1 tab`, `½-1 tab`, `1-2x2` | `ambiguous_quantity` | `range` |
| same | `one tab`, `สองเม็ด`, `1/0 tab`, `1.5 เม็ดครึ่ง` | `ambiguous_quantity` | `unparsed_token` |
| `test_extract_stray_number_before_quantity_is_unverifiable` | `1 0.5 tab` | `ambiguous_quantity` | `unparsed_token` |
| `test_range_quantity_raises_missing_dose_not_silent_pass` | `ครั้งละ 1-2 เม็ด` | `ambiguous_quantity` | `range` |
| s5r3 `test_grammar_table_closed`, `test_reason_labels_complete`, `test_versions_bumped` | constants | rev-1 set, 6 reasons, rev-1 versions | §G2 set with R1 and T1, 7 reasons, §6 versions |

## Clinical risks

| Risk | Mitigation |
|---|---|
| An unseen dose form is read as a wrong resolved value (F1–F7) | Closed grammar with every numeric-ish token consumed, otherwise `unverifiable` and `missing_field(dose)` (A03, A06). Fuzz of ≥ 2000 phrases against an independent reference, with 0 misreads (A07). Teeth are shown on `1c1f476` and `29d8b20`. |
| A Thai time phrase `ครึ่งชั่วโมง` is read as half a tablet, giving a 1.5× warfarin dose | T1 treats it as time, never quantity. Where it could still be the half of `N เม็ดครึ่ง`, the entry is `ambiguous_quantity` rather than either value (A15). |
| A daily or weight-based total (mg/day, mg/kg) is compared as a per-dose strength, hiding 2-fold or larger differences (same class as B1) | R1 gives `per_unit_amount`, so the dose is shown as "could not be verified" and never compared (A16). L1 liquids are unchanged. |
| A quantity-looking count above 10 (e.g. `30 1/2 tabs`, a dispensed count) is read as a per-dose amount | QV bound on every quantity production (A17). |
| A Thai word that starts with a unit (`มกราคม`, `มลพิษ`) is read as a strength | Word-only rule, written in G1 and tested (A18). |
| The grammar and the reference share one misreading of the spec | Different technique, no shared code or regex (A08). Generator-built values are checked (§F.3). The checker reviews §G2 against the reference. |
| Grammar-valid text that is clinically something else (a pack count, `mg/tab` written as a per-unit strength) | QV ≤ 10. R1 makes `mg/tab` unverifiable, which is fail-safe. The residual risk is stated in `notes` and on the page (§7). Pharmacist review is needed before non-synthetic use. |
| More `missing_field(dose)` alerts on real lists (alert burden from R1, T1 conflicts and unread time phrases) | Clean synthetic lists are unchanged (A10, A11). Real-list alert volume must be measured with pharmacist review before non-synthetic use. Labelled System Evaluation. |
| The hyphen mixed number `1-1/2` is read as 1.5, but the writer meant a range | Only a proper fraction after an INT is read as mixed. `INT-INT`, `FRAC-INT`, en dash and `~` are `range`. Needs pharmacist sign-off. |
| A reason label is missing, so the template crashes or the page is blank | A13 checks 7/7 labels in backend and web. |
| Tuning on the test split | 0 new eval cases; frozen artifacts are pinned by hash (A09); metrics must be identical (A10). |

## Run commands

```bash
cd /Users/king_phuripol/AI-Engineer/01_Projects/Senior-Project/Full-Agent-s5
make test                                   # unit/contract tests incl. grammar, probes, fuzz (offline)
cd backend && python -m pytest tests/test_pharma_s5r3.py -q   # this slice only
make pharma-eval                            # results.json must equal 1c1f476 except versions/notes
make dev API_PORT=8105 WEB_PORT=3105        # API http://127.0.0.1:8105, web http://127.0.0.1:3105/pharmacist/reconcile
make e2e-pharma                             # Playwright pharma specs against 3105/8105
```

## Decisions needed (none blocking this slice)

- **Pharmacist:** sign off the §G2 grammar before any non-synthetic use. The items to sign off are:
  - the hyphen mixed number;
  - `วันละ N เม็ด` with N > 1 treated as `ambiguous_quantity`;
  - the QV ≤ 10 bound;
  - T1's conflict rule (`N เม็ดครึ่งชั่วโมง` is ambiguous);
  - R1 treating `mg/tab` and `mcg/dose` as unverifiable.
- **Innovation Lead + Safety Reviewer:** before any external or model extraction provider is enabled, decide whether the pipeline re-checks every provider-`resolved` dose against this grammar and downgrades a disagreement to `unverifiable`. Recommendation: yes.
- **Integration auditor awareness:** the `pharma.extract.v2` reason enum is widened additively, to 7 values. There is no task-name or gateway-contract change.
