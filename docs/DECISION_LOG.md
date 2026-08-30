# Decision Log

Machine-readable decisions are in `project_state/decisions.json` and validated against `schemas/decision.schema.json`. This document is the readable register. Decisions are append-only; superseded entries remain visible.

## DEC-0001 - One project, two tracks

- **Date:** 2026-08-11
- **Status:** accepted
- **Owners:** all five members
- **Decision:** Run one Senior Project under one title, with Research and Innovation as coordinated internal tracks.
- **Rationale:** The model contribution and Clinical Front Door share data, contracts, evaluation, and the final demonstration.
- **Consequences:** There is one schedule and one integration gate. Neither track may optimize in isolation at the expense of the joint deliverable.

## DEC-0002 - Flagship approximately 4B; 27B is stretch

- **Date:** 2026-08-11
- **Status:** superseded by DEC-0009 on 2026-08-26
- **Owner:** Phurinat Polasa
- **Decision:** Treat approximately 4B parameters as the flagship target. Permit 27B work only after the 4B release candidate passes architecture, data, safety, evaluation, compute, and schedule gates.
- **Rationale:** Evidence at small and 4B scales is more important than unsupported scale.
- **Consequences:** No 27B critical-path dependency and no 27B resource commitment before a separate approval.

## DEC-0003 - Stable Model Gateway

- **Date:** 2026-08-11
- **Status:** accepted
- **Owner:** Supreeya Nuamkhayan
- **Decision:** All Innovation inference uses the versioned Model API Contract through a Model Gateway. Mock and external APIs are prototype providers only.
- **Rationale:** Product work can proceed before the team model is ready without provider lock-in.
- **Consequences:** No provider-specific objects may cross the gateway boundary. Contract tests are required for every adapter.

## DEC-0004 - Patient-level temporal integrity

- **Date:** 2026-08-11
- **Status:** accepted
- **Owner:** Jakkapat Bunjongruxsa
- **Decision:** Split by patient before window generation and require `available_at_time` on every evidence and label item.
- **Rationale:** Encounter- or image-level splits and future information would inflate performance and invalidate the clinical simulation.
- **Consequences:** Any leakage finding invalidates affected results until data and experiments are rebuilt.

## DEC-0005 - Decision support with mandatory human review

- **Date:** 2026-08-11
- **Status:** accepted
- **Owner:** Thanrada Tungweerapornpong
- **Decision:** The system supports, but never autonomously makes, diagnosis, treatment, referral, or discharge decisions.
- **Rationale:** The project is a research prototype in a safety-critical domain.
- **Consequences:** User-facing outputs require limitations, uncertainty, escalation, and human confirmation.

## DEC-0006 - Restrict real-patient data from external APIs

- **Date:** 2026-08-11
- **Status:** accepted
- **Owner:** Jakkapat Bunjongruxsa
- **Decision:** Do not send real, identifiable, or linkable patient data to an external API without explicit, scoped, recorded authorization.
- **Rationale:** Privacy, consent, ethics, and vendor data-handling obligations must be resolved before transfer.
- **Consequences:** Default external-provider testing uses synthetic or approved de-identified fixtures.

## DEC-0007 - Official Semester 1 schedule is immutable

- **Date:** 2026-08-11
- **Status:** accepted
- **Owner:** Phurinat Polasa
- **Decision:** Lock the Semester 1 dates transcribed from `Senior_Project 2026_sem1_activities.pdf` into `project_state/official_deadlines.json`.
- **Rationale:** Planning buffers may move; faculty deadlines may not.
- **Consequences:** Corrections require a new official source, human approval, synchronized registry update, and a superseding decision.

## DEC-0008 - Planning-system ownership boundary

- **Date:** 2026-08-11
- **Status:** accepted
- **Owner:** Phurinat Polasa
- **Decision:** `project_state/` and `docs/` remain the sole authoritative record of deadlines, milestones, tasks, risks, decisions, approvals, contracts, and specifications. `.planning/`, introduced by the GSD toolchain, is a subordinate execution layer that owns phase sequencing and per-phase execution artifacts only. `.planning/` may reference an authoritative identifier such as `M1`, `TASK-0003`, or `RISK-0002`, but may never be the place where that item's status, scope, or definition lives. `.planning/REQUIREMENTS.md` is a derived index: every requirement must cite its source document, and any substantive change is made in the source first.
- **Rationale:** The repository now carries two vocabularies for the same work — `docs/project_management/` (M0-M9, TASK-XXXX, RISK-XXXX) and `.planning/` (Phase 1-7, REQUIREMENTS, STATE). Divergence has already occurred: `MILESTONES.md` M8 and `MASTER_PLAN.md` Phase 6 give different 4B release-candidate windows, and recording one Group Application status required editing five files by hand. Authority must sit with `project_state/` and `docs/` for two reasons. First, they are enforced — 199 harness checks and JSON Schema validation cover them, while `.planning/` had zero coverage when this decision was written. Second, `.planning/` is a third-party format owned by the `@opengsd/gsd-core` release cycle; installing it overwrote 71 skill files in one command, and a future update may change its structure. A project's source of truth may not depend on another project's upgrade path.
- **Consequences:**
  - `.planning/README.md` states this boundary at the point of use so future sessions and agents see it without reading this log.
  - `scripts/verify_harness.py` enforces the boundary: phase dependencies must resolve to real phases, requirement identifiers must map to a phase, and any `TASK-`/`RISK-`/`DEC-` identifier appearing in `.planning/` must exist in `project_state/`.
  - Deleting or regenerating `.planning/` must never lose project state. If it would, the boundary has been violated and the content belongs in `docs/` or `project_state/`.
  - Where the two disagree, `project_state/` and `docs/` win, and the `.planning/` artifact is corrected.
  - Accepted by the human owner on 2026-08-11 and in force from that date. Superseding it requires a new Decision Log entry, not an edit to this one.

## DEC-0009 - Approximately 27B replaces approximately 4B as the flagship target

- **Date:** 2026-08-26
- **Status:** accepted
- **Supersedes:** DEC-0002
- **Owner:** Phurinat Polasa
- **Decision:** Approximately 27B is the flagship target of the Research Track. The approximately 4B target is withdrawn and no longer appears as a project deliverable. Every gate that DEC-0002 attached to the 4B release candidate now attaches to the 27B release candidate, unchanged in substance: G0-G4 must close on recorded evidence, and a valid Tier 4 manifest plus explicit time-bounded human approval are required before any flagship run.
- **Rationale:** The flagship scale is the project owner's decision and was given directly on 2026-08-26 while the Project Idea document was being prepared for the immutable DL-0002 deadline. Recording it as a superseding entry keeps the submitted document consistent with the enforced record instead of leaving it contradicting a locked decision.
- **Consequences:**
  - RISK-0004 is restated against 27B and its probability raised to `CRITICAL`. Compute feasibility is now the dominant threat to the Research Track flagship.
  - The scope fallback ladder is unchanged and load-bearing. If compute cannot support stable 27B training, the delivered model is reported at its true scale and is never relabelled as approximately 27B.
  - Small-scale architecture validation before scaling is unchanged and still gates any flagship run. A larger target does not license skipping a gate.
  - Compute, storage, cost, and schedule impact must be re-estimated against 27B before any Tier 3 or Tier 4 request. No estimate carried over from 4B remains valid.
  - `docs/PROJECT_CHARTER.md`, `docs/research/RESEARCH_SPEC.md`, `docs/research/SUCCESS_CRITERIA.md`, `docs/research/TRAINING_SPEC.md`, `docs/project_management/MASTER_PLAN.md`, `docs/project_management/MILESTONES.md`, and the `.planning/` artifacts still name 4B. They must be reconciled before the Proposal Report on 2026-10-02.
- **Open concern recorded, not resolved:** approximately 27B is roughly a sevenfold parameter increase over the withdrawn target, against a risk register that already rated 4B compute feasibility `HIGH`. This decision records the owner's direction; it does not establish that the compute exists. The feasibility evidence is owed at the flagship gate.

## DEC-0010 - Python and FastAPI as the Clinical Front Door runtime

- **Date:** 2026-08-30
- **Status:** accepted
- **Owner:** Supreeya Nuamkhayan
- **Decision:** Implement the Clinical Front Door API, the Model Gateway and the shared contract runtime in Python with FastAPI. Contract models are Pydantic models bound to the JSON Schemas already in `schemas/`, which remain the machine source of truth. Provider SDKs stay inside gateway adapters per DEC-0003.
- **Rationale:** One language across the project. The Research Track is Python by necessity and `scripts/` is already Python. The five shared contracts exist as JSON Schema, and Pydantic binds to them directly, so the executable contract and the machine contract cannot drift into two separate definitions. A second language would mean maintaining contract models twice and syncing them by hand — exactly the drift RISK-0006 describes.
- **Alternatives considered:**
  - TypeScript with Node — better for a frontend-heavy project, but adds a second language and a second copy of the contract models.
  - Python with Django REST Framework — heavier than an API-first service with no admin or ORM requirement needs at this stage.
  - Defer and let the choice emerge from the first implementation — forbidden by GOV-01, and it is how architecture decisions become accidents.
- **Consequences:**
  - Phase 2 is unblocked: contract models, the mock provider and the ten contract fixtures can be written.
  - `shared/` holds the versioned Pydantic contract models; `schemas/` stays authoritative and the models are tested against the existing fixtures in `tests/fixtures/`.
  - Provider-specific types may not appear in Front Door business logic or in any client.
  - A dependency file and a virtual environment enter the repository for the first time. `scripts/` stays stdlib-only so `verify_harness.py` keeps running with no install step.
  - A browser UI, if later required, consumes the same API as any other client and does not reopen this decision.
- **Ordering constraint honoured:** recorded and accepted before any Phase 2 implementation file exists.

## DEC-0011 - Accept a non-commercial research-use ceiling on the open-weight release

- **Date:** 2026-08-30
- **Status:** accepted
- **Owner:** Phurinat Polasa
- **Decision:** Accept the ceiling. Released weights are for **non-commercial research use only**, and the candidate dataset set is not narrowed to avoid it. Every artifact describing the release — Proposal Report, Progress Report, model card, README, any publication — states the restriction explicitly instead of using the unqualified term *open-weight*. The term may still describe what it actually denotes, that the weights are published and inspectable, but never as an implied grant of unrestricted use.
- **Rationale:** This is an academic Senior Project; its deliverable is research evidence, not a commercial artifact, so a non-commercial licence costs nothing the project needs. Narrowing the candidate set to preserve commercial rights would cost real capability — dropping the MIMIC family removes the only patient-linked multimodal cohort, and dropping CT-RATE removes the only 3D CT source. Paying in evidence quality for a permission the project has no use for is a bad trade.
- **Alternatives considered:**
  - Restrict to permissively licensed data only — would leave VQA-RAD as effectively the sole source, removing patient linkage, longitudinal structure and 3D coverage.
  - Defer the release terms until release — would let the submitted document's unqualified claim stand through two more reports.
  - Release no weights, only code and evaluation artifacts — remains the RISK-0010 fallback, but is not warranted by the present evidence.
- **Consequences:**
  - An unqualified *open-weight* claim is now a **known inaccuracy**, not a pending detail. TASK-0008's retrospective review must list it for correction in the Proposal Report.
  - **RISK-0010 stays OPEN.** This decision does not settle whether PhysioNet permits releasing weights trained on MIMIC at all (TASK-0020), nor whether CT-RATE's ShareAlike term propagates to the released weights.
  - If TASK-0020 returns that PhysioNet does not permit a weights release, this decision does not authorise one anyway.
  - The release licence is chosen at the release gate, and must be at least as restrictive as the most restrictive contributing dataset.
