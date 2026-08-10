# Project Charter

**Status:** Accepted baseline  
**Effective date:** 2026-08-11  
**Project:** Case-Adaptive Medical Multimodal Foundation Model for Clinical Reasoning and Care-Pathway Decision Support

## Purpose

Build one coherent Senior Project that contributes both a testable research model and a usable clinical decision-support prototype. The Research Track investigates whether case-specific, inspectable computation can improve the quality-efficiency-auditability trade-off of medical multimodal reasoning. The Innovation Track demonstrates the same contracts in an AI Clinical Front Door that supports early intake and safe care-pathway decisions under incomplete information.

## Team

| Member | Student ID | Primary accountability | Track |
|---|---|---|---|
| Phurinat Polasa | 66070501042 | Program management and Research Lead | Cross-project / Research |
| Thanapol Popit | 66070501085 | Model architecture and development | Research |
| Jakkapat Bunjongruxsa | 66070501008 | Data governance and clinical workflow | Innovation / Shared |
| Thanrada Tungweerapornpong | 66070501025 | Safety and evaluation | Innovation / Shared |
| Supreeya Nuamkhayan | 66070501087 | Product and system development | Innovation |

The advisor name is not recorded in the available project context. Confirming the advisor and submission evidence is an active P0 task; no system or agent may invent this information.

## Problem

Many medical AI systems are narrow by disease, modality, or task and apply a similar computation path to every case. Real intake is incomplete and temporal: symptoms, history, vitals, tests, imaging, consultation, diagnosis, and outcomes become available at different times. A safe system must decide what information is usable now, what to ask or inspect next, how urgent the case may be, where it should be reviewed, when to abstain, and how a clinician can audit or override it.

## Intended contribution

### Research Track

- Open-weight multi-disease medical multimodal model.
- Text, 2D medical imaging, 3D CT/MRI, structured clinical variables, and longitudinal records.
- Case-adaptive discrete, typed, acyclic computation graph that can be exported, replayed, measured, and intervened on.
- Controlled fixed-path, static-DAG, random-routing, and mixture/sparse-routing comparisons.
- Medical capability, efficiency, graph diversity, routing behavior, faithfulness, robustness, and calibration evidence.
- Flagship approximately 4B checkpoint with code, model card, evaluation scripts, and Hugging Face release after approval.
- 27B scaling only as a gated stretch objective.

### Innovation Track

- API-first AI Clinical Front Door for multi-disease, multi-system intake.
- Adaptive questions and next-information selection.
- Urgency, red-flag, care-pathway, and uncertainty/escalation outputs.
- Human confirmation, correction, reason capture, and audit history.
- Stable Model Gateway supporting mock, authorized external prototype, baseline, and team-model adapters.
- Provider replacement without client changes.

## Users and non-users

Primary research-prototype users are supervised triage nurses, intake staff, clinicians, evaluators, and researchers. It is not for unsupervised patient self-diagnosis, treatment decisions, prescribing, autonomous referral, discharge, or real-world clinical deployment without separate governance and validation.

## In scope

- Public, licensed, approved, synthetic, de-identified, or otherwise authorized data only.
- Patient-level split and strict temporal availability enforcement.
- Multi-disease evidence across representative disease systems selected through the data feasibility gate.
- Contract-first integration and reproducible experiment governance.
- Human-factor evaluation in simulation or appropriately approved settings.

## Out of scope unless separately approved

- Autonomous diagnosis or treatment.
- Live clinical use affecting patient care.
- External transfer of real or linkable patient data.
- Clinical claims beyond the evaluated population and setting.
- Training a 27B model before completion of every 4B gate.
- Claiming that an inspectable DAG is a clinical explanation without intervention evidence.
- Scraping or redistributing data/weights contrary to licenses.

## Deliverables

1. Academic submissions and presentations on the official schedule.
2. Versioned patient-journey, data, API, evaluation, safety, and approval contracts.
3. Reproducible Research Track code, manifests, baselines, ablations, and results.
4. Approximately 4B research release candidate, conditional on gates and compute.
5. AI Clinical Front Door integrated through the Model Gateway.
6. Safety case, audit evidence, human-review workflow, and end-to-end demonstration.
7. Final report, documentation, reproducibility package, and authorized public release.

## Success definition

Success is not simply a trained model or working UI. It requires the combined criteria in `docs/research/SUCCESS_CRITERIA.md` and `docs/innovation/ACCEPTANCE_CRITERIA.md`, verified through `docs/shared/EVALUATION_CONTRACT.md`, with no unresolved critical safety or data-integrity failure.

## Governance

- Official dates, accepted decisions, schemas, and contracts are source of truth.
- Major changes require a proposal containing rationale, alternatives, track impact, evaluation impact, schedule impact, migration, rollback, and human decision.
- Experiments are predeclared. Results, including failures, are retained.
- Reviewers remain independent and read-only for the change they review.
- Human approval gates are defined in `docs/shared/HUMAN_APPROVAL_POLICY.md`.

## Charter change control

Material changes to mission, team, flagship target, modalities, claims, clinical role, release plan, or success criteria require explicit approval and a new accepted Decision Log entry. Minor clarifications may be edited with reviewer confirmation and a referenced task.

