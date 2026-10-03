---
name: integration-check
description: Verify Research and Innovation against shared Patient Journey, Model API, graph, evaluation, safety, approval, and reproducibility contracts. Use before integrated milestones, demos, or releases.
argument-hint: [optional-scope-or-revision]
---

# Integration Check Workflow

Scope/revision: `$ARGUMENTS`.

Prefer the read-only `integration-auditor` for the final verdict. This workflow prepares/runs safe evidence and must not self-certify authored changes.

1. Freeze exact revisions, models/providers, schemas, fixtures, and acceptance/milestone scope.
2. Build a traceability matrix: requirement -> implementation -> test/evidence -> owner -> verdict.
3. Run `make test`, `python3 scripts/validate_manifest.py research/manifests/*.json`, and `python3 scripts/temporal_leakage_audit.py <journey.json> --as-of <ISO-8601>` on the canonical synthetic fixture; then walk the `DEMO_MODE=1 make dev` flow (docs/DEMO-RUNBOOK.md).
4. Run canonical synthetic fixture through:
   - Patient Journey snapshot at decision time;
   - request schema and authorization/temporal guard;
   - mock provider;
   - team provider if available;
   - gateway normalization and response schema;
   - policy/safety layer;
   - UI/human-review/audit representation where implemented.
5. Test urgent red flag, missing modality, low-confidence abstention, future evidence, unauthorized external payload, timeout, malformed response, idempotent retry, and provider swap.
6. Verify provider-specific fields do not escape adapters; client behavior is provider-independent.
7. Verify graph schema/version/evidence references/export-replay link and no hidden chain-of-thought display.
8. Verify original output is immutable and human confirmation/override is a new audit event.
9. Trace evaluation/result to manifest, code/config/data/split/model/provider/checksums.
10. Ask `clinical-safety-reviewer` and `integration-auditor` for independent read-only verdicts. Implementation owners remediate findings; reviewers re-check.

Do not claim integration because Research and Innovation unit tests separately pass.

Return revisions, traceability/compatibility matrix, test commands/results, contract drift, safety/data findings, reproducibility gaps, reviewer verdicts, affected milestone, remediation owners, and re-check criteria.

