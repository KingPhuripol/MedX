# Innovation Acceptance Criteria

**Status as of 30 Aug 2026:** A0–A4 closed on the mock and baseline adapters.
A5 cannot start — no team model exists, the Research track has no code. A6 is end-of-project.
Evidence: `make smoke` (222 tests), `make eval` (EVAL-0001), `make demo`.

## A0 - Contract prototype — CLOSED

- [x] Valid synthetic Patient Journey creates a versioned gateway request. — `shared/contracts/`, `innovation/frontdoor/service.py`
- [x] Mock provider returns a response that validates against the Model API schemas. — `tests/test_contracts.py`
- [x] Invalid/future/unauthorized evidence is blocked. — blocked *before* the provider; the temporal test uses a tripwire adapter that fails if reached
- [x] All events include safe audit metadata. — `innovation/gateway/audit.py`; a test asserts no payload text reaches the trail

## A1 - Usable supervised flow — CLOSED

- [x] Intake captures known, unknown, refused, and unavailable information distinctly. — four schema statuses, one per state; `tests/test_intake.py`
- [x] Red-flag screen runs before learned inference. — `SafetyPolicy.screen()`; a provider that clears every flag cannot lower the screen's finding
- [x] Next-information flow updates the decision snapshot without rewriting history. — append-only; earlier recommendations keep the evidence they saw
- [x] Dashboard separates urgency, pathway, information gaps, uncertainty, and critical categories. — `/ui/recommendations/{id}`, one section each
- [x] Human can confirm, modify, reject, request information, or escalate with a reason. — structured `reason_code` required for MODIFY and REJECT
- [x] Workflow cannot complete without human review. — `act_on()` raises until confirmed; `human_review.required` asserted on every response path

## A2 - Provider independence — CLOSED for enabled adapters

- [x] Mock and baseline implement the same gateway interface. Team model pending A5.
- [x] Provider-specific fields/errors do not escape adapters. — the gateway builds the response; response models forbid unknown fields
- [x] Shared contract fixtures pass for each enabled adapter. — `ADAPTERS` parametrisation, 21 cases per provider, verified by collecting test IDs
- [x] Timeout, invalid schema, rate/cost limit, and unavailable provider fail safely. — real deadline enforcement plus a circuit breaker
- [x] Offline mock demo requires no network. — `make demo`

## A3 - Safety and audit — CLOSED

- [x] Research-prototype and human-review labels are prominent. — banner on every screen and in every API payload
- [x] Model cannot downgrade deterministic red-flag escalation silently. — merge keeps the more severe state; parametrised test over every level and flag state
- [x] Missing/unsupported modalities remain explicit. — `UNSUPPORTED_MODALITY` surfaced, never ignored
- [x] Abstention and low-confidence states are actionable. — SR-004/SR-005 escalate and say why
- [x] Original model output and later human actions remain immutable audit events. — database triggers abort on UPDATE and DELETE across all five tables
- [x] External API payload tests prove synthetic/authorized content policy. — restricted classifications refused without a recorded approval; non-synthetic journeys refused at 403
- [x] Accessibility checks cover keyboard, contrast, focus, and non-color urgency. — measured in a browser: lowest contrast 8.95:1, 0 of 8 controls off the tab order, urgency carries text + glyph + border

## A4 - Evaluation readiness — CLOSED except the independent review

- [x] Frozen simulated case set covers multiple systems, urgency, missingness, contradiction, and provider failure. — 12 cases, 9 scenarios, `tests/fixtures/cases/`
- [x] Urgency, critical-case, abstention, and human-override metrics are implemented. — 8 metrics, definitions frozen before the first run, no pass/fail threshold (SAFETY_SPEC forbids inventing one)
- [x] Patient-level and temporal integrity audits pass. — `temporal_violation_rate` 0.0; `make leakage-fixture`
- [ ] **Independent safety and integration reviewers issue no unresolved critical failure.** — not started. `clinical-safety-reviewer` and `integration-auditor` are read-only reviewers and must not review work they wrote, so this cannot be self-certified.

**Result on the mock adapter (EVAL-0001):** under-triage 0.0, critical-case sensitivity 1.0,
human-review-required 1.0, temporal violations 0.0, safe failure 1.0 — and **escalation 0.83**.

That last number is the honest one. The system escalates five cases in six. It is safe and
close to useless, which is exactly why escalation rate is reported beside under-triage: a
system that escalates everything scores perfectly on the primary safety metric. It reflects
a mock provider that cannot read a complaint, and it is the bar the case-adaptive model has
to beat.

## A4.1 - Evaluation readiness in the committed setting — REOPENED 7 Sep

A4 was closed on a 12-case set that contains **no `IMMEDIATE_REVIEW` and no `ROUTINE_REVIEW`
expectation**. DEC-0016 names the care setting and reopens the question, and tracing the screen showed
the problem is structural rather than a shortage of cases (RISK-0015).

- [ ] `over_triage_rate` is defined and frozen **before** any new run. `EVALUATION_CONTRACT.md` requires metrics frozen before results are inspected; adding one after seeing 0.83 would be metric-shopping.
- [ ] Cases carry a declared band (`expected_maximum_urgency` beside `expected_minimum_urgency`), a `care_setting`, and a presentation type.
- [ ] The set exercises all four urgency levels, carries a T1 snapshot of one patient, and contains at least one out-of-setting case whose correct answer is abstain-or-escalate.
- [ ] EVAL-0002 is recorded beside a preserved, unmodified EVAL-0001, and the escalation change is reported **with its cause named**.

**Why the number is expected to get worse.** `SCR-002` raises `COMPLAINT_NOT_EVALUATED_BY_RULE` as
`UNKNOWN` for every request carrying a chief complaint and `SR-002` escalates any `UNKNOWN`, so every
complaint-bearing case escalates by construction, independently of content. `IMMEDIATE_REVIEW` is
reachable only through a `TRIGGERED` flag, and the only one produced anywhere is missing required
evidence — so the top level is reachable only through absent information, never clinical severity, and
neither provider ever emits `TRIGGERED`. Adding routine cases therefore cannot make the set
discriminate; it makes the failure **visible and measured**, which is the point. Making the levels
reachable is TASK-0033, deliberately scheduled after the Proposal.

## A5 - Research-model integration — BLOCKED on the model, groundwork done

- [ ] Team model adapter passes the same fixtures as mock provider. — **no model exists**; the Research track has no code. Adding it is an entry in `ADAPTERS` plus one in the registry.
- [x] `model_version`, `contract_version`, `graph_schema_version`, evidence references, and uncertainty are displayed/logged. — dashboard provenance table and audit record
- [x] Provider swap requires configuration only, not client/UI logic changes. — `FRONT_DOOR_PROVIDER` env var; verified by swapping mock and baseline with no code change
- [x] Graph explorer displays executed typed structure and does not expose hidden chain-of-thought. — `/ui/recommendations/{id}/graph`; a test asserts no reasoning field appears

## A6 - Final demonstration

- [ ] Demonstrate at least one evolving patient journey from intake through human review.
- [ ] Demonstrate urgent escalation, missing-information/abstention, and provider failure.
- [ ] Compare mock/baseline/team providers without changing clients.
- [ ] Present limitations and non-deployment boundary.
- [ ] Primary and offline backup demos are rehearsed.
- [ ] Reproduction instructions, fixtures, versions, and expected outputs are archived.

## Rejection conditions

Any autonomous clinical action, unapproved real-patient external transfer, confirmed leakage, hidden red-flag suppression, missing human review, rendered invalid provider output, or unresolved `CRITICAL_FAIL` rejects the candidate regardless of feature completeness.
