# Synthesis Summary

Entry point for `gsd-roadmapper`. Produced by `gsd-doc-synthesizer` from 23 per-doc
classifications under manifest-authoritative precedence.

- Mode: `new` (no existing PROJECT.md, REQUIREMENTS.md, ROADMAP.md, or STATE.md)
- Precedence source: `.planning/ingest-manifest.yaml` (`manifest_override: true` on all 23 docs)
- Classifications: `.planning/intel/classifications/`

---

## Doc counts

| Type | Count |
|---|---:|
| ADR | 2 |
| SPEC | 14 |
| DOC | 7 |
| **Total** | **23** |

| Precedence tier | Meaning | Count | Locked |
|---:|---|---:|---:|
| 0 | Accepted decisions and immutable schedule | 2 | 2 |
| 1 | Shared contracts and safety rules | 6 | 6 |
| 2 | Track specifications (Research and Innovation, equal authority) | 8 | 0 |
| 3 | Plans | 5 | 0 |
| 4 | Status summaries | 2 | 0 |

Locked total: **8**. UNKNOWN or low-confidence: **0**. Medium-confidence: 1
(`docs/innovation/PRODUCT_SPEC.md`, superseded by manifest override — see INFO-01).

Cross-ref graph: 10 doc-to-doc edges, max depth 2, **acyclic** (DFS three-colour marking; 50-depth
cap not approached).

---

## Decisions

**8 locked decisions**, all precedence 0, none proposed, none superseded.
File: `.planning/intel/decisions.md`

- DEC-0001 One project, two tracks — docs/DECISION_LOG.md
- DEC-0002 Flagship approximately 4B; 27B is stretch — docs/DECISION_LOG.md
- DEC-0003 Stable Model Gateway — docs/DECISION_LOG.md
- DEC-0004 Patient-level temporal integrity — docs/DECISION_LOG.md
- DEC-0005 Decision support with mandatory human review — docs/DECISION_LOG.md
- DEC-0006 Restrict real-patient data from external APIs — docs/DECISION_LOG.md
- DEC-0007 Official Semester 1 schedule is immutable — docs/DECISION_LOG.md
- Official Semester 1 deadlines are immutable (schedule lock) — docs/project_management/OFFICIAL_DEADLINES.md

These override every SPEC, plan, and status summary. None may be auto-overridden downstream.

---

## Requirements

**23 requirements** extracted. File: `.planning/intel/requirements.md`

*Innovation acceptance gates (8)* — REQ-A0-contract-prototype, REQ-A1-usable-supervised-flow,
REQ-A2-provider-independence, REQ-A3-safety-and-audit, REQ-A4-evaluation-readiness,
REQ-A5-research-model-integration, REQ-A6-final-demonstration, REQ-A-rejection-conditions

*Research gates (10)* — REQ-G0-governance-and-contracts, REQ-G1-data-integrity,
REQ-G2-executor-and-reproducibility, REQ-G3-adaptation-and-collapse,
REQ-G4-controlled-utility-and-faithfulness, REQ-G5-4b-authorization, REQ-G6-4b-release-candidate,
REQ-G7-public-release, REQ-27B-stretch-gate, REQ-minimum-defensible-outcome

*Product and integration (5)* — REQ-product-jobs-to-be-done, REQ-product-nonfunctional,
REQ-product-release-stages, REQ-adapter-contract-tests, REQ-architecture-test-obligations

Gates are cumulative in both tracks: a later gate cannot compensate for an earlier integrity
failure. REQ-G5 depends on REQ-G0..G4; REQ-27B-stretch-gate depends on REQ-G6.

No PRD-typed document exists in this set (INFO-03); requirements were extracted from the
requirement-bearing SPECs. No requirement was invented.

---

## Constraints

**43 constraints**. File: `.planning/intel/constraints.md`

| Tier | Group | Count |
|---:|---|---:|
| 0 | Immutable schedule | 2 |
| 1 | Locked shared contracts and safety rules | 20 |
| 2 | Track specifications | 21 |

By type: `protocol` 30, `schema` 7, `api-contract` 4, `nfr` 2 (folded into REQ-product-nonfunctional
and CON-COMPILER-MODES).

Headline constraints downstream planning must not violate:

- **CON-DEADLINES** — seven official academic deadlines, immutable, Asia/Bangkok:
  Group Application 14 Aug 2026 23:55 · Project Idea 28 Aug 2026 · CITI 25 Sep 2026 ·
  Proposal Report 2 Oct 2026 · Proposal Presentation 8-9 Oct 2026 · Progress Report 4 Dec 2026 ·
  Progress Presentation 14-15 Dec 2026. Never negotiable in planning.
- **CON-TEMPORAL / CON-SPLIT-INVARIANTS** — patient-level splits before window generation;
  every input at decision time `T` depends only on evidence with `available_at_time <= T`.
- **CON-SAFETY-PROHIBITED / CON-SAFETY-CONTROLS** — no autonomous diagnosis, treatment,
  prescription, referral, or discharge; deterministic red-flag rules cannot be downgraded by the
  model; no hidden chain-of-thought exposure.
- **CON-API-REQUEST / CON-API-RESPONSE / CON-API-ERRORS** — all inference crosses the Model
  Gateway; `human_review.required` is always `true`; no field may assert autonomous action.
- **CON-APPROVAL-GATES** — Tier 3/4 training, >1 GPU, >60 min, external transfer of real data,
  publication, deletion, and governance changes all require recorded human approval; an agent
  cannot approve.
- **CON-TRAINING-TIERS / CON-MANIFEST-PREFLIGHT** — five run tiers; failed pre-flight blocks the run.
- **CON-CLAIM-BOUNDARY** — claim only what frozen evaluation supports; prefer "supports",
  "assists", "suggests for review", "research prototype".
- **CON-KILL-TESTS** — seven small-model kill tests gate any scaling; stopping is a valid outcome.

---

## Context topics

**16 topics**. File: `.planning/intel/context.md`

Specified versus implemented · Mission and dual-track structure · Problem framing · Research
hypothesis and questions (RQ1-RQ5) · Target model family · Development ladder · Product framing
and users · Team and ownership · Phase plan (0-7) · Milestones (M0-M9) · Active tasks
(TASK-0001..0015) · Risk register (RISK-0001..0010, all OPEN) · Current status snapshot · Scope
fallback ladder · Out of scope · Governance and change control · Weekly operating cycle

---

## Implementation reality check

**Nothing in these documents is built.** The repository contains a verification harness
(`scripts/`, 8 files), ten JSON schemas, six machine state files, three test fixtures, and one
experiment manifest. `research/`, `innovation/`, and `shared/` hold only a `README.md` each.
`data/`, `checkpoints/`, `logs/`, and `sources/` are empty.

Downstream planning must treat the model, Model Gateway, Front Door, DAG executor, provider
adapters, and every dataset as **not started**. Corroborated by WEEKLY_STATUS.md ("No integration
result exists yet"). See INFO-05.

---

## Conflicts

| Bucket | Count |
|---|---:|
| BLOCKERS | **0** |
| WARNINGS (competing variants / unresolved inputs) | **3** |
| INFO (auto-resolved / transparency) | **5** |

- **0 blockers.** No LOCKED-vs-LOCKED contradiction exists in this set. All eight locked documents
  were checked pairwise on overlapping scope and are consistent or complementary (INFO-04). No
  reference cycles. No UNKNOWN or low-confidence classifications.
- **WARN-01** — the immutable deadline transcription cannot be verified against its cited source
  PDF (absent from `sources/`; machine state says `PENDING_VISUAL_VERIFICATION`). Provenance gap,
  not a date conflict — the seven dates agree across all three places they appear.
- **WARN-02** — advisor identity and Group Application submission state are unrecorded three days
  before an immutable deadline. Recorded as absent, not inferred. Do not fabricate.
- **WARN-03** — MILESTONES.md M8 (Mar-Apr 2027) and MASTER_PLAN.md Phase 6 (Feb-Mar 2027) give
  different 4B release-candidate windows at equal precedence. Both variants preserved; no winner
  picked. Low impact — both are labelled planning assumptions, not official dates.

Full detail: `.planning/INGEST-CONFLICTS.md`

---

## Intel files

- `.planning/intel/decisions.md` — 8 locked decisions (precedence 0)
- `.planning/intel/requirements.md` — 23 requirements, all SPECIFIED / none implemented
- `.planning/intel/constraints.md` — 43 constraints across tiers 0-2
- `.planning/intel/context.md` — 16 context topics from plans and status summaries
- `.planning/INGEST-CONFLICTS.md` — 0 blockers, 3 warnings, 5 info

## Routing guidance

No blockers, so synthesis is safe to route. Resolve WARN-02 (advisor and submission state) with
the human owner before any roadmap commits to M0 completion, and carry WARN-01 as an open
verification task. WARN-03 is low-impact and may be reconciled during roadmapping.
