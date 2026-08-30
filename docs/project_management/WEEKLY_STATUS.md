# Weekly Status

## Week of 31 August - 6 September 2026

**Project health:** RED
**Reason:** `scripts/project_status.py` derives health from open critical-impact risks and active P0
tasks, and four critical-impact risks plus three P0 tasks are still open. The derivation is correct and
was not adjusted to look better. What changed this week is that the record now matches reality and the
schedule is honest: **no task is overdue**, and P0/P1 concentration is back inside the capacity rule.

### Next official deadline

- **CITI: 25 Sep 2026 — 26 days out, immutable.** Then Proposal Report 2 Oct, Proposal Presentation 8-9 Oct.
- DL-0002 Project Idea was **submitted and advisor-signed on 28 Aug 2026**, within the immutable deadline.

### This week's outcomes

1. **M1 closed on evidence.** The submitted, advisor-signed PDF is archived at
   `sources/2026-08-28_project_idea_submitted_signed.pdf` with its SHA-256 and signature metadata
   recorded in `docs/academic/SUBMISSION_RECORD.md`. Signature: Sansiri Tarnpradab, 28 Aug 2026
   13:48:54 +07:00, read from the file, not inferred.
2. **The repository was holding the wrong document.** What was submitted is a different draft from the
   one in the repository: 5 references instead of 13, no in-text citations, all five Thai member names
   filled in, different wording throughout. `docs/academic/PROJECT_IDEA.md` is now a transcription of
   what was actually submitted, verified character-identical to the PDF (6,473 Thai characters, exact
   sequence match). `make idea-docx` reproduces the submitted text exactly.
3. The 13-reference draft is preserved as `docs/academic/PROPOSAL_SOURCE_DRAFT.md`. Its verified
   citation work is the starting capital for the Proposal Report, so none of it was discarded.
4. **DEC-0009 propagated everywhere (TASK-0017).** `CLAUDE.md`, `.claude/rules/research.md`, the
   charter, RESEARCH_SPEC, SUCCESS_CRITERIA, TRAINING_SPEC, HUMAN_APPROVAL_POLICY, MASTER_PLAN,
   MILESTONES, TASK_BOARD and the `.planning/` artifacts now all name 27B. The MASTER_PLAN scope
   fallback ladder was rewritten rather than search-replaced: its old rung 5, "remove 27B work
   entirely", was incoherent once 27B became the flagship.
5. **G0 moved from one of five closed to four of five.** `project_state/contract_versions.json`
   registers all five shared contracts at 1.0.0; `HUMAN_APPROVAL_POLICY.md` carries a version header;
   `schemas/dataset-feasibility.schema.json` and `project_state/dataset_feasibility.json` exist. Both
   new state files are registered in `scripts/verify_harness.py` and were negative-tested — an invalid
   verdict value makes the harness fail, so the checks are real. Harness: 236 → **241 checks, passing**.
6. **Schedule re-planned honestly.** Eight tasks that had silently passed their due dates were re-dated
   against real capacity. TASK-0004 moved from Phurinat to Thanapol; TASK-0005 and TASK-0011 raised to
   P0. Workload concentration: **50% → 33%**, inside the 40% rule.

### Not done, and owed

- **TASK-0005 data feasibility is seeded, not answered.** All six candidates are `UNDER_REVIEW` with
  every dimension `UNVERIFIED` and no evidence cited. The structure to record findings is not a
  finding. This is the single biggest blocker to both G0 and the Proposal's data section.
- **TASK-0004** novelty matrix, search protocol and baseline shortlist still do not exist. Required for DL-0004.
- **TASK-0006** clinical workflow and gateway feasibility, still not started.
- **TASK-0018** no compute estimate for 27B exists.
- **No implementation code exists.** `research/`, `innovation/` and `shared/` contain only READMEs.
  Phase 2 turns the contracts into runnable code and has not started; GOV-01 requires the runtime
  decision to be recorded before that code is written.
- The Group Application receipt is still unarchived and the advisor contact path unrecorded (TASK-0001).

### CITI is a data blocker, not just an academic one

MIMIC-family data is reached through PhysioNet credentialed access, which requires completed CITI
training. If that holds on verification, TASK-0011 is a prerequisite for the access dimension of
TASK-0005 — so a late CITI delays the data path, not merely a certificate. TASK-0011 is now P0 and
started. The licence, patient-linkage, temporal-validity and modality-coverage dimensions do not
depend on CITI and must proceed now regardless.

### What the 27B propagation did not settle

It made the documents consistent with an accepted decision. It did not establish that the compute
exists. Approximately 27B is roughly a sevenfold increase over the withdrawn target, against a register
that already rated 4B feasibility HIGH. RISK-0004 stays CRITICAL, and rungs 3 and 5 of the rewritten
fallback ladder — deliver a smaller model reported at its true scale, or drop the flagship run — remain
live until TASK-0018 produces numbers.

### Top risks

1. RISK-0004 compute feasibility at 27B — CRITICAL, no estimate exists.
2. RISK-0002 multimodal data feasibility — no dataset accepted, no dimension verified.
3. RISK-0008 academic writing absorbing technical capacity — three immutable deadlines in six weeks
   alongside the first real implementation work, which has not begun.
4. RISK-0003 temporal or patient-identity leakage.

### Human decisions required this week

1. **TASK-0008** — did a member who did not write the Project Idea review it before submission? The
   advisor's signature is approval to submit, not that internal review (Phase 1 CONTEXT D-03). If it did
   not happen, the criterion was not met and the review now runs retrospectively.
2. **Group Application receipt** — retrievable or not? If not, record that no documentary evidence
   exists rather than leaving M0 contradicting itself.
3. **Phase 2 start** — the runtime and framework decision (GOV-01) must be an accepted Decision Log
   entry *before* gateway or prototype code is written. Nothing can be implemented until it is recorded.

### Next update protocol

Replace this section at weekly review with completed evidence, carry-over reasons, changed risks,
workload concerns, decisions, and the next seven-day plan. Do not report a task complete without its
referenced evidence.
