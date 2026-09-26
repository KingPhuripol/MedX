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
