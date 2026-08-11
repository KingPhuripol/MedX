# Requirements

No document in this ingest set is typed `PRD`. `docs/innovation/PRODUCT_SPEC.md` was promoted
PRD -> SPEC by the manifest (see INFO-01 in INGEST-CONFLICTS.md). Requirements below are
therefore extracted from the requirement-bearing SPEC documents: the two acceptance/gate
documents and the product specification.

**Implementation status: every requirement below is SPECIFIED, none is IMPLEMENTED.** The
repository currently contains a verification harness, JSON schemas, and fixtures only. See
`context.md` -> "Specified versus implemented" for the evidence.

Gates are cumulative in both tracks. A later gate cannot compensate for an earlier integrity failure.

---

## REQ-A0-contract-prototype

- source: docs/innovation/ACCEPTANCE_CRITERIA.md (A0)
- description: Contract prototype — a synthetic Patient Journey drives a versioned gateway request answered by a mock provider.
- acceptance:
  - Valid synthetic Patient Journey creates a versioned gateway request.
  - Mock provider returns a response that validates against the Model API schemas.
  - Invalid/future/unauthorized evidence is blocked.
  - All events include safe audit metadata.
- scope: Innovation track, Model Gateway, contract validation

## REQ-A1-usable-supervised-flow

- source: docs/innovation/ACCEPTANCE_CRITERIA.md (A1)
- description: Usable supervised flow from intake through mandatory human review.
- acceptance:
  - Intake captures known, unknown, refused, and unavailable information distinctly.
  - Red-flag screen runs before learned inference.
  - Next-information flow updates the decision snapshot without rewriting history.
  - Dashboard separates urgency, pathway, information gaps, uncertainty, and critical categories.
  - Human can confirm, modify, reject, request information, or escalate with a reason.
  - Workflow cannot complete without human review.
- scope: Innovation track, intake, adaptive interview, human review

## REQ-A2-provider-independence

- source: docs/innovation/ACCEPTANCE_CRITERIA.md (A2)
- description: Provider independence behind the stable gateway boundary.
- acceptance:
  - Mock, external/baseline (if enabled), and team model implement the same gateway interface.
  - Provider-specific fields/errors do not escape adapters.
  - Shared contract fixtures pass for each enabled adapter.
  - Timeout, invalid schema, rate/cost limit, and unavailable provider fail safely.
  - Offline mock demo requires no network.
- scope: Innovation track, Model Gateway, adapters, failure handling

## REQ-A3-safety-and-audit

- source: docs/innovation/ACCEPTANCE_CRITERIA.md (A3)
- description: Safety labelling, non-suppression of deterministic escalation, and immutable audit.
- acceptance:
  - Research-prototype and human-review labels are prominent.
  - Model cannot downgrade deterministic red-flag escalation silently.
  - Missing/unsupported modalities remain explicit.
  - Abstention and low-confidence states are actionable.
  - Original model output and later human actions remain immutable audit events.
  - External API payload tests prove synthetic/authorized content policy.
  - Accessibility checks cover keyboard, contrast, focus, and non-color urgency.
- scope: Innovation track, safety controls, audit trail, accessibility

## REQ-A4-evaluation-readiness

- source: docs/innovation/ACCEPTANCE_CRITERIA.md (A4)
- description: Frozen simulated case set and implemented metrics with passing integrity audits.
- acceptance:
  - Frozen simulated case set covers multiple systems, urgency, missingness, contradiction, and provider failure.
  - Urgency, critical-case, pathway, next-information, calibration/abstention, timing, and human override metrics are implemented.
  - Patient-level and temporal integrity audits pass.
  - Independent safety and integration reviewers issue no unresolved critical failure.
- scope: Innovation track, evaluation, data integrity, independent review

## REQ-A5-research-model-integration

- source: docs/innovation/ACCEPTANCE_CRITERIA.md (A5)
- description: Team research model integrates through the identical contract used by the mock provider.
- acceptance:
  - Team model adapter passes the same fixtures as mock provider.
  - `model_version`, `contract_version`, `graph_schema_version`, evidence references, and uncertainty are displayed/logged.
  - Provider swap requires configuration only, not client/UI logic changes.
  - Graph explorer displays executed typed structure and does not expose hidden chain-of-thought.
- scope: cross-track integration, Model Gateway, DAG explorer

## REQ-A6-final-demonstration

- source: docs/innovation/ACCEPTANCE_CRITERIA.md (A6)
- description: End-to-end demonstration with rehearsed offline backup and archived reproduction package.
- acceptance:
  - Demonstrate at least one evolving patient journey from intake through human review.
  - Demonstrate urgent escalation, missing-information/abstention, and provider failure.
  - Compare mock/baseline/team providers without changing clients.
  - Present limitations and non-deployment boundary.
  - Primary and offline backup demos are rehearsed.
  - Reproduction instructions, fixtures, versions, and expected outputs are archived.
- scope: Innovation track, final demonstration, reproducibility

## REQ-A-rejection-conditions

- source: docs/innovation/ACCEPTANCE_CRITERIA.md (Rejection conditions)
- description: Absolute rejection conditions that override feature completeness.
- acceptance: The candidate is rejected regardless of feature completeness on any of — autonomous clinical action; unapproved real-patient external transfer; confirmed leakage; hidden red-flag suppression; missing human review; rendered invalid provider output; unresolved `CRITICAL_FAIL`.
- scope: Innovation track, release gating, safety veto

---

## REQ-G0-governance-and-contracts

- source: docs/research/SUCCESS_CRITERIA.md (G0)
- description: Governance and contracts accepted and versioned before research claims.
- acceptance:
  - Research questions and claim boundaries accepted.
  - Data, Patient Journey, Model API, Evaluation, and Approval contracts versioned.
  - Dataset access/license/ethics feasibility recorded.
  - Experiment manifest validation and evidence lineage work.
  - Official academic plan and owners accepted.
- scope: Research track, governance, contract versioning

## REQ-G1-data-integrity

- source: docs/research/SUCCESS_CRITERIA.md (G1)
- description: Patient-level and temporal data integrity established and audited.
- acceptance:
  - Stable patient identity and disjoint patient-level splits.
  - Every evidence/label item has source, version, and `available_at_time`.
  - Training-only fitting for preprocessing and sampling.
  - Temporal leakage, duplication, label provenance, missingness, and license audits pass.
  - A dataset card states population, exclusions, modality pairing, limitations, and permitted use.
  - Hard failure: any patient overlap or future evidence in a reported evaluation.
- scope: Research track, data integrity, splits, temporal validity

## REQ-G2-executor-and-reproducibility

- source: docs/research/SUCCESS_CRITERIA.md (G2)
- description: Graph executor correctness and end-to-end reproducibility.
- acceptance:
  - Graph type, acyclicity, budget, authorization, serialization, and replay tests pass.
  - Same inputs/version/config reproduce graph and output within tolerance.
  - Fixed-path baseline pipeline and evaluator work end-to-end.
  - Checkpoint round-trip and recovery smoke tests pass.
  - Every result traces to a valid manifest and artifact checksums.
- scope: Research track, DAG executor, replay, reproducibility

## REQ-G3-adaptation-and-collapse

- source: docs/research/SUCCESS_CRITERIA.md (G3)
- description: Graphs demonstrably adapt to case attributes without collapse.
- acceptance:
  - Graphs vary by predeclared case/task/modality/temporal attributes beyond seed noise.
  - No all-node, single-route, single-operator, or unavailable-modality collapse.
  - Variation is not primarily patient/site/file identifiers.
  - Graph cost respects declared budgets with low invalid/fallback rate.
  - Benign perturbations are stable and relevant evidence changes cause plausible graph changes.
- scope: Research track, RQ1 adaptation, collapse detection

## REQ-G4-controlled-utility-and-faithfulness

- source: docs/research/SUCCESS_CRITERIA.md (G4)
- description: Controlled comparison and causal faithfulness evidence at matched budgets.
- acceptance:
  - Proposed model is competitive with same-backbone fixed/static controls on primary tasks or provides a predeclared efficiency/calibration advantage.
  - Equal-budget comparisons and search budgets are documented.
  - Node/edge/operator/modality/graph-swap interventions affect outputs in predicted directions often enough to support the scoped faithfulness claim.
  - Replay agreement meets declared tolerance.
  - Missing-modality and temporal-update evaluations pass defined safety/quality gates.
  - Negative results and failed hypotheses are reported.
- scope: Research track, RQ2 utility, RQ3 faithfulness, RQ4 robustness

## REQ-G5-4b-authorization

- source: docs/research/SUCCESS_CRITERIA.md (G5)
- description: Authorization gate for approximately 4B training. Requires G0-G4 plus the criteria below.
- acceptance:
  - Tier 4 manifest, compute/cost/storage estimate, hardware reservation, and human approval.
  - Small-scale recipe has stable loss, routing, checkpoint/recovery, and evaluation.
  - Stop criteria and rollback plan are explicit.
  - Schedule impact does not endanger academic deliverables.
  - Data volume/quality and license permit the intended training/release.
- scope: Research track, flagship scaling authorization, human approval
- depends_on: REQ-G0, REQ-G1, REQ-G2, REQ-G3, REQ-G4

## REQ-G6-4b-release-candidate

- source: docs/research/SUCCESS_CRITERIA.md (G6)
- description: Approximately 4B release-candidate completeness.
- acceptance:
  - Base and derived checkpoints have complete lineage and checksums.
  - Frozen medical and architecture evaluations complete with valid statistics.
  - Safety, calibration, robustness, subgroup, contamination, and limitations analyses complete.
  - Model can be served through the stable Model API Contract.
  - Model card, code, inference, evaluation, environment, and license artifacts are complete.
  - Independent integration and clinical safety verdicts contain no unresolved critical failure.
- scope: Research track, release candidate, evaluation completeness

## REQ-G7-public-release

- source: docs/research/SUCCESS_CRITERIA.md (G7)
- description: Hugging Face / public release gate.
- acceptance:
  - `/hf-release-check` passes.
  - No secrets, PHI, prohibited dataset content, or unlicensed derivative.
  - Usage limitations and research-only/decision-support boundary are prominent.
  - Release version is immutable and reproducible from approved artifacts.
  - A human explicitly approves publishing.
- scope: Research track, public release, licensing, human approval

## REQ-27B-stretch-gate

- source: docs/research/SUCCESS_CRITERIA.md (27B stretch gate); docs/DECISION_LOG.md (DEC-0002)
- description: 27B-class work is stretch scope only, gated behind G6 and a separate decision.
- acceptance: Only after G6 and an approved decision showing additional research value, available compute, no schedule threat, a separate manifest, and explicit human approval. Failure to attempt 27B does not reduce project success.
- scope: Research track, stretch scope
- depends_on: REQ-G6

## REQ-minimum-defensible-outcome

- source: docs/research/SUCCESS_CRITERIA.md (Minimum defensible outcome if scaling fails)
- description: Fallback validity condition if flagship scaling fails.
- acceptance: A smaller open-weight model is a valid outcome only if G0-G4, product integration, data/safety integrity, honest limitation reporting, and reproducibility pass. The project must not relabel a smaller model as approximately 4B or hide the scale shortfall.
- scope: Research track, fallback scope, claim honesty

---

## REQ-product-jobs-to-be-done

- source: docs/innovation/PRODUCT_SPEC.md (Jobs to be done)
- description: The eight jobs the AI Clinical Front Door must perform for supervised users.
- acceptance:
  1. Capture a chief complaint and known context without forcing a disease-specific form.
  2. Show immediately available red flags and missing critical information.
  3. Ask/rank the next useful questions or evidence items.
  4. Update the state when vitals, labs, ECG, images, or prior records become available.
  5. Support urgency and care-pathway selection across multiple disease systems.
  6. Express uncertainty and abstain/escalate safely.
  7. Let a human confirm, modify, reject, or request more information with a reason.
  8. Preserve an auditable history of evidence availability, provider/model version, outputs, safety overrides, and human actions.
- scope: Innovation track, product functionality

## REQ-product-nonfunctional

- source: docs/innovation/PRODUCT_SPEC.md (Non-functional requirements)
- description: Non-functional requirements for the Front Door prototype.
- acceptance:
  - Contract validation on every boundary.
  - Deterministic synthetic fixtures for tests and demos.
  - Provider timeout and circuit breaker with safe escalation.
  - Idempotency for encounter/timepoint submissions.
  - Role-based access and minimum data display in any approved data environment.
  - Immutable audit event sequence; correction is a new event.
  - Accessible UI: keyboard navigation, readable contrast, no color-only urgency signal.
  - Latency reported by provider and end-to-end; no invented real-time clinical SLA.
  - Backup demo works without network/external API.
- scope: Innovation track, non-functional, accessibility, resilience

## REQ-product-release-stages

- source: docs/innovation/PRODUCT_SPEC.md (Release stages)
- description: Ordered release staging for the Front Door.
- acceptance: 1. Contract and synthetic CLI fixture. 2. Mock-provider clickable prototype. 3. Product alpha with audit/human confirmation and safe failure. 4. Authorized external/baseline provider adapter. 5. Team-model adapter with identical contract tests. 6. Simulated evaluation and product beta. 7. Final integrated demo and reproducibility package.
- scope: Innovation track, delivery sequencing

## REQ-adapter-contract-tests

- source: docs/shared/MODEL_API_CONTRACT.md (Contract tests)
- description: Every provider adapter passes the same ten-case contract fixture suite.
- acceptance:
  1. canonical valid request/response fixture; 2. missing modality and explicit unknown; 3. urgent red-flag case; 4. low-confidence abstention; 5. temporal violation rejection; 6. unauthorized external payload rejection; 7. timeout/provider error; 8. malformed output quarantine; 9. request idempotency; 10. no provider-native fields in client response.
  - Team-model integration is accepted only when it passes the same fixtures as the mock adapter.
- scope: cross-track integration, adapter certification

## REQ-architecture-test-obligations

- source: docs/research/ARCHITECTURE_SPEC.md (Test obligations)
- description: Test classes required for the graph architecture.
- acceptance:
  - unit: type checking, acyclicity, budget, evidence availability, serialization, deterministic compiler behavior;
  - property: generated graphs always meet invariants;
  - contract: API input/output and exported graph schemas;
  - intervention: node, edge, graph, operator, and modality manipulation;
  - robustness: missing/corrupted modality, timepoint update, provider/encoder failure;
  - performance: compilation overhead and per-case cost;
  - integration: identical gateway fixture across mock and team providers.
- scope: Research track, testing obligations
