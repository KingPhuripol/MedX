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
- **Status:** accepted
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

