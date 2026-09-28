# Table 3.2 evaluation results

> **System Evaluation, not clinical efficacy**
> **Research prototype - not for clinical use**
> **Synthetic data**

- Evaluation ID: s6-care-test-0002 (slice s6)
- Dataset: s6r-heldout-synthetic-v1.2.2 v552b1acd2533428c03d6c88a2ff7e3f68f7dd8daef89f5981fc5daebb8b73729 (synthetic); split: test (splits.json sha256 44363099d8d8c7e93a4e0ed729fd52412306c0af874dacb21a56e43efe176c91 (seed 20260927)); frozen: yes
- Patients: 72; decision points: 160
- CI: 95% percentile patient-level cluster bootstrap, n_boot=2000, seed=20260926
- Manifest sha256: d75a91cfa35943d5dda8955b08024f785860621dc7340ea0be3e78a195398ccd
- Frozen ledger entry hash: 35397d9df957edd0594cde96c5617368c9fc982637784343606995a8c4961000
- Predictions sha256: 7df8e7f7bd8ac79c81c9d13b7e3118a91b6c35906ac4594ba10a8d9a36caf0a3
- Comparator sha256: 08c2540c7dfe2d0b9882fbd4a2047aea1a27d0c6c11058175de5f30565da8e6d
- numpy 2.5.3; eval 0.2.0

| Evaluated item | Metric | Point estimate | 95% CI | Comparator | Difference (95% CI) | n patients / decision points | Threshold (predeclared rule) |
|---|---|---|---|---|---|---|---|
| Abstention | coverage | 0.8000 | [0.7051, 0.8795] | none declared | - | 72 / 160 | not declared |
| Abstention | selective_hit_at_k(exact_ci=patient_all_success, k=3) *primary* | 1.0000 | [1.0000, 1.0000]; exact (Clopper-Pearson, patient-level 27/27) [0.8723, 1.0000] | always_answer: 0.9733 [0.9211, 1.0000]; n 36 / 75 | 0.0267 [0.0000, 0.0789] | 36 / 75 (scored 27 / 56) | >= 0.7 on point: met |
|  |  |  |  | always_answer_on_answered: 1.0000 [1.0000, 1.0000]; exact (Clopper-Pearson, patient-level 27/27) [0.8723, 1.0000]; n 36 / 75 (scored 27 / 56) | 0.0000 [0.0000, 0.0000] |  |  |
|  |  |  |  | train_prior: 0.5000 [0.3279, 0.6792]; n 36 / 75 (scored 27 / 56) | 0.5000 [0.3208, 0.6721] |  |  |
| Case Graph | selective_hit_at_k(exact_ci=patient_all_success, k=3) | 0.0781 | [0.0161, 0.1493] | none declared | - | 72 / 80 (scored 58 / 64) | not declared |
| Case Graph | selective_accuracy(exact_ci=patient_all_success) | 0.9661 | [0.9153, 1.0000] | none declared | - | 38 / 79 (scored 29 / 59) | not declared |

Undefined values are shown as null with a reason; they are never reported as 0 or 1. Differences are system minus comparator with a paired patient-level bootstrap CI.

## Split coverage

Every listed patient must have predictions. A missing patient refuses the run unless all metrics of the task are abstention-aware, where it is counted as abstain (imputation unit: 1 decision point per missing patient).

| Task | Population | Arm | n_listed | n_predicted | n_missing | missing_policy | n_imputed_abstain_decision_points |
|---|---|---|---|---|---|---|---|
| care_coverage | null | system | 72 | 72 | 0 | complete | 0 |
| care_next_info | null | system | 36 | 36 | 0 | complete | 0 |
|  |  | comparator:always_answer | 36 | 36 | 0 |  | 0 |
|  |  | comparator:always_answer_on_answered | 36 | 36 | 0 |  | 0 |
|  |  | comparator:train_prior | 36 | 36 | 0 |  | 0 |
| care_ordered_proxy | null | system | 72 | 72 | 0 | complete | 0 |
| care_pathway | null | system | 38 | 38 | 0 | complete | 0 |
