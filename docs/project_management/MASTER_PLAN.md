# PM Master Plan

**Baseline date:** 2026-08-11  
**Planning horizon:** Semester 1 academic gates plus full-project delivery  
**Planning unit:** evidence-backed milestone, not activity volume

## Execution strategy

Run the academic deliverables and technical program as one dependency network. The Project Idea and Proposal must lock the problem, feasibility, novelty, contracts, evaluation, safety, and fallback plan before expensive implementation. Progress must show reproducible evidence, not only a UI or training loss.

## Phases

| Phase | Target window | Research outcome | Innovation outcome | Exit gate |
|---|---|---|---|---|
| 0. Governance and idea | 11-28 Aug 2026 | Research questions, architecture hypothesis, data/benchmark feasibility | Clinical workflow, product boundary, gateway/API v1 | Project Idea ready and critical feasibility risks owned |
| 1. Proposal foundation | 29 Aug-2 Oct 2026 | baseline plan, data pipeline design, small-model design, evaluation protocol | clickable/mock flow, safety architecture, acceptance plan | Proposal Report accepted internally |
| 2. Proposal defense | 3-9 Oct 2026 | defensible novelty and controlled-comparison story | defensible clinical value and human-approval story | Proposal presentation delivered |
| 3. First evidence | 10 Oct-20 Nov 2026 | patient split, temporal audit, fixed baseline, small dynamic DAG, export/replay | contract-tested gateway, intake flow, mock/external adapter, audit log | Evidence inventory supports progress report |
| 4. Progress gate | 21 Nov-15 Dec 2026 | preliminary controlled results and failure analysis | product alpha and cross-track integration evidence | Progress report and presentation delivered |
| 5. Architecture maturation | Jan-Feb 2027 | discrete/typed DAG, faithfulness, robustness, multi-modality expansion | team-model adapter and multimodal workflow | Small-model kill gates pass |
| 6. Flagship scaling | Feb-Mar 2027 | approved approximately 27B training and evaluation | product beta on frozen contract | 27B candidate meets release-candidate gates |
| 7. Final evidence and release | Apr-May 2027 | result freeze, reproducibility, model card, approved HF staging | clinician/usability evaluation, backup demo, documentation | final integrated package and authorized release |

Dates after Semester 1 are planning assumptions until official faculty dates are received. They are not represented as official deadlines.

## Critical paths

### Academic

Group status/advisor -> Project Idea -> CITI -> Proposal Report -> Proposal Presentation -> validated technical evidence -> Progress Report -> Progress Presentation.

### Research

Data/license feasibility -> patient identity and temporal schema -> frozen split -> fixed baseline -> small adaptive model -> graph validity and faithfulness -> controlled ablations -> compute estimate -> 27B approval -> 27B training/evaluation -> release candidate.

### Innovation

Clinical problem boundary -> patient journey and output contract -> mock gateway -> intake and confirmation flow -> safety rules/audit -> external or baseline provider -> team-model adapter -> simulated evaluation -> product release candidate.

### Integration

Shared schemas -> contract fixtures -> mock provider -> Research adapter -> cross-track contract tests -> end-to-end evidence -> independent safety/integration verdict.

## Weekly operating cycle

1. Monday: run `/project-status`, review next official deadline, risks, dependencies, workload, and unfinished evidence.
2. Select only tasks with owner, due date, dependency, definition of done, and evidence.
3. Midweek: resolve blockers and verify integration contracts.
4. Friday: review evidence, move valid tasks, record decisions/risks, and update `WEEKLY_STATUS.md`.
5. Any critical safety, data, schedule, or compute trigger interrupts the cycle and is escalated immediately.

## Capacity rules

- Do not allocate more than 40% of active P0/P1 tasks to one member without an explicit short-term recovery plan.
- Every critical responsibility has a reviewer or backup.
- Protect advisor review windows; do not plan first completion on an official deadline.
- Cut P4 before P3. A human decides any P0-P2 scope reduction.

## Scope fallback ladder

If feasibility or time fails, preserve validity in this order:

1. Keep one project, patient-level/temporal integrity, safety, controlled comparisons, stable gateway, and end-to-end demonstration.
2. Reduce the number of datasets/tasks while retaining representative text, imaging, and temporal evidence.
3. Reduce the flagship training scale below approximately 27B. The delivered model is named and reported at its true scale, and the shortfall is stated plainly in the report, the model card, and any release. It is never relabelled as approximately 27B.
4. Defer 3D breadth only through approved scope change if data/access makes it infeasible; retain the 3D interface and limitation analysis.
5. Drop the flagship training run entirely. Deliver the validated small-model architecture evidence and the integrated Clinical Front Door, and report that the scaling gate was not reached and why.

Never preserve headline scale by sacrificing valid splits, baselines, safety, or reproducibility. RISK-0004 is CRITICAL: DEC-0009 records the owner's direction on scale, not the existence of the compute. Rungs 3 and 5 are live possibilities until TASK-0018 produces an estimate.

