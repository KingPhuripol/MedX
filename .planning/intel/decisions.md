# Decisions (ADR tier, precedence 0)

Extracted from documents the ingest manifest typed `ADR` with `precedence: 0, locked: true`.
These are accepted decisions and the immutable schedule. Under this project's authority model
they override every SPEC, plan, and status summary. None may be auto-overridden by synthesis.

Status vocabulary: `locked` = accepted and manifest-locked; `proposed` = not accepted.

> **Updated 2026-08-30.** This snapshot was extracted on 2026-08-11 and captured eight decisions.
> DEC-0009 has since been accepted and supersedes DEC-0002. Both are recorded below.
> The authoritative record is `docs/DECISION_LOG.md` and `project_state/decisions.json` (DEC-0008).

---

## DEC-0001: One project, two tracks

- source: docs/DECISION_LOG.md
- status: locked (Accepted, 2026-08-11, owners: all five members)
- decision: Run one Senior Project under one title, with Research and Innovation as coordinated internal tracks.
- scope: project structure, track boundary, integration gate
- rationale: The model contribution and Clinical Front Door share data, contracts, evaluation, and the final demonstration.
- consequences: There is one schedule and one integration gate. Neither track may optimize in isolation at the expense of the joint deliverable.

## DEC-0002: Flagship approximately 4B; 27B is stretch — SUPERSEDED

- source: docs/DECISION_LOG.md
- status: **superseded by DEC-0009 on 2026-08-26** (was: locked, accepted 2026-08-11, owner: Phurinat Polasa)
- **note: this entry is history. The flagship target is approximately 27B. See DEC-0009 below.**
- decision: Treat approximately 4B parameters as the flagship target. Permit 27B work only after the 4B release candidate passes architecture, data, safety, evaluation, compute, and schedule gates.
- scope: model scale, flagship target, stretch scope
- rationale: Evidence at small and 4B scales is more important than unsupported scale.
- consequences: No 27B critical-path dependency and no 27B resource commitment before a separate approval.

## DEC-0003: Stable Model Gateway

- source: docs/DECISION_LOG.md
- status: locked (Accepted, 2026-08-11, owner: Supreeya Nuamkhayan)
- decision: All Innovation inference uses the versioned Model API Contract through a Model Gateway. Mock and external APIs are prototype providers only.
- scope: integration architecture, provider boundary, Innovation inference
- rationale: Product work can proceed before the team model is ready without provider lock-in.
- consequences: No provider-specific objects may cross the gateway boundary. Contract tests are required for every adapter.

## DEC-0004: Patient-level temporal integrity

- source: docs/DECISION_LOG.md
- status: locked (Accepted, 2026-08-11, owner: Jakkapat Bunjongruxsa)
- decision: Split by patient before window generation and require `available_at_time` on every evidence and label item.
- scope: data splits, temporal integrity, evidence and label metadata
- rationale: Encounter- or image-level splits and future information would inflate performance and invalidate the clinical simulation.
- consequences: Any leakage finding invalidates affected results until data and experiments are rebuilt.

## DEC-0005: Decision support with mandatory human review

- source: docs/DECISION_LOG.md
- status: locked (Accepted, 2026-08-11, owner: Thanrada Tungweerapornpong)
- decision: The system supports, but never autonomously makes, diagnosis, treatment, referral, or discharge decisions.
- scope: clinical role, claim boundary, human review
- rationale: The project is a research prototype in a safety-critical domain.
- consequences: User-facing outputs require limitations, uncertainty, escalation, and human confirmation.

## DEC-0006: Restrict real-patient data from external APIs

- source: docs/DECISION_LOG.md
- status: locked (Accepted, 2026-08-11, owner: Jakkapat Bunjongruxsa)
- decision: Do not send real, identifiable, or linkable patient data to an external API without explicit, scoped, recorded authorization.
- scope: privacy, external providers, data transfer authorization
- rationale: Privacy, consent, ethics, and vendor data-handling obligations must be resolved before transfer.
- consequences: Default external-provider testing uses synthetic or approved de-identified fixtures.

## DEC-0007: Official Semester 1 schedule is immutable

- source: docs/DECISION_LOG.md
- status: locked (Accepted, 2026-08-11, owner: Phurinat Polasa)
- decision: Lock the Semester 1 dates transcribed from `Senior_Project 2026_sem1_activities.pdf` into `project_state/official_deadlines.json`.
- scope: schedule governance, academic deadlines
- rationale: Planning buffers may move; faculty deadlines may not.
- consequences: Corrections require a new official source, human approval, synchronized registry update, and a superseding decision.

## Official Semester 1 deadlines are immutable (schedule lock)

- source: docs/project_management/OFFICIAL_DEADLINES.md
- status: locked (authority: `Senior_Project 2026_sem1_activities.pdf`; transcribed 2026-08-11; timezone Asia/Bangkok)
- decision: Official deadlines are immutable. Internal buffers are planning commitments, not replacements. A compressed window must be exposed as risk with the minimum valid deliverable prioritized; it may not silently move the official deadline.
- scope: academic deadlines, schedule governance, planning buffers
- note: The seven dates themselves are recorded as hard constraints in `constraints.md` (CON-DEADLINES). See WARNING in INGEST-CONFLICTS.md regarding outstanding visual verification of the transcription source.

---

## Decision-log entries also present in machine state

`project_state/decisions.json` carries DEC-0001..DEC-0007 with matching IDs, dates, statuses, and
owners. `docs/DECISION_LOG.md` states it is the readable register and that decisions are
append-only with superseded entries remaining visible. No entry in this ingest set is superseded.

## DEC-0009: Approximately 27B replaces approximately 4B as the flagship target

- source: docs/DECISION_LOG.md
- status: locked (Accepted, 2026-08-26, owner: Phurinat Polasa)
- supersedes: DEC-0002
- decision: Approximately 27B is the flagship target of the Research Track. The approximately 4B target is withdrawn and no longer appears as a project deliverable. Every gate DEC-0002 attached to the 4B release candidate now attaches unchanged to the 27B release candidate: G0-G4 must close on recorded evidence, and a valid Tier 4 manifest plus explicit time-bounded human approval are required before any flagship run.
- scope: model scale, flagship target, stretch scope
- rationale: The flagship scale is the project owner's decision, given directly on 2026-08-26 while the Project Idea was being prepared for the immutable DL-0002 deadline. Recording it as a superseding entry keeps the submitted document consistent with the enforced record.
- consequences: RISK-0004 restated against 27B with probability raised to CRITICAL. Compute, storage, cost and schedule must be re-estimated against 27B before any Tier 3 or Tier 4 request; no estimate carried over from 4B remains valid (TASK-0018). The scope fallback ladder in MASTER_PLAN.md was rewritten for a 27B flagship. There is no stretch model above the flagship.
- open concern: this decision records the owner's direction; it does not establish that the compute exists. Feasibility evidence is owed at the flagship gate.
