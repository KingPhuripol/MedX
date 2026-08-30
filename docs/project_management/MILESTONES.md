# Milestones

Milestone status uses `NOT_STARTED`, `IN_PROGRESS`, `AT_RISK`, `BLOCKED`, or `COMPLETE`. `COMPLETE` requires every exit criterion and referenced evidence.

## M0 - Group and repository control

- **Due:** 14 Aug 2026, before 23:55 if application is unsubmitted
- **Status:** IN_PROGRESS — submission and advisor are settled; documentary evidence is not
- **Exit criteria:** group application status proven; advisor identity recorded; repository Harness validated; ownership acknowledged.
- **Evidence:** submission confirmed by the project owner on 11 Aug 2026 (RISK-0001 closed); advisor recorded as ดร.สัญญ์สิริ ธารประดับ, independently corroborated on 30 Aug 2026 by the digital signature in the submitted Project Idea (Sansiri Tarnpradab, 28 Aug 2026 13:48:54 +07:00) — see `docs/academic/SUBMISSION_RECORD.md`; `make verify` passing.
- **Still open:** the submission receipt is not archived and the advisor contact path is not recorded (TASK-0001). The milestone is not marked COMPLETE on an owner's recollection alone.

## M1 - Project Idea

- **Official due:** 28 Aug 2026
- **Internal advisor-ready:** 23 Aug 2026
- **Status:** COMPLETE — submitted and signed by the advisor on 28 Aug 2026, within the immutable deadline
- **Evidence:** `sources/2026-08-28_project_idea_submitted_signed.pdf` (SHA-256 `667271ff7e154a2fa5bf83985daa9241aab7790b909d74135c21443453b28d89`), recorded in `docs/academic/SUBMISSION_RECORD.md`; transcription verified character-identical at `docs/academic/PROJECT_IDEA.md`.
- **Carried forward, not resolved:** the submitted version has 5 references and no in-text citations, so claims C-01 and C-02 stand without attribution (`docs/academic/PROJECT_IDEA_CLAIMS.md`). The pre-submission review by a member who did not write the document did not happen (Phase 1 CONTEXT D-03); it now runs retrospectively as TASK-0008. Both must close before DL-0004.
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

