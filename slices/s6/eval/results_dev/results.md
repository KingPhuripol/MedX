# Table 3.2 evaluation results

> **System Evaluation, not clinical efficacy**
> **Research prototype - not for clinical use**
> **Synthetic data**
> **UNFROZEN - exploratory (dev split)**

- Evaluation ID: s6-care-dev-0001 (slice s6)
- Dataset: s1r-synthetic-v1.2.0 v19033a7270f850852378834e4f76ffb5e90314ee88d0a303582999f6398c3e4d (synthetic); split: dev (splits.json sha256 fb9454a2bc7433b663c6d921ebd68d3a1897bdbffb02dc3849e9d37976c828e9 (seed 20260926)); frozen: no
- Patients: 36; decision points: 80
- CI: 95% percentile patient-level cluster bootstrap, n_boot=2000, seed=20260926
- Manifest sha256: e6a0a3774985c164259c77121a0384c9a15329c76027334f3851d02dda4f204f
- Frozen ledger entry hash: none (not frozen)
- Predictions sha256: 2c64f63a88077a7b8e517bb8b91fc7c891b79741275ade1b63a6debad92281e0
- Comparator sha256: 0a7939427284d14eaf660b0a0016cb263acea54b8a5cdbaf1787b0b0e246b6d9
- numpy 2.5.3; eval 0.2.0

| Evaluated item | Metric | Point estimate | 95% CI | Comparator | Difference (95% CI) | n patients / decision points | Threshold (predeclared rule) |
|---|---|---|---|---|---|---|---|
| Abstention | coverage | 0.7875 | [0.6538, 0.9048] | none declared | - | 36 / 80 | not declared |
| Abstention | selective_hit_at_k(exact_ci=patient_all_success, k=3) *primary* | 1.0000 | [1.0000, 1.0000]; exact (Clopper-Pearson, patient-level 15/15) [0.7820, 1.0000] | always_answer: 1.0000 | 0.0000 [0.0000, 0.0000] | 21 / 42 | >= 0.8 on point: met |
|  |  |  |  | always_answer_on_answered: 1.0000 | 0.0000 [0.0000, 0.0000] |  |  |
|  |  |  |  | train_prior: 0.5806 | 0.4194 [0.1852, 0.6923] |  |  |
| Case Graph | selective_hit_at_k(exact_ci=patient_all_success, k=3) | 0.0323 | [0.0000, 0.1111] | none declared | - | 36 / 40 | not declared |
| Case Graph | selective_accuracy(exact_ci=patient_all_success) | 0.9394 | [0.7931, 1.0000] | none declared | - | 22 / 45 | not declared |

Undefined values are shown as null with a reason; they are never reported as 0 or 1. Differences are system minus comparator with a paired patient-level bootstrap CI.

## Split coverage

Every listed patient must have predictions. A missing patient refuses the run unless all metrics of the task are abstention-aware, where it is counted as abstain (imputation unit: 1 decision point per missing patient).

| Task | Population | Arm | n_listed | n_predicted | n_missing | missing_policy | n_imputed_abstain_decision_points |
|---|---|---|---|---|---|---|---|
| care_coverage | null | system | 36 | 36 | 0 | complete | 0 |
| care_next_info | null | system | 21 | 21 | 0 | complete | 0 |
|  |  | comparator:always_answer | 21 | 21 | 0 |  | 0 |
|  |  | comparator:always_answer_on_answered | 21 | 21 | 0 |  | 0 |
|  |  | comparator:train_prior | 21 | 21 | 0 |  | 0 |
| care_ordered_proxy | null | system | 36 | 36 | 0 | complete | 0 |
| care_pathway | null | system | 22 | 22 | 0 | complete | 0 |
