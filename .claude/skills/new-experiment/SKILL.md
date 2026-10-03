---
name: new-experiment
description: Create a complete, validated experiment manifest and pre-flight plan before any research run. Manual workflow because it creates durable experiment state.
argument-hint: <short-slug>
disable-model-invocation: true
---

# New Experiment Workflow

Experiment slug: `$ARGUMENTS`.

Do not run training in this workflow.

1. Read `docs/PROPOSAL.md`, `docs/DECISIONS.md`, `slices/s9/SPEC.md`, `research/estimate/ESTIMATE.md`, and related manifests in `research/manifests/`.
2. Require a precise research question and falsifiable hypothesis. If absent, stop and ask the human/Research Lead.
3. Identify primary comparison, baseline manifest(s), fairness constraints, data/split/temporal-audit versions, and primary metric before results exist.
4. Classify Tier 0-4 using the training tiers in `CLAUDE.md`. Any multi-GPU/multi-node/>60m/flagship is Tier 3/4 and requires an approval ID before execution.
5. Write the manifest by hand as `research/manifests/<slug>.json`, conforming to `schemas/experiment-manifest.schema.json` (copy the closest existing manifest as a template). Fill owner, question, hypothesis, decision, tier, model/license, dataset/split/audit versions, graph mode, primary metric, fixed/changed factors, and resource estimate. Never leave placeholders.

6. Review every generated planning field for the actual run; do not reuse synthetic Harness values for a model experiment.
7. Specify code revision/dirty policy, model/config, parameter estimate, initialization/license, data/split/preprocessing, seeds, optimizer/steps/tokens/precision, graph mode/objectives, resource estimate, artifacts/retention, metrics, statistics, stop/exclusion rules, risks, and approvals.
8. Link the slice and research question. Declare expected evidence and the decision the result will inform.
9. Validate:

```bash
python3 scripts/validate_manifest.py research/manifests/<slug>.json
```

10. Run only non-training pre-flight checks needed to establish schema/config/data availability. Leave `status` as `planned`.

Return manifest path/ID, hypothesis, tier, comparison/fairness, primary metric, pre-flight gaps, budget, approval requirement, stop rules, and recommended next command. Do not claim that manifest creation authorizes execution.
