---
name: architecture-ablation
description: Design and execute a controlled case-adaptive DAG ablation family that isolates topology, routing, operator, modality, compute, and faithfulness effects. Manual workflow because runs may consume compute.
argument-hint: <base-manifest.json>
disable-model-invocation: true
---

# Architecture Ablation Workflow

Base manifest: `$ARGUMENTS`.

1. Read the base manifest, Research/Architecture/Training Specs, Benchmark Contract, and Success Criteria.
2. State the one causal question. Do not change multiple independent factors in one ablation unless factorial design is explicit.
3. Select applicable controls:
   - same-backbone fixed path;
   - static typed DAG;
   - random/matched DAG or shuffled router;
   - sparse/MoE-style control;
   - dynamic typed DAG;
   - node/edge/operator/modality/graph swap interventions.
4. Freeze shared data/split/preprocessing, parameter/compute budget, tokens/steps, optimizer/search opportunity, seeds, evaluator, and primary metric. Report any impossible match.
5. Predeclare adaptation/collapse metrics, graph budget, replay tolerance, intervention predicted direction, efficiency metrics, statistics, stop/exclusion rules, and remediation budget.
6. Create one child manifest per condition with unique IDs and explicit `parent_experiment_id`/changed factor. Validate each.
7. Tier and approval rules apply to every run. Without required approval, produce the ablation plan/manifests and stop.
8. Smoke-test graph generation/export/replay/intervention on synthetic data.
9. Execute approved conditions without selectively extending the favored method.
10. Analyze paired outcomes, graph behavior, cost, replay, intervention effects, and failure modes. A pretty graph is not evidence.

Return causal question, control matrix, changed vs fixed factors, fairness gaps, manifests, approval/tier, exact evidence, faithfulness/adaptation conclusion, kill/continue recommendation, and claim boundary.

