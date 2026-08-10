---
paths:
  - "shared/**/*"
  - "schemas/**/*"
  - "project_state/**/*"
  - "data/**/*"
---

# Data and Shared Contract Rules

- Split by patient before derivation; all modalities/encounters/windows from a patient stay in one split.
- Every evidence/label item has provenance and `available_at_time`; input at `T` may depend only on availability `<= T`.
- Fit transforms on training data only and preserve missingness explicitly.
- Build new versioned outputs rather than mutating source/raw data.
- Breaking schema/contract changes need version bump, migration fixture, integration tests, and human decision when material.
- Never log/commit secrets, raw PHI, identifiers, checkpoints, or restricted payloads.

