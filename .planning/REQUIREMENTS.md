# Requirements: Case-Adaptive Medical Multimodal Model and AI Clinical Front Door

**Defined:** 2026-08-11
**Core Value:** Every claim this project makes is reproducible by an independent reviewer and
traceable to evidence that was actually available at the simulated decision time.

**Sources:** 23 ingested documents synthesized into `.planning/intel/`. Twenty-three requirements
were extracted verbatim from the requirement-bearing SPECs (`.planning/intel/requirements.md`);
none were invented. Nine further requirements (AC-01..AC-06, GOV-01..GOV-03) are derived from
tier-0 `CON-DEADLINES` and from three recorded open items — they are gap-fills surfaced by
goal-backward checking, each with its source named below.

**Implementation status: every requirement below is SPECIFIED. None is implemented.** The
repository holds a verification harness, JSON schemas, and fixtures only.

**Gates are cumulative in both tracks. A later gate cannot compensate for an earlier integrity
failure.** RG-06 depends on RG-01..RG-05. RG-09 (v2) depends on RG-07.

---

## v1 Requirements

### Academic Deliverables (AC)

Derived from `CON-DEADLINES` (tier 0, locked) and `docs/project_management/MILESTONES.md`. Dates are
Asia/Bangkok and **immutable**. DL-0001 (Group Application, 14 Aug 2026) is already submitted and is
recorded as Validated in PROJECT.md, so it carries no requirement here.

- [ ] **AC-01**: Project Idea document (2-4 pages plus references) is delivered before DL-0002,
      28 Aug 2026, with every claim traceable to a cited source or labelled as hypothesis or
      planned work
- [ ] **AC-02**: CITI completion evidence is recorded for all five members before DL-0003,
      25 Sep 2026
- [ ] **AC-03**: Proposal Report is delivered before DL-0004, 2 Oct 2026
- [ ] **AC-04**: Proposal Presentation is delivered within the DL-0005 window, 8-9 Oct 2026
- [ ] **AC-05**: Progress Report is delivered before DL-0006, 4 Dec 2026, reporting deviations and
      failures alongside successes
- [ ] **AC-06**: Progress Presentation is delivered within the DL-0007 window, 14-15 Dec 2026

### Governance Open Items (GOV)

Derived from WARN-02 and WARN-01 in `.planning/INGEST-CONFLICTS.md` and from the human owner's
instruction that the Front Door runtime is deliberately undecided.

- [ ] **GOV-01**: The Front Door runtime and framework choice is recorded as an accepted Decision Log
      entry — with rationale, alternatives, track impact, and rollback — before any Front Door or
      Model Gateway implementation code is written
- [ ] **GOV-02**: The official-deadline transcription is verified against a restored faculty source
      under `sources/`, or the unverified status is carried as an owned open risk with a named owner
      (WARN-01; `transcription_status: PENDING_VISUAL_VERIFICATION`)
- [ ] **GOV-03**: Advisor identity is recorded in project state from an authoritative source; no
      agent or system may infer or invent it (WARN-02)

### Research Gates (RG)

Source: `docs/research/SUCCESS_CRITERIA.md`, `docs/DECISION_LOG.md`. Cumulative and ordered.

- [ ] **RG-01** *(REQ-G0)*: Governance and contracts accepted and versioned before any research
      claim — research questions and claim boundary accepted, five shared contracts versioned,
      dataset access/license/ethics feasibility recorded, manifest validation and evidence lineage
      working, academic plan and owners accepted
- [ ] **RG-02** *(REQ-G1)*: Patient-level and temporal data integrity established and audited —
      disjoint patient splits, `available_at_time` on every item, train-only fitting, passing
      leakage/duplication/provenance/missingness/license audits, and a dataset card. Any patient
      overlap or future evidence in a reported evaluation is a hard failure
- [ ] **RG-03** *(REQ-G2)*: Graph executor correctness and end-to-end reproducibility — type,
      acyclicity, budget, authorization, serialization, and replay tests pass; same inputs reproduce
      graph and output within tolerance; fixed-path baseline pipeline and evaluator run end to end;
      checkpoint round-trip and recovery smoke pass; every result traces to a valid manifest and
      artifact checksums
- [ ] **RG-04** *(REQ-G3)*: Graphs demonstrably adapt to case attributes without collapse — variation
      beyond seed noise, no all-node/single-route/single-operator/unavailable-modality collapse, not
      driven by patient/site/file identifiers, budgets respected, stable under benign perturbation
- [ ] **RG-05** *(REQ-G4)*: Controlled comparison and causal faithfulness at matched budgets —
      competitive with same-backbone fixed and static controls or a predeclared efficiency or
      calibration advantage; documented equal budgets; interventions affect outputs in predicted
      directions; replay agreement within tolerance; negative results reported
- [ ] **RG-06** *(REQ-G5)*: Approximately 4B authorization gate — Tier 4 manifest, compute/cost/
      storage estimate, hardware reservation, recorded human approval, stable small-scale recipe,
      explicit stop criteria and rollback, no schedule threat to academic deliverables, and data
      volume/quality/license permitting the intended training and release.
      **Depends on RG-01, RG-02, RG-03, RG-04, RG-05**
- [ ] **RG-07** *(REQ-G6)*: Approximately 4B release-candidate completeness — checkpoint lineage and
      checksums, frozen medical and architecture evaluations with valid statistics, safety/
      calibration/robustness/subgroup/contamination/limitations analyses, servable through the stable
      Model API Contract, complete model card and artifacts, and independent integration and clinical
      safety verdicts with no unresolved critical failure
- [ ] **RG-08** *(REQ-G7)*: Public release gate — `/hf-release-check` passes; no secrets, PHI,
      prohibited dataset content, or unlicensed derivative; usage limitations and the research-only
      decision-support boundary are prominent; the release version is immutable and reproducible from
      approved artifacts; a human explicitly approves publishing
- [ ] **RG-10** *(REQ-minimum-defensible-outcome)*: If flagship scaling is declined or fails, a
      smaller open-weight model is reported honestly — the scale shortfall is stated and never
      relabelled, and validity still rests on closed RG-01..RG-05, product integration, data and
      safety integrity, and reproducibility

### Innovation Acceptance (IA)

Source: `docs/innovation/ACCEPTANCE_CRITERIA.md`. Cumulative and ordered.

- [ ] **IA-01** *(REQ-A0)*: Contract prototype — a valid synthetic Patient Journey creates a versioned
      gateway request, a mock provider returns a schema-valid response, invalid/future/unauthorized
      evidence is blocked, and all events carry safe audit metadata
- [ ] **IA-02** *(REQ-A1)*: Usable supervised flow — intake distinguishes known/unknown/refused/
      unavailable, the red-flag screen runs before learned inference, next-information updates the
      snapshot without rewriting history, the dashboard separates urgency/pathway/gaps/uncertainty/
      critical categories, the human can confirm/modify/reject/request/escalate with a reason, and
      the workflow cannot complete without human review
- [ ] **IA-03** *(REQ-A2)*: Provider independence — mock, external or baseline, and team model
      implement the same gateway interface; no provider-specific field or error escapes an adapter;
      shared fixtures pass for every enabled adapter; timeout, invalid schema, rate/cost limit, and
      unavailable provider all fail safely; the offline mock demo needs no network
- [ ] **IA-04** *(REQ-A3)*: Safety labelling, non-suppression, and immutable audit — research-prototype
      and human-review labels prominent; the model cannot silently downgrade a deterministic red-flag
      escalation; missing or unsupported modalities stay explicit; abstention and low-confidence
      states are actionable; original output and later human actions are immutable audit events;
      external-payload tests prove the synthetic/authorized policy; accessibility covers keyboard,
      contrast, focus, and non-colour urgency
- [ ] **IA-05** *(REQ-A4)*: Evaluation readiness — a frozen simulated case set covering multiple
      systems, urgency, missingness, contradiction, and provider failure; implemented urgency,
      critical-case, pathway, next-information, calibration/abstention, timing, and human-override
      metrics; passing patient-level and temporal integrity audits; independent safety and
      integration reviewers with no unresolved critical failure
- [ ] **IA-06** *(REQ-A5)*: Research model integrates through the identical contract used by the mock
      provider — the team-model adapter passes the same fixtures; `model_version`,
      `contract_version`, `graph_schema_version`, evidence references, and uncertainty are displayed
      and logged; provider swap is configuration-only; the graph explorer shows the executed typed
      structure and exposes no hidden chain-of-thought
- [ ] **IA-07** *(REQ-A6)*: Final demonstration — at least one evolving patient journey from intake
      through human review; urgent escalation, missing-information abstention, and provider failure
      demonstrated; mock, baseline, and team providers compared without client changes; limitations
      and the non-deployment boundary presented; primary and offline backup demos rehearsed;
      reproduction instructions, fixtures, versions, and expected outputs archived
- [ ] **IA-08** *(REQ-A-rejection-conditions)*: An executable release veto — a candidate is rejected
      regardless of feature completeness on autonomous clinical action, unapproved real-patient
      external transfer, confirmed leakage, hidden red-flag suppression, missing human review,
      rendered invalid provider output, or an unresolved `CRITICAL_FAIL`

### Product (PD)

Source: `docs/innovation/PRODUCT_SPEC.md`.

- [ ] **PD-01** *(REQ-product-jobs-to-be-done)*: The eight jobs the Front Door performs for supervised
      users — capture a chief complaint without a disease-specific form; show available red flags and
      missing critical information; rank the next useful questions or evidence; update state when
      vitals, labs, ECG, images, or prior records arrive; support urgency and care-pathway selection
      across disease systems; express uncertainty and abstain or escalate safely; let a human confirm,
      modify, reject, or request more information with a reason; preserve an auditable history
- [ ] **PD-02** *(REQ-product-nonfunctional)*: Contract validation on every boundary; deterministic
      synthetic fixtures; provider timeout and circuit breaker with safe escalation; idempotent
      encounter/timepoint submission; role-based access and minimum data display; immutable
      append-only audit where correction is a new event; accessible UI with keyboard navigation,
      readable contrast, and no colour-only urgency signal; latency reported without inventing a
      clinical SLA; a backup demo that works without network
- [ ] **PD-03** *(REQ-product-release-stages)*: The seven-stage release ladder is accepted and
      followed in order — (1) contract and synthetic CLI fixture, (2) mock-provider clickable
      prototype, (3) product alpha with audit, human confirmation, and safe failure, (4) authorized
      external or baseline adapter, (5) team-model adapter with identical contract tests,
      (6) simulated evaluation and product beta, (7) final integrated demo and reproducibility
      package. Stages 1-2 close in Phase 2; stages 3-4 in Phase 3; stage 5 in Phase 5; stage 6 in
      Phase 4; stage 7 in Phase 7

### Integration and Test Obligations (IT)

Source: `docs/shared/MODEL_API_CONTRACT.md`, `docs/research/ARCHITECTURE_SPEC.md`.

- [ ] **IT-01** *(REQ-adapter-contract-tests)*: Every provider adapter passes the same ten-case
      fixture suite — canonical valid pair; missing modality and explicit unknown; urgent red flag;
      low-confidence abstention; temporal violation rejection; unauthorized external payload
      rejection; timeout/provider error; malformed output quarantine; request idempotency; no
      provider-native fields in the client response. Team-model integration is accepted only when it
      passes the identical suite
- [ ] **IT-02** *(REQ-architecture-test-obligations)*: All seven test classes run and pass — unit
      (type checking, acyclicity, budget, evidence availability, serialization, deterministic
      compiler behaviour); property (generated graphs always meet invariants); contract (API and
      exported graph schemas); intervention (node, edge, graph, operator, modality manipulation);
      robustness (missing or corrupted modality, timepoint update, provider or encoder failure);
      performance (compilation overhead and per-case cost); integration (identical gateway fixture
      across mock and team providers)

---

## v2 Requirements

Deferred. Tracked but not in the current roadmap.

### Stretch Scaling

- **RG-09** *(REQ-27B-stretch-gate)*: 27B-class work (`Medical-DAG-Large`) is stretch scope, gated
  behind RG-07 (G6) and a separate accepted decision showing additional research value, available
  compute, no schedule threat, a separate Tier 4 manifest, and explicit human approval.
  **Depends on RG-07.** Per DEC-0002, failure to attempt 27B does not reduce project success.

---

## Out of Scope

| Feature | Reason |
|---------|--------|
| Autonomous diagnosis, treatment, prescription, test order, referral, discharge, or patient instruction | Prohibited by DEC-0005 and CON-SAFETY-PROHIBITED — safety-critical domain, supervised prototype only |
| Live clinical use affecting patient care | Requires separate university, ethics, and clinical governance outside this project |
| External transfer of real, identifiable, or linkable patient data | Denied by default under DEC-0006; exceptions require a scoped, recorded approval ID |
| Patient-facing direct use | Users are supervised intake staff, clinicians, evaluators, and researchers only |
| Production deployment of the Front Door | Prototype boundary; no operational SLA is claimed |
| Mapping urgency to a real hospital triage scale | CON-URGENCY-TAXONOMY — abstract research levels only until authorized clinical validation |
| Presenting the exported DAG as a clinical explanation without intervention evidence | RQ3 requires causal-faithfulness evidence; visualization alone is decorative |
| Universal numeric safety or p-value thresholds | CON-SAFETY-GATES and CON-EVAL-STATS forbid inventing thresholds before clinical and sample-size review |
| Scraping or redistributing data or weights contrary to licenses | Binding license, consent, and ethics conditions |

---

## Traceability

Which phases cover which requirements. Each v1 requirement maps to exactly one phase.

| Requirement | Phase | Status |
|-------------|-------|--------|
| AC-01 | Phase 1 | Pending |
| RG-01 | Phase 1 | Pending |
| GOV-02 | Phase 1 | Pending |
| GOV-03 | Phase 1 | Pending |
| AC-02 | Phase 2 | Pending |
| AC-03 | Phase 2 | Pending |
| AC-04 | Phase 2 | Pending |
| GOV-01 | Phase 2 | Pending |
| IA-01 | Phase 2 | Pending |
| IT-01 | Phase 2 | Pending |
| PD-03 | Phase 2 | Pending |
| RG-02 | Phase 3 | Pending |
| RG-03 | Phase 3 | Pending |
| IA-02 | Phase 3 | Pending |
| IA-03 | Phase 3 | Pending |
| IA-04 | Phase 3 | Pending |
| PD-01 | Phase 3 | Pending |
| PD-02 | Phase 3 | Pending |
| AC-05 | Phase 4 | Pending |
| AC-06 | Phase 4 | Pending |
| IA-05 | Phase 4 | Pending |
| IA-08 | Phase 4 | Pending |
| RG-04 | Phase 5 | Pending |
| RG-05 | Phase 5 | Pending |
| IA-06 | Phase 5 | Pending |
| IT-02 | Phase 5 | Pending |
| RG-06 | Phase 6 | Pending |
| RG-07 | Phase 6 | Pending |
| RG-10 | Phase 6 | Pending |
| RG-08 | Phase 7 | Pending |
| IA-07 | Phase 7 | Pending |
| RG-09 | v2 (deferred) | Not scheduled |

**Coverage:**
- v1 requirements: 31 total
- Mapped to phases: 31
- Unmapped: 0 ✓
- v2 deferred: 1 (RG-09)

**Cross-cutting notes (single-phase mapping does not mean single-phase relevance):**
- **IT-01** is certified for the mock adapter in Phase 2, then re-run unchanged for every adapter
  added in Phases 3, 5, and 6. Re-running it is a gate in those phases, not a new requirement.
- **IT-02** first lands its unit, property, and contract classes in Phase 3 with the executor; the
  requirement completes in Phase 5 when intervention, robustness, performance, and integration
  classes also pass.
- **IA-08** is implemented as an executable veto in Phase 4 and re-run at every later release or demo
  gate (Phases 5, 6, 7).
- **PD-03** is accepted and its ladder locked in Phase 2; individual stages close in the phases named
  in the requirement text.
- **RG-10** is decided in Phase 6 but its preconditions are the gates closed in Phases 1-5.

---
*Requirements defined: 2026-08-11*
*Last updated: 2026-08-11 after initial ingest of 23 project documents*
