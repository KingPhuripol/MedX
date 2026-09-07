# Task Board

Machine state is authoritative for automation: `project_state/tasks.json`. This board is the readable working view. Valid states: `BACKLOG`, `READY`, `IN_PROGRESS`, `BLOCKED`, `REVIEW`, `DONE`.

> ⚠️ **This board is behind `project_state/tasks.json` as of 2026-09-02.** The machine record now
> holds TASK-0001…TASK-0025; this board shows fifteen and several statuses, owners and due dates
> here contradict it. The TASK-0004 row was corrected on 2026-09-02 because that task was being
> worked; **the rest has not been reconciled.** Read `project_state/tasks.json` for anything you
> intend to act on. Per DEC-0008 the machine record wins, and a readable view that disagrees with it
> is worse than no readable view.

## Active P0/P1

| ID | Pri | Owner | Track | Status | Due | Task | Definition of done / evidence |
|---|---|---|---|---|---|---|---|
| TASK-0001 | P0 | Phurinat | PM | IN_PROGRESS | 2026-08-12 | Confirm Group Application submission state | Submission confirmed by owner 11 Aug; **advisor identity and contact path still unrecorded** |
| TASK-0002 | P0 | Phurinat | PM | REVIEW | 2026-08-14 | Finalize and submit Group Application if required | Submitted per owner confirmation; **signed form and receipt not archived**, so definition of done is unmet |
| TASK-0003 | P1 | Phurinat | Cross-track | IN_PROGRESS | 2026-08-14 | Project Idea evidence outline | One integrated outline maps every claim to method, feasibility evidence, evaluation, owner, and reference need |
| TASK-0004 | P1 | Thanapol | Research | READY | 2026-09-18 | Build literature and benchmark novelty matrix | Primary-source matrix over medical multimodal, dynamic/sparse computation, graph faithfulness and Clinical Front Door work; public benchmark access, licence and reproducibility verified. Evidence: `docs/research/RELATED_WORK.md`, `project_state/literature.json`. Reassigned from Phurinat 2026-08-30 under the 40% capacity rule |
| TASK-0005 | P1 | Jakkapat | Shared/Data | READY | 2026-08-17 | Data feasibility and ethics inventory | Candidate datasets, modalities, patient linkage, temporal fields, access, license, CITI/ethics path, fallback |
| TASK-0006 | P1 | Supreeya | Innovation | READY | 2026-08-17 | Clinical workflow and gateway feasibility | Workflow, users, boundaries, mock flow, API fixture, provider isolation, audit events reviewed |
| TASK-0007 | P1 | Phurinat | Cross-track | READY | 2026-08-18 | First integrated Project Idea draft | 2-4 pages plus references; internally consistent with source-of-truth contracts |
| TASK-0008 | P1 | Thanrada | Shared/Evaluation | READY | 2026-08-21 | Safety and evaluation review of Project Idea | Safety claims, primary metrics, failure modes, under-triage emphasis, uncertainty and human review assessed |

## Near-term P2

| ID | Owner | Due | Task | Dependency |
|---|---|---|---|---|
| TASK-0009 | Thanapol | 2026-08-20 | Architecture v0 feasibility note and smallest falsifiable prototype | TASK-0004, TASK-0005 |
| TASK-0010 | Thanrada | 2026-08-20 | Frozen evaluation question/metric draft | TASK-0004, TASK-0006 |
| TASK-0011 | All members | 2026-09-18 | Complete CITI and submit evidence to PM | Course access/instructions |
| TASK-0012 | Phurinat | 2026-09-18 | Proposal Research sections rough complete | M1 decisions |
| TASK-0013 | Supreeya | 2026-09-18 | Proposal Innovation/system sections rough complete | M1 decisions |
| TASK-0014 | Jakkapat | 2026-09-18 | Proposal data/governance sections rough complete | data inventory |
| TASK-0015 | Thanrada | 2026-09-18 | Proposal evaluation/safety sections rough complete | evaluation contract |

## Backlog governed by gates

- Freeze a public benchmark subset only after access/license and metric feasibility checks.
- Build fixed-path baseline before claiming an adaptive advantage.
- Create small dynamic DAG and graph export/replay before discrete scaling.
- Implement mock gateway and contract tests before connecting an external provider.
- Start flagship 27B preparation only after M7.
- Consider 27B only after M8 and a separate human decision.

## Movement rules

- `READY` requires resolved dependencies, named owner, due date, DoD, and evidence.
- `DONE` requires the evidence; narrative confidence is insufficient.
- A blocked P0/P1 task is added to Weekly Status and Risk Register the same day.
- Any material scope change creates a Decision Log entry before dependent work continues.

