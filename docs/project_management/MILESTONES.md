# Milestones

Milestone status uses `NOT_STARTED`, `IN_PROGRESS`, `AT_RISK`, `BLOCKED`, or `COMPLETE`. `COMPLETE` requires every exit criterion and referenced evidence.

## M0 - Group and repository control

- **Due:** 14 Aug 2026, before 23:55 if application is unsubmitted
- **Status:** COMPLETE on the owner's confirmation, **not on documentary evidence**
- **Exit criteria:** group application status proven; advisor identity recorded; repository Harness validated; ownership acknowledged.
- **Evidence:** submission confirmed by the project owner on 11 Aug 2026 (RISK-0001 closed); advisor recorded as ดร.สัญญ์สิริ ธารประดับ, independently corroborated on 30 Aug 2026 by the digital signature in the submitted Project Idea (Sansiri Tarnpradab, 28 Aug 2026 13:48:54 +07:00) — see `docs/academic/SUBMISSION_RECORD.md`; `make verify` passing.
- **Documented limitation — read this before citing M0 as evidenced:** the Group Application receipt was never archived and was confirmed unrecoverable by the project owner on 30 Aug 2026. The submission rests on the owner's confirmation of 11 Aug 2026 and nothing else. The milestone is closed because no action can now recover the evidence, not because the evidence exists. The advisor contact path is still unrecorded. RISK-0012 is raised so the remaining deadlines capture their evidence at submission time, as was done for the Project Idea.

## M1 - Project Idea

- **Official due:** 28 Aug 2026
- **Internal advisor-ready:** 23 Aug 2026
- **Status:** COMPLETE — submitted and signed by the advisor on 28 Aug 2026, within the immutable deadline
- **Evidence:** `sources/2026-08-28_project_idea_submitted_signed.pdf` (SHA-256 `667271ff7e154a2fa5bf83985daa9241aab7790b909d74135c21443453b28d89`), recorded in `docs/academic/SUBMISSION_RECORD.md`; transcription verified character-identical at `docs/academic/PROJECT_IDEA.md`.
- **Carried forward, not resolved:**
  1. The submitted version has 5 references and no in-text citations, so claims C-01 and C-02 stand without attribution (`docs/academic/PROJECT_IDEA_CLAIMS.md`).
  2. **Phase 1 CONTEXT D-03 was NOT MET** — confirmed 30 Aug 2026: the document was written and submitted by one person with no review by a non-author. The advisor signature is approval to submit, not that review. TASK-0008 now runs retrospectively; RISK-0011 records the systemic form.
  3. The document claims 3D CT support, but the feasibility survey found no CT dataset among the original candidates; CT-RATE was added as DS-0007 on 30 Aug to close the gap, at the cost of a CC-BY-NC-SA licence.
  4. The document promises an open-weight model, but every candidate dataset except VQA-RAD is non-commercial (RISK-0010).

  All four must be addressed in the Proposal Report. The submitted document is not edited retrospectively.
- **Exit criteria:** 2-4 pages plus references; one-project/two-track framing; problem, contribution, scope, data feasibility, methods, evaluation, safety, expected outputs, risks, and references consistent with contracts.
- **Kill condition:** core dataset/ethics/compute assumptions have no feasible path and no approved fallback.

## M2 - Ethics and proposal foundation

- **CITI due:** 25 Sep 2026; internal completion 18 Sep
- **Proposal due:** 2 Oct 2026; advisor-ready 27 Sep
- **Status:** NOT_STARTED
- **Exit criteria:** all CITI evidence; integrated proposal; architecture and training plan; benchmark and success contracts; product workflow; safety and human-approval plan; credible schedule and fallback ladder.

## M3 - Proposal Presentation

- **Official window:** 8-9 Oct 2026
- **Internal advisor-ready:** 3 Oct 2026
- **Status:** NOT_STARTED
- **Exit criteria:** timed presentation; claims map to planned evidence; readable architecture and workflow; limitations; team ownership; demo or mock; backup assets; rehearsed Q&A.

## M4 - First integrated evidence

- **Evidence freeze:** 20 Nov 2026
- **Status:** NOT_STARTED
- **Research exit:** licensed data inventory; patient-level split; temporal audit; fixed baseline; small adaptive prototype; graph export/replay; preliminary diversity/collapse metrics.
- **Innovation exit:** contract-tested mock gateway; adaptive intake; urgency/pathway/next-information schema; human confirmation; audit log; safe provider failure behavior.
- **Integration exit:** same fixtures pass mock and Research adapters; no unresolved critical safety finding.

## M5 - Progress Report

- **Official due:** 4 Dec 2026
- **Internal advisor-ready:** 29 Nov 2026
- **Status:** NOT_STARTED
- **Exit criteria:** reproducible evidence inventory; methods and deviations; results including failures; updated risks/schedule; integration and safety evidence; next-semester plan.

## M6 - Progress Presentation

- **Official window:** 14-15 Dec 2026
- **Internal advisor-ready:** 9 Dec 2026
- **Status:** NOT_STARTED
- **Exit criteria:** timed evidence-first presentation; functioning primary and backup demo; honest limitations; next gates; prepared Q&A.

## M7 - Small-model architecture gate

- **Planning target:** Feb 2027
- **Status:** NOT_STARTED
- **Exit criteria:** case-dependent graphs, no collapse, competitive controlled results, faithfulness interventions, missing-modality robustness, replay, stable training, and an approved 27B plan.

## M8 - Approximately 27B release candidate

- **Planning target:** Mar-Apr 2027
- **Status:** NOT_STARTED
- **Exit criteria:** approved Tier 4 runs, frozen evaluation, reproducible checkpoint, data/license clearance, safety and limitations, model card, inference path, and integration adapter.

## M9 - Final integrated release

- **Planning target:** May 2027 pending official dates
- **Status:** NOT_STARTED
- **Exit criteria:** final report/presentation, end-to-end Clinical Front Door, independent safety/integration verdicts, archived evidence, reproducibility package, and human-approved release/publishing.

