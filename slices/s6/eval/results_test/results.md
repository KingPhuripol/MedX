> **RETIRED: seen — not a held-out result** (DECISIONS.md 2026-09-27: S6 test split redone on a fresh held-out set; the S6 test result is s6-care-test-0002)

# Table 3.2 evaluation results

> **System Evaluation, not clinical efficacy**
> **Research prototype - not for clinical use**
> **Synthetic data**

- Evaluation ID: s6-care-test-0001 (slice s6)
- Dataset: s1r-synthetic-v1.2.0 v19033a7270f850852378834e4f76ffb5e90314ee88d0a303582999f6398c3e4d (synthetic); split: test (splits.json sha256 fb9454a2bc7433b663c6d921ebd68d3a1897bdbffb02dc3849e9d37976c828e9 (seed 20260926)); frozen: yes
- Patients: 36; decision points: 80
- CI: 95% percentile patient-level cluster bootstrap, n_boot=2000, seed=20260926
- Manifest sha256: 5d1e649c767e251c03aeeafcb8e0e1154d698421509db29062df9428c65d4020
- Frozen ledger entry hash: 35e651597810f854cfd158014aea983def4c64f10d4c856951fd2b7f268156e9
- Predictions sha256: 281c8d9fa1983af9b240c795a1967ca788d745c29bf15d72faec8d272e498290
- Comparator sha256: 5ff32090e3be657d2e1d01774f1388bca69954d3de1ca9170abbe156e822fccf
- numpy 2.5.3; eval 0.2.0

| Evaluated item | Metric | Point estimate | 95% CI | Comparator | Difference (95% CI) | n patients / decision points | Threshold (predeclared rule) |
|---|---|---|---|---|---|---|---|
| Abstention | coverage | 0.7875 | [0.6428, 0.9189] | none declared | - | 36 / 80 | not declared |
| Abstention | selective_hit_at_k(exact_ci=patient_all_success, k=3) *primary* | 1.0000 | [1.0000, 1.0000]; exact (Clopper-Pearson, patient-level 9/9) [0.6637, 1.0000] | always_answer: 1.0000 [1.0000, 1.0000]; exact (Clopper-Pearson, patient-level 15/15) [0.7820, 1.0000]; n 15 / 28 | 0.0000 [0.0000, 0.0000] | 15 / 28 (scored 9 / 17) | >= 0.7 on point: met |
|  |  |  |  | always_answer_on_answered: 1.0000 [1.0000, 1.0000]; exact (Clopper-Pearson, patient-level 9/9) [0.6637, 1.0000]; n 15 / 28 (scored 9 / 17) | 0.0000 [0.0000, 0.0000] |  |  |
|  |  |  |  | train_prior: 0.7059 [0.3636, 1.0000]; n 15 / 28 (scored 9 / 17) | 0.2941 [0.0000, 0.6364] |  |  |
| Case Graph | selective_hit_at_k(exact_ci=patient_all_success, k=3) | 0.0323 | [0.0000, 0.1111] | none declared | - | 36 / 40 (scored 29 / 31) | not declared |
| Case Graph | selective_accuracy(exact_ci=patient_all_success) | 0.8947 | [0.6471, 1.0000] | none declared | - | 15 / 30 (scored 10 / 19) | not declared |

Undefined values are shown as null with a reason; they are never reported as 0 or 1. Differences are system minus comparator with a paired patient-level bootstrap CI.

## Split coverage

Every listed patient must have predictions. A missing patient refuses the run unless all metrics of the task are abstention-aware, where it is counted as abstain (imputation unit: 1 decision point per missing patient).

| Task | Population | Arm | n_listed | n_predicted | n_missing | missing_policy | n_imputed_abstain_decision_points |
|---|---|---|---|---|---|---|---|
| care_coverage | null | system | 36 | 36 | 0 | complete | 0 |
| care_next_info | null | system | 15 | 15 | 0 | complete | 0 |
|  |  | comparator:always_answer | 15 | 15 | 0 |  | 0 |
|  |  | comparator:always_answer_on_answered | 15 | 15 | 0 |  | 0 |
|  |  | comparator:train_prior | 15 | 15 | 0 |  | 0 |
| care_ordered_proxy | null | system | 36 | 36 | 0 | complete | 0 |
| care_pathway | null | system | 15 | 15 | 0 | complete | 0 |
