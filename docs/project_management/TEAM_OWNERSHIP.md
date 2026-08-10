# Team Ownership

Ownership is accountability, not exclusive implementation. Every critical artifact has an owner and reviewer. Member nicknames from earlier discussion may be used conversationally, but repository records use full names.

| Area | Accountable owner | Primary responsibilities | Required reviewer/backup |
|---|---|---|---|
| Program, scope, schedule, academic integration | Phurinat Polasa | milestones, dependencies, advisor windows, research direction, writing integration, compute governance, release coordination | Thanrada for evidence/safety; Supreeya for product feasibility |
| Model architecture and training implementation | Thanapol Popit | graph compiler, typed operators, routing, executor, training pipeline, checkpoint/recovery, scaling, ablations | Phurinat for research alignment; Thanrada for independent evaluation |
| Data and clinical workflow | Jakkapat Bunjongruxsa | patient journey, data access/license, temporal alignment, patient split, validation, leakage audit, workflow cases | Thanrada for evaluation leakage; Supreeya for product schema |
| Safety and evaluation | Thanrada Tungweerapornpong | evaluation protocol, urgency/routing labels, safety metrics, failure analysis, statistics, simulated clinician evaluation | Phurinat for study questions; clinical domain reviewer when available |
| System and product | Supreeya Nuamkhayan | frontend/backend, Model Gateway, adapters, database, dashboard, DAG Explorer, audit log, deployment/demo | Jakkapat for data contract; Thanrada for safety; Thanapol for model adapter |

## RACI for joint artifacts

| Artifact | A | R | C | I |
|---|---|---|---|---|
| Project Idea / Proposal / Progress Report | Phurinat | all section owners | advisor | all members |
| Research Spec / Benchmark Contract | Phurinat | Phurinat, Thanapol, Thanrada | Jakkapat | Supreeya |
| Architecture / Training Spec | Thanapol | Thanapol | Phurinat, Thanrada | all members |
| Data Contract / Patient Journey | Jakkapat | Jakkapat | Thanrada, Supreeya, Thanapol | Phurinat |
| Product / Clinical Workflow | Supreeya | Supreeya, Jakkapat | Thanrada | Phurinat, Thanapol |
| Safety / Evaluation Contract | Thanrada | Thanrada | Jakkapat, Phurinat, Supreeya | Thanapol |
| Model API Contract | Supreeya | Supreeya, Thanapol | Jakkapat, Thanrada | Phurinat |
| Hugging Face release | Phurinat | Thanapol, documentation owner | Jakkapat for licensing; Thanrada for safety | all members |

## Workload controls

- No owner marks their own safety-critical deliverable accepted without independent review.
- Each P0/P1 task has a named backup when absence would block an official deliverable.
- PM reports overloaded ownership instead of silently absorbing work.
- Changes to this map require all affected members to acknowledge the change.

