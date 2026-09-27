# Decisions

Dated approvals and material decisions. Old log (DEC-0001..0022) is in tag `archive/pre-factory-2026-09-26`.

## 2026-09-26 — Reset to Proposal v8
- **What:** removed old code and docs; `docs/PROPOSAL.md` is the single source of truth; four-role loop factory.
- **Approved by:** project owner (chat, 2026-09-26), including deletion and agent/config changes.
- **Rollback:** tags `archive/pre-factory-2026-09-26`, `archive/opd-2026-09-26`, `archive/agent-worktree-2026-09-26`; `../_archive/pre-factory-2026-09-26.tar.gz`.

## 2026-09-27 — Case Graph wiring (I2) prototype defaults
- **What:** For the research prototype on synthetic data, all labelled "pending clinical sign-off" (D1): (D-I2-1) vitals freshness window 60 min per vital, citing RCP NEWS2 (2017) Chart 4; a reading older than the window is `not_evaluated` with its time shown. (D-I2-2) `as_of` ceiling = latest `available_at_time` + 5 min on the assess API, plus a floor. (D-I2-3) same-timestamp conflicting readings resolve to the worse value or are flagged; latest-wins vs worst-in-window across timestamps is reported only, not decided. (D-I2-4) a symptom the patient never mentions is `unknown`, never `absent`; only an explicit denial is `absent`. (D-I2-5) graph export schema bumps to `casegraph-export/0.3`; ledger appends are sequenced after E1 (one writer at a time).
- **Scope:** synthetic data only; before any real data a licensed clinician must approve D-I2-1 to D-I2-4.
- **Approved by:** project owner (chat, 2026-09-27).
