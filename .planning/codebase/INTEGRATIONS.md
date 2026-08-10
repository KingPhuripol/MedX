# External Integrations

**Analysis Date:** 2026-08-11

## Current State

This repository contains **no implemented external integrations**. All systems described below are **specified in documentation but not yet coded**. The codebase uses only Python standard library utilities for governance and validation.

The project follows a strict principle: external integrations are specified in contracts first, then implemented behind stable gateway adapters. Clients and implementation code never directly import provider SDKs or use provider-specific types.

## APIs & External Services

### Specified for Implementation (Not Yet Coded)

**Medical Model Providers:**
- `docs/innovation/PRODUCT_SPEC.md` specifies a Model Gateway that will support:
  - Mock provider (deterministic synthetic responses; offline default)
  - Authorized external prototype provider (for accelerated prototyping with real patient data approval)
  - Team Medical-DAG provider (flagship multimodal model to be trained)
  - Reproducible baseline provider (comparison/ablation reference)

- All providers implement `docs/shared/MODEL_API_CONTRACT.md` (schemas at `schemas/model-api-request.schema.json`, `schemas/model-api-response.schema.json`)
- SDK types and vendor-specific logic remain inside provider adapters; client code uses only the contract
- **No external provider SDK is imported in current code** — the contract validation fixtures exist (`tests/fixtures/model_api/request.json`, `tests/fixtures/model_api/response.json`) but no adapter code

**Hugging Face Hub:**
- Mentioned in `docs/research/SUCCESS_CRITERIA.md` as a release target (G7 - Public release)
- **Status:** Planned for after model training and evaluation gates pass
- **Policy:** `docs/shared/HUMAN_APPROVAL_POLICY.md` requires explicit human approval before publishing model weights, data cards, or reports to public repositories

## Data Storage

### Databases (Specified, Not Implemented)

**Audit/Decision Store:**
- `docs/innovation/PRODUCT_SPEC.md` specifies "Audit Store" in the Front Door architecture; technology not yet selected
- Every decision must record: request_id, inputs (by safe reference), model/provider version, timestamp, human review action, override reason, outcome
- Requirement: Immutable append-only audit event sequence with correction as a new event
- **No ORM, connection pool, or storage backend currently exists**

**Patient Journey Longitudinal Storage:**
- `docs/shared/PATIENT_JOURNEY_SCHEMA.md` defines the schema (`schemas/patient-journey.schema.json`)
- Each journey contains timestamped events with evidence references and metadata
- **Test fixture exists:** `tests/fixtures/patient_journey/valid.json`; no production data store is integrated

### File Storage

**Datasets:**
- Raw/interim/processed data live in `data/raw/`, `data/interim/`, `data/processed/` (created by `scripts/bootstrap.sh`, currently empty)
- No cloud storage (S3, GCS) configured
- Specification: `docs/shared/DATA_CONTRACT.md` governs all data: classifications, temporal invariants, patient splits, evidence item structure, versioning
- **Checksums and content-addressed storage are required by spec** but not yet implemented

**Experiment Artifacts:**
- Checkpoints, logs, and model weights will store in `artifacts/experiments/` and `checkpoints/` (directories created by bootstrap; currently empty)
- **No storage backend configured.** Specification: `docs/research/TRAINING_SPEC.md` requires experiment manifests to declare checkpoint locations, retention, and checksums

**Caching:**
- None implemented
- Specification: `docs/shared/DATA_CONTRACT.md` mentions cache keys must include data/transform version and authorization scope

## Authentication & Identity

### Patient Identity Management (Specified, Not Implemented)

- **Requirement:** `docs/shared/DATA_CONTRACT.md` mandates stable `patient_id` assigned before deriving encounters/windows/images/text
- All encounters, modalities, and derivatives from one patient remain in exactly one split (train/validation/test/etc.)
- No authentication provider configured; identity is internal and governance-enforced at data preparation

### User Authorization (Specified, Not Implemented)

- **Role-based access:** `docs/innovation/PRODUCT_SPEC.md` requires role-based access for intake staff, clinicians, evaluators, researchers
- **Data authorization:** `docs/shared/MODEL_API_CONTRACT.md` requires every request to include authorization: data classification, external-provider permission, approval ID when applicable
- **External data policy:** `docs/shared/DATA_CONTRACT.md` forbids real/identifiable patient data to external APIs without explicit approval recorded under `docs/shared/HUMAN_APPROVAL_POLICY.md`
- No auth middleware, SSO, or RBAC system currently exists

### Human Approval Tracking (Specified, Not Implemented)

- Schema: `schemas/human-approval.schema.json`
- All Tier 3/4 training runs and publications require recorded approval via `project_state/approvals.json`
- **Requirement:** Approval must be recorded before execution; approval_ids are tied to scope (compute, data, release)
- No approval workflow platform configured

## Monitoring & Observability

### Error Tracking (Not Implemented)

- Specification: `docs/shared/MODEL_API_CONTRACT.md` defines error codes: `INVALID_REQUEST`, `TEMPORAL_VIOLATION`, `UNAUTHORIZED_DATA`, `UNSUPPORTED_MODALITY`, `PROVIDER_TIMEOUT`, `INVALID_PROVIDER_OUTPUT`, `BUDGET_EXCEEDED`, `LOW_CONFIDENCE`
- No error tracking service (Sentry, Bugsnag) integrated

### Logging (Not Implemented)

- **Requirement:** `docs/innovation/SAFETY_SPEC.md` requires structured audit logs: model/provider version, contract version, timestamps, inputs, outputs, overrides, reviewer identity
- **Specification:** `docs/shared/DATA_CONTRACT.md` Section "Data incident" requires preserve evidence safely, mark dependent manifests invalid, notify owners
- No logging framework currently configured; only stdout from Makefile tasks and Python scripts

### Metrics & Monitoring (Specified, Not Implemented)

- **Training monitoring:** `docs/research/TRAINING_SPEC.md` requires recording environment, CUDA/driver/framework versions, hardware model, distributed topology
- **Product analytics:** `docs/innovation/PRODUCT_SPEC.md` specifies recording completion/abandonment, steps to pathway, time, missingness, model/provider failures, safety overrides, human agreement/override/rejection
- No time-series database, monitoring dashboard, or telemetry client configured

## CI/CD & Deployment

### Continuous Integration (Not Implemented)

- No GitHub Actions, GitLab CI, or other CI service configured
- **Harness validation:** `scripts/verify_harness.py` validates project state on every session start (configured as `SessionStart` hook in `.claude/settings.json`)
- **Post-edit checks:** `.claude/hooks/post_edit_checks.py` validates Python syntax and JSON formatting after edits

### Deployment & Hosting (Not Implemented)

- **Specification:** `docs/innovation/PRODUCT_SPEC.md` mentions "Product alpha with audit/human confirmation" as a release stage, but no deployment target is configured
- **Model publishing:** `docs/research/SUCCESS_CRITERIA.md` G7 specifies Hugging Face Hub release; no deployment credentials or automation exist
- No cloud provider (AWS, GCP, Azure) credentials or infrastructure configured

### Secrets Management (Not Applicable)

- No external secrets stored in `.env` files (project_state, schemas, and docs are all committed to Git)
- **Policy:** CLAUDE.md forbids sending real patient data to external APIs without approval; approval records live in `project_state/approvals.json`
- Future credential storage will be governed by `docs/shared/HUMAN_APPROVAL_POLICY.md` before any external API integration

## Environment Configuration

**Required env vars:**
- None. The harness runs with only Git and Python 3.10+ in the environment
- Timezone is hardcoded as `Asia/Bangkok` in `project_state/official_deadlines.json` (immutable)
- No API keys, database URLs, or service credentials configured

**Secrets location:**
- Not applicable. No external services integrated.
- **Future policy:** `docs/shared/HUMAN_APPROVAL_POLICY.md` will govern approval IDs and credential storage when external services are added

## Webhooks & Callbacks

### Incoming (Not Implemented)

- No webhook endpoints specified
- **Future specification:** Clinical Front Door may accept asynchonous updates (new vital signs, lab results, ECG data)

### Outgoing (Not Implemented)

- No callbacks to external systems
- **Future specification:** Model Gateway may need to notify Audit Store, escalation systems, or provider monitoring

## Planned Integration Roadmap

From `docs/innovation/PRODUCT_SPEC.md` Section "Release stages":

1. ✓ Contract and synthetic CLI fixture (schema exists; fixture under `tests/fixtures/`)
2. Mock-provider clickable prototype (not yet built)
3. Product alpha with audit/human confirmation and safe failure (audit store unspecified)
4. Authorized external/baseline provider adapter (contract exists; adapter code not implemented)
5. Team-model adapter with identical contract tests (model training not yet started)
6. Simulated evaluation and product beta (evaluation framework not yet built)
7. Final integrated demo and reproducibility package

From `docs/research/ARCHITECTURE_SPEC.md`:

- Modality encoders (text, 2D, 3D, structured/temporal) — not yet implemented
- Evidence adapters for contract validation — specified in `schemas/model-api-request.schema.json` but no adapter code
- Case Graph Compiler — core AI logic; no implementation
- Typed operator library — defined vocabulary; no executable operators
- DAG executor with deterministic replay — core engine; no implementation
- Output/safety heads — task-specific; no implementation

## Cross-Component Integration

**Model Gateway (Core Boundary - Not Yet Implemented):**
- `docs/innovation/PRODUCT_SPEC.md` specifies the gateway as the single point where all provider SDKs are hidden
- Validates input/output, deadlines, retries, budgets, redaction, and provenance
- Ensures no client/UI code imports provider-native types or sees hidden chain-of-thought
- **Current state:** Contract defined; implementation is Phase 2-3 work

**Data Flow (Specified - Not Yet Wired):**

```
Patient Journey (timestamped events with evidence)
        ↓
Evidence Adapters (authorization + contract validation)
        ↓
Modality Encoders (text, 2D, 3D, structured tokens)
        ↓
Patient-State Workspace (bounded representation)
        ↓
Case Graph Compiler (task + availability → acyclic DAG)
        ↓
Typed Operator Library (diagnosis, risk, triage logic)
        ↓
DAG Executor (deterministic, auditable, budget-enforced)
        ↓
Task Output Heads (urgency, pathways, next-info)
        ↓
Safety Layer (red-flag override, escalation)
        ↓
Model Gateway Contract → Front Door API
        ↓
Audit Store + UI + Human Confirmation
```

None of these components currently exist in code; all are specified in `docs/research/ARCHITECTURE_SPEC.md`.

---

*Integration audit: 2026-08-11*
