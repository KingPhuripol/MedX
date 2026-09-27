# Decisions

Dated approvals and material decisions. Old log (DEC-0001..0022) is in tag `archive/pre-factory-2026-09-26`.

## 2026-09-26 — Reset to Proposal v8
- **What:** removed old code and docs; `docs/PROPOSAL.md` is the single source of truth; four-role loop factory.
- **Approved by:** project owner (chat, 2026-09-26), including deletion and agent/config changes.
- **Rollback:** tags `archive/pre-factory-2026-09-26`, `archive/opd-2026-09-26`, `archive/agent-worktree-2026-09-26`; `../_archive/pre-factory-2026-09-26.tar.gz`.

## 2026-09-27 — S6 test split redone on a fresh held-out set
- **What:** The S6 ledger recorded the frozen test evaluation `s6-care-test-0001` twice (runs seq 2 and 4, identical predictions sha256 `281c8d9f…`, the second a report re-render). The owner chose to redo it rather than accept it. `s6-care-test-0001` is retired and relabelled "seen — not a held-out result"; it must never be reported as the S6 test result. S6 may be improved on train/dev only; then a fresh held-out test set is generated from a new seed (patients disjoint from all existing splits), its manifest frozen before any run, and evaluated exactly once. The runner must allow a report re-render of an existing run without appending a new run line.
- **Approved by:** project owner (chat, 2026-09-27).
