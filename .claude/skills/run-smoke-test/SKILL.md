---
name: run-smoke-test
description: Run the lightweight, non-expensive verification suite and report exact failures. Use after code, contract, Harness, model-interface, or pipeline changes.
argument-hint: [optional-component]
---

# Smoke Test Workflow

Optional component: `$ARGUMENTS`.

1. Read the active task and affected contracts/tests.
2. Confirm the intended command is Tier 0 or Tier 1: synthetic/tiny data, one device, under 20 minutes, no external publishing, no real-patient payload, no destructive transform.
3. Inspect the repository for component-specific test commands. Never invent success for an absent suite.
4. Run the Harness smoke suite:

```bash
bash scripts/run_smoke_test.sh
```

5. If component code exists, run the narrowest deterministic unit/contract test using the documented project command. Use synthetic fixtures and bound runtime/data.
6. For model/training code, test import/config, one forward batch, one backward batch where applicable, graph validation/export/replay, checkpoint round trip, and evaluator invocation - never a full training run.
7. For Innovation, test canonical API fixture, future-evidence rejection, unauthorized external payload rejection, abstention, provider timeout/invalid output, human review, and audit event append.
8. Record exact commands, versions, duration, pass/fail/skip counts, and first actionable failure. A skipped or absent check is not passing evidence.
9. Do not edit code merely to make a failing test disappear unless the user's request includes a fix.

Return scope, tier confirmation, commands, exact results, skipped/missing coverage, failure diagnosis, affected acceptance/gate, artifacts, and next action. Stop if the command expands beyond Tier 1 or requires approval.

