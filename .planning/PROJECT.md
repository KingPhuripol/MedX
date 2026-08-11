# Case-Adaptive Medical Multimodal Foundation Model for Clinical Reasoning and Care-Pathway Decision Support

## What This Is

One Senior Project run as two coordinated tracks by five members. The **Research Track** builds an
open-weight medical multimodal model (flagship target approximately 4B) that compiles time-valid
evidence and task context into a discrete, typed, exportable, replayable computation DAG. The
**Innovation Track** builds an API-first AI Clinical Front Door that uses the same contracts to
support intake, urgency screening, care-pathway suggestion, next-information selection, calibrated
uncertainty, escalation, and mandatory human confirmation.

This is a research and clinical decision-support prototype. It supports, assists, and suggests for
review. It does not diagnose, treat, prescribe, refer, discharge, or act on a real patient.

## Core Value

Every claim this project makes is reproducible by an independent reviewer and traceable to evidence
that was actually available at the simulated decision time — integrity before scale, speed, or
headline results.

## Requirements

### Validated

<!-- Shipped and confirmed. -->

- ✓ **M0 — Group Application submitted** (DL-0001, 14 Aug 2026) — confirmed by the human owner.
  Repository control and the verification harness (8 scripts, 10 JSON schemas, 6 state files,
  3 fixtures) exist and pass `python3 scripts/verify_harness.py`.

### Active

Full list with IDs and phase mapping: `.planning/REQUIREMENTS.md`. Summary of committed scope:

- [ ] Six remaining official academic deliverables (AC-01..AC-06) delivered on their immutable dates
- [ ] Research gates G0-G4 closed on recorded evidence before any flagship scaling (RG-01..RG-05)
- [ ] Approximately 4B authorization, training, and release candidate under recorded human approval
      (RG-06, RG-07), or an honestly-reported smaller defensible outcome (RG-10)
- [ ] Authorized, reproducible public release (RG-08)
- [ ] Innovation acceptance A0-A6 — contract prototype through final demonstration (IA-01..IA-07)
- [ ] An executable release veto enforcing the absolute rejection conditions (IA-08)
- [ ] Front Door product jobs, non-functional obligations, and staged release ladder (PD-01..PD-03)
- [ ] Adapter contract certification and the seven architecture test classes (IT-01, IT-02)
- [ ] Three open governance items closed: Front Door runtime decision, deadline-source verification,
      advisor identity (GOV-01..GOV-03)

### Out of Scope

- **27B-class training (`Medical-DAG-Large`)** — stretch scope only, gated behind RG-07 (G6) and a
  separate accepted decision plus explicit human approval (DEC-0002). Tracked as v2. Failure to
  attempt it does not reduce project success.
- **Autonomous diagnosis, treatment, prescription, test order, referral, discharge, or patient
  instruction** — prohibited by DEC-0005 and CON-SAFETY-PROHIBITED.
- **Live clinical use affecting patient care** — requires separate governance outside this project.
- **External transfer of real, identifiable, or linkable patient data** — denied by default under
  DEC-0006; any exception needs a scoped, recorded approval ID.
- **Clinical claims beyond the evaluated population, modality, site, or task** — CON-CLAIM-BOUNDARY.
- **Patient-facing direct use and production deployment** — outside the prototype boundary.
- **Presenting an inspectable DAG as a clinical explanation without intervention evidence** — RQ3
  requires causal-faithfulness evidence, not visualization alone.

## Context

**Nothing described in the specification set is built yet.** The repository holds a verification
harness only: `scripts/` (8 stdlib-only Python and Bash tools), `schemas/` (10 JSON schemas),
`project_state/` (6 machine state files), `tests/fixtures/` (3 fixtures), and one experiment
manifest. `research/`, `innovation/`, and `shared/` contain a `README.md` each and no source code.
`data/`, `checkpoints/`, `logs/`, and `sources/` are empty. Plan every model, gateway, Front Door,
DAG executor, adapter, and dataset as **not started**.

**Stack today:** Python 3.10+, standard library only, no package manager, no external dependencies,
no test framework. The training stack (PyTorch/CUDA) and the Front Door runtime are both specified
but not chosen or installed. See `.planning/codebase/STACK.md`.

**Team and ownership** (`docs/project_management/TEAM_OWNERSHIP.md`): Phurinat Polasa — program
management and Research Lead; Thanapol Popit — model architecture; Jakkapat Bunjongruxsa — data
governance and clinical workflow; Thanrada Tungweerapornpong — safety and evaluation; Supreeya
Nuamkhayan — product and system development. No owner accepts their own safety-critical deliverable
without independent review. No member holds more than 40% of active P0/P1 tasks without a recovery
plan.

**Research hypothesis (designed to be falsifiable early):** medical cases should not all use an
identical fixed computation path. RQ1 adaptation, RQ2 controlled utility, RQ3 faithfulness and
inspectability, RQ4 temporal and missing-modality robustness, RQ5 multi-disease generalization.
Stopping or reframing is a valid research outcome (CON-KILL-TESTS).

**Scope fallback ladder** (apply in this order if feasibility or time fails): (1) keep one project
with patient-level and temporal integrity, safety, controlled comparisons, a stable gateway, and an
end-to-end demonstration; (2) reduce datasets and tasks while keeping representative text, imaging,
and temporal evidence; (3) reduce training scale and report the limitation; (4) defer 3D breadth
only through an approved scope change; (5) remove 27B entirely. Never preserve headline scale by
sacrificing valid splits, baselines, safety, or reproducibility.

**Open risks carried into planning** (all 10 OPEN in `docs/project_management/RISK_REGISTER.md`):
no dataset supports all modalities linked at patient level (RISK-0002); temporal or identity leakage
invalidates results (RISK-0003); compute cannot support stable 4B training (RISK-0004); routing
collapses or offers no controlled benefit (RISK-0005); cross-track contract drift (RISK-0006); false
reassurance or critical under-triage (RISK-0007); academic writing absorbs technical capacity
(RISK-0008); external API privacy/cost/lock-in (RISK-0009); release license or sensitive-artifact
breach (RISK-0010).

## Constraints

- **Schedule (immutable)**: Six remaining official deadlines, Asia/Bangkok — Project Idea 28 Aug
  2026; CITI 25 Sep 2026; Proposal Report 2 Oct 2026; Proposal Presentation 8-9 Oct 2026; Progress
  Report 4 Dec 2026; Progress Presentation 14-15 Dec 2026 — because faculty dates are not
  negotiable by planning (CON-DEADLINES, DEC-0007). Post-Semester-1 dates are planning assumptions
  only (CON-DATES-UNOFFICIAL).
- **Data integrity**: split by stable `patient_id` before deriving encounters, windows, or samples;
  every evidence and label item carries `available_at_time`; at decision time `T` nothing may depend
  on `available_at_time > T`; fit preprocessing on training data only; preserve missingness — because
  encounter-level splits or future information invalidate the clinical simulation (DEC-0004,
  CON-SPLIT-INVARIANTS, CON-TEMPORAL, CON-PREPROCESSING, CON-MISSINGNESS).
- **Safety**: deterministic red-flag rules run independently of the model and cannot be downgraded by
  it; no autonomous clinical action; no hidden chain-of-thought exposure; `human_review.required` is
  always `true` — because this is a safety-critical domain and the prototype is supervised
  (DEC-0005, CON-SAFETY-PROHIBITED, CON-SAFETY-CONTROLS, CON-API-RESPONSE).
- **Integration**: all Innovation inference crosses the versioned Model Gateway; no provider-specific
  object escapes an adapter; every adapter passes the same ten-case fixture suite — because the
  product must proceed before the team model exists, without provider lock-in (DEC-0003,
  CON-API-REQUEST/RESPONSE/ERRORS/VERSIONING).
- **Approval gates**: Tier 3/4 training, more than one GPU, expected runtime over 60 minutes,
  external transfer of non-synthetic data, publication, and deletion each require a specific,
  time-bounded, recorded human approval — because an agent cannot approve and a hook prompt is not
  authorization (CON-APPROVAL-GATES, CON-APPROVAL-RECORD, CON-TRAINING-TIERS).
- **Evaluation**: freeze question, cohort, snapshot, metric, comparison, and exclusion before viewing
  final results; report safety first; preserve failures; no metric shopping; no universal numeric
  threshold is assumed — because post-hoc selection destroys the claim (CON-EVAL-PRINCIPLES,
  CON-EVAL-STATS, CON-BENCHMARK-FREEZE, CON-LEAKAGE-ISOLATION).
- **Claim boundary**: claim only what frozen evaluation supports; prefer "supports", "assists",
  "suggests for review", "research prototype" (CON-CLAIM-BOUNDARY, CON-CLAIM-MAP).
- **Tech stack**: Python 3.10+, standard library only in `scripts/` and `.claude/hooks/`. The Front
  Door runtime is **deliberately undecided** and must be chosen via a recorded Decision Log entry in
  Phase 2 before any Front Door code is written.

## Key Decisions

<decisions>

All eight entries below are **locked** at precedence 0 and may not be re-litigated by any downstream
phase, plan, or agent. Changing one requires explicit human approval and a superseding Decision Log
entry. Source of truth: `docs/DECISION_LOG.md`, `docs/project_management/OFFICIAL_DEADLINES.md`,
`project_state/decisions.json`.

- **D-01 [locked]:** DEC-0001 — Run one Senior Project under one title with Research and Innovation
  as coordinated internal tracks. One schedule, one integration gate; neither track may optimize in
  isolation at the expense of the joint deliverable.
- **D-02 [locked]:** DEC-0002 — Approximately 4B parameters is the flagship target; 27B-class work is
  stretch scope permitted only after the 4B release candidate passes every gate and a separate
  approval. No 27B critical-path dependency or resource commitment before that approval.
- **D-03 [locked]:** DEC-0003 — All Innovation inference uses the versioned Model API Contract
  through a stable Model Gateway. Mock and external APIs are prototype providers only; no
  provider-specific object crosses the boundary; contract tests are required for every adapter.
- **D-04 [locked]:** DEC-0004 — Split by patient before window generation and require
  `available_at_time` on every evidence and label item. Any leakage finding invalidates affected
  results until data and experiments are rebuilt.
- **D-05 [locked]:** DEC-0005 — The system supports, but never autonomously makes, diagnosis,
  treatment, referral, or discharge decisions. User-facing outputs require limitations, uncertainty,
  escalation, and human confirmation.
- **D-06 [locked]:** DEC-0006 — Do not send real, identifiable, or linkable patient data to an
  external API without explicit, scoped, recorded authorization. Default external-provider testing
  uses synthetic or approved de-identified fixtures.
- **D-07 [locked]:** DEC-0007 — The official Semester 1 schedule is immutable. Corrections require a
  new official faculty source, human approval, a synchronized registry update, and a superseding
  decision.
- **D-08 [locked]:** Official deadlines are immutable and internal buffers are planning commitments,
  not replacements. A compressed window is exposed as risk with the minimum valid deliverable
  prioritized; it may never silently move an official date.

</decisions>

Project-level decisions made during roadmapping (revisable through the normal Decision Log process):

| Decision | Rationale | Outcome |
|----------|-----------|---------|
| Phases bundle both tracks per gate window rather than splitting Research and Innovation into separate phase chains | DEC-0001 gives one schedule and one integration gate; within a phase the two tracks proceed in parallel by owner | — Pending |
| Academic deliverables are phase exit criteria, not standalone phases | The immutable deadline is the natural delivery boundary and forces the evidence to exist; standalone writing phases would be PM theater | — Pending |
| Front Door runtime left unchosen until Phase 2 | A material architecture choice requires a recorded Decision Log entry; assuming a framework now would pre-empt that governance | — Pending |
| Team-model gateway integration (A5) placed in Phase 5, before 4B scaling | Integrating the small model early is the control for RISK-0006 contract drift, and must be proven before scaling consumes the schedule | — Pending |
| 27B stretch gate moved to v2 requirements | DEC-0002 makes it non-critical-path; keeping it in v1 would imply a commitment the decision explicitly withholds | — Pending |

---
*Last updated: 2026-08-11 after initial ingest of 23 project documents (`/gsd-ingest-docs`)*
