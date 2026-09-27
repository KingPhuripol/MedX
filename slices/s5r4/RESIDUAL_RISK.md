# s5r4 residual risk (dose grammar rev 3, `s5-dose-grammar-1.2.0`)

Synthetic data only. No agent can accept a row. Only a pharmacist or the owner can accept one, and the acceptance must be recorded in `docs/DECISIONS.md`. Until a row is accepted, it blocks any non-synthetic use.

| id | class | example input | observed output (status, value, quantity) | why it is residual | found by | status |
|---|---|---|---|---|---|---|
| RR-01 | unmarked daily total (declared) | `เมทฟอร์มิน 1000 มก. วันละ 2 ครั้ง`, meant as 1000 mg per day | `resolved`, 1000 mg, quantity null (frequency q12h) | The entry is plausibly typed, but no rule covers it. With no D1 marker, the text cannot tell a daily total from a per-dose order, so it is read as 1000 mg per dose. See s5r3 D11, Out of scope and Decisions. | planner | pending pharmacist acceptance |

## Checker RESIDUAL findings

None were recorded at the builder commit. The checker round of this slice adds one row per RESIDUAL finding, listing its non-PLAUSIBLE code points. If there are none, the checker states "none found" here.
