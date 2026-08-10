# Model API Contract

**Owners:** Supreeya Nuamkhayan and Thanapol Popit  
**Safety reviewer:** Thanrada Tungweerapornpong  
**Version:** 1.0.0  
**Schemas:** `schemas/model-api-request.schema.json`, `schemas/model-api-response.schema.json`

## Boundary

Every provider - mock, external prototype, baseline, or team model - implements this contract through the Model Gateway. Clients never import provider SDK types or parse provider-native text. The gateway validates, normalizes, times, budgets, and audits requests/responses.

## Request

Required fields:

- `contract_version`, `request_id`, `journey_id`, `decision_time`, `task`;
- `evidence`: authorized references or approved inline synthetic values, each with `evidence_id`, type, modality, and `available_at_time`;
- `missing_information`: explicit status without future values;
- `requested_outputs`;
- `authorization`: data classification, external-provider permission, and approval ID when applicable;
- `provider_constraints`: timeout, maximum output, cost/budget class, deterministic preference.

The gateway rejects duplicate IDs, unsupported contract version, evidence after decision time, prohibited classification/provider combination, missing authorization, or malformed modality metadata.

## Response

Required fields:

- `contract_version`, `request_id`, `response_id`, `provider`, `model_version`;
- `status`: `COMPLETED`, `ABSTAINED`, `ESCALATED`, or `FAILED_SAFE`;
- `urgency`: abstract versioned level, confidence if meaningful, and evidence references;
- `red_flags`: triggered/unknown flags and evidence references;
- `care_pathways`: ranked candidates with normalized code, confidence/score semantics, evidence references;
- `next_information`: ranked information types with reason codes;
- `uncertainty`: calibration method/version if applicable, limitations, OOD/unsupported, abstention reason;
- `human_review`: always `required: true` with permitted actions;
- `graph`: schema/version/reference or inline safe typed structure for providers that support it;
- `provenance`: request/input checksum, model/config/provider versions, started/completed times, policy version;
- `errors`: structured safe errors, empty on successful response.

No response may contain a field asserting autonomous action or hidden chain-of-thought.

## Error behavior

| Code | Meaning | Gateway behavior |
|---|---|---|
| `INVALID_REQUEST` | schema/contract violation | reject before provider; record safe error |
| `TEMPORAL_VIOLATION` | evidence is future to decision | block; data-integrity escalation |
| `UNAUTHORIZED_DATA` | provider/classification not approved | block; privacy escalation |
| `UNSUPPORTED_MODALITY` | provider cannot use evidence | abstain or route approved fallback explicitly |
| `PROVIDER_TIMEOUT` | deadline exceeded | safe failure/escalation; no hidden retry storm |
| `INVALID_PROVIDER_OUTPUT` | response fails contract | quarantine; never partially render |
| `BUDGET_EXCEEDED` | cost/token/time limit | safe failure; human decides retry |
| `LOW_CONFIDENCE` | policy threshold unmet | abstain/escalate |

Retries are idempotent, bounded, and audited. Switching providers is explicit in the audit record and never changes task semantics silently.

## Versioning

- Major: breaking field or semantic change.
- Minor: backward-compatible optional capability.
- Patch: clarification/validation fix.

Gateway supports an explicit compatibility matrix. Unknown major versions fail safe. Deprecations include migration, adapter fixtures, and a removal date approved through the Decision Log.

## Contract tests

Every adapter passes:

1. canonical valid request/response fixture;
2. missing modality and explicit unknown;
3. urgent red-flag case;
4. low-confidence abstention;
5. temporal violation rejection;
6. unauthorized external payload rejection;
7. timeout/provider error;
8. malformed output quarantine;
9. request idempotency;
10. no provider-native fields in client response.

Team-model integration is accepted only when it passes the same fixtures as the mock adapter.

