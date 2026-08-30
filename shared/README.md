# Shared Implementation Area

Cross-track runtime code: versioned contract models, Patient Journey snapshot logic,
canonical fixtures, graph/API serialization, and shared validation. Machine schemas
remain in `schemas/` and are the source of truth.

Breaking contract changes require a version, migration fixture, cross-track tests, and a
recorded human decision when material.

## Layout

| Path | Purpose |
|---|---|
| `contracts/journey.py` | Patient Journey and event models |
| `contracts/model_api.py` | Gateway request and response models |
| `contracts/errors.py` | Contract error codes and `ContractViolation` |
| `snapshot.py` | The snapshot operation: evidence available at a decision time |

## The rule these models exist to enforce

`available_at_time` is when evidence became *usable for a decision*, which is not when it
was observed. For a MIMIC-IV lab that is `storetime`, not `charttime` — deriving it from
`charttime` would place a result inside a decision made before the result existed. See
`docs/research/DATASET_FEASIBILITY.md`.

`take_snapshot` is the only place that rule is applied, so there is one implementation to
audit rather than one per call site. It never mutates the journey; a snapshot is a new
artifact, and a later snapshot is another new one.

## Keeping the two contracts from drifting

`schemas/` is the machine contract and `shared/contracts/` is the executable one.
`tests/test_contracts.py` validates the same fixtures through both, in both directions,
so a divergence fails the suite instead of drifting silently (RISK-0006).
