# Innovation Implementation Area

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

## Run the API

```
python3 -m uvicorn innovation.api.app:app --reload
```

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

`tests/test_gateway.py` implements the ten cases in `docs/shared/MODEL_API_CONTRACT.md`.
Any new adapter is certified by passing that suite unchanged — a team-model adapter is
accepted only when it passes the same fixtures as the mock.

Do not call external providers directly from UI or business logic, and do not use
real-patient payloads without an approval recorded under the Human Approval Policy.
