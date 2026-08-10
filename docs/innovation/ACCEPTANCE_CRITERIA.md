# Innovation Acceptance Criteria

## A0 - Contract prototype

- [ ] Valid synthetic Patient Journey creates a versioned gateway request.
- [ ] Mock provider returns a response that validates against the Model API schemas.
- [ ] Invalid/future/unauthorized evidence is blocked.
- [ ] All events include safe audit metadata.

## A1 - Usable supervised flow

- [ ] Intake captures known, unknown, refused, and unavailable information distinctly.
- [ ] Red-flag screen runs before learned inference.
- [ ] Next-information flow updates the decision snapshot without rewriting history.
- [ ] Dashboard separates urgency, pathway, information gaps, uncertainty, and critical categories.
- [ ] Human can confirm, modify, reject, request information, or escalate with a reason.
- [ ] Workflow cannot complete without human review.

## A2 - Provider independence

- [ ] Mock, external/baseline (if enabled), and team model implement the same gateway interface.
- [ ] Provider-specific fields/errors do not escape adapters.
- [ ] Shared contract fixtures pass for each enabled adapter.
- [ ] Timeout, invalid schema, rate/cost limit, and unavailable provider fail safely.
- [ ] Offline mock demo requires no network.

## A3 - Safety and audit

- [ ] Research-prototype and human-review labels are prominent.
- [ ] Model cannot downgrade deterministic red-flag escalation silently.
- [ ] Missing/unsupported modalities remain explicit.
- [ ] Abstention and low-confidence states are actionable.
- [ ] Original model output and later human actions remain immutable audit events.
- [ ] External API payload tests prove synthetic/authorized content policy.
- [ ] Accessibility checks cover keyboard, contrast, focus, and non-color urgency.

## A4 - Evaluation readiness

- [ ] Frozen simulated case set covers multiple systems, urgency, missingness, contradiction, and provider failure.
- [ ] Urgency, critical-case, pathway, next-information, calibration/abstention, timing, and human override metrics are implemented.
- [ ] Patient-level and temporal integrity audits pass.
- [ ] Independent safety and integration reviewers issue no unresolved critical failure.

## A5 - Research-model integration

- [ ] Team model adapter passes the same fixtures as mock provider.
- [ ] `model_version`, `contract_version`, `graph_schema_version`, evidence references, and uncertainty are displayed/logged.
- [ ] Provider swap requires configuration only, not client/UI logic changes.
- [ ] Graph explorer displays executed typed structure and does not expose hidden chain-of-thought.

## A6 - Final demonstration

- [ ] Demonstrate at least one evolving patient journey from intake through human review.
- [ ] Demonstrate urgent escalation, missing-information/abstention, and provider failure.
- [ ] Compare mock/baseline/team providers without changing clients.
- [ ] Present limitations and non-deployment boundary.
- [ ] Primary and offline backup demos are rehearsed.
- [ ] Reproduction instructions, fixtures, versions, and expected outputs are archived.

## Rejection conditions

Any autonomous clinical action, unapproved real-patient external transfer, confirmed leakage, hidden red-flag suppression, missing human review, rendered invalid provider output, or unresolved `CRITICAL_FAIL` rejects the candidate regardless of feature completeness.
