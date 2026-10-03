---
paths:
  - "research/**/*"
  - "eval/**/*"
  - "eval_i2/**/*"
---

# Research Path Rules

- Read `docs/PROPOSAL.md` and the active `slices/<id>/SPEC.md` before material changes.
- Every experiment begins with a validated manifest; keep settings config-first and versioned.
- Add controlled baselines, graph/collapse/replay/faithfulness metrics, and tests with architecture changes.
- Tier 3/4, multi-GPU, >60-minute, approximately 27B or any flagship-scale run, publishing, and checkpoint deletion require explicit human approval.
- Never use final-test outcomes to select metrics, thresholds, configs, or claims.

