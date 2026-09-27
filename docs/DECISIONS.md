# Decisions

Dated approvals and material decisions. Old log (DEC-0001..0022) is in tag `archive/pre-factory-2026-09-26`.

## 2026-09-26 — Reset to Proposal v8
- **What:** removed old code and docs; `docs/PROPOSAL.md` is the single source of truth; four-role loop factory.
- **Approved by:** project owner (chat, 2026-09-26), including deletion and agent/config changes.
- **Rollback:** tags `archive/pre-factory-2026-09-26`, `archive/opd-2026-09-26`, `archive/agent-worktree-2026-09-26`; `../_archive/pre-factory-2026-09-26.tar.gz`.

## 2026-09-27 — S5 Pharma evaluation definitions
- **What:** (1) A notice that a source does not state dose or frequency counts as an alert. Clean medication lists are therefore fully specified in every source; an incomplete source is its own labelled discrepancy type `missing_field`, injected and measured by recall like the others. The pipeline still never treats a missing value as agreement. (2) The S5 fixture set grows to at least 90 patients (at least 30 in the frozen test split) so each discrepancy type has at least 30 injected cases, one per patient, with patient-level bootstrap CIs.
- **Approved by:** project owner (chat, 2026-09-27).
- **Timing:** decided on dev results before any frozen test-split evaluation; thresholds unchanged (false alerts per clean list <= 0.10, recall per type >= 0.95).

## 2026-09-27 — Evaluation ledger: freeze and test runs allowed on factory branches
- **What:** Exception to `eval/ledger/README.md` rule 1 ("appends on `main` only"). A slice may freeze its evaluation manifests and run its single test-split evaluation on its own `factory/<slice>` branch, provided that: (1) the branch reaches `main` through `factory/int` by ordinary merges (no rebase, squash or force-push), so ledger history is preserved; (2) `python -m eval ledger verify --git-history` passes on `factory/int` and again on `main` after each merge; (3) only one slice appends to a given ledger file at a time — a ledger merge conflict is resolved per README rule 4 (redo the later freeze/run on top of the merged ledger), never by editing entries.
- **Applies to:** E1 and S6 now; later evaluation slices on the same terms.
- **Approved by:** project owner (chat, 2026-09-27).

## 2026-09-27 — Case Graph wiring (I2) prototype defaults
- **What:** For the research prototype on synthetic data, all labelled "pending clinical sign-off" (D1): (D-I2-1) vitals freshness window 60 min per vital, citing RCP NEWS2 (2017) Chart 4; a reading older than the window is `not_evaluated` with its time shown. (D-I2-2) `as_of` ceiling = latest `available_at_time` + 5 min on the assess API, plus a floor. (D-I2-3) same-timestamp conflicting readings resolve to the worse value or are flagged; latest-wins vs worst-in-window across timestamps is reported only, not decided. (D-I2-4) a symptom the patient never mentions is `unknown`, never `absent`; only an explicit denial is `absent`. (D-I2-5) graph export schema bumps to `casegraph-export/0.3`; ledger appends are sequenced after E1 (one writer at a time).
- **Scope:** synthetic data only; before any real data a licensed clinician must approve D-I2-1 to D-I2-4.
- **Approved by:** project owner (chat, 2026-09-27).

## 2026-09-27 — S6 test split redone on a fresh held-out set
- **What:** The S6 ledger recorded the frozen test evaluation `s6-care-test-0001` twice (runs seq 2 and 4, identical predictions sha256 `281c8d9f…`, the second a report re-render). The owner chose to redo it rather than accept it. `s6-care-test-0001` is retired and relabelled "seen — not a held-out result"; it must never be reported as the S6 test result. S6 may be improved on train/dev only; then a fresh held-out test set is generated from a new seed (patients disjoint from all existing splits), its manifest frozen before any run, and evaluated exactly once. The runner must allow a report re-render of an existing run without appending a new run line.
- **Approved by:** project owner (chat, 2026-09-27).
