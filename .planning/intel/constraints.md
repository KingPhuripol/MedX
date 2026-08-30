# Constraints

> ⚠️ **Generated snapshot, extracted 2026-08-11 — partially stale.** It still describes the
> flagship as approximately 4B. DEC-0009 (2026-08-26) makes the flagship approximately 27B and
> withdraws the 4B target. Authority sits with `docs/` and `project_state/` (DEC-0008); read
> `docs/DECISION_LOG.md` before relying on any scale figure here.

Extracted from `SPEC`-typed documents plus the immutable schedule. Ordered by manifest
precedence: tier 0 (immutable schedule) first, then tier 1 (locked shared contracts and safety
rules), then tier 2 (track specifications).

Tier 1 constraints are **locked**: a contradiction against them is a BLOCKER, not an
auto-resolution. Tier 2 constraints yield to tier 0 and tier 1.

---

# Tier 0 — Immutable schedule

## CON-DEADLINES: Seven official academic deadlines (immutable)

- source: docs/project_management/OFFICIAL_DEADLINES.md; docs/DECISION_LOG.md (DEC-0007); project_state/official_deadlines.json
- type: protocol
- content:
  Timezone Asia/Bangkok. These dates are **hard constraints, never negotiable**. They may not be
  moved by planning. A correction requires a new official faculty source, explicit human approval,
  a superseding Decision Log entry, and a synchronized registry update.

  | ID | Deliverable | Official deadline | Required form/content |
  |---|---|---|---|
  | DL-0001 | Group Application | 14 Aug 2026, 23:55 | Group application; applies only if not already submitted |
  | DL-0002 | Project Idea | 28 Aug 2026 | 2-4 pages plus references |
  | DL-0003 | CITI | 25 Sep 2026 | Required CITI completion/evidence |
  | DL-0004 | Proposal Report | 2 Oct 2026 | Official proposal report |
  | DL-0005 | Proposal Presentation | 8-9 Oct 2026 | Official presentation window (plan against 8 Oct) |
  | DL-0006 | Progress Report | 4 Dec 2026 | Official progress report |
  | DL-0007 | Progress Presentation | 14-15 Dec 2026 | Official presentation window (plan against 14 Dec) |

  Internal review buffers (T-14/T-10/T-7/T-5/T-3/T-1 ladders per deliverable) are planning
  commitments, not replacements for the official dates. If a window is already compressed, the
  Project Manager must expose the risk and prioritize the minimum valid deliverable; it may not
  silently move the official deadline.

  Machine state records `source_file_present: false` and
  `transcription_status: PENDING_VISUAL_VERIFICATION`; DL-0001 status is `NEEDS_CONFIRMATION`.
  See WARN-01 and WARN-02 in INGEST-CONFLICTS.md. The dates themselves are corroborated across
  the deadlines document, the machine registry, and the operating constitution.

## CON-DATES-UNOFFICIAL: Post-Semester-1 dates are planning assumptions

- source: docs/project_management/MASTER_PLAN.md
- type: protocol
- content: Dates after Semester 1 (Jan 2027 onward) are planning assumptions until official faculty dates are received. They must not be represented as official deadlines.

---

# Tier 1 — Locked shared contracts and safety rules

## CON-DATA-CLASSIFICATION: Five data classes and external-API defaults

- source: docs/shared/DATA_CONTRACT.md
- type: schema
- content:
  `SYNTHETIC` (allowed within provider terms/budget); `PUBLIC_LICENSED` (only if license and
  provider terms permit); `DEIDENTIFIED_APPROVED` (denied unless separate approval explicitly
  covers provider transfer); `IDENTIFIABLE_OR_LINKABLE` (denied); `RESTRICTED_DERIVATIVE`
  (embedding, report, crop, or artifact inheriting restrictions — denied unless explicitly
  cleared). De-identification does not automatically authorize external transfer or redistribution.

## CON-SPLIT-INVARIANTS: Patient-level identity and split invariants

- source: docs/shared/DATA_CONTRACT.md; docs/DECISION_LOG.md (DEC-0004)
- type: protocol
- content:
  1. Assign a stable internal `patient_id` before deriving encounters, windows, images, text chunks, or tasks.
  2. Split at patient level. All encounters, modalities, duplicates, derivatives, and temporal windows from one patient remain in exactly one of `train`, `validation`, `internal_test`, `external_test`, `expert_test`, or approved special sets.
  3. If identities cannot be linked across sources, do not claim guaranteed disjointness; isolate the source and report the limitation.
  4. Near-duplicate images/text and shared accession/study identifiers are audited after splitting, without moving samples based on labels.
  5. Final test split is frozen and access logged.

## CON-TEMPORAL: Temporal availability invariant

- source: docs/shared/DATA_CONTRACT.md; docs/DECISION_LOG.md (DEC-0004)
- type: protocol
- content:
  Every evidence item and label carries `observed_at`, `available_at_time`, `recorded_at` where
  available, and provenance/transformation lineage. For decision time `T`, every model input,
  retrieval result, feature, derived variable, preprocessing statistic, and prompt content must
  depend only on evidence with `available_at_time <= T`.

  Forbidden at early snapshots: final/discharge diagnosis; discharge summary or retrospective
  problem-list update; a report signed after the decision time; lab/image acquired or released
  later; disposition, procedure, ICU admission, deterioration, mortality, or outcome;
  retrospective billing/coding or manual annotation created with future chart access;
  normalization/imputation/feature selection fitted using validation/test data.

  When source timestamps are ambiguous, use the conservative latest plausible availability or
  exclude the field from temporal evaluation.

## CON-LABELS: Labels are evidence; targets are separate

- source: docs/shared/DATA_CONTRACT.md
- type: protocol
- content: Record label definition/version, source, annotator/process, `available_at_time`, confidence/adjudication, and whether the label was observable prospectively or only retrospectively. Do not equate final diagnosis with urgency/pathway ground truth. Define separate targets for urgency, pathway, next information, critical categories, outcome, and diagnosis. Derived labels must document rules and be recreated only from authorized source fields.

## CON-MISSINGNESS: Missingness is preserved, never coerced

- source: docs/shared/DATA_CONTRACT.md
- type: schema
- content: Represent `NOT_MEASURED`, `MEASURED_UNKNOWN`, `NOT_AVAILABLE_YET`, `WITHHELD`, `UNSUPPORTED`, `CORRUPT`, and `NOT_APPLICABLE` distinctly where relevant. Never convert missing to normal/negative without an explicit, evaluated rule.

## CON-PREPROCESSING: Train-only fitting and no label encoding in structure

- source: docs/shared/DATA_CONTRACT.md
- type: protocol
- content: Fit trainable transformations on the training split only. Version every transform and its inputs. Preserve original units/geometry metadata and reversible mapping when possible. Do not encode labels or future metadata in paths, filenames, sample ordering, padding, or cache keys. Cache keys include data/transform version and authorization scope. Augmentation must not create clinically impossible combinations without labeling them synthetic.

## CON-DATA-CHECKS: Required automated data checks

- source: docs/shared/DATA_CONTRACT.md
- type: protocol
- content: schema and identifier uniqueness; patient disjointness across splits; `available_at_time` at each decision snapshot; label/input provenance separation; duplicate/near-duplicate and source overlap checks; unit/range/geometry and missingness checks; train-only preprocessing fit; payload classification/authorization and no-secret/no-PHI logs; manifest counts/checksums and license completeness.

## CON-DATA-INCIDENT: Data incident response

- source: docs/shared/DATA_CONTRACT.md
- type: protocol
- content: On patient overlap, future leakage, unauthorized access/transfer, license breach, or corrupt lineage — stop affected pipeline, preserve evidence safely, mark dependent manifests invalid, notify owners, update Risk Register, determine affected results/releases, rebuild from a new version, and independently re-audit.

## CON-JOURNEY-SCHEMA: Patient Journey structure

- source: docs/shared/PATIENT_JOURNEY_SCHEMA.md (v1.0.0); schemas/patient-journey.schema.json
- type: schema
- content:
  Append-only timeline whose snapshots expose only time-valid evidence. Required top level:
  `schema_version`, `journey_id`, `patient_id`, `encounter_id`, `split`, `data_classification`,
  `source`, `encounter_start`, `events`. Optional `outcomes` — later evidence with true
  availability, never implicit early input.

  Required per event: `event_id` unique within journey; `event_type` in {CHIEF_COMPLAINT,
  TRIAGE_NOTE, DEMOGRAPHICS, HISTORY, MEDICATION, ALLERGY, VITAL, EXAM, LAB, ECG, IMAGE_2D,
  IMAGE_3D, REPORT, CONSULT, DIAGNOSIS, DISPOSITION, OUTCOME, or versioned extension};
  `modality` in {TEXT, STRUCTURED, IMAGE_2D, IMAGE_3D, SIGNAL, LABEL, REFERENCE}; `observed_at`
  and `available_at_time` in ISO-8601; `source_ref`; `status`; `data_classification`; exactly one
  safe `payload_ref`/checksum or schema-permitted inline synthetic `value`.

## CON-SNAPSHOT: Snapshot operation is pure and recorded

- source: docs/shared/PATIENT_JOURNEY_SCHEMA.md
- type: protocol
- content: Given `decision_time = T` — (1) select events with `available_at_time <= T`; (2) apply authorization and task filters; (3) retain explicit missing/unavailable catalog entries without exposing future values; (4) order by `available_at_time` then stable event ID; (5) record selected evidence IDs and rejected reasons; (6) never mutate the base journey. The snapshot records `journey_id`, `decision_time`, task, evidence IDs, missingness, data/split/transform versions, and checksum. A later snapshot is a new artifact. Schema validation does not prove temporal validity; run `scripts/temporal_leakage_audit.py`.

## CON-API-REQUEST: Model API request contract

- source: docs/shared/MODEL_API_CONTRACT.md (v1.0.0); schemas/model-api-request.schema.json
- type: api-contract
- content:
  Required: `contract_version`, `request_id`, `journey_id`, `decision_time`, `task`; `evidence`
  (authorized references or approved inline synthetic values, each with `evidence_id`, type,
  modality, `available_at_time`); `missing_information` (explicit status without future values);
  `requested_outputs`; `authorization` (data classification, external-provider permission,
  approval ID when applicable); `provider_constraints` (timeout, maximum output, cost/budget
  class, deterministic preference).

  The gateway rejects duplicate IDs, unsupported contract version, evidence after decision time,
  prohibited classification/provider combination, missing authorization, or malformed modality
  metadata.

## CON-API-RESPONSE: Model API response contract

- source: docs/shared/MODEL_API_CONTRACT.md; schemas/model-api-response.schema.json
- type: api-contract
- content:
  Required: `contract_version`, `request_id`, `response_id`, `provider`, `model_version`;
  `status` in {COMPLETED, ABSTAINED, ESCALATED, FAILED_SAFE}; `urgency` (abstract versioned level,
  confidence if meaningful, evidence references); `red_flags`; `care_pathways` (ranked candidates
  with normalized code, confidence/score semantics, evidence references); `next_information`
  (ranked types with reason codes); `uncertainty` (calibration method/version, limitations,
  OOD/unsupported, abstention reason); `human_review` — **always `required: true`** with permitted
  actions; `graph`; `provenance`; `errors`.

  **No response may contain a field asserting autonomous action or hidden chain-of-thought.**

## CON-API-ERRORS: Gateway error taxonomy

- source: docs/shared/MODEL_API_CONTRACT.md
- type: api-contract
- content:
  `INVALID_REQUEST` reject before provider; `TEMPORAL_VIOLATION` block + data-integrity
  escalation; `UNAUTHORIZED_DATA` block + privacy escalation; `UNSUPPORTED_MODALITY` abstain or
  route approved fallback explicitly; `PROVIDER_TIMEOUT` safe failure/escalation with no hidden
  retry storm; `INVALID_PROVIDER_OUTPUT` quarantine, never partially render; `BUDGET_EXCEEDED`
  safe failure, human decides retry; `LOW_CONFIDENCE` abstain/escalate.
  Retries are idempotent, bounded, and audited. Switching providers is explicit in the audit
  record and never changes task semantics silently.

## CON-API-VERSIONING: Contract versioning and compatibility

- source: docs/shared/MODEL_API_CONTRACT.md
- type: api-contract
- content: Major = breaking field or semantic change; Minor = backward-compatible optional capability; Patch = clarification/validation fix. Gateway supports an explicit compatibility matrix. Unknown major versions fail safe. Deprecations include migration, adapter fixtures, and a removal date approved through the Decision Log.

## CON-EVAL-PRINCIPLES: Evaluation freeze and reporting principles

- source: docs/shared/EVALUATION_CONTRACT.md (v1.0.0)
- type: protocol
- content: Freeze question, cohort/split, temporal snapshot, metric, comparison, and exclusion before viewing final results. Treat patient as the independent unit unless the design justifies otherwise. Separate model selection (`validation`) from internal/external/expert final tests. Report safety first, then utility, architecture behavior, efficiency, calibration, and human factors. Preserve failures and deviations. No metric shopping.

## CON-EVAL-LAYERS: Five evaluation layers

- source: docs/shared/EVALUATION_CONTRACT.md
- type: protocol
- content: (1) Data integrity — failure blocks all downstream claims. (2) Medical capability. (3) Architecture — per the Benchmark Contract. (4) Clinical Front Door. (5) Safety and human factors.

## CON-EVAL-FAILURE-POLICY: Missing prediction and failure policy

- source: docs/shared/EVALUATION_CONTRACT.md
- type: protocol
- content: Schema-invalid outputs count as failures, not silently dropped. Provider timeout/failure is reported with denominator and operational metric. Abstention is scored under selective-risk/coverage and safety policy, not converted to a random prediction. Missing ground truth uses predeclared exclusion and remains in cohort accounting. Runs stopped by a safety/data gate are invalid, not zero or missing by convenience.

## CON-EVAL-STATS: Statistical reporting requirements

- source: docs/shared/EVALUATION_CONTRACT.md; docs/research/BENCHMARK_CONTRACT.md
- type: protocol
- content: For each primary metric report definition, direction, numerator/denominator, point estimate, patient-level uncertainty interval, comparison/effect size, and practical interpretation. Use paired inference for same cases. Resample/model clusters when data are clustered by patient/site. Label exploratory analyses and account for multiplicity. **No universal p-value or metric threshold is assumed**; thresholds must reflect sample size, clinical asymmetry, baseline, and intended scoped claim, and are frozen before final test.

## CON-EVAL-VERDICT: Review roles and verdict vocabulary

- source: docs/shared/EVALUATION_CONTRACT.md; docs/innovation/SAFETY_SPEC.md
- type: protocol
- content: Evaluation owner generates evidence; Integration Auditor verifies reproducibility and cross-contract alignment; Clinical Safety Reviewer independently assesses safety. Final status is `PASS`, `CONDITIONAL_PASS`, `FAIL`, or `CRITICAL_FAIL`. Critical data/safety failures override aggregate performance. The reviewer never edits the implementation under review.

## CON-CLAIM-MAP: Result-to-claim map

- source: docs/shared/EVALUATION_CONTRACT.md
- type: protocol
- content: Every proposal/report/presentation/public claim cites the evaluation IDs and manifests that support it, plus limitations. If no valid evaluation supports a statement, write it as a hypothesis, design goal, or planned work.

## CON-APPROVAL-GATES: Actions always requiring explicit human approval

- source: docs/shared/HUMAN_APPROVAL_POLICY.md
- type: protocol
- content:
  *Compute/training:* Tier 3 or Tier 4 runs; more than one GPU or any multi-node/cluster
  scheduler job; expected runtime over 60 minutes or material paid compute; approximately 4B/27B
  training, full-dataset transforms, or substantial artifact storage; increasing approved budget,
  devices, time, data, or objective after approval.

  *Data/privacy:* real, identifiable, linkable, de-identified-approved, or restricted-derivative
  data sent to any external API/service; destructive/irreversible dataset transformation or
  deletion; new data license/ethics interpretation, identity linkage, or release of derived data;
  access-control/retention exception.

  *Publication/external:* Hugging Face upload/release, model/data card publication,
  package/deployment release, Git push to public remote, public report/site, or external message;
  deleting checkpoints, experiment evidence, audit logs, datasets, releases, or branches;
  changing a published artifact or tag.

  *Governance/safety:* official deadline correction; material changes to mission, track boundary,
  modality scope, flagship target, research question, success criterion, split/label,
  API/evaluation contract, clinical taxonomy, safety rule, or claim; accepting/waiving a safety or
  integration failure; enabling any real clinical use or action affecting care.

## CON-APPROVAL-RECORD: Approval is specific, time-bounded, recorded, non-self-granted

- source: docs/shared/HUMAN_APPROVAL_POLICY.md; schemas/human-approval.schema.json
- type: protocol
- content: An approval is specific, time-bounded, and recorded; approval of one run/provider/release does not approve later variants. The record states approval ID and type, requester and approver identity/role, requested/decided times, expiry, exact action/command/provider/release/experiment and environment, data classification and fields, compute/cost/time/storage limits, rationale/alternatives/risks/safeguards/monitoring/stop-rollback/evidence, decision in {APPROVED, DENIED, EXPIRED, REVOKED}, and linked task/risk/decision/manifest. **An agent cannot approve; the requester cannot impersonate the approver.** Repository role ownership does not override university, ethics, dataset, or clinical governance. A hook prompt is a runtime confirmation, not proof of authorization. Any member may request an emergency stop.

## CON-SAFETY-PROHIBITED: Prohibited system behaviour

- source: docs/innovation/SAFETY_SPEC.md; docs/DECISION_LOG.md (DEC-0005)
- type: protocol
- content:
  - autonomous diagnosis, treatment, prescription, test order, referral, discharge, or patient instruction;
  - presenting a differential or pathway as confirmed fact;
  - hiding a red flag because model confidence is low or another score is reassuring;
  - producing a recommendation from invalid, future, unauthorized, or missing-required evidence;
  - sending real/linkable patient information to an external API without approval;
  - exposing hidden chain-of-thought as an explanation;
  - silently changing urgency/pathway taxonomy or safety thresholds;
  - using the prototype for actual care without separate authorization.

## CON-SAFETY-CONTROLS: Layered safety controls

- source: docs/innovation/SAFETY_SPEC.md
- type: protocol
- content:
  *Input:* schema/version validation, authorization, evidence availability check, units/ranges,
  missingness, contradictory/implausible value flags, modality support, minimum-required-information policy.
  *Deterministic:* versioned red-flag rules and conservative escalation run independently of the
  model. **A model cannot override them downward.** Changes require clinical review, tests, and a
  Decision Log entry.
  *Model:* calibrated uncertainty where feasible, abstention, OOD/unsupported detection,
  constrained outputs, evidence references, no free-form autonomous instruction.
  *Interface:* prominent `RESEARCH PROTOTYPE - HUMAN REVIEW REQUIRED`; urgency not encoded only by
  color; known/missing evidence timeline; limitation text; review action before completion;
  immutable original output after override.
  *Operational:* provider timeout/circuit breaker, synthetic offline demo, access control in
  approved environments, minimum retention, no secrets in logs, monitoring of failures/overrides,
  disable switch.

## CON-SAFETY-GATES: Release/demo blocking conditions

- source: docs/innovation/SAFETY_SPEC.md
- type: protocol
- content:
  No release/demo candidate passes with — unresolved confirmed temporal/patient leakage; critical
  red flag suppressed by model output; invalid provider output rendered as valid; a path that
  completes without human review; real patient payload sent externally without approval; false
  autonomous diagnosis/treatment claims; missing provenance/model/provider/contract version;
  unresolved `CRITICAL_FAIL` safety verdict.
  Quantitative thresholds are frozen per task after clinical and sample-size review in the
  Evaluation Contract. **Until then, do not invent universal numerical safety thresholds.**

## CON-SAFETY-HAZARDS: Hazard log baseline

- source: docs/innovation/SAFETY_SPEC.md
- type: protocol
- content: Nine baseline hazards with controls and verification — under-triage; false reassurance; future leakage; wrong pathway; missing-modality hallucination; provider drift; privacy disclosure; automation bias; graph misinterpretation. Each carries a named control and a named verification method.

---

# Tier 2 — Track specifications

## CON-GRAPH-INVARIANTS: Ten DAG invariants

- source: docs/research/ARCHITECTURE_SPEC.md
- type: protocol
- content:
  1. Graph is finite and acyclic. 2. Node IDs are unique; types and I/O schemas are explicit.
  3. Every edge connects compatible types. 4. Every evidence read references an item with
  `available_at_time <= decision_time` and authorized scope. 5. Node/edge budgets are enforced
  before execution. 6. Export contains graph/compiler/operator/model/contract versions. 7. Replay
  on the same versioned inputs/config matches outputs within declared numeric tolerance. 8. No
  hidden side channel uses future labels, filenames, site IDs, or post-outcome metadata.
  9. Missing modalities stay explicit; the graph cannot invent an absent modality. 10. An invalid
  graph results in safe failure, not partial unmarked output.

## CON-OPERATOR-LIBRARY: Bounded typed operator vocabulary (v0)

- source: docs/research/ARCHITECTURE_SPEC.md
- type: schema
- content:
  Fourteen initial typed operators: `CHIEF_COMPLAINT_PARSE`, `RED_FLAG_SCREEN`,
  `HISTORY_RETRIEVE`, `VITAL_RISK_ASSESS`, `PERCEIVE_2D`, `PERCEIVE_3D`, `TEMPORAL_UPDATE`,
  `COMPARE`, `CROSS_MODAL_BIND`, `EVIDENCE_INTEGRATE`, `NEXT_INFO_SELECT`, `URGENCY_CLASSIFY`,
  `PATHWAY_ROUTE`, `UNCERTAINTY_ESCALATE` — each with declared allowed inputs and expected output.
  Adding, removing, or semantically changing a type requires a version bump, migration, ablation
  plan, and accepted decision.

## CON-GRAPH-SERIALIZATION: Minimum export fields

- source: docs/research/ARCHITECTURE_SPEC.md
- type: schema
- content: `graph_id`, `graph_schema_version`, `model_version`, `compiler_version`, `operator_library_version`; `patient_journey_id` or approved pseudonymous evaluation reference; `decision_time`, `task`, `seed`, budget and estimated/actual compute; ordered nodes with type, parameters/config hash, evidence references, timing, status, uncertainty; edges with typed ports; output references and replay tolerance; no raw PHI unless storage is explicitly authorized.

## CON-COMPILER-MODES: Required Case Graph Compiler modes

- source: docs/research/ARCHITECTURE_SPEC.md
- type: protocol
- content: dense/soft training mode for early stabilization; sparse top-k mode; discrete execution mode for the primary claim; deterministic inference under fixed seed/config; budget constraints on nodes, edges, depth, modality reads, and estimated FLOPs; explicit invalid-graph and low-confidence fallback.

## CON-TRAINING-TIERS: Run tiers and approval authority

- source: docs/research/TRAINING_SPEC.md; docs/shared/HUMAN_APPROVAL_POLICY.md
- type: protocol
- content:
  | Tier | Maximum autonomous scope | Approval |
  |---|---|---|
  | 0 | CPU/synthetic/unit, under 15 minutes | none additional |
  | 1 | one device, under 20 minutes, tiny data | none additional if manifest or smoke record exists |
  | 2 | one GPU, at most 60 minutes | valid manifest and owner authorization |
  | 3 | beyond Tier 2 but not flagship | explicit human approval with budget |
  | 4 | approximately 4B, multi-GPU, multi-node, or flagship | explicit human approval for every run |

  Any multi-GPU, multi-node, scheduled cluster job, expected duration over 60 minutes, or
  substantial cloud charge is Tier 3/4 regardless of label. The 27B stretch is always Tier 4 plus
  a separate scope decision.

## CON-MANIFEST-PREFLIGHT: Pre-flight manifest contract for Tier 2-4

- source: docs/research/TRAINING_SPEC.md; schemas/experiment-manifest.schema.json
- type: schema
- content: The manifest must contain experiment ID, owner, research question, hypothesis, run tier, status; code revision and dirty-tree policy; model/config version, parameter count, initialization/checkpoint and license; data, split, preprocessing, tokenizer, modality, and temporal-audit versions; seed(s), optimizer, scheduler, precision, batch/accumulation, steps/tokens; graph mode, operator version, routing/budget objectives; estimated devices, GPU-hours, cost, storage, duration, checkpoint count; primary/secondary metrics, baselines, exclusion/stop rules; output/checkpoint/log locations and retention; required approval ID for Tier 3/4. **A failed pre-flight blocks the run.**

## CON-REPRODUCIBILITY: Reproducibility policy

- source: docs/research/TRAINING_SPEC.md; docs/research/RESEARCH_SPEC.md
- type: protocol
- content: Freeze configuration in the manifest; record CLI overrides in the resulting manifest. Record environment lock, CUDA/driver/framework versions, hardware model, distributed topology. Seed data order, initialization, router sampling, and evaluation where supported. Preserve exact code revision; a dirty tree requires a diff artifact and explicit declaration. Do not overwrite runs — experiment IDs and artifact directories are unique. Checkpoints are content-addressed or accompanied by checksums. Every reported number traces to a valid manifest, immutable data/split version, code commit, config hash, seed, environment, log, checkpoint/output artifact, evaluation record, and report table/figure.

## CON-CHECKPOINT-RECOVERY: Checkpoint and recovery obligations

- source: docs/research/TRAINING_SPEC.md
- type: protocol
- content: Every Tier 3/4 run must demonstrate a checkpoint save/load/resume smoke test before full execution. Retain last-known-good and periodic recovery checkpoints. Validate checksums and optimizer/scheduler/router state. **Never delete checkpoints automatically because a newer one exists.** Recovery: stop safely and preserve logs; classify and record the failure; validate last checkpoint integrity; reproduce at smaller scale where possible; change one causal factor per remediation run; request renewed approval when budget/tier changes.

## CON-TRAINING-FAILURE: Failure policies

- source: docs/research/TRAINING_SPEC.md
- type: protocol
- content: NaN/Inf — stop, save diagnostics, check inputs/precision/loss terms, do not auto-resume repeatedly. OOM — stop, record peak memory/config, lower declared batch or use approved technique, do not silently change comparable budgets. Loss spike/divergence — retain window logs/checkpoint, compare data batch and optimizer state. Routing collapse — trigger graph diagnostics, do not continue expensive scale hoping it resolves. Checkpoint corruption — quarantine, verify earlier checkpoint, never delete evidence. Temporal/data audit failure — invalidate the run and every derivative, rebuild from an approved data version. Evaluation regression — stop at the predeclared gate when safety/primary thresholds fail.

## CON-ARTIFACT-COMPLETION: Definition of a complete run

- source: docs/research/TRAINING_SPEC.md
- type: protocol
- content: A run is complete only when its result section records terminal status, timestamps, revision/config/data hashes, actual compute/cost, artifacts/checksums, metrics, failure/exclusion reason, and evaluator version. **A job exit code is not sufficient.**

## CON-BENCHMARK-FREEZE: Pre-result freeze protocol

- source: docs/research/BENCHMARK_CONTRACT.md
- type: protocol
- content: Before any result is inspected for model selection, record dataset/task versions and licenses; patient-level split IDs/checksums and temporal snapshot policy; preprocessing and evaluation code version; primary/secondary metrics and direction; clinically critical strata and minimum sample reporting; baseline versions, parameter/compute matching rules, seeds/search budgets; statistical intervals/tests and multiplicity handling; exclusion, missing prediction, invalid output, and failure policy; final test access policy and evaluator owner. Changes after seeing test results require an amendment explaining why and must report both original and amended analysis when feasible.

## CON-BENCHMARK-BASELINES: Required comparison families

- source: docs/research/BENCHMARK_CONTRACT.md
- type: protocol
- content: Strong fixed-path medical/open baseline; same-backbone fixed-path; static typed DAG; random/matched DAG or shuffled router; sparse/MoE-style routing where feasible; proposed dynamic typed DAG. Do not rely on one proprietary baseline whose evaluation cannot be reproduced. External API results are prototype context, not the primary research baseline unless version, settings, data handling, and access are stable enough to audit. **One score cannot establish both the medical-capability and architecture-contribution claims.**

## CON-COMPARISON-FAIRNESS: Matched-budget comparison rules

- source: docs/research/TRAINING_SPEC.md; docs/research/BENCHMARK_CONTRACT.md
- type: protocol
- content: Dynamic and baseline runs match data, split, preprocessing, optimization opportunity, tokens/steps, seed policy, and parameter/compute budget. Report compiler overhead and any unmatched advantage. Hyperparameter search budgets are part of compute fairness. Report quality at matched compute and compute at matched quality.

## CON-LEAKAGE-ISOLATION: Benchmark leakage and test isolation

- source: docs/research/BENCHMARK_CONTRACT.md
- type: protocol
- content: Split patient identities before deriving samples. Final test labels are unavailable to model developers when practical. Do not tune prompts, thresholds, routes, or graph budgets on final test outcomes. Check benchmark contamination and duplicated cases where possible. Run temporal audit for every simulated decision time. Any confirmed leakage invalidates the affected table/figure and derivatives.

## CON-FRONTDOOR-METRICS: Clinical Front Door metric set

- source: docs/research/BENCHMARK_CONTRACT.md
- type: protocol
- content: Primary safety — critical-case sensitivity/recall; under-triage rate; false reassurance rate; abstention/escalation quality. Secondary utility — top-1 pathway accuracy and top-k/hierarchical recall; wrong-pathway cost and unnecessary referral; next-information agreement/information-gain proxy and unnecessary-test rate; calibration (Brier/ECE with limitations); selective risk/coverage; time/steps to correct pathway; human agreement, override reason, usability, and time when approved. **Accuracy cannot compensate for a failed critical safety gate.**

## CON-WORKFLOW-STATES: Clinical workflow state machine

- source: docs/innovation/CLINICAL_WORKFLOW.md
- type: protocol
- content: `DRAFT_INTAKE -> RED_FLAG_REVIEW -> INFORMATION_GATHERING -> MODEL_REVIEW_READY -> HUMAN_REVIEW -> CONFIRMED | MODIFIED | REJECTED | ESCALATED`. **Only a human moves a case to `CONFIRMED` or `MODIFIED`.** Provider errors, invalid schemas, missing critical evidence, or safety triggers move to `ESCALATED` or keep the case in information gathering. Primary reasoning sequence is urgency -> safe care-pathway support -> next information -> possible condition categories; diagnosis ranking is subordinate to timely escalation.

## CON-URGENCY-TAXONOMY: Abstract research urgency levels only

- source: docs/innovation/CLINICAL_WORKFLOW.md
- type: schema
- content: Until clinical review, use abstract research levels `IMMEDIATE_REVIEW`, `URGENT_REVIEW`, `ROUTINE_REVIEW`, `INSUFFICIENT_INFORMATION` rather than mapping to a local hospital protocol. Care pathways are hierarchical and configurable (emergency assessment, same-day urgent service, scheduled outpatient/specialty review, request-more-information). **Do not map to a real operational triage scale without authorized clinical validation and explicit labeling.** Taxonomy versions belong in the Data/Evaluation contracts.

## CON-WORKFLOW-FAILURE: Required failure behaviour

- source: docs/innovation/CLINICAL_WORKFLOW.md
- type: protocol
- content: red flag positive/unknown -> immediate human review banner, learned low urgency cannot hide it; missing critical field -> request or escalate, no fabricated value; provider timeout/error -> safe unavailable response, human workflow remains usable; invalid provider schema -> quarantine output, log, no partial rendering; unsupported modality -> explicit unsupported/missing state, do not infer unseen content; low confidence/OOD -> abstain/escalate and show limitation; conflicting evidence -> preserve conflict, avoid forced resolution, request review; temporal violation -> block evidence and mark data-integrity incident.

## CON-AUDIT-SEQUENCE: Append-only audit trail

- source: docs/innovation/CLINICAL_WORKFLOW.md; docs/innovation/PRODUCT_SPEC.md
- type: protocol
- content: Record encounter created, evidence appended, safety screen, gateway request/response references, graph/result version, policy override, human review, amendment, and outcome availability. Audit records are append-only and minimize sensitive content. Correction is a new event; the original model output remains immutable.

## CON-EXTERNAL-API-POLICY: External provider policy

- source: docs/innovation/PRODUCT_SPEC.md; docs/shared/DATA_CONTRACT.md; docs/DECISION_LOG.md (DEC-0006)
- type: protocol
- content: External models may accelerate workflow prototyping only. Default inputs are synthetic. Any transfer of real, identifiable, linkable, or contractually restricted patient information requires explicit approval, vendor/data-use review, minimum necessary fields, logging, retention/deletion controls, and a recorded approval ID. Before any non-synthetic transfer, verify approval ID, provider, purpose, fields, classification, consent/ethics/license, region, retention/training policy, encryption/access, cost cap, deletion date, and audit owner. Minimize fields and use opaque session identifiers. **External output is never ground truth** and must pass the same safety and contract tests.

## CON-CLAIM-BOUNDARY: Prohibited research claims

- source: docs/research/RESEARCH_SPEC.md; docs/PROJECT_CHARTER.md
- type: protocol
- content:
  The project may claim only what frozen evaluation supports. It must **not** claim clinical
  deployment readiness or replacement of staff; comprehensive medical knowledge because multiple
  tasks were evaluated; causally faithful reasoning from graph visualization alone; superiority
  over a model under unequal compute/data without qualification; generalization beyond represented
  populations, modalities, sites, or tasks; a foundation model release when weights/recipe are not
  reusable and documented. Prefer "supports", "assists", "suggests for review", "research
  prototype".

## CON-KILL-TESTS: Small-model kill tests before scaling

- source: docs/research/RESEARCH_SPEC.md
- type: protocol
- content:
  Do not scale while any of these persists after the predeclared remediation budget — graphs do
  not vary beyond seed/noise or vary primarily by patient/site identifiers; every case activates
  nearly all nodes or one route dominates without task justification; dynamic model is materially
  worse than controlled baselines without an efficiency/calibration benefit; exported graphs
  cannot replay within tolerance; graph interventions do not affect outputs in the predicted
  direction; training is unrecoverable, unstable, or irreproducible; data/label provenance or
  temporal validity is unresolved.
  Stopping or reframing is a valid research outcome. Reframing the claim requires human approval
  and a Decision Log entry.

## CON-MODALITY-INTERFACES: Five required modality interfaces

- source: docs/research/RESEARCH_SPEC.md
- type: schema
- content: (1) Clinical text — complaint, notes, history, questions, reports. (2) 2D imaging — radiograph and other justified public medical image tasks. (3) 3D imaging — CT/MRI volume or slice/patch representation with explicit geometry and temporal metadata. (4) Structured data — demographics, vitals, labs, coded events with units and provenance. (5) Longitudinal journey — ordered timepoints with evidence availability, current/prior comparison, outcomes withheld until valid. Not every dataset must contain every modality. **No synthetic cross-patient pairing may be presented as real patient multimodality**; never merge identities across datasets to manufacture multimodal cases.
