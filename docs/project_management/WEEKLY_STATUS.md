# Weekly Status

## Week of 10-16 August 2026

**Project health:** RED  
**Reason:** Updated 11 Aug. The Group Application is submitted per owner confirmation, so the immediate deadline exposure is gone and RISK-0001 is closed. Health stays RED because `scripts/project_status.py` derives it from open critical-impact risks and active P0 tasks, and both still hold: four critical risks are open (RISK-0003, RISK-0007, RISK-0009, RISK-0010) and two P0 tasks remain active. Beyond that, the advisor identity is unrecorded, the submission receipt is not archived, nothing is implemented beyond the verification harness, and feasibility work has just started.

### Next official deadline

- Project Idea: 28 Aug 2026, Asia/Bangkok. 2-4 pages plus references.
- Group Application (14 Aug 2026, 23:55): submitted per owner confirmation on 11 Aug. Receipt not yet archived.

### This week's outcomes

1. ~~Prove whether the Group Application is already submitted; otherwise complete it.~~ Done 11 Aug — submitted per owner confirmation. Remaining: archive the receipt and record the advisor.
2. Produce the Project Idea evidence outline by 14 Aug.
3. Start literature/benchmark, data/ethics, clinical workflow/gateway, and safety/evaluation feasibility work.
4. Validate and commit the project Harness after human review.

### Research

- Direction: approximately 4B open-weight multi-disease model; typed case-adaptive DAG; 27B stretch.
- Current gate: research question, comparable baseline, data feasibility, and smallest falsifiable prototype.
- Blocker: no dataset/benchmark shortlist has yet been accepted.

### Innovation

- Direction: API-first Clinical Front Door with mock/external prototype providers behind a stable gateway.
- Current gate: clinical workflow, versioned API fixture, safety boundaries, and audit events.
- Blocker: pathway taxonomy and first simulated use-case set are not yet accepted.

### Data, safety, and integration

- Patient-level splits and `available_at_time` are locked policies.
- External APIs default to synthetic fixtures; real-patient transfer is prohibited without recorded approval.
- No integration result exists yet; mock and team adapters must share contract fixtures.

### Top risks

1. RISK-0002 multimodal data feasibility.
2. RISK-0008 compressed academic writing windows.
3. RISK-0004 4B compute feasibility.
4. RISK-0003 temporal or patient-identity leakage.

RISK-0001 (Group Application state) closed 11 Aug on owner confirmation of submission.

### Human decisions required this week

- Archive the Group Application submission receipt and record the advisor identity. Submission itself is confirmed; the supporting evidence is not yet filed.
- Confirm ownership map and member availability.
- Confirm whether the source schedule PDF can be restored under `sources/` for visual transcription verification.

### Next update protocol

Replace this section at weekly review with completed evidence, carry-over reasons, changed risks, workload concerns, decisions, and the next seven-day plan. Do not report a task complete without its referenced evidence.
