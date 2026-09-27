# Open reviewer conditions (carried forward)

Every slice below passed its loop with CONDITIONAL_PASS. These conditions must close at the stated gate, or be waived by a dated entry in `docs/DECISIONS.md`. Full text is in each slice's review output.

## Must close in the Case Graph wiring slice (before any UI/demo shows red-flag screening as performed)
| From | Sev | Condition |
|---|---|---|
| S2r | HIGH | Stale vitals give an all-clear: add clinician-approved freshness windows; stale reading → `not_evaluated`; checkpoint shows reading times. |
| S2r | HIGH | `performed=true` overclaims: screening block must carry `rule_set_version`, PLACEHOLDER label and scope ("vitals thresholds only"); never render as "no red flags". Wire S4 rules (rf-1.1.0) in place of placeholders. |
| S4 | HIGH | `as_of` unbounded (`backend/app/triage/router.py`): reject `as_of` beyond latest `available_at_time` + skew; add a floor. |
| S4 | MEDIUM | Snapshot keeps only the latest fact per kind: same-timestamp conflicts resolve to the worst value or are flagged; latest-wins vs worst-in-window needs a clinical decision. |
| S2r | MEDIUM | Alerts invariant must equal the declared rule set; `import_graph` must re-validate Alerts and verify `output_sha256`. |
| int | MEDIUM | Two mock task registries (S3 `register_task`, S4 `mock_tasks`) → one registry. `casegraph.evidence` (S1) and `casegraph.data` (S2) → one type system. |

## Must close before any reported number (E1 / progress report)
| From | Sev | Condition |
|---|---|---|
| S4, S5r | HIGH | Degenerate bootstrap CIs ([1,1], [0,0]) → report exact Clopper-Pearson/Wilson intervals. |
| all | — | Label every result "System Evaluation on synthetic data — not clinical performance"; rules, fixtures and gold share authors (circular). |

## Must close before real data (MIMIC / hospital)
| From | Sev | Condition |
|---|---|---|
| S8r | MEDIUM | Real-data guard accepts a ledger in any git repo; a normally committed truncation defeats anti-resubmission; exit-3 errors print patient ids. |
| S9r | MEDIUM | Approval block inside an HTML comment can count; duplicate JSON keys resolve last-wins. |
| S9 | — | Human approver list for `approved_by`; GPU allocation (Tier 4) approval. |

## Standing (human)
- D1: licensed clinical review of red-flag rules/thresholds, department list, Thai dialogue templates, cross-reactivity table, `missing_field` severity.
- SCBXBeta2 font licence before any public push/deploy.
- UMLS licence / THIS (TMT) terms.
