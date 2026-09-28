# Slice s5r4 — Pharma Agent v1.4 (dose grammar rev 4, final; bounded adversarial scope)

- Owner (Gantt): ธัญรดา / ภูริณัฐ
- Source of truth: `docs/PROPOSAL.md` (v8) 3.2.4 (rules are primary; dose or frequency differences between sources are flagged for pharmacist review) and 3.6 / Table 3.2 (recall from synthetic error injection, patient-level bootstrap CIs, System Evaluation label).
- **Base.** `slices/s5r3/SPEC.md` revision 3 (commits `5fb09a9`, `e8b7ebb`), as built on this branch up to `6b2a67a`. Everything in `slices/s5/`, `s5r/`, `s5r2/` and `s5r3/SPEC.md` still applies. Where this file differs, this file wins.
- **Revision 4 of this file (after s5r4 checker round 1 on `6b2a67a`: 19 BLOCKER, 5 RESIDUAL, 0 CONFORMANCE FAIL). This is the final planned grammar revision for S5.** It fixes the classes, not the instances:
  1. **§N Thai/Unicode normalisation** runs before tokenising. It is a closed list of 5 steps. Tone marks typed before a vowel, a doubled U+0E40 and a decomposed `ำ` then read the same as the standard spelling. This fixes HT1/3/7/8/9 and DD1–DD5.
  2. **§C1 closed free-text vocabulary.** In the dose part of the entry, every word that no production consumes must be on a closed list. Otherwise the dose is `unparsed_token`. A misspelt `ครึ่ง`/`แบ่ง`/`ทั้ง…`, an unknown word, or a word with homoglyph letters can therefore no longer be silently ignored. This fixes HT2/4/5 and RS1–RS5.
  3. **§P per-unit wording.** Joined, hyphenated and dotted per-unit words (`perday`, `aday`, `a-day`, `mg.kg`, `mg kg`, `TDD`, `daily dose`) give `per_unit_amount`. So does `daily` directly after the dose when a multi-dose frequency is also written, and so does a per-day word in front of the strength. This fixes PD1–PD6.
  4. **No invisible character is removed.** The §N removal list is empty, so rev-3 INVISIBLE handling is unchanged.
  5. **RR-01 scope** is narrowed (§R). The stopping rule now says who writes `RESIDUAL_RISK.md` rows, and when.
  6. **Version bumps:**
     - `MOCK_RULES_VERSION = "s5-mock-rules-2.3.0"`
     - `DOSE_GRAMMAR_VERSION = "s5-dose-grammar-1.3.0"`
     - `PIPELINE_VERSION = "s5-pipeline-2.5.0"`
     - `TEMPLATE_VERSION` (`template-1.3.0`) and `RULES_VERSION` do not change.
     - No reason value is added, so the 7-value enum and its labels are unchanged.
- Status: PLAN rev 4. All data is synthetic. Tier 0 only. No external provider, gateway change or contract change. Servers, if started: API 8105, web 3105. Branch `factory/s5r4`.

## Scope

1. Implement §N, §C1 and §P in `backend/app/pharma/mock_rules.py`. Implement them independently in `backend/tests/pharma_dose_reference.py`, using its own code and no `app.*` import. Add the four fuzz classes in §F4 to `backend/tests/pharma_dose_fuzz.py`.
2. Add the rev-4 tests (see "Required test cases").
3. Freeze the rev-3 parser for the teeth test: `backend/tests/legacy/mock_rules_6b2a67a.py`, byte-identical to `git show 6b2a67a:backend/app/pharma/mock_rules.py`, with its sha256 pinned in the test.
4. Update `slices/s5r4/RESIDUAL_RISK.md`. The planner has already done this in this revision's commit (§R). The builder does not edit it.

### §N — Normalisation (closed; before tokenising; used for the dose, D1, R1, C1 and the frequency mapping)

Apply these steps in this order, exactly as written:

| Step | Rule |
|---|---|
| N1 | Unicode NFC (unchanged; not NFKC). |
| N2 | U+0E4D, optionally followed by one tone mark (U+0E48–U+0E4B), then U+0E32 → that tone mark (if present) + U+0E33. Example: `ค<U+0E48><U+0E4D><U+0E32>` → `ค่ำ`. |
| N3 | One left-to-right, non-overlapping pass of regex `([่-๋])([ัิ-ื])` → `\2\1`, so a tone mark typed before an upper vowel moves after it. Examples: `คร<U+0E48><U+0E36>ง` → `ครึ่ง`, `ท<U+0E49><U+0E31>งวัน` → `ทั้งวัน`. |
| N4 | U+0E40 U+0E40 → U+0E41 (`แ`). |
| N5 | Collapse each whitespace run (`str.isspace()`) to one ASCII space and trim (unchanged). |

Nothing else is rewritten:

- The zero-width/format **removal list is empty**. Every INVISIBLE character stays a never-consumed numeric-ish token, as in rev 3, so I1–I10 are unchanged.
- Homoglyphs, full-width letters, duplicated tone marks and misspellings are **not** corrected. §C1 makes them unverifiable instead.
- The page and audit keep showing the entry as today (`raw_span` = N1 + N5 of the original). N2–N4 change only the text the grammar reads.

### §C1 — Closed free-text vocabulary (new check; ID `C1` joins `DOSE_GRAMMAR`; consumes nothing)

**Where it applies.** The *dose region* starts at the entry's first numeric-ish token (s5r3 §G1) and runs to the end. Text before it is the drug-name region, which C1 does not check (RR-07). Within the dose region, blank out every character of every token consumed by a production (S1–S3, L1, Q1–Q7, T1, F1–F3). What is left is the *free text*. Before checking it:

- casefold the free text;
- compact dotted abbreviations: a whole-word match of `[^\W\d_](\.[^\W\d_])+\.?` loses its dots, so `p.r.n.` → `prn`, `q.d.` → `qd` and `b.i.d.` → `bid`.

C1 **fires** if either of these holds:

- **Thai.** A maximal run of Thai letters or marks (U+0E01–U+0E3A, U+0E40–U+0E4E) cannot be segmented completely by one greedy, longest-first, left-to-right pass over `V_TH_FREE`.
- **Other letters.** A maximal run of other Unicode letters (category `L*`, outside the Thai block) is not in `V_EN_FREE`. This covers Latin, Cyrillic, Greek and full-width letters.

`V_EN_FREE` (one constant; exactly these words):

```
od bd bid tid qid qd qod hs prn po ac pc daily nightly weekly monthly once twice thrice every other day days week
month morning evening night bedtime noon before after with without meal meals food breakfast lunch dinner supper
as needed when required for pain fever oral orally by mouth at in the take sc sl im iv
```

`V_TH_FREE` (one constant; exactly these words):

```
รับประทาน กิน ทาน อาหาร นอน มี อาการ ปวด ไข้ วัน เว้น ให้ ก่อน หลัง พร้อม เช้า กลางวัน เที่ยง เย็น ค่ำ ตอน เวลา
เมื่อ ทุก ทันที ต่อ แบ่ง รวม ทั้งหมด ทั้งวัน
```

Some words are deliberately **not** on these lists: units, quantity words, number words, `ครั้ง`, `ครั้งละ`, `วันละ`, time words, `x`, `a`, `per`, `to`, `or` and `and`. They are acceptable only when a production consumes them.

**Result.** A C1 firing is an `unparsed_token`-level reason. It is the lowest in the s5r3 §2 order, so any higher reason still wins. C1 does not change which tokens count as numeric-ish, and it never creates a `range`.

Coverage was checked by the planner with a prototype. With these lists, 0 of 1372 resolved fixture and eval-log strings and 0 test literals change. 1 of about 1560 resolved fuzz phrases changes: `… 2x 3 times a week`, where `times a` is left unconsumed.

### §P — Per-unit and daily-total wording (extends rev-3 R1(b) and D1; reason `per_unit_amount`)

- **P1, R1(b) key.** After an anchor's TAIL (rev 3), take:
  - `w1`, the next run of Latin letters;
  - `w2`, the run of Latin letters after it, but only if the two are separated by nothing except `space - . _`.

  Set `key = casefold(w1 + w2)`. R1(b) also fires when `key` starts with `per`, `aday`, `aweek`, `amonth`, `kg`, `tdd`, `dailydose` or `dailytotal`. Examples: `perday`, `per-day`, `a-day`, `a.day`, `aday`, `mg kg`, `mg.kg`, `TDD`, `daily dose`. It also fires when Thai text after the TAIL begins with `กก` or `กิโล`, in addition to the rev-3 `ต่อ`.
- **P2, D1 anywhere in the entry.** D1 also fires on:
  - the Latin whole word `tdd`;
  - `daily` followed by `dose`, `doses` or `total`, either joined or separated only by `space - . _`.
- **P3, D1 in the drug-name region.** D1 also fires on a Latin word before the first numeric-ish token that starts with `per`, or that is `daily`, `day`, `aday` or `dose`. Example: `Metformin per day 1000 mg bid`.
- **P4, daily plus a multi-dose frequency.** D1 fires when both of these hold:
  - an anchor's P1 `key` starts with `daily` or `everyday`, or the Thai text after the anchor's TAIL begins with `ทุกวัน`;
  - the entry also contains a multi-dose frequency. That means one of these:
    - a Latin whole word (after dot compaction) in {`bd bid tid qid twice thrice`};
    - an F1 match with an interval of 1–23 hours;
    - an F2 match with a count ≥ 2, or with `twice`/`thrice`, per `day`/`daily`;
    - an F3 `วันละ INT ครั้ง` with INT ≥ 2.

  Example: `1000 mg daily, bid`. A lone `50 mg daily` stays resolved as once daily. Fixtures contain 88 such entries, and 0 of them have a multi-dose frequency.
- Frequency is unchanged by P1–P4, as with rev-3 R1/D1.

## Stopping rule (bounds the adversarial loop; set by the orchestrator)

The checker probes the **declared classes** and runs the fuzz harness:

- the declared classes are F1–F7, P, H, U, V, W, I, SL, DT, D and QF (s5r3), plus N, M, PU and K (below);
- the fuzz harness covers every §F class.

It may also add its own probes. For each finding it writes down the **meaning a pharmacist reads from the displayed text**. It then puts the finding in exactly one class:

| Class | Definition | Outcome |
|---|---|---|
| **CONFORMANCE FAIL** | The implementation disagrees with this spec: a listed probe row, the reference in the fuzz, or a closure property. This applies whatever the alphabet. | FAIL, back to the **builder** |
| **BLOCKER** | The implementation and the reference both `resolve` an entry to a value, unit or quantity different from that meaning (a MISREAD). The entry is fully in PLAUSIBLE. It is **not** in a declared residual class (RR-01, RR-07). | FAIL, back to the **planner**. This is the final planned revision, so the orchestrator takes the finding to the **owner**. The owner decides between a rev 5 and recording it for pharmacist acceptance. No agent may downgrade it. |
| **RESIDUAL** | A MISREAD on an entry with ≥ 1 code point outside PLAUSIBLE, **or** a MISREAD inside a declared residual class | Listed in the checker report, and written into `RESIDUAL_RISK.md` by the **planner** (§R). **Not** a blocker |
| **SAFE** | `unverifiable` (any reason) or `not_stated`, including results the checker would have preferred as `resolved` | Never a failure. The checker may add an alert-burden note |

PLAUSIBLE is the union of these sets and is unchanged:

- ASCII U+0020–U+007E;
- Thai U+0E00–U+0E7F;
- `str.isspace()` characters;
- `½ ¼ ¾ × – — µ ‘ ’ “ ” …`.

## §R — `RESIDUAL_RISK.md`

The columns are: `id` | class | example input (`<U+XXXX>` for code points) | observed output (status, value, quantity) | why it is residual | found by | status. Every row has the status `pending pharmacist acceptance`. No agent may mark a row accepted. Only a pharmacist or the owner can, and the decision is recorded in `docs/DECISIONS.md`.

- **RR-01 (scope resolved).** RR-01 covers **only** an entry that meets all three conditions:
  - it states a bare `NUM UNIT` with no per-unit or daily marker at all: no D1 word or P2–P4 trigger, no R1 trigger including the P1 keys, and no SLASH-LIKE character;
  - C1 does not fire;
  - the writer meant a daily total.

  Example: `เมทฟอร์มิน 1000 มก. วันละ 2 ครั้ง`. The checker's B-PER wordings (`perday`, `TDD`, `daily dose`, `mg kg`, `mg.kg`, `a-day`) are **not** RR-01. §P covers them, and a plausibly typed misread that contains a per-unit or daily word is a BLOCKER.
- **RR-02 to RR-06.** These are the checker round-1 RESIDUAL findings RS1–RS5 (Cyrillic, full-width and Cyrillic letters in `a day`, `per` and `divided`). The planner recorded them in this revision. Rev 4 expects `unparsed_token` (C1) for each, and the rev-4 checker confirms this.
- **RR-07 (declared, rev 4).** Words in the drug-name region, before the first number, are not read, apart from the D1 words and P3. A dose modifier written there is not seen. Example: `Metformin double 500 mg bid` resolves as 500 mg.
- **Who writes rows, and when.** The checker may not write under `slices/`. It lists every RESIDUAL finding in its report in §R row format, with the non-PLAUSIBLE code points. After that checker round, and before merge, the **planner** appends those rows to `RESIDUAL_RISK.md` in a docs-only commit. That commit needs no rebuild. The reviewer checks that the rows match the checker report 1:1. A22 is measured on that commit.

## Out of scope

- Everything s5r3 declares out of scope. This slice does not read unmarked daily totals, add reason values or eval cases, change the manifest, gateway or contract, or use an external provider.
- Spelling correction beyond N2–N4, removing any invisible character, and widening `V_EN_FREE`/`V_TH_FREE` beyond the lists above. Widening a list is a planner change that needs pharmacist sign-off.
- Reading the drug-name region (RR-07) or a daily total written without a marker (RR-01).
- Accepting any residual risk. That needs a human decision.

## Acceptance

Thresholds apply to the frozen `test` split **and** to all patients. Report both.

| ID | Criterion | Threshold | How measured |
|---|---|---|---|
| S5R4-A01 | All prior items still pass | S5-A01..A18, S5R-A01..A11, S5R2-A01..A18 and S5R3-A01..A23 pass. The only amendments allowed are: the rev-4 versions (A16); `C1` in the grammar ID set (A03); and s5r3/s5r4 test expectations for inputs that fall under a §N/§C1/§P rule, each listed in the builder report as a changed expectation mapped to its rule. Any other changed expectation is a STOP | `make test`, `make pharma-eval`, `make e2e-pharma`; per-ID checklist in the builder report |
| S5R4-A02 | `make test` green | Exit 0; 0 failed, 0 errors, 0 skip/xfail in pharma tests; offline; fuzz test ≤ 20 s; each code-point sweep ≤ 5 s | `make test` from a clean clone of `factory/s5r4` |
| S5R4-A03 | Grammar closed | `DOSE_GRAMMAR` IDs are exactly {S1,S2,S3,L1,R1,D1,C1,Q1..Q7,T1,F1,F2,F3}. Each of these is one constant: QF, NEUTRAL, the INVISIBLE list, the D1 lexicon, `V_EN_FREE`, `V_TH_FREE`, the P1 key prefixes, the P4 multi-dose words and the §N step table. 0 deleted piecewise regex names. Every `resolved` trace has 0 unconsumed numeric-ish tokens and 0 C1 firings | pytest `test_grammar_table_closed`, `test_no_piecewise_dose_regex`, `test_resolved_consumes_all_numeric_tokens` |
| S5R4-A04 | Rev-3 probe tables unchanged | F1–F7/P 15/15, H 13/13, U 12/12, V 6/6, W 5/5, I 10/10, SL 11/11, DT 15/15, D 12/12, QF 12/12: exact status, reason, dose, quantity and listed Freq | existing `test_probe_*` suites |
| S5R4-A05 | N-probes (normalisation) | 13/13 exact (table below) | pytest `test_probe_normalise[N1..N13]` |
| S5R4-A06 | M-probes (C1: misspelt, unknown or homoglyph words) | 11/11 exact; 0 resolved | pytest `test_probe_free_text[M1..M11]` |
| S5R4-A07 | PU-probes (per-unit wording) | 11/11 exact status, reason and listed Freq | pytest `test_probe_per_unit_words[PU1..PU11]` |
| S5R4-A08 | K-probes (controls stay resolved) | 8/8 exact value, unit, quantity and listed Freq | pytest `test_probe_controls[K1..K8]` |
| S5R4-A09 | Normalisation is closed and neutral on existing data | §N output equals N1+N5 on 100% of fixture entries, eval-log strings and pre-rev-4 test inputs. N2–N4 are idempotent (applying §N twice = once) on every fuzz phrase | pytest `test_normalise_identity_on_existing`, `test_normalise_idempotent` |
| S5R4-A10 | Unverifiable is visible | In a two-source snapshot, each of I1, SL1, DT1, D1, QF1, M1, M6, PU1 and N6 gives exactly 1 `missing_field(dose)` (`field_status=unverifiable`, reason) and 0 `dose_mismatch`, and `unchecked_by_reason.unverifiable` rises by 1 per pair | pytest `test_negative_raises_missing_dose[...]` |
| S5R4-A11 | Fuzz: 0 misreads | ≥ 2000 phrases (seed 5303). Every production and every class, including rev-3 `invisible`, `slash_like`, `dotted_tail`, `daily_total` and `q4b_follower` and rev-4 `th_normalise`, `th_misspelt`, `unknown_word` and `per_unit_word`, has ≥ 20 phrases. Resolved ≥ 25%, unverifiable ≥ 25%, EN and TH quantity segments ≥ 30% each. **0** safety violations; 100% status and reason agreement with the reference; reference check 100%; 0 resolved quantity > 10 | pytest `test_dose_fuzz_vs_reference` |
| S5R4-A12 | Closure properties | Over every generated phrase: 0 `resolved` when the phrase contains (a) an INVISIBLE character, (b) an unconsumed SLASH-LIKE character, (c) a D1/P marker, or (d) a C1 firing per the reference. (e) For every `th_normalise` phrase, the output equals the output of its canonical spelling | assertions in `test_dose_fuzz_vs_reference` |
| S5R4-A13 | Tests have teeth | The harness finds ≥ 1 safety misread in each rev-3 class on the frozen `e6a354f` parser, and in each rev-4 class (`th_normalise`, `th_misspelt`, `unknown_word`, `per_unit_word`) on the frozen `6b2a67a` parser. The piecewise stub is caught in each of the 10 s5r3 §F.4 classes | pytest `test_fuzz_catches_e6a354f`, `test_fuzz_catches_6b2a67a` (both legacy copies sha256-pinned), `test_fuzz_catches_piecewise_stub` |
| S5R4-A14 | Reference independent | `pharma_dose_reference.py` imports no `app.*` module (AST scan). It shares no regex literal with `mock_rules.py`. It computes INVISIBLE, SLASH-LIKE, §N and C1 with its own code. Its vocabulary sets equal the implementation's and the lists in this spec | pytest `test_reference_independent`, `test_vocab_sets_match_spec` |
| S5R4-A15 | Frequency unchanged | 100% of fixture entries and existing test inputs match the pinned `1c1f476` frequency table (only the s5r3 §4 Q5-fraction exception). Every rev-3 and rev-4 probe with a Freq column equals that Freq | pytest `test_frequency_unchanged`, `test_t1_r1_frequency_neutral` (extended to N, PU and K) |
| S5R4-A16 | Versions | The exact strings `s5-mock-rules-2.3.0`, `s5-dose-grammar-1.3.0` and `s5-pipeline-2.5.0` appear in the code, in every run record and in `results.json.versions`. `template-1.3.0` and `RULES_VERSION` are unchanged | pytest `test_versions_bumped` (amended) |
| S5R4-A17 | Frozen data untouched | sha256 of `fixtures/patients.json`, `fixtures/test_manifest.json` (v3), `injection_log.jsonl` and `injection_log_surface.jsonl` equals `1c1f476`. The generators are byte-identical. 0 new eval cases | pytest `test_frozen_artifacts_unchanged`; `git diff 1c1f476 --stat` in the builder report |
| S5R4-A18 | Evaluation holds | Every `results.json` field except `versions` and `notes` equals `1c1f476`. That covers: recall ≥ 0.95 per each of 9 types and each surface form (test and all); clean false alerts ≤ 0.10; extra issues/case ≤ 0.10; extraction accuracy ≥ 0.98; label = System Evaluation | `make pharma-eval`; pytest `test_eval_thresholds`, `test_results_unchanged_except_versions` |
| S5R4-A19 | Clean fixtures use only grammar forms | 96/96 clean entries are `resolved` with the gold quantity. 0 of them hit R1, D1, P1–P4, a QF failure, C1, INVISIBLE or an unconsumed SLASH-LIKE character. 100% of surface-suite `after` strings give their logged status and reason | pytest `test_clean_fixtures_grammar_only`, `test_surface_after_strings_expected` |
| S5R4-A20 | Labels, wording, UI | 7/7 reason labels in `phrasing.py` and `web/lib/pharma.ts`. `notes[0]` and the page scope say "could not be verified", not "may be misread". 0 serious or critical axe violations; 0 colour literals; 0 `diagnos\|prescrib\|treat` in UI copy | pytest `test_reason_labels_complete`, `test_results_notes_grammar`; Vitest `pharma-page.test.tsx`; `make e2e-pharma`; s0 `test_repo_hygiene` |
| S5R4-A21 | Stopping rule applied | The checker report classifies every finding with the table above. It records the meaning and the non-PLAUSIBLE code points for each finding. PASS requires **0 CONFORMANCE FAIL and 0 BLOCKER**. SAFE and RESIDUAL never fail the slice. HT1–HT9, DD1–DD5 and PD1–PD6 from round 1 are re-run and are 0 BLOCKER | checker report plus a classification script (like `tests/e2e/s5r4_classify_findings.py`) |
| S5R4-A22 | Residual risk recorded | `RESIDUAL_RISK.md` is in §R format and holds RR-01 (narrowed scope), RR-02..RR-06 (RS1–RS5), RR-07, and 1 row per rev-4 checker RESIDUAL finding, appended by the planner after the checker round (§R). If there is none, it says "none found (rev-4 round)". Every row is `pending pharmacist acceptance`; 0 rows are marked accepted | reviewer compares the file with the checker report 1:1; `grep -c "pending pharmacist acceptance"` equals the number of rows |

### Rev-4 probe tables

`<U+XXXX>` is one inserted code point. A dash in the Freq column means frequency is not asserted. N-probes must also equal the output of the standard spelling.

| Probe | Input | Expected | Freq |
|---|---|---|---|
| N1 | `วาร์ฟาริน 3 มก. 1 เม็ดคร<U+0E48><U+0E36>ง วันละ 1 ครั้ง` (HT1) | 3 mg, qty 1.5, resolved | q24h |
| N2 | `วาร์ฟาริน 3 มก. 1 เม็ด คร<U+0E48><U+0E36>ง วันละ 1 ครั้ง` (HT3) | 3 mg, qty 1.5, resolved | q24h |
| N3 | `วาร์ฟาริน 3 มก. ครั้งละ 1 เม็ดคร<U+0E48><U+0E36>ง` (HT7) | 3 mg, qty 1.5, resolved | – |
| N4 | `วาร์ฟาริน 3 มก. 2 เม็ดคร<U+0E48><U+0E36>ง ก่อนนอน` (HT8) | 3 mg, qty 2.5, resolved | – |
| N5 | `โอเมพราโซล 20 มก. 1 แคปซูลคร<U+0E48><U+0E36>ง ก่อนนอน` (HT9) | 20 mg, qty 1.5, resolved | – |
| N6 | `เมทฟอร์มิน 1000 มก. <U+0E40><U+0E40>บ่งวันละ 2 ครั้ง` (DD1) | `per_unit_amount` | q12h |
| N7 | `เมทฟอร์มิน 1000 มก. <U+0E40><U+0E40>บ่ง วันละ 2 ครั้ง` (DD2) | `per_unit_amount` | q12h |
| N8 | `เมทฟอร์มิน 1000 มก. <U+0E40><U+0E40>บ่งทาน เช้า-เย็น` (DD3) | `per_unit_amount` | – |
| N9 | `เมทฟอร์มิน 1000 มก. ท<U+0E49><U+0E31>งวัน` (DD4) | `per_unit_amount` | – |
| N10 | `เมทฟอร์มิน 1000 มก. ท<U+0E49><U+0E31>งหมด วันละ 2 ครั้ง` (DD5) | `per_unit_amount` | q12h |
| N11 | `วาร์ฟาริน 3 มก. 1 เม็ดครึ่ง ค<U+0E48><U+0E4D><U+0E32>` | 3 mg, qty 1.5, resolved (N2 → `ค่ำ`, a QF item) | – |
| N12 | `วาร์ฟาริน 3 มก. 1 <U+0E40><U+0E40>คปซูล วันละ 1 ครั้ง` | 3 mg, qty 1, resolved | q24h |
| N13 | `วาร์ฟาริน 3 มก. 1 เม็ดคร<U+0E48><U+0E48><U+0E36>ง` (doubled tone mark) | `unparsed_token` (not corrected; C1) | – |
| M1 | `วาร์ฟาริน 3 มก. 1 เม็ดครื่ง วันละ 1 ครั้ง` (HT2) | `unparsed_token` | – |
| M2 | `วาร์ฟาริน 3 มก. 1 เม็ดครึง วันละ 1 ครั้ง` (HT4) | `unparsed_token` | – |
| M3 | `วาร์ฟาริน 3 มก. 1 เม็ดคึ่ง วันละ 1 ครั้ง` (HT5) | `unparsed_token` | – |
| M4 | `เมทฟอร์มิน 1000 มก. แบงวันละ 2 ครั้ง` (tone mark missing) | `unparsed_token` | – |
| M5 | `Warfarin 3 mg 1 tab and a hlaf od` | `unparsed_token` | – |
| M6 | `Metformin 1000 mg <U+0430> day` (RS1) | `unparsed_token` | – |
| M7 | `Metformin 1000 mg <U+0440>er day` (RS2) | `unparsed_token` | – |
| M8 | `Metformin 1000 mg <U+FF50><U+FF45><U+FF52> day` (RS3) | `unparsed_token` | – |
| M9 | `Metformin 1000 mg <U+0434>ivided bid` (RS4) | `unparsed_token` | – |
| M10 | `Metformin 1000 mg d<U+0456>vided bid` (RS5) | `unparsed_token` | – |
| M11 | `Warfarin 3 mg 1 tab od (Coumadin)` | `unparsed_token` (a name after the dose is not read; alert-burden example) | q24h |
| PU1 | `Metformin 1000 mg perday` (PD1) | `per_unit_amount` | – |
| PU2 | `Metformin 1000 mg TDD bid` (PD2) | `per_unit_amount` | q12h |
| PU3 | `Metformin 1000 mg daily dose, bid` (PD3) | `per_unit_amount` | – |
| PU4 | `Warfarin 5 mg kg q24h` (PD4) | `per_unit_amount` | q24h |
| PU5 | `Warfarin 5 mg.kg q24h` (PD5) | `per_unit_amount` | q24h |
| PU6 | `Metformin 1000 mg a-day` (PD6) | `per_unit_amount` | – |
| PU7 | `Metformin 1000 mg daily, bid` | `per_unit_amount` (P4) | – |
| PU8 | `Metformin 1000 mg every day bid` | `per_unit_amount` (P4) | – |
| PU9 | `เมทฟอร์มิน 1000 มก. ทุกวัน วันละ 2 ครั้ง` | `per_unit_amount` (P4) | q12h |
| PU10 | `Metformin per day 1000 mg bid` | `per_unit_amount` (P3) | q12h |
| PU11 | `Metformin TDD 1000 mg bid` | `per_unit_amount` (P2) | q12h |
| K1 | `Atenolol 50 mg daily` | 50 mg, resolved | q24h |
| K2 | `Metformin 500 mg daily pc` | 500 mg, resolved | q24h |
| K3 | `Paracetamol 500 mg PO as needed` | 500 mg, resolved | – |
| K4 | `Metformin 500 mg q.d.` | 500 mg, resolved | q24h |
| K5 | `Metformin 500 mg every other day` | 500 mg, resolved | – |
| K6 | `เมทฟอร์มิน 500 มก. 1 เม็ด รับประทานหลังอาหาร` | 500 mg, qty 1, resolved | – |
| K7 | `ซาร่า 500 มก. 2 แคปซูล เวลาปวด` | 500 mg, qty 2, resolved | – |
| K8 | `Metformin 500 mg once a day` (DT15) | 500 mg, resolved | q24h |

## Required test cases

- `backend/tests/test_pharma_s5r4.py` (extended):
  - `test_probe_normalise`, `test_probe_free_text`, `test_probe_per_unit_words` and `test_probe_controls`, with rows exactly as above;
  - `test_normalise_identity_on_existing` and `test_normalise_idempotent`;
  - `test_vocab_sets_match_spec`;
  - `test_negative_raises_missing_dose` for the A10 list;
  - `test_fuzz_catches_6b2a67a`, plus the existing `test_fuzz_catches_e6a354f`;
  - the amended `test_grammar_table_closed` and `test_versions_bumped`;
  - `test_t1_r1_frequency_neutral`, extended to N, PU and K.
- Write every non-ASCII code point in test sources as a `\uXXXX` escape when it is invisible, a homoglyph, a full-width character or a mis-ordered Thai mark. Do not write it literally.
- Fuzz generator: four rev-4 classes, each with ≥ 20 phrases.
  - `th_normalise`: N2–N4 variants of `ครึ่ง`, `ทั้ง`, `ครั้ง`, `แบ่ง`, `แคปซูล` and `ค่ำ` in quantity, QF and D1 positions. Each is paired with its canonical spelling.
  - `th_misspelt`: tone mark dropped, vowel swapped or consonant dropped in `ครึ่ง`, `แบ่ง`, `ทั้งหมด` and `ทั้งวัน`, after QW and after the strength.
  - `unknown_word`: non-vocabulary Latin and Thai words, and vocabulary words with ≥ 1 Cyrillic, Greek or full-width letter, in the dose region.
  - `per_unit_word`: every P1 key form (joined, spaced, `-`, `.`, `_`), P2 to P4 triggers, and the K1/K2/K8-style controls that must resolve.
- Every s5/s5r/s5r2/s5r3/s5r4 test stays in place. Only the A01 amendments are allowed.

## Clinical risks

| Risk | Mitigation |
|---|---|
| A Thai spelling that renders identically (tone mark before the vowel, doubled U+0E40) hides `ครึ่ง` or a D1 marker, so half a tablet is dropped (warfarin 1 vs 1.5 tablets) or a divided total is read per dose (2× overdose) | The closed normalisation §N is tested for identity on all existing data (A05, A09, A12e). |
| A misspelt or unknown word next to the dose is silently ignored | The closed free-text vocabulary C1 makes the dose `unparsed_token`, visible as "could not be verified" (A06, A12d). |
| Per-unit or daily wording outside the rev-3 lists (`perday`, `TDD`, `mg kg`, `daily … bid`) is read as a per-dose amount | §P gives `per_unit_amount` (A07). A lone `X mg daily` stays resolved as once daily (K1). |
| More `missing_field(dose)` alerts on real lists (alert burden): any word outside the vocabulary, such as a brand name after the dose (M11), is unverifiable | This is fail-safe by design. 0 clean fixtures change (A18, A19). Real-list alert volume and the vocabulary must be reviewed with a pharmacist before non-synthetic use. |
| An unmarked daily total (RR-01) or a modifier in the name region (RR-07) is read wrongly | Declared, not accepted. Both block non-synthetic use until a pharmacist or the owner accepts them (§R). |
| The adversarial loop does not converge before the presentation | This is the final planned revision. Classes are closed (§N, C1, §P). Only a plausibly typed misread outside RR-01/RR-07 blocks, and the owner decides on it. |
| Tuning on the test split | 0 new eval cases; hashes are pinned; metrics are identical (A17, A18). The vocabulary lists are standard sig vocabulary. Their coverage of the frozen fixtures is a no-change check, not a fit. |

## Run commands

```bash
cd /Users/king_phuripol/AI-Engineer/01_Projects/Senior-Project/Full-Agent-s5
make test                                                  # all tests incl. probes, sweeps, fuzz (offline)
cd backend && python -m pytest tests/test_pharma_s5r4.py tests/test_pharma_s5r3.py -q   # grammar focus
make pharma-eval                                           # results.json == 1c1f476 except versions/notes
make dev API_PORT=8105 WEB_PORT=3105                       # http://127.0.0.1:3105/pharmacist/reconcile
make e2e-pharma
git show 6b2a67a:backend/app/pharma/mock_rules.py | shasum -a 256   # must equal the pinned rev-3 legacy-copy hash
.venv/bin/python tests/e2e/s5r4_classify_findings.py      # checker's round-1 findings, re-run on rev 4
```

## Decisions needed (none block this synthetic slice)

- **Pharmacist and owner:** accept or reject each `RESIDUAL_RISK.md` row (RR-01 to RR-07, plus any rev-4 rows) and record the decision in `docs/DECISIONS.md`. Until then, every row blocks non-synthetic use.
- **Pharmacist:** sign off on §N, `V_EN_FREE`, `V_TH_FREE`, the §P keys and the P4 multi-dose rule, together with the rev-3 items (QF, NEUTRAL, D1 lexicon, PLAUSIBLE).
- **Owner:** decide on any rev-4 BLOCKER: a rev 5, or recording it for pharmacist acceptance.
