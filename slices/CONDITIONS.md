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
| ctrate-loader | MEDIUM | Missing `no_chest_{split}.txt` is silently treated as "no exclusions" (`research/data/ctrate/loader.py` `_read_no_chest`); must fail loudly when expected. |
| ctrate-loader | MEDIUM | Label-source guard lets a report from another scan of the same patient through; block same-patient reports before any stage-3 report-substitution sampler uses CT-RATE. |
| ctrate-loader | MEDIUM | Missing-is-not-negative audit compares gold against counts derived from the same transformed values, so it cannot catch a pipeline bug; check against raw CSV blanks. |
| ctrate-loader | LOW | Download approval gate (`research/data/ctrate/access.py` `approval_resolves`) is a substring match: `DEC-0001` matches `DEC-00012`, and a section that rejects the download still passes; require exact id + explicit approval line. |
| ctrate-loader | LOW | `verify(root)` creates any path it is given; restrict to `data/raw/`. Two LFS files are size-checked only (HF masks LFS sha256); record our own sha256 after download. |
| ctrate-loader | LOW | `AbnormalityLabels` needs a `label_origin` field (provider text-classifier predictions from the report); metrics must be named "agreement with report-derived labels". `--unseal-test` unseals inputs and gold together; revisit in the CT reader eval slice. |
| ctrate-loader | — (human) | Download approval (who accepts terms, accessors, multi-TB storage); `train` vs `train_fixed` volumes; CC BY-NC-SA flow-down to released weights; confirm 10% dev / seed 20260926. |

## cg-t123 (CONDITIONAL_PASS ×2, 2026-10-03)
| ID | Sev | Condition | Gate |
|---|---|---|---|
| M1 | MEDIUM | When one assess builds several versions, only the last version's graph_id and alerts reach the assessment, `escalation_required` and its audit row (`casegraph_run.py`, triage `router.py`). An intermediate version's urgent alert must also escalate. | Before any backend source of results/orders (CG-F3) |
| L1 | LOW | **CLOSED by cg-l1 (commits f369783, 94f9f79).** An unparseable conversation timestamp now fails closed: `time_problem` in `conversation_meds.py`; `newest()` never returns a bad-time fact; never superseded; gate row `conversation.<kind>:unparseable_time` (`not_evaluated`); not handed to the provider; `PHARMA_GATES_VERSION` = `cg-pharma-gates-6`. Tests: `test_cgl1_nonknown_bad_time_never_superseded`, `test_cgl1_known_bad_time_never_newest`, `test_cgl1_known_bad_time_not_sent_to_provider`, `test_cgl1_helpers_total_on_bad_time`, `test_cgl1_order_permutation_invariant`, `test_cgl1_parse_medication_facts_bad_time_not_superseded`, `test_cgl1_gates_version_bumped`, `test_cgl1_fact_refs_independent_of_bad_time_filter`, `test_cgl1_same_source_item_refs_agree` (`casegraph/tests/test_cgl1_unparseable_time.py`); checker evidence `tests/e2e/test_cgl1_checker.py` (not in `make test` testpaths). Note: the typed `conversation_*_facts` echo lists only valid-time facts (`IntakeValue` is `AwareDatetime`); a bad-time fact is reported by its gate row and `conversation_fact_use`. | Closed |
| L1-F1 | LOW | Allergy-kind (`allergy_status`/`allergens`) `conversation_fact_use` may still label a bad-time fact `superseded`/`used`; it must report `not_used` with reason `conversation.<kind>:unparseable_time` (`Executor._conversation_fact_use`, owned by cg-l2). Not safety-silent: the gate token keeps Pharma `!= evaluated`, but a single fact reads as used while the provider never received it. | In cg-l2 (owns fact_use), and before UI-DAG renders `conversation_fact_use` |
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
