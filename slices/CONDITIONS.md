# Open reviewer conditions (carried forward)

Every slice below passed its loop with CONDITIONAL_PASS. These conditions must close at the stated gate, or be waived by a dated entry in `docs/DECISIONS.md`. Full text is in each slice's review output.

## Must close in the Case Graph wiring slice (before any UI/demo shows red-flag screening as performed)
| ID | From | Sev | Condition | Status (slice i2, branch `factory/i2`) |
|---|---|---|---|---|
| C1 | S2r | HIGH | Stale vitals give an all-clear: add clinician-approved freshness windows; stale reading → `not_evaluated`; checkpoint shows reading times. | CLOSED (windows PROPOSED, clinical sign-off is D-I2-1). `casegraph/tests/test_i2_freshness.py`: `test_vital_freshness_boundary[*]` (9 vitals), `test_freshness_config_cited`, `test_checkpoint_shows_reading_times`. Commit 3f3874f. |
| C2 | S2r | HIGH | `performed=true` overclaims: screening block must carry `rule_set_version`, PLACEHOLDER label and scope ("vitals thresholds only"); never render as "no red flags". Wire S4 rules (rf-1.1.0) in place of placeholders. | CLOSED. Web: `web/tests/TriageReview.screening.test.tsx` (4 states: evaluated 0 alerts renders "0 of 16 declared rules fired", evaluated with alerts, partial INCOMPLETE, unavailable NOT PERFORMED; text banners with role=alert; no overclaim match). Backend: `casegraph/tests/test_i2_wiring.py`: `test_red_flag_node_rf110`, `test_placeholder_rules_unreachable`, `test_never_no_red_flags`, `test_red_flag_parity_s4_fixtures[*]`; commit 1aecd0a. API: `backend/tests/triage/test_i2_checkpoint.py::test_never_no_red_flags_api` (40 fixtures), `test_checkpoint_via_triage_endpoints[*]` (the assess response carries the rf-1.1.0 screening block). |
| C3 | S4 | HIGH | `as_of` unbounded (`backend/app/triage/router.py`): reject `as_of` beyond latest `available_at_time` + skew; add a floor. | CLOSED (skew 5 min default, D-I2-2). `backend/tests/triage/test_i2_as_of.py`: `test_as_of_ceiling`, `test_as_of_floor`, `test_as_of_rejection_audited[*]`, `test_as_of_skew_is_configurable`. Commit 3f3874f. |
| C4 | S4 | MEDIUM | Snapshot keeps only the latest fact per kind: same-timestamp conflicts resolve to the worst value or are flagged; latest-wins vs worst-in-window needs a clinical decision. | CLOSED for same-timestamp conflicts; latest-wins vs worst-in-window is reported only (D-I2-3). `backend/tests/triage/test_i2_conflicts.py`: `test_same_timestamp_worst[min\|ordinal\|bidirectional\|flag]`, `test_conflict_order_invariant`; `casegraph/tests/test_i2_freshness.py::test_same_timestamp_conflict_shown_at_checkpoint`. Commit 3f3874f. |
| C5 | S2r | MEDIUM | Alerts invariant must equal the declared rule set; `import_graph` must re-validate Alerts and verify `output_sha256`. | CLOSED. `casegraph/tests/test_i2_wiring.py`: `test_alerts_equals_declared_rules` (missing/extra/duplicate 3/3), `test_import_revalidates` (tampered output/hash/Alerts 3/3). Commit 1aecd0a. |
| C6 | int | MEDIUM | Two mock task registries (S3 `register_task`, S4 `mock_tasks`) → one registry. `casegraph.evidence` (S1) and `casegraph.data` (S2) → one type system. | CLOSED. `backend/tests/test_mock_registry.py`: `test_single_mock_registry`, `test_mock_label_every_task`; `casegraph/tests/test_evidence_types.py::test_one_evidence_type_system`; `casegraph/tests/test_i2_wiring.py::test_s1r_snapshot_loads_lossless` (400 snapshots); `backend/tests/voice/test_provenance.py::test_s3_finish_evidence_loads`. Commit 1aecd0a. |

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
