# Phase 1: Governance Baseline and Project Idea - Context

**Gathered:** 2026-08-11
**Status:** Ready for planning

<domain>
## Phase Boundary

This phase delivers two things and nothing else:

1. **A submitted Project Idea document** — 2-4 pages plus references, delivered before DL-0002
   (28 Aug 2026, immutable), in which every claim is traceable to a cited source or is explicitly
   labelled as hypothesis or planned work.
2. **A closed G0 governance gate (RG-01)** — accepted research questions and claim boundary, five
   versioned shared contracts, a recorded dataset access/license/ethics feasibility inventory,
   working manifest validation with evidence lineage, and an accepted owner map.

Plus two governance open items: GOV-02 (deadline transcription provenance) and GOV-03 (advisor
identity).

**Not in this phase:** any model, gateway, Front Door, DAG executor, dataset ingestion, or training
work. The Front Door runtime choice is GOV-01 and belongs to Phase 2. Nothing in this phase writes
implementation code beyond harness validation logic.

</domain>

<decisions>
## Implementation Decisions

### Project Idea evidence standard

- **D-01:** Traceability is enforced with inline citations **plus** a claims table that maps every
  claim to either a cited source or an explicit `hypothesis` / `planned work` label. The table makes
  the "no unlabelled claim" rule mechanically checkable rather than a matter of careful reading.
- **D-02:** The claims table is a **separate artifact in the repository under `docs/`**, not part of
  the submitted document. The submitted document stays within the faculty format of 2-4 pages plus
  references and carries a pointer to the table. — **Reversibility:** reversible — the table can be
  inlined later if the faculty format turns out to permit an appendix.
- **D-03:** A **team member who did not write the document** reviews it and signs off before
  submission. Self-review does not satisfy criterion 1. This also spreads load away from Phurinat,
  who currently owns 56% of active P0/P1 work against a 40% concentration threshold.

### Shared contract versioning

- **D-04:** Each of the five shared contracts carries its **own independent semver**. They are not
  locked to a single contract-set version. Rationale: the schemas are already split per file, and a
  breaking change to `DATA_CONTRACT` should not force a version bump on `MODEL_API_CONTRACT`
  clients. — **Reversibility:** costly — collapsing to a single set version later means rewriting
  every recorded version reference and every fixture that pins one.
- **D-05:** `project_state/contract_versions.json` is the **authoritative registry**.
  `scripts/verify_harness.py` must check that the registry, the markdown `**Version:**` header, the
  schema `contract_version` const, and the fixtures all agree. Drift becomes a failing check rather
  than something a human has to notice. — **Reversibility:** reversible — the registry is additive
  and the check can be removed.
- **D-06:** `docs/shared/HUMAN_APPROVAL_POLICY.md` currently has **no version header at all** while
  the other four contracts are at 1.0.0. It must be given one before RG-01 can claim "five shared
  contracts versioned".

### Dataset feasibility inventory

- **D-07:** The inventory is **machine-readable JSON validated by a schema**
  (`schemas/dataset-feasibility.schema.json`) and checked in the harness, matching the existing repo
  pattern of schema + fixture + validator. Its field vocabulary is **reused from
  `docs/shared/DATA_CONTRACT.md` §"dataset version record"** rather than invented fresh, so the
  feasibility record is a pre-flight form of the record the pipeline will later produce.
- **D-08:** The inventory **reaches an explicit verdict per modality combination** —
  `FEASIBLE` / `FALLBACK_REQUIRED` / `INFEASIBLE` — not merely a collection of dataset facts. A
  verdict of `FALLBACK_REQUIRED` recorded honestly **closes** the gate; it is not a failure. This is
  what makes RISK-0002 resolvable rather than perpetually open.

### GOV-02 — deadline transcription provenance

- **D-09:** The source PDF (`Senior_Project 2026_sem1_activities.pdf`) **cannot be restored**, so
  GOV-02 is closed via the second route the requirement allows: the unverified transcription is
  carried as an **owned open risk**, owner **Phurinat Polasa**. `transcription_status` stays
  `PENDING_VISUAL_VERIFICATION` and `source_file_present` stays `false`. All seven dates remain
  binding and immutable. — **Reversibility:** reversible — if the source is later restored, verify
  visually and flip the status.

**Honest statement of what D-09 does and does not achieve.** It satisfies the requirement as
written. It does **not** reduce the underlying risk. All seven deadlines currently rest on a source
nobody can check. The three places the dates appear — `project_state/official_deadlines.json`,
`docs/project_management/OFFICIAL_DEADLINES.md`, and `CLAUDE.md` — agree with each other, but all
three descend from the same transcription, so their agreement is not independent corroboration. If
that transcription was wrong at the start, every plan built on it is wrong, and the operating
constitution forbids moving a date without a new official faculty source. The cheap mitigation is to
obtain the schedule from course staff or a classmate. Planning should treat that as worth doing even
though the gate can close without it.

### Claude's Discretion

None. Every area presented was decided by the owner.

</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### Governing authority (locked, precedence 0)
- `CLAUDE.md` — operating constitution: claim boundary, data rules, training tiers, approval gates,
  definition of done
- `docs/DECISION_LOG.md` — DEC-0001..DEC-0007, accepted and locked; override every SPEC and plan
- `project_state/official_deadlines.json` — the immutable date registry; DL-0002 governs this phase

### Shared contracts (locked, precedence 1) — the five that RG-01 requires versioned
- `docs/shared/DATA_CONTRACT.md` — §"dataset version record" is the field vocabulary for D-07
- `docs/shared/PATIENT_JOURNEY_SCHEMA.md`
- `docs/shared/MODEL_API_CONTRACT.md`
- `docs/shared/EVALUATION_CONTRACT.md`
- `docs/shared/HUMAN_APPROVAL_POLICY.md` — **missing its version header** (D-06)

### Phase requirements and gates
- `.planning/REQUIREMENTS.md` — AC-01, RG-01, GOV-02, GOV-03
- `.planning/ROADMAP.md` §"Phase 1" — goal, four success criteria, M1 kill condition
- `docs/research/SUCCESS_CRITERIA.md` — source of the G0 gate definition
- `docs/research/RESEARCH_SPEC.md` — research questions and claim boundary that G0 must accept

### Project management state
- `docs/project_management/TEAM_OWNERSHIP.md` — the owner map RG-01 must accept
- `docs/project_management/RISK_REGISTER.md` — RISK-0002 (dataset feasibility) is the live threat to
  success criterion 4; the GOV-02 risk lands here
- `project_state/tasks.json`, `project_state/risks.json` — machine state that must stay in sync with
  the readable registers

### Existing harness to extend
- `scripts/verify_harness.py` — where the D-05 version-agreement check belongs
- `scripts/harness_lib.py` — the dependency-free schema validator all checks are built on
- `scripts/validate_manifest.py` — manifest validation and evidence lineage for RG-01

</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets
- `scripts/harness_lib.py` — hand-rolled, dependency-free JSON-Schema subset validator plus
  `load_json`, `iso_datetime`, `parse_frontmatter`, `ValidationError`. Both the contract-version
  check (D-05) and the dataset feasibility validator (D-07) should be built on this, not on a new
  dependency. The repo is deliberately stdlib-only with no package manifest.
- `scripts/verify_harness.py` — already runs 199 checks and is the natural home for the new
  version-agreement assertion. It already `py_compile`s scripts and validates fixtures.
- `schemas/*.json` — ten existing schemas establish the shape a new
  `dataset-feasibility.schema.json` should follow.
- `tests/fixtures/` — three JSON fixtures show the fixture-per-contract convention.

### Established Patterns
- **Contract = markdown doc + JSON schema + fixture + validator script.** Every new machine-readable
  artifact in this phase should follow all four parts, or explicitly say why not.
- **`contract_version` is a schema `const`**, so a version bump is a deliberate edit to the schema
  and every fixture that pins it. This is a feature: it makes drift loud.
- **Stdlib only.** No `pyproject.toml`, `requirements.txt`, or `package.json` exists. Do not
  introduce `jsonschema`, `pydantic`, or any third-party library without a recorded decision.
- **No test framework exists.** Verification is `make smoke` chaining three validator scripts over
  three fixtures. New checks belong in that chain, not in a pytest suite that does not exist yet.

### Integration Points
- `project_state/contract_versions.json` is a new file that `verify_harness.py` must load and
  cross-check against `docs/shared/*.md` headers and `schemas/*.json` consts.
- The dataset feasibility JSON plugs into the same load-and-validate path as the existing state
  files.
- `.claude/hooks/approval_gate.py` treats `docs/shared/` and `schemas/` as protected prefixes, so
  contract and schema edits in this phase will prompt for approval. Expect it; do not work around it.

</code_context>

<specifics>
## Specific Ideas

- The claims table is explicitly a **repository artifact**, not a document appendix. The submitted
  document must not exceed the faculty format on account of it.
- The reviewer gate is **role-based, not name-based**: whoever did not write the document reviews
  it. Planning should not hard-code a reviewer name.
- A `FALLBACK_REQUIRED` verdict in the dataset inventory is a **legitimate gate-closing outcome**,
  consistent with the M1 kill condition. Planning must not treat it as a failure state to be avoided.

</specifics>

<deferred>
## Deferred Ideas

- **GOV-01 — Front Door runtime and framework choice.** Deliberately undecided by the owner and
  already scheduled as Phase 2 work, ordered before any Front Door or Model Gateway implementation.
  Not to be pre-empted here.
- **Obtaining the official schedule from course staff or a classmate.** Not required to close
  GOV-02, but it is the only action that actually reduces the deadline-provenance risk. Worth
  raising with the owner outside the gate.
- **Splitting workload away from Phurinat.** The 56% P0/P1 concentration exceeds the documented 40%
  threshold. Surfaced by D-03 but the wider rebalance is an owner-map question, not a Phase 1
  deliverable.

</deferred>

---

*Phase: 1-Governance Baseline and Project Idea*
*Context gathered: 2026-08-11*
