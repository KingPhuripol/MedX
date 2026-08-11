# Conflict Detection Report

Mode: `new` (no existing PROJECT.md, REQUIREMENTS.md, ROADMAP.md, or STATE.md)
Docs synthesized: 23 (2 ADR, 14 SPEC, 7 DOC) — 8 locked
Precedence: manifest-authoritative (`.planning/ingest-manifest.yaml`), tiers 0-4, lower = higher authority
Cross-ref graph: 10 doc-to-doc edges, max depth 2, **no cycles**

## Conflict Detection Report

### BLOCKERS (0)

No blockers. Specifically:

- **No LOCKED-vs-LOCKED contradiction.** All eight locked documents (docs/DECISION_LOG.md,
  docs/project_management/OFFICIAL_DEADLINES.md, docs/shared/DATA_CONTRACT.md,
  docs/shared/PATIENT_JOURNEY_SCHEMA.md, docs/shared/MODEL_API_CONTRACT.md,
  docs/shared/EVALUATION_CONTRACT.md, docs/shared/HUMAN_APPROVAL_POLICY.md,
  docs/innovation/SAFETY_SPEC.md) were checked pairwise on overlapping scope. Every pair is
  consistent or complementary. Detail in the INFO section (INFO-04).
- **No reference cycles.** DFS three-colour marking over the `cross_refs` graph found no cycle;
  max traversal depth 2, far under the 50 cap.
- **No UNKNOWN or low-confidence classifications.** All 23 docs carry `manifest_override: true`
  with an authoritative type. One doc is `confidence: medium` (see INFO-01), which the manifest
  override supersedes.
- Mode is `new`, so no ingest-vs-existing-CONTEXT.md locked-decision check applies.

### WARNINGS (3)

[WARNING] WARN-01 — Immutable deadline transcription cannot be verified against its cited source
  Found: docs/project_management/OFFICIAL_DEADLINES.md (ADR, precedence 0, locked) cites authority
    "Senior_Project 2026_sem1_activities.pdf" and states "The PDF is referenced by the project but
    is not present in the current local `sources/` mirror."
  Found: docs/DECISION_LOG.md DEC-0007 locks dates "transcribed from
    `Senior_Project 2026_sem1_activities.pdf`".
  Found: repository inspection — `sources/` is empty; the PDF is absent.
  Found: project_state/official_deadlines.json records `"source_file_present": false` and
    `"transcription_status": "PENDING_VISUAL_VERIFICATION"`.
  Found: docs/project_management/WEEKLY_STATUS.md lists "Confirm whether the source schedule PDF
    can be restored under `sources/` for visual transcription verification" as a human decision
    required this week.
  Impact: The highest-authority schedule constraint in the project rests on an unverifiable
    transcription. This is NOT a date conflict — the seven dates agree across
    OFFICIAL_DEADLINES.md, project_state/official_deadlines.json, and the operating constitution
    (CLAUDE.md). The gap is provenance, not value.
  → Restore the PDF under `sources/`, verify visually, and record confirmation. Do NOT move any
    date unless a faculty source proves a correction (that path requires human approval, a
    superseding Decision Log entry, and a synchronized registry update). Until verified, treat the
    seven dates in constraints.md CON-DEADLINES as binding and immutable.

[WARNING] WARN-02 — Advisor identity and Group Application submission state are unrecorded, 3 days from an immutable deadline
  Found: docs/PROJECT_CHARTER.md — "The advisor name is not recorded in the available project
    context. Confirming the advisor and submission evidence is an active P0 task; no system or
    agent may invent this information."
  Found: docs/project_management/MILESTONES.md M0 status `AT_RISK` — "submission state and advisor
    are not recorded".
  Found: docs/project_management/WEEKLY_STATUS.md — project health `RED`, next official deadline
    Group Application 14 Aug 2026 23:55 Asia/Bangkok.
  Found: project_state/official_deadlines.json DL-0001 status `NEEDS_CONFIRMATION`.
  Found: docs/project_management/RISK_REGISTER.md RISK-0001 (HIGH probability, CRITICAL impact,
    owner Phurinat) status `OPEN`.
  Found: docs/project_management/TASK_BOARD.md TASK-0001 `IN_PROGRESS` due 2026-08-12 and
    TASK-0002 `READY` due 2026-08-14.
  Impact: Two required planning inputs are absent, not contradictory. Synthesis recorded them as
    absent rather than inferring them. Any downstream roadmap must carry M0 as AT_RISK and must
    not fabricate an advisor name or a submission status.
  → Confirm submission evidence and advisor identity with the human owner before routing. This is
    a source-data gap, not a document conflict; it does not corrupt the synthesized intel.

[WARNING] WARN-03 — Competing 4B release-candidate windows between two equal-precedence plans
  Found: docs/project_management/MILESTONES.md (DOC, precedence 3) — M8 "Approximately 4B release
    candidate", planning target **Mar-Apr 2027**.
  Found: docs/project_management/MASTER_PLAN.md (DOC, precedence 3) — Phase 6 "Flagship scaling",
    target window **Feb-Mar 2027**, exit gate "4B candidate meets release-candidate gates".
  Impact: Both documents sit at precedence 3, so precedence cannot resolve the divergence.
    Synthesis did not pick a winner. Low material impact: both documents explicitly label
    post-Semester-1 dates as planning assumptions, not official deadlines
    (MASTER_PLAN.md: "Dates after Semester 1 are planning assumptions until official faculty dates
    are received. They are not represented as official deadlines."). Both variants are preserved
    verbatim in `.planning/intel/context.md` under "Phase plan" and "Milestones".
  → Reconcile the 4B release-candidate window across MILESTONES.md M8 and MASTER_PLAN.md Phase 6,
    or confirm the overlap is intentional (scaling completes Feb-Mar, RC gate closes Mar-Apr).
    Adjacent milestones M7 (Feb 2027 vs Phase 5 Jan-Feb 2027) and M9 (May 2027 vs Phase 7 Apr-May
    2027) are consistent and need no action.

### INFO (5)

[INFO] INFO-01 — Manifest override: PRODUCT_SPEC.md promoted PRD -> SPEC (precedence 2)
  Note: The classifier for docs/innovation/PRODUCT_SPEC.md returned `confidence: medium` with the
    note "Hybrid PRD+SPEC ... Classified as PRD due to dominant product/user-facing perspective".
    The manifest overrides this to SPEC at precedence 2, with the stated rationale: "Leaving it at
    PRD would make Research win every Research-vs-Innovation contradiction automatically,
    contradicting DEC-0001 ('Neither track may optimize in isolation at the expense of the joint
    deliverable')." Manifest honoured. PRODUCT_SPEC.md now sits at the same tier as
    ARCHITECTURE_SPEC.md, so no Research-vs-Innovation conflict can be auto-resolved by tier
    alone. No such conflict arose in this ingest set.

[INFO] INFO-02 — Manifest override: DECISION_LOG.md and OFFICIAL_DEADLINES.md promoted DOC -> ADR (precedence 0, locked)
  Note: GSD's default heuristic placed both at type DOC, the lowest default tier, inverting this
    project's authority model. The manifest corrects them to ADR/precedence 0/locked per
    CLAUDE.md: "When documents conflict, contracts and accepted Decision Log entries override
    plans; plans override status summaries." Manifest honoured. Consequence: DEC-0001..DEC-0007
    and the seven official deadlines are now the highest authority in the synthesized intel and
    cannot be auto-overridden by any SPEC.

[INFO] INFO-03 — No PRD-typed document exists in this ingest set
  Note: Requirements in `.planning/intel/requirements.md` were therefore extracted from the
    requirement-bearing SPEC documents — docs/innovation/ACCEPTANCE_CRITERIA.md (A0-A6 plus
    rejection conditions), docs/research/SUCCESS_CRITERIA.md (G0-G7, 27B stretch gate, minimum
    defensible outcome), docs/innovation/PRODUCT_SPEC.md (jobs to be done, non-functional
    requirements, release stages), docs/shared/MODEL_API_CONTRACT.md (adapter contract tests), and
    docs/research/ARCHITECTURE_SPEC.md (test obligations). No requirement was invented; every
    entry carries its source.

[INFO] INFO-04 — Locked-document pairwise consistency check passed
  Note: Overlapping-scope pairs verified consistent, no auto-resolution needed —
    DEC-0003 (Model Gateway) vs MODEL_API_CONTRACT.md boundary and versioning: aligned.
    DEC-0004 (patient split + `available_at_time`) vs DATA_CONTRACT.md identity/split and temporal
      invariants vs PATIENT_JOURNEY_SCHEMA.md snapshot operation: aligned.
    DEC-0005 (mandatory human review) vs MODEL_API_CONTRACT.md `human_review: always required:true`
      vs SAFETY_SPEC.md prohibited behaviour: aligned.
    DEC-0006 (external-API restriction) vs DATA_CONTRACT.md external API payload vs
      HUMAN_APPROVAL_POLICY.md data/privacy gates: aligned.
    DEC-0007 (immutable schedule) vs OFFICIAL_DEADLINES.md vs HUMAN_APPROVAL_POLICY.md
      "official deadline correction" gate: aligned.
    DEC-0002 (4B flagship, 27B stretch) vs HUMAN_APPROVAL_POLICY.md approximately-4B/27B approval
      requirement: aligned.
    SAFETY_SPEC.md "do not invent universal numerical safety thresholds" vs EVALUATION_CONTRACT.md
      "No universal p-value or metric threshold is assumed": aligned.
    EVALUATION_CONTRACT.md verdict vocabulary {PASS, CONDITIONAL_PASS, FAIL, CRITICAL_FAIL} vs
      SAFETY_SPEC.md verdict rubric: identical.
    DATA_CONTRACT.md five data classes and six split names vs PATIENT_JOURNEY_SCHEMA.md
      `data_classification` / `split` fields and canonical example (`expert_test`, `SYNTHETIC`):
      aligned.
  No lower-precedence document was found to contradict a higher-precedence one, so the
  auto-resolved bucket is otherwise empty.

[INFO] INFO-05 — Specified versus implemented boundary recorded
  Note: Per ingest instruction, synthesis distinguished what is SPECIFIED from what is BUILT.
    Repository inspection found only a verification harness (`scripts/`, 8 files), ten JSON
    schemas, six machine state files, three test fixtures, and one experiment manifest.
    `research/`, `innovation/`, and `shared/` contain only a `README.md` each — no source code.
    `data/`, `checkpoints/`, `logs/`, and `sources/` are empty. Corroborated by WEEKLY_STATUS.md
    ("No integration result exists yet"). Every requirement in requirements.md is therefore marked
    SPECIFIED / not implemented. Downstream planning must treat the model, Model Gateway, Front
    Door, DAG executor, adapters, and all datasets as not started.
