# `.planning/` — GSD execution layer

**This directory is not authoritative.** Read this before treating anything here as fact.

Governed by **DEC-0008** in `docs/DECISION_LOG.md`.

## The boundary

| What | Owner | Lives in |
|---|---|---|
| Official deadlines | **authoritative** | `project_state/official_deadlines.json` |
| Milestones `M0`–`M9` | **authoritative** | `docs/project_management/MILESTONES.md` |
| Tasks `TASK-XXXX` | **authoritative** | `project_state/tasks.json` + `TASK_BOARD.md` |
| Risks `RISK-XXXX` | **authoritative** | `project_state/risks.json` + `RISK_REGISTER.md` |
| Decisions `DEC-XXXX` | **authoritative** | `project_state/decisions.json` + `DECISION_LOG.md` |
| Approvals, experiments, evaluations | **authoritative** | `project_state/` |
| Contracts and specifications | **authoritative** | `docs/shared/`, `docs/research/`, `docs/innovation/` |
| Phase sequencing (`Phase 1`–`7`) | execution | `.planning/ROADMAP.md` |
| Per-phase context, plans, summaries | execution | `.planning/phases/` |
| Codebase map | execution | `.planning/codebase/` |
| Ingest intel | execution | `.planning/intel/` |

## The one rule

Files here **may reference** an authoritative identifier — `M1`, `TASK-0003`, `RISK-0002`,
`DEC-0004`. They **must never be the place that identifier's status, scope, or definition lives**.

A phase may say it serves `M1`. A phase may not redefine what `M1` is, when it is due, or whether
it is done.

**Test:** if deleting `.planning/` entirely would lose project state, the boundary has been
violated. Move that content to `docs/` or `project_state/`.

## On disagreement

`project_state/` and `docs/` win. The `.planning/` artifact is corrected, never the other way
around. Two known divergences are tracked in `.planning/INGEST-CONFLICTS.md`.

## `REQUIREMENTS.md` is a derived index

`.planning/REQUIREMENTS.md` restates requirements that already exist in `docs/`. It is an index for
mapping requirements onto phases — not a source. Every entry cites its source document. Substantive
changes are made in the source document first, then reflected here. The checkboxes track execution
progress only.

## Why this way round

Two reasons, both structural:

1. **Enforcement.** `project_state/` and `docs/` are covered by `scripts/verify_harness.py` and by
   JSON Schema validation. When DEC-0008 was written, `.planning/` had zero coverage — the harness
   did not reference it once.
2. **Ownership.** `.planning/` is a third-party format belonging to the `@opengsd/gsd-core` release
   cycle. Installing it overwrote 71 skill files in a single command, and a future update may change
   its structure. A project's source of truth must not depend on another project's upgrade path.

## What the harness enforces

`scripts/verify_harness.py` checks that:

- every `**Depends on**:` in `ROADMAP.md` resolves to a phase that exists
- every requirement identifier in `REQUIREMENTS.md` maps to a phase in the traceability table
- every `TASK-`, `RISK-`, and `DEC-` identifier appearing anywhere in `.planning/` exists in
  `project_state/`

The first check exists because a dependency was once parsed out of prose — `M0` in a sentence became
a dependency on a non-existent "Phase 0", which silently blocked every phase in the roadmap and left
the manager dashboard with nothing to recommend. Nothing caught it. Now something does.
