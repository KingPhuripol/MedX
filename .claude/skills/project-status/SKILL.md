---
name: project-status
description: Produce and optionally synchronize an evidence-backed Senior Project status using official deadlines, milestones, tasks, risks, workload, approvals, and both tracks. Use for status checks, weekly planning, or deadline risk.
argument-hint: [optional-focus]
---

# Project Status Workflow

Focus, if supplied: `$ARGUMENTS`.

1. Read `project_state/official_deadlines.json`, the PM Source-of-Truth documents, Project Charter, Decision Log, and current machine tasks/risks/decisions.
2. Use Asia/Bangkok and the actual current date. For presentation windows, plan against the earliest date.
3. Identify the next official deadline, days remaining, active internal buffer, and missing deliverable evidence.
4. Evaluate milestone exit criteria; do not infer completion from status labels alone.
5. Trace the cross-track critical path and blocked dependencies.
6. Check P0/P1 ownership, overdue dates, evidence gaps, and whether one member owns more than 40% of active P0/P1 tasks.
7. Review open risks, triggers, mitigations, approvals, data/safety/integration failures, and architecture/scale gates.
8. Assign health:
   - `GREEN`: no milestone-threatening blocker.
   - `YELLOW`: credible risk needing action.
   - `RED`: critical path, official deliverable, data integrity, or safety is at risk.
9. If asked to update status, synchronize `WEEKLY_STATUS.md`, `TASK_BOARD.md`, `RISK_REGISTER.md`, and machine state. Never move an official deadline or fabricate missing evidence.
10. Run `python3 scripts/verify_harness.py` after edits.

Output exactly these sections:

```text
PROJECT HEALTH:
AS OF / TIMEZONE:
NEXT OFFICIAL DEADLINE:
DAYS REMAINING / ACTIVE BUFFER:
MILESTONE CONFIDENCE:
UNMET EXIT CRITERIA:
CRITICAL PATH:
P0/P1 TASKS:
RESEARCH:
INNOVATION:
DATA / EVALUATION / SAFETY / INTEGRATION:
BLOCKERS:
TOP RISKS AND TRIGGERS:
OVERDUE / WORKLOAD CONCERNS:
HUMAN DECISIONS OR APPROVALS:
NEXT 7-DAY PLAN:
STATE CHANGES AND VERIFICATION:
```

State unknown submission/advisor/result information as unknown and create an action; never fill it in.

