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
