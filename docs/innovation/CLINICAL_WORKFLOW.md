# Clinical Workflow Specification

**Owner:** Jakkapat Bunjongruxsa  
**Safety reviewer:** Thanrada Tungweerapornpong  
**Use:** simulated/research decision support only

## Workflow principle

The system reasons from the evidence available now, not the final chart. The primary sequence is urgency -> safe care-pathway support -> next information -> possible condition categories. Diagnosis ranking is subordinate to timely escalation.

## States

```text
DRAFT_INTAKE
  -> RED_FLAG_REVIEW
  -> INFORMATION_GATHERING
  -> MODEL_REVIEW_READY
  -> HUMAN_REVIEW
  -> CONFIRMED | MODIFIED | REJECTED | ESCALATED
```

Only a human moves a case to `CONFIRMED` or `MODIFIED`. Provider errors, invalid schemas, missing critical evidence, or safety triggers move to `ESCALATED` or keep the case in information gathering.

## End-to-end flow

### 1. Create encounter simulation

Create stable pseudonymous patient/encounter/journey IDs, authorization context, encounter start, and decision time. Never use name, phone, national ID, or raw medical-record number in external-provider fixtures.

### 2. Capture initial complaint

Record patient-reported text, source, language, time observed, time available, and uncertainty. Do not normalize away qualifiers such as onset, severity, negation, or who reported the information.

### 3. Deterministic safety screen

Run versioned red-flag and required-information rules before learned inference. A positive or unknown critical rule produces conservative escalation for review; the model may add context but cannot suppress the rule silently.

### 4. Adaptive information gathering

Rank questions/evidence categories using current information only. Examples include symptom characteristics, vitals, relevant history, medication/allergy, ECG/lab/imaging categories. The system recommends information, not an autonomous test order.

Every candidate includes:

- normalized information type;
- reason code tied to an uncertainty or pathway distinction;
- expected usefulness/confidence where supported;
- availability/authorization constraint;
- urgency prerequisite if waiting would be unsafe.

### 5. State update

Append new evidence as an immutable event with `observed_at` and `available_at_time`. Re-evaluate at a new `decision_time`. Preserve prior outputs and graph to show how evidence changed the recommendation.

### 6. Model/policy output

Return versioned urgency, red flags, critical categories, pathways, next information, uncertainty, escalation, limitations, and executed graph reference. If required fields are missing or the provider is unavailable, return a safe error/abstention contract.

### 7. Human review

The reviewer sees the evidence timeline, current output, safety rules, model/provider version, and limitations. They may confirm, change urgency/pathway, request information, reject, or escalate. They record a reason and identity/role approved for the study.

### 8. Outcome and retrospective labels

Final diagnosis, disposition, intervention, deterioration, or outcome may be appended later with their true availability. They may evaluate earlier decisions but must never enter the model input for those earlier snapshots.

## Representative multi-system scenarios

The initial evaluation set should include, subject to data/clinical review:

- chest pain with cardiac, pulmonary, gastrointestinal, musculoskeletal, and uncertain/urgent patterns;
- shortness of breath across cardiopulmonary and systemic causes;
- abdominal pain across medical/surgical/uncertain pathways;
- neurological symptom with time-sensitive red flags;
- fever/systemic symptoms with high-risk and low-risk patterns;
- missing-modality and contradictory-evidence cases.

These are scenario categories, not claims that the system diagnoses these conditions.

## Urgency and pathway taxonomy

Taxonomy versions belong in the Data/Evaluation contracts. Until clinical review, use abstract research levels (`IMMEDIATE_REVIEW`, `URGENT_REVIEW`, `ROUTINE_REVIEW`, `INSUFFICIENT_INFORMATION`) rather than mapping to a local hospital protocol. Care pathways are hierarchical and configurable, such as emergency assessment, same-day urgent service, scheduled outpatient/specialty review, or request-more-information.

Do not map to a real operational triage scale without authorized clinical validation and explicit labeling.

## Failure handling

| Failure | Required behavior |
|---|---|
| red flag positive/unknown | immediate human review banner; learned low urgency cannot hide it |
| missing critical field | request or escalate; no fabricated value |
| provider timeout/error | safe unavailable response; human workflow remains usable |
| invalid provider schema | quarantine output; log; no partial rendering |
| unsupported modality | explicit unsupported/missing state; do not infer unseen content |
| low confidence/OOD | abstain/escalate and show limitation |
| conflicting evidence | preserve conflict, avoid forced resolution, request review |
| temporal violation | block evidence and mark data-integrity incident |

## Audit sequence

Record encounter created, evidence appended, safety screen, gateway request/response references, graph/result version, policy override, human review, amendment, and outcome availability. Audit records are append-only and minimize sensitive content.

