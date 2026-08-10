---
name: proposal-readiness
description: Audit the Proposal Report and Proposal Presentation for completeness, evidence, feasibility, consistency, schedule, safety, and advisor-ready quality against immutable Semester 1 dates.
argument-hint: [report-or-deck-path]
---

# Proposal Readiness Workflow

Target: `$ARGUMENTS`.

Official Proposal Report deadline is 2 Oct 2026. Advisor-ready target is 27 Sep; freeze 29 Sep; readiness audit 1 Oct. Presentation is 8-9 Oct, planned against 8 Oct; advisor-ready 3 Oct; freeze 5 Oct; final rehearsal 7 Oct.

1. Read official schedule, Project Charter, Decision Log, all Source-of-Truth specs/contracts, milestones/tasks/risks/ownership, and the target/report requirements.
2. Verify title, one-project/two-track framing, five members/roles, advisor fact status, and dates are consistent.
3. Map required sections: problem/motivation, related work/novelty, RQs/hypotheses, model architecture, data/access/ethics, training/compute, benchmark/statistics, Clinical Front Door workflow/system, safety/human review, integration, scope/non-scope, deliverables, success/kill gates, schedule/ownership, risks/fallbacks, references.
4. Check every factual external claim has a verified source and every project result is either valid evidence or clearly labeled planned/hypothesis. Do not fabricate preliminary results.
5. Test feasibility: public/authorized data path, patient linkage/temporal fields, baseline and 4B compute path, smallest falsifiable prototype, stable gateway/mock path, evaluation/safety reviewers, and 27B stretch boundary.
6. Check claims: no autonomous diagnosis/treatment/deployment, no graph-as-reasoning claim without intervention, no universal multi-disease/3D/longitudinal capability beyond plan/evidence.
7. Check internal consistency of API fields, taxonomy, metrics, model scale, modalities, gates, timeline, and task owners.
8. For presentation, require claim-evidence story, readable diagrams, time budget, limitations, demo/backup, rehearsed Q&A, and accessibility.
9. Obtain read-only safety and integration reviews for final candidate.
10. Verdict `NOT_READY`, `CONDITIONALLY_READY`, or `ADVISOR_READY`; list blockers by deadline/owner/evidence. Do not submit or send externally.

Return days/buffer, coverage matrix, evidence/citation gaps, feasibility threats, consistency/claim/safety findings, report/deck/demo verdict, owners/dates, advisor questions, and exact next actions.

