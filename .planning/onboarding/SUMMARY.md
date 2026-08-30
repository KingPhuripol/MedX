# Onboarding Summary

> ⚠️ **Generated snapshot, extracted 2026-08-11 — partially stale.** It still describes the
> flagship as approximately 4B. DEC-0009 (2026-08-26) makes the flagship approximately 27B and
> withdraws the 4B target. Authority sits with `docs/` and `project_state/` (DEC-0008); read
> `docs/DECISION_LOG.md` before relying on any scale figure here.

Project: Case-Adaptive Medical Multimodal Foundation Model for Clinical Reasoning and
Care-Pathway Decision Support

## Project State
- PROJECT.md: present
- REQUIREMENTS.md: present
- ROADMAP.md: present
- STATE.md: present

## Codebase Context
- Brownfield repo: yes
- Map readiness: complete
- Codebase map: `.planning/codebase/` (complete codebase map)
- Fast map available: yes

Key finding from the map: only a verification harness exists today — 8 scripts, 10 JSON schemas,
6 machine state files, 3 fixtures. `research/`, `innovation/`, and `shared/` are README stubs. The
model, Model Gateway, Front Door, DAG executor, and every dataset are **not started**. Every
requirement is SPECIFIED, none implemented.

## Docs Context
- Existing ADR/PRD/SPEC/RFC candidates detected by the projection: 5
- Actually ingested by `/gsd-ingest-docs`: **23** (2 ADR, 14 SPEC, 7 DOC; 8 locked)

Precedence was set by an explicit manifest at `.planning/ingest-manifest.yaml`, not by heuristics.
Default classification had placed `docs/DECISION_LOG.md` and
`docs/project_management/OFFICIAL_DEADLINES.md` at the lowest tier, which would have let any SPEC
silently override an accepted decision. The manifest restores the authority model stated in
CLAUDE.md: contracts and accepted Decision Log entries override plans; plans override status
summaries.

Conflict report: `.planning/INGEST-CONFLICTS.md` — **0 blockers**, 3 warnings, 5 info.

## Open Items Carried Forward
1. WARN-03 — `MILESTONES.md` M8 (Mar–Apr 2027) vs `MASTER_PLAN.md` Phase 6 (Feb–Mar 2027) for the
   4B release candidate. Equal precedence, both variants preserved, no winner picked. Needs a human
   decision before Phase 6 planning.
2. GOV-03 (Phase 1) — advisor identity is unrecorded. Not inferred.
3. GOV-02 (Phase 1) — the cited deadline source PDF is absent from `sources/`; machine state records
   `transcription_status: PENDING_VISUAL_VERIFICATION`. Provenance gap only; the seven dates agree
   across all three places they appear and remain binding.
4. GOV-01 (Phase 2) — the Front Door target runtime is deliberately unchosen. It must be recorded as
   a Decision Log entry before any gateway or prototype implementation.
5. Machine state lag — the human owner confirmed in session that the Group Application (DL-0001) was
   submitted, and M0 is recorded Validated in PROJECT.md. `project_state/official_deadlines.json`
   still reads `NEEDS_CONFIRMATION` and RISK-0001 is still open at HIGH/CRITICAL. Those records need
   updating so the repository, not chat history, is the source of truth.

## Recommended Next Step
- `/gsd-manager`
