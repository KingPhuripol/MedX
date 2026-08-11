# Context

Topic-keyed notes from `DOC`-typed sources (precedence 3 plans and precedence 4 status
summaries), plus narrative framing from the track specifications. Under this project's authority
model, everything here **yields to** `decisions.md` and `constraints.md`.

---

## Specified versus implemented

- source: repository inspection (`research/`, `innovation/`, `shared/`, `scripts/`, `schemas/`, `tests/`, `data/`, `experiments/`); docs/project_management/WEEKLY_STATUS.md

**Almost nothing described in these documents is built.** What exists today:

- `scripts/` — verification harness and utilities: `bootstrap.sh`, `harness_lib.py`,
  `new_experiment.py`, `project_status.py`, `run_smoke_test.sh`, `temporal_leakage_audit.py`,
  `validate_manifest.py`, `verify_harness.py`.
- `schemas/` — ten JSON schemas: decision, evaluation-record, experiment-manifest,
  human-approval, model-api-request, model-api-response, official-deadlines, patient-journey,
  risk, task.
- `project_state/` — six machine state files: approvals, decisions, evaluations,
  official_deadlines, risks, tasks.
- `tests/fixtures/` — three fixtures: `model_api/request.json`, `model_api/response.json`,
  `patient_journey/valid.json`.
- `experiments/manifests/` — one manifest: `exp_0000_harness_smoke.json`.
- `research/`, `innovation/`, `shared/` — **each contains only a `README.md`. No source code.**
- `data/`, `checkpoints/`, `logs/`, `sources/` — **empty.**

Corroborated by WEEKLY_STATUS.md: "No integration result exists yet"; "no dataset/benchmark
shortlist has yet been accepted"; "pathway taxonomy and first simulated use-case set are not yet
accepted". Downstream planning must treat the model, Model Gateway, Front Door, DAG executor,
adapters, and all datasets as **not started**.

---

## Mission and dual-track structure

- source: docs/PROJECT_CHARTER.md; docs/DECISION_LOG.md (DEC-0001)

One Senior Project: *Case-Adaptive Medical Multimodal Foundation Model for Clinical Reasoning and
Care-Pathway Decision Support*. Charter status: Accepted baseline, effective 2026-08-11.

**Research Track** investigates whether case-specific, inspectable computation improves the
quality-efficiency-auditability trade-off of medical multimodal reasoning. **Innovation Track**
demonstrates the same contracts in an AI Clinical Front Door supporting early intake and care-pathway
decisions under incomplete information. The tracks share the Data Contract, Patient Journey Schema,
Model API Contract, Evaluation Contract, safety rules, and final demonstration.

## Problem framing

- source: docs/PROJECT_CHARTER.md

Many medical AI systems are narrow by disease, modality, or task and apply a similar computation
path to every case. Real intake is incomplete and temporal: symptoms, history, vitals, tests,
imaging, consultation, diagnosis, and outcomes become available at different times. A safe system
must decide what information is usable now, what to ask or inspect next, how urgent the case may
be, where it should be reviewed, when to abstain, and how a clinician can audit or override it.

## Research hypothesis and questions

- source: docs/research/RESEARCH_SPEC.md

Core hypothesis: medical cases should not all use an identical fixed computation path. A model
that compiles available, time-valid evidence and task context into a sparse, typed, inspectable
computation DAG may achieve a better quality-efficiency-auditability trade-off than fixed-path or
static-graph alternatives, especially under missing modalities and evolving longitudinal
information. **The project does not assume the hypothesis is true; the research program is
designed to falsify it early at small scale.**

- RQ1 Adaptation — does the executed graph vary meaningfully with case evidence, modality availability, temporal stage, complexity, and task rather than with noise or identifiers?
- RQ2 Controlled utility — under comparable budgets, does dynamic typed computation improve task quality, efficiency, robustness, or calibration relative to fixed-path, static-DAG, random-routing, and sparse/MoE baselines?
- RQ3 Faithfulness and inspectability — does the exported graph reflect computation that causally affects output rather than a decorative explanation?
- RQ4 Temporal and missing-modality robustness — can the model operate using only evidence available at the simulated decision time, update when new evidence arrives, and degrade safely?
- RQ5 Multi-disease generalization — does capability hold across representative disease systems, tasks, and unseen modality combinations?

## Target model family (working identifiers, not public claims)

- source: docs/research/RESEARCH_SPEC.md

`Medical-DAG-Base` (small architecture-validation model, expected 300M-700M class);
`Medical-DAG-4B` (flagship, approximately 4B, conditional on gates); `Medical-DAG-4B-Instruct`
(instruction/safety tuned derivative); `Medical-DAG-4B-FrontDoor` (contract-aligned downstream
adapter or tuned variant); `Medical-DAG-Large` (27B-class stretch, separate decision only).

## Development ladder (Research)

- source: docs/research/RESEARCH_SPEC.md; docs/research/TRAINING_SPEC.md

Stage A contract and synthetic executor -> Stage B fixed and static baselines -> Stage C small
adaptive model -> Stage D controlled ablation suite -> Stage E approximately 4B scaling (only
after G0-G4 and Training Spec approvals) -> Stage F public release and integration.

Training stage plan: executor validation -> fixed baseline -> soft/sparse routing pilot ->
discrete routing pilot -> controlled small experiments -> approximately 4B base stage ->
instruction/safety stage -> FrontDoor adaptation.

## Product framing and users

- source: docs/innovation/PRODUCT_SPEC.md

The AI Clinical Front Door is a supervised decision-support prototype that organizes progressively
available patient information, screens for urgency/red flags, recommends a care pathway for
clinician review, identifies the next useful information, represents uncertainty, and escalates
when safety or evidence is insufficient. **It does not diagnose, treat, prescribe, discharge, or
autonomously route a real patient.**

Users: supervised triage nurse or intake staff in a simulated/research workflow; clinician
reviewing recommendations and overrides; evaluator examining safety, agreement, timing, and
failure cases; researcher inspecting executed graph and model/provider behaviour. Patient-facing
direct use and production clinical deployment are outside this project unless separately governed.

Core screens: Intake; Adaptive interview; Clinical dashboard; DAG explorer; Human confirmation.

Architecture (specified, not built): `Client/UI -> Front Door API (+ Audit Store) -> Safety/Policy
Layer -> Model Gateway -> {Mock provider | Authorized external prototype provider | Reproducible
baseline provider | Team Medical-DAG provider}`.

## Team and ownership

- source: docs/PROJECT_CHARTER.md; docs/project_management/TEAM_OWNERSHIP.md

| Member | Student ID | Primary accountability | Track |
|---|---|---|---|
| Phurinat Polasa | 66070501042 | Program management and Research Lead | Cross-project / Research |
| Thanapol Popit | 66070501085 | Model architecture and development | Research |
| Jakkapat Bunjongruxsa | 66070501008 | Data governance and clinical workflow | Innovation / Shared |
| Thanrada Tungweerapornpong | 66070501025 | Safety and evaluation | Innovation / Shared |
| Supreeya Nuamkhayan | 66070501087 | Product and system development | Innovation |

**The advisor name is not recorded in the available project context.** Confirming the advisor and
submission evidence is an active P0 task; no system or agent may invent this information. See
WARN-02 in INGEST-CONFLICTS.md.

Workload controls: no owner marks their own safety-critical deliverable accepted without
independent review; each P0/P1 task has a named backup when absence would block an official
deliverable; PM reports overloaded ownership rather than silently absorbing work; no more than 40%
of active P0/P1 tasks to one member without an explicit short-term recovery plan.

## Phase plan

- source: docs/project_management/MASTER_PLAN.md (baseline 2026-08-11)

| Phase | Target window | Exit gate |
|---|---|---|
| 0. Governance and idea | 11-28 Aug 2026 | Project Idea ready and critical feasibility risks owned |
| 1. Proposal foundation | 29 Aug-2 Oct 2026 | Proposal Report accepted internally |
| 2. Proposal defense | 3-9 Oct 2026 | Proposal presentation delivered |
| 3. First evidence | 10 Oct-20 Nov 2026 | Evidence inventory supports progress report |
| 4. Progress gate | 21 Nov-15 Dec 2026 | Progress report and presentation delivered |
| 5. Architecture maturation | Jan-Feb 2027 | Small-model kill gates pass |
| 6. Flagship scaling | Feb-Mar 2027 | 4B candidate meets release-candidate gates |
| 7. Final evidence and release | Apr-May 2027 | Final integrated package and authorized release |

Critical paths — *Academic:* group status/advisor -> Project Idea -> CITI -> Proposal Report ->
Proposal Presentation -> validated technical evidence -> Progress Report -> Progress Presentation.
*Research:* data/license feasibility -> patient identity and temporal schema -> frozen split ->
fixed baseline -> small adaptive model -> graph validity and faithfulness -> controlled ablations
-> 4B approval -> 4B training/evaluation -> release candidate. *Innovation:* clinical problem
boundary -> patient journey and output contract -> mock gateway -> intake and confirmation flow ->
safety rules/audit -> external or baseline provider -> team-model adapter -> simulated evaluation
-> product release candidate. *Integration:* shared schemas -> contract fixtures -> mock provider
-> Research adapter -> cross-track contract tests -> end-to-end evidence -> independent
safety/integration verdict.

## Milestones

- source: docs/project_management/MILESTONES.md

Status vocabulary: `NOT_STARTED`, `IN_PROGRESS`, `AT_RISK`, `BLOCKED`, `COMPLETE`. `COMPLETE`
requires every exit criterion and referenced evidence.

| ID | Milestone | Due / target | Status |
|---|---|---|---|
| M0 | Group and repository control | 14 Aug 2026 (before 23:55 if unsubmitted) | **AT_RISK** — submission state and advisor not recorded |
| M1 | Project Idea | official 28 Aug 2026; advisor-ready 23 Aug | **IN_PROGRESS** |
| M2 | Ethics and proposal foundation | CITI 25 Sep (internal 18 Sep); Proposal 2 Oct (advisor-ready 27 Sep) | NOT_STARTED |
| M3 | Proposal Presentation | official 8-9 Oct 2026; advisor-ready 3 Oct | NOT_STARTED |
| M4 | First integrated evidence | evidence freeze 20 Nov 2026 | NOT_STARTED |
| M5 | Progress Report | official 4 Dec 2026; advisor-ready 29 Nov | NOT_STARTED |
| M6 | Progress Presentation | official 14-15 Dec 2026; advisor-ready 9 Dec | NOT_STARTED |
| M7 | Small-model architecture gate | planning target Feb 2027 | NOT_STARTED |
| M8 | Approximately 4B release candidate | planning target Mar-Apr 2027 | NOT_STARTED |
| M9 | Final integrated release | planning target May 2027, pending official dates | NOT_STARTED |

M1 kill condition: core dataset/ethics/compute assumptions have no feasible path and no approved
fallback. See WARN-03 for the M8 window divergence against the Master Plan.

## Active tasks

- source: docs/project_management/TASK_BOARD.md (readable view; `project_state/tasks.json` authoritative)

States: `BACKLOG`, `READY`, `IN_PROGRESS`, `BLOCKED`, `REVIEW`, `DONE`.

| ID | Pri | Owner | Status | Due | Task |
|---|---|---|---|---|---|
| TASK-0001 | P0 | Phurinat | IN_PROGRESS | 2026-08-12 | Confirm Group Application submission state |
| TASK-0002 | P0 | Phurinat | READY | 2026-08-14 | Finalize and submit Group Application if required |
| TASK-0003 | P1 | Phurinat | IN_PROGRESS | 2026-08-14 | Project Idea evidence outline |
| TASK-0004 | P1 | Phurinat | READY | 2026-08-17 | Literature and benchmark novelty matrix |
| TASK-0005 | P1 | Jakkapat | READY | 2026-08-17 | Data feasibility and ethics inventory |
| TASK-0006 | P1 | Supreeya | READY | 2026-08-17 | Clinical workflow and gateway feasibility |
| TASK-0007 | P1 | Phurinat | READY | 2026-08-18 | First integrated Project Idea draft |
| TASK-0008 | P1 | Thanrada | READY | 2026-08-21 | Safety and evaluation review of Project Idea |

Near-term P2: TASK-0009 (Thanapol, architecture v0 feasibility note and smallest falsifiable
prototype), TASK-0010 (Thanrada, frozen evaluation question/metric draft), TASK-0011 (all members,
CITI by 18 Sep), TASK-0012..0015 (proposal sections rough complete by 18 Sep).

Gate-governed backlog: freeze a public benchmark subset only after access/license and metric
feasibility checks; build fixed-path baseline before claiming an adaptive advantage; create small
dynamic DAG and graph export/replay before discrete scaling; implement mock gateway and contract
tests before connecting an external provider; start 4B preparation only after M7; consider 27B
only after M8 and a separate human decision.

Movement rules: `READY` requires resolved dependencies, named owner, due date, DoD, and evidence.
`DONE` requires the evidence; narrative confidence is insufficient. A blocked P0/P1 task is added
to Weekly Status and Risk Register the same day. Any material scope change creates a Decision Log
entry before dependent work continues.

## Risk register

- source: docs/project_management/RISK_REGISTER.md (precedence 4; `project_state/risks.json` machine state)

All ten risks are `OPEN`.

| ID | Risk | P | I | Owner |
|---|---|---|---|---|
| RISK-0001 | Group Application may be unsubmitted close to deadline | HIGH | CRITICAL | Phurinat |
| RISK-0002 | No dataset supports all desired modalities linked at patient level | HIGH | HIGH | Jakkapat |
| RISK-0003 | Temporal or patient-identity leakage invalidates results | MEDIUM | CRITICAL | Jakkapat |
| RISK-0004 | Compute cannot support stable approximately 4B training | HIGH | HIGH | Phurinat |
| RISK-0005 | Dynamic routing collapses or offers no controlled benefit | MEDIUM | HIGH | Thanapol |
| RISK-0006 | Research and Innovation contracts drift | MEDIUM | HIGH | Supreeya |
| RISK-0007 | Prototype gives false reassurance or under-triages critical cases | MEDIUM | CRITICAL | Thanrada |
| RISK-0008 | Academic writing absorbs technical critical-path capacity | HIGH | HIGH | Phurinat |
| RISK-0009 | External API causes privacy, cost, or provider lock-in | MEDIUM | CRITICAL | Supreeya |
| RISK-0010 | Public release violates data/model license or contains sensitive artifacts | LOW | CRITICAL | Jakkapat |

Immediate-escalation triggers: official deliverable inside T-5 without an advisor-ready version; a
critical dataset, advisor approval, ethics requirement, or compute path becomes unavailable;
temporal leakage or patient overlap touches reported results; safety testing shows false
reassurance, critical under-triage, or missing human approval; a Tier 4 run proposed without valid
gates and explicit approval; one member owns more than 40% of active P0/P1 tasks without recovery
support.

## Current status snapshot

- source: docs/project_management/WEEKLY_STATUS.md (week of 10-16 August 2026, precedence 4 — lowest authority)

**Project health: RED.** Reason: the Group Application deadline is three days away and
submission/advisor status is not recorded. Technical direction is defined, but evidence and
feasibility work has just started.

Next official deadline: Group Application 14 Aug 2026, 23:55 Asia/Bangkok (if not already
submitted); internal target 14 Aug 2026, 18:00.

This week's outcomes: (1) prove whether the Group Application is already submitted, otherwise
complete it; (2) produce the Project Idea evidence outline by 14 Aug; (3) start
literature/benchmark, data/ethics, clinical workflow/gateway, and safety/evaluation feasibility
work; (4) validate and commit the project Harness after human review.

Research blocker: no dataset/benchmark shortlist has yet been accepted. Innovation blocker:
pathway taxonomy and first simulated use-case set are not yet accepted.

Human decisions required this week: confirm Group Application submission evidence and advisor
identity; confirm ownership map and member availability; confirm whether the source schedule PDF
can be restored under `sources/` for visual transcription verification.

## Scope fallback ladder

- source: docs/project_management/MASTER_PLAN.md

If feasibility or time fails, preserve validity in this order: (1) keep one project, patient-level
and temporal integrity, safety, controlled comparisons, stable gateway, and end-to-end
demonstration; (2) reduce the number of datasets/tasks while retaining representative text,
imaging, and temporal evidence; (3) reduce training scale while preserving the approximately 4B
target as conditional and reporting the limitation honestly; (4) defer 3D breadth only through
approved scope change if data/access makes it infeasible, retaining the 3D interface and
limitation analysis; (5) remove 27B work entirely.

**Never preserve headline scale by sacrificing valid splits, baselines, safety, or
reproducibility.** Cut P4 before P3; a human decides any P0-P2 scope reduction.

## Out of scope unless separately approved

- source: docs/PROJECT_CHARTER.md

Autonomous diagnosis or treatment; live clinical use affecting patient care; external transfer of
real or linkable patient data; clinical claims beyond the evaluated population and setting;
training a 27B model before completion of every 4B gate; claiming that an inspectable DAG is a
clinical explanation without intervention evidence; scraping or redistributing data/weights
contrary to licenses.

## Governance and change control

- source: docs/PROJECT_CHARTER.md

Official dates, accepted decisions, schemas, and contracts are source of truth. Major changes
require a proposal containing rationale, alternatives, track impact, evaluation impact, schedule
impact, migration, rollback, and human decision. Experiments are predeclared; results including
failures are retained. Reviewers remain independent and read-only for the change they review.
Material changes to mission, team, flagship target, modalities, claims, clinical role, release
plan, or success criteria require explicit approval and a new accepted Decision Log entry.

## Weekly operating cycle

- source: docs/project_management/MASTER_PLAN.md

Monday: run `/project-status`, review next official deadline, risks, dependencies, workload, and
unfinished evidence. Select only tasks with owner, due date, dependency, definition of done, and
evidence. Midweek: resolve blockers and verify integration contracts. Friday: review evidence,
move valid tasks, record decisions/risks, update `WEEKLY_STATUS.md`. Any critical safety, data,
schedule, or compute trigger interrupts the cycle and is escalated immediately.
