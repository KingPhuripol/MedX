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

## ctrate-loader (CONDITIONAL_PASS ×2, 2026-10-03) — must close before the first real CT-RATE download/build
| From | Sev | Condition |
|---|---|---|
| ctrate-loader | MEDIUM | CLOSED (slice ctrate-r1): a missing `no_chest_{split}.txt` is a `missing_file` load error; empty = zero exclusions. Tests: `test_ctrate_loader.py::test_missing_no_chest_file_fails_loudly`, `::test_empty_no_chest_file_means_zero_exclusions`. Original: missing `no_chest_{split}.txt` treated as "no exclusions". |
| ctrate-loader | MEDIUM | CLOSED (ctrate-r1): `report_provenance` returns `same_patient` for another scan of the label source's patient (counted `blocked_same_patient`, Collator raises). Tests: `test_ctrate_guard.py::test_same_patient_other_scan_blocked_and_counted`, `::test_same_patient_valid_pair_blocked`, `::test_same_patient_digit_variants_blocked`, `::test_train_k_vs_valid_k_allowed`, `::test_collator_raises_on_same_patient_report`. |
| ctrate-loader | MEDIUM | CLOSED (ctrate-r1): `audit --raw` re-reads the raw CSVs with stdlib `csv` and compares cell by cell; without `--raw`, or with an empty one, the status is `NOT_RUN` (exit ≠ 0); a raw label row whose patient is missing from splits.json (not excluded by raw no_chest) is an error. Tests: `test_ctrate_audit.py::test_empty_raw_is_not_given_never_pass`, `::test_patient_silently_dropped_by_the_pipeline_fails_raw_audit`, `::test_planted_pipeline_bug_blank_to_zero_fails`, `::test_planted_pipeline_bug_zero_to_missing_fails`, `::test_missing_audit_does_not_use_loader`, `::test_audit_without_raw_is_not_pass`. |
| ctrate-loader | LOW | CLOSED (ctrate-r1): `approval_resolves` needs one exact-id heading, the line `- **Decision:** APPROVED: CT-RATE download`, a non-empty `Approved by`, no denial wording and no later revocation. Tests: `test_ctrate_download_gate.py::test_approval_resolves_adversarial` (17 cases), `::test_prepare_execute_refuses`. The gate checks format only: anyone who can edit DECISIONS.md can satisfy it (no authentication of the approver). |
| ctrate-loader | LOW | CLOSED (ctrate-r1): `verify` refuses roots outside `data/raw` or non-existent and never creates directories; `--record` writes `local_sha256.json` once and later runs compare to it, `unpinned_lfs` until then. Tests: `test_ctrate_download_gate.py::test_verify_refuses_outside_raw`, `::test_verify_record_then_detects_same_size_tamper`, `::test_verify_record_never_overwrites`, `::test_verify_record_revision_mismatch_fails`. |
| ctrate-loader | LOW | CLOSED (ctrate-r1): required `label_origin`, `LABEL_METRIC_NAME`, both in the build manifest; `--unseal-test` help states the joint unseal (separation stays deferred to the CT reader eval slice). Tests: `test_ctrate_loader.py::test_label_origin_required`, `test_ctrate_audit.py::test_label_origin_tamper_fails_schema`, `::test_manifest_names_label_metric`, `test_ctrate_split.py::test_unseal_help_documents_joint_unseal`. |
| ctrate-r1 | LOW | Approval gate edge cases still pass: a revocation line above the first `## ` heading is ignored; an approval inside a fenced code block counts; `Approved by` holding only a zero-width char, `TBD` or the `<name or role>` placeholder counts; deny words miss cancel/rescind/draft/await/not yet. Execution is still behind --accept-terms, HF_TOKEN and a data/raw target. | Before any `prepare --execute` |
| ctrate-r1 | LOW | `verify` crashes with a traceback (fails closed, non-zero exit) when `local_sha256.json` is corrupt or not an object; should return a FAIL report "local record unreadable". | Before the first real download |
| ctrate-r1 | LOW | `missing_not_negative` with `--raw` still concatenates the old manifest-count check with the independent raw check (only adds errors); split into two named sub-steps or reword SPEC R3. | Next ctrate change |
| ctrate-loader | — (human) | Download approval (who accepts terms, accessors, multi-TB storage); `train` vs `train_fixed` volumes; CC BY-NC-SA flow-down to released weights; confirm 10% dev / seed 20260926. |

## cg-t123 (CONDITIONAL_PASS ×2, 2026-10-03)
| ID | Sev | Condition | Gate |
|---|---|---|---|
| M1 | MEDIUM | When one assess builds several versions, only the last version's graph_id and alerts reach the assessment, `escalation_required` and its audit row (`casegraph_run.py`, triage `router.py`). An intermediate version's urgent alert must also escalate. | **CLOSED (cg-m1)**: `test_cg_m1_multiversion.py::test_intermediate_alert_escalates[P1..P5]`, `::test_no_alert_any_version_does_not_escalate`, `::test_built_graphs_linked_in_order`, `::test_last_version_failure_records_built_and_escalates[compile,execute]`, `::test_middle_version_failure_stops_and_escalates`. Fail-safe alert extraction: `::test_unreadable_alerts_in_a_built_version_fail_safe`. Follow-ups tracked below as M1-R2..R5. |
| M1-R2 | MEDIUM | The screening banner shows only the latest version; an earlier version in the same assess may have fired. Until the web renders `built_graphs[*].escalation`, no demo may present the latest screening block alone as the case's red-flag status. | ui-dag build (renders per-version escalation) |
| M1-R3 | MEDIUM (human decision) | Graph-only alerts (`graph_alert_rule_ids`) are not part of the review acknowledgement gate (`_review` checks engine alerts only). Reviewers recommend requiring acknowledgement of every graph alert rule id. Needs a licensed clinician decision. | Before CG-F3 |
| M1-R4 | MEDIUM (human decision) | A built version whose screening is NOT PERFORMED/unavailable does not force escalation (existing single-version semantics). Reviewers recommend it should, per the CLAUDE.md "missing → abstain/escalate" invariant. Needs a decision. | Before CG-F3 |
| M1-R5 | MEDIUM | If the last version built in an assess is T2/T3, a nurse review hits `checkpoint_role_mismatch`. Unreachable today (triage has no results/orders). | Before CG-F3 |
| M1-C3 | LOW | `test_single_version_audit_keys_unchanged` compares the audit row with the response, not with a fixed pre-change baseline; add a golden check for one synthetic case. | Next cg change |
| L1 | LOW | An unparseable conversation timestamp sorts as oldest; it should fail closed (open, never superseded). Unreachable today (`AwareDatetime`). | Next cg change |
| L2 | LOW | `ConversationFactUse.used=True` for `use=superseded`; consumers must read `use`, or set used=False for superseded. | Before UI-DAG renders `conversation_fact_use` |
| L3 | LOW | The gate-semantics version is not visible in exports, and there is no golden test that fails if gate behaviour changes without a version bump. | Before cg-t123 output is cited as evidence |
| L5 | LOW | Transcript-derived conversation facts cite `turns` instead of a real item id; refs are truncated to 70 chars; `next_stage` is dead code. | Next cg change |
| L6 | LOW | `tests/e2e/cgt123_inprocess_check.py` is not part of `make test`. | Next checker change |
| L9 | LOW | `AllergyList` record text is still cut at 300 chars (`pharma_s5.py` `_allergy_text`). | Next cg change |
| N2 | LOW | graph-versions maps any `ValueError` (including a code bug) to `stored_graph_integrity`; it is audited, but the error type is broad. | Carry |
| C3 | LOW | The s2 provider config skips VoiceIntakeFacts (non-default config). | Carry |
| C5 | LOW | The backend has no `pharma_agent` gateway, so a backend T3 fails safe as `not_evaluated`. | CG-F3 |
| — | — | A7b secondary agreement with SYN gold is not measurable; never cite it. | Standing |
| — | human | Pharmacist sign-off on supersession, ties, KNOWN [] = "takes none", and pre-run orders folded into T1. | Before any clinical use |

## Standing (human)
- D1: licensed clinical review of red-flag rules/thresholds, department list, Thai dialogue templates, cross-reactivity table, `missing_field` severity.
- SCBXBeta2 font licence before any public push/deploy.
- UMLS licence / THIS (TMT) terms.
