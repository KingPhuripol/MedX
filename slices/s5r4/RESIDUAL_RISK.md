# s5r4 residual risk (dose grammar rev 5, `s5-dose-grammar-1.4.0`)

Synthetic data only. No agent can accept a row. Only a pharmacist or the owner can accept one, and the acceptance must be recorded in `docs/DECISIONS.md`. Until a row is accepted, it blocks any non-synthetic use.

**Who writes rows.** The planner writes every row. The checker may not write under `slices/`. It lists each RESIDUAL finding in its report in this row format. After each checker round, and before merge, the planner appends those rows here in a docs-only commit. See the §R section of `SPEC.md`.

| id | class | example input | observed output (status, value, quantity) | why it is residual | found by | status |
|---|---|---|---|---|---|---|
| RR-01 | unmarked daily total (declared; scope narrowed in rev 4) | `เมทฟอร์มิน 1000 มก. วันละ 2 ครั้ง`, meant as 1000 mg per day | `resolved`, 1000 mg, quantity null (frequency q12h) | The entry is a bare `NUM UNIT` with no marker of any kind: no D1 word or P2–P4 trigger, no R1 trigger including the P1 keys, and no SLASH-LIKE character. C1 does not fire. Rev 5: this also covers a time-of-day schedule with no DAILY statement, for example `1000 มก. เช้า-เย็น`. The text cannot tell a daily total from a per-dose order. RR-01 does **not** cover per-unit or daily wordings such as `perday`, `TDD`, `daily dose`, `mg kg`, `mg.kg` or `a-day`. §P covers those. | planner | pending pharmacist acceptance |
| RR-02 | homoglyph letter in a per-unit word (checker round 1, RS1) | `Metformin 1000 mg <U+0430> day` (Cyrillic a) | at `6b2a67a`: `resolved`, 1000 mg, null. Rev 4 expects `unverifiable` / `unparsed_token` (C1; probe M6) | Not plausibly typed: U+0430 | checker | pending pharmacist acceptance |
| RR-03 | homoglyph letter in a per-unit word (RS2) | `Metformin 1000 mg <U+0440>er day` (Cyrillic er) | at `6b2a67a`: `resolved`, 1000 mg, null. Rev 4 expects `unparsed_token` (M7) | Not plausibly typed: U+0440 | checker | pending pharmacist acceptance |
| RR-04 | full-width letters in a per-unit word (RS3) | `Metformin 1000 mg <U+FF50><U+FF45><U+FF52> day` | at `6b2a67a`: `resolved`, 1000 mg, null. Rev 4 expects `unparsed_token` (M8) | Not plausibly typed: U+FF50, U+FF45, U+FF52 | checker | pending pharmacist acceptance |
| RR-05 | homoglyph letter in a D1 word (RS4) | `Metformin 1000 mg <U+0434>ivided bid` (Cyrillic de) | at `6b2a67a`: `resolved`, 1000 mg, null. Rev 4 expects `unparsed_token` (M9) | Not plausibly typed: U+0434 | checker | pending pharmacist acceptance |
| RR-06 | homoglyph letter in a D1 word (RS5) | `Metformin 1000 mg d<U+0456>vided bid` (Cyrillic i) | at `6b2a67a`: `resolved`, 1000 mg, null. Rev 4 expects `unparsed_token` (M10) | Not plausibly typed: U+0456 | checker | pending pharmacist acceptance |
| RR-07 | dose modifier in the drug-name region (declared, rev 4) | `Metformin double 500 mg bid` | `resolved`, 500 mg, null (frequency q12h) | Text before the first number is treated as the drug name. Only the D1 words and the P3 per-day words are read there. Any other modifier is not seen. | planner | pending pharmacist acceptance |

## Checker RESIDUAL findings, rev-4 round (`d2ff98c`)

none found (rev-4 round). The checker report (`tests/e2e/s5r4_r2_classify_findings.py`) lists these findings:

- 4 BLOCKER classes, B1–B4. Spec rev 5 fixes them.
- 0 RESIDUAL.
- 0 CONFORMANCE FAIL.
- 2 SAFE alert-burden notes:
  - AB1 `Perindopril 4 mg od`. P3 is narrowed in rev 5, so this now resolves.
  - AB2 `Warfarin 3 mg 1 tab od (Coumadin)`, probe M11. This is on the pharmacist review list.

## Checker RESIDUAL findings, rev-5 round

Pending the rev-5 checker round. The planner appends one row per finding here, or writes "none found (rev-5 round)".
