# Innovation Implementation Area

The additive synthetic Clinical Front Door v2 workspace and bounded Agent Design implementation are documented in [the v2 handoff](../docs/innovation/v2/README.md). Start at `/workspace`; `/ui/v2` remains the recovery fallback and legacy screens remain at `/ui/`.

AI Clinical Front Door — an API-first clinical decision-support **research prototype**.
It does not diagnose, prescribe, order tests, refer, or discharge, and every output
requires human confirmation before it may inform care.

## Layout

```
Client / UI
     |
innovation/api/          Front Door HTTP API (FastAPI, DEC-0010)
     |
innovation/frontdoor/    workflow: snapshot -> assess -> hold for human review
     |
innovation/gateway/      safety policy, then the Model Gateway
     |
innovation/gateway/providers/   mock (default) | external | baseline | team model
```

Provider SDK types, tokens, prompts and errors stay inside adapters. A client never sees
a provider-native field — the gateway builds the response, and the response models refuse
unknown fields, so that is structural rather than a convention.

## Run the offline demonstration

```
python3 -m innovation.demo
```

Synthetic journey, mock provider, no network. This is Innovation release stage 1
("contract and synthetic CLI fixture"). It shows the two properties the prototype exists
to demonstrate: evidence that did not exist at the decision time cannot reach the model,
and nothing takes effect without a human confirming it.

## Run the API and the screens

```
python3 -m uvicorn innovation.api.app:app --reload
```

API docs at `/docs`, screens at `/ui/`. Optional configuration:
`FRONT_DOOR_PROVIDER=mock|baseline`, `FRONT_DOOR_DB=path.sqlite3`,
`FRONT_DOOR_AUDIT_LOG=audit.jsonl`.

The five screens (`PRODUCT_SPEC.md` §Core screens) call the **same public API** as any
other client — in-process, but as real HTTP requests through the same app — so no screen
has a privileged path, and a test asserts the intake screen produces a `POST /encounters`
rather than reaching past the API into the service.

Urgency is encoded four ways, colour last: written level, shape glyph, border weight, then
colour. Measured in a browser: lowest text contrast 8.95:1 against a 4.5:1 requirement,
zero controls removed from the tab order, skip link and visible focus ring present.

## Where each rule lives

| Rule | Enforced in |
|---|---|
| Evidence must exist at the decision time | `shared/snapshot.py`, and again at the gateway boundary |
| Red flags outrank diagnostic ranking; a model may not lower urgency | `gateway/safety.py` |
| Unknown is not absent | `gateway/safety.py` (SR-002) |
| Missing required information abstains rather than concludes | `gateway/safety.py` (SR-003) |
| Restricted data may not reach an external provider without a recorded approval | `gateway/gateway.py` |
| Nothing takes effect without human confirmation | `frontdoor/service.py` |
| Every call is audited, by reference and never by payload | `gateway/audit.py` |

The safety rules sit in the gateway rather than in a provider deliberately: if they lived
in the provider, swapping providers would silently change the safety behaviour.

## Contract tests

`tests/test_gateway.py` implements the ten cases in `docs/shared/MODEL_API_CONTRACT.md`,
parametrised over `ADAPTERS`. Both `MockProvider` and `BaselineProvider` run the full
suite, so a new adapter is certified by being appended to that list — a team-model adapter
is accepted only when it passes the same fixtures as the others.

The suite asserts contract-level properties, never one provider's particular answers.
Provider-specific behaviour lives in clearly separated tests at the bottom of the file so
it cannot be mistaken for a contract requirement.

Do not call external providers directly from UI or business logic, and do not use
real-patient payloads without an approval recorded under the Human Approval Policy.
