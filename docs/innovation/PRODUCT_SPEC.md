# Product Specification - AI Clinical Front Door

**Product owner:** Supreeya Nuamkhayan  
**Clinical workflow owner:** Jakkapat Bunjongruxsa  
**Safety/evaluation owner:** Thanrada Tungweerapornpong  
**Status:** research-prototype baseline

## Product statement

The AI Clinical Front Door is a supervised decision-support prototype that organizes progressively available patient information, screens for urgency/red flags, recommends a care pathway for clinician review, identifies the next useful information, represents uncertainty, and escalates when safety or evidence is insufficient.

It does not diagnose, treat, prescribe, discharge, or autonomously route a real patient.

## Care setting (DEC-0016)

The evaluated setting is the **first-contact triage station of a hospital emergency department**, before physician assessment: adults 18+, non-trauma, non-obstetric. Arrival mode is a recorded stratum, not an inclusion criterion.

Two decision moments are supported and reported separately. **T0** is the earliest time at which a chief complaint and a first vital set are both available — which is exactly what `REQUIRED_FRONT_DOOR_EVIDENCE` already encodes in `innovation/gateway/safety.py`, so the minimum intake *is* T0. **T1** is the earliest time a first laboratory result or imaging report becomes available, capped at T0 + 120 minutes.

Input from outside the setting — paediatric age, trauma mechanism, prehospital origin — is an out-of-distribution condition and abstains or escalates rather than being scored.

## Users

- supervised triage nurse or intake staff **at the emergency-department first-contact triage point**, in a simulated/research workflow;
- clinician reviewing recommendations and overrides;
- evaluator examining safety, agreement, timing, and failure cases;
- researcher inspecting executed graph and model/provider behavior.

Patient-facing direct use and production clinical deployment are outside this project unless separately governed.

## Jobs to be done

1. Capture a chief complaint and known context without forcing a disease-specific form.
2. Show immediately available red flags and missing critical information.
3. Ask/rank the next useful questions or evidence items.
4. Update the state when vitals, labs, ECG, images, or prior records become available — the T0 to T1 transition, and the reason `available_at_time` is a sequence rather than a single filter.
5. Support urgency and care-pathway selection across multiple disease systems.
6. Express uncertainty and abstain/escalate safely.
7. Let a human confirm, modify, reject, or request more information with a reason.
8. Preserve an auditable history of evidence availability, provider/model version, outputs, safety overrides, and human actions.

## Supported output contract

The UI renders only fields from `MODEL_API_CONTRACT.md`:

- urgency level and calibrated confidence;
- red flags and critical-condition categories not to miss;
- ranked care pathways;
- next-information candidates;
- uncertainty, abstention, and escalation state;
- safe evidence references and executed DAG summary;
- limitations and required human review.

It must not render raw hidden chain-of-thought or convert a ranked candidate into a factual diagnosis.

## Architecture

```text
Client/UI
   |
Front Door API ---- Audit Store
   |
Safety/Policy Layer
   |
Model Gateway (stable contract)
   |-- Mock provider
   |-- Authorized external prototype provider
   |-- Reproducible baseline provider
   `-- Team Medical-DAG provider
```

Provider SDK types, tokens, errors, and prompts remain inside adapters. The gateway validates input/output, deadlines, retries, budgets, redaction, and provenance. A provider failure returns a contract error and safe escalation; no client fallback may silently alter semantics.

## Core screens

### Intake

Chief complaint, symptom timing, demographics permitted by study, relevant history, medication/allergy summary, risk factors, source, and consent/authorization context. Required fields are minimal; missingness is explicit.

### Adaptive interview

Displays one or a small ranked set of next questions, why each information category is needed, what is already known, and a skip/not-known option. It must not coerce answers or imply a diagnosis.

### Clinical dashboard

Urgency, red flags, pathway candidates, information gaps, uncertainty/abstention, evidence timeline, provider/model version, limitations, and prominent human-review control.

### DAG explorer

Shows typed executed nodes/edges, modality/evidence references, status, compute/timing, and graph changes across timepoints. It does not display private reasoning text.

### Human confirmation

Confirm, modify, reject, request information, or escalate. Overrides require a structured reason; the original output remains immutable in the audit trail.

## Non-functional requirements

- Contract validation on every boundary.
- Deterministic synthetic fixtures for tests and demos.
- Provider timeout and circuit breaker with safe escalation.
- Idempotency for encounter/timepoint submissions.
- Role-based access and minimum data display in any approved data environment.
- Immutable audit event sequence; correction is a new event.
- Accessible UI: keyboard navigation, readable contrast, no color-only urgency signal.
- Latency reported by provider and end-to-end; no invented real-time clinical SLA.
- Backup demo works without network/external API.

## External API policy

External models may accelerate workflow prototyping only. Default inputs are synthetic. Any transfer of real, identifiable, linkable, or contractually restricted patient information requires explicit approval, vendor/data-use review, minimum necessary fields, logging, retention/deletion controls, and a recorded approval ID. External output is never ground truth and must pass the same safety and contract tests.

## Product analytics for the study

Record completion/abandonment, steps to pathway, time, missingness, model/provider failures, safety overrides, human agreement/override/rejection, and structured reasons. Do not implement surveillance or collect data unrelated to research questions.

## Release stages

1. Contract and synthetic CLI fixture.
2. Mock-provider clickable prototype.
3. Product alpha with audit/human confirmation and safe failure.
4. Authorized external/baseline provider adapter.
5. Team-model adapter with identical contract tests.
6. Simulated evaluation and product beta.
7. Final integrated demo and reproducibility package.

