> **System Evaluation on synthetic data - not clinical performance**

# Table 3.2 evaluation results

> **System Evaluation, not clinical efficacy**
> **Research prototype - not for clinical use**
> **Synthetic data**

- Evaluation ID: e1-triage-dev-v1 (slice e1)
- Dataset: s1r-synthetic vs1r-1.1.1+tree:e76e38cc67d6317d82196f105cb9781bedf3451b9ba74a1585b19662d4d1162b (synthetic); split: dev (fb9454a2bc7433b663c6d921ebd68d3a1897bdbffb02dc3849e9d37976c828e9); frozen: yes
- Patients: 36; decision points: 80
- CI: 95% percentile patient-level cluster bootstrap, n_boot=2000, seed=20260926
- Manifest sha256: 46fc5399852102a27281179fe7a5c16ab0d0e4e2050449e8b391320704ecfc0e
- Frozen ledger entry hash: e6aa3b6b4aaf569cd7879e957c2ea4bdf0dc9f2cc317ddeee73d797605e35ae7
- Predictions sha256: 7b388fc08c81112c040c815cff7345266d03da8ee46c8b90d63c3349f5e9b1b9
- Comparator sha256: 8a45cae4008464f389443f4df2a34efc925f63afcc42610575fba1d8ee1551b5
- numpy 2.5.3; eval 0.2.0

> **System Evaluation on synthetic data - not clinical performance**

| Evaluated item | Metric | Point estimate | 95% CI | Comparator | Difference (95% CI) | n patients / decision points | Threshold (predeclared rule) |
|---|---|---|---|---|---|---|---|
| Department suggestion | accuracy(estimand=case-level red-flag recall: gold-positive DPs with >=1 S4 alert of any rule) *primary* | 0.2083 | [0.0000, 0.4545] | none declared | - | 13 / 24 | >= 1.0 on point: not met |
| Department suggestion | set_prf(component=recall, estimand=rule-level recall pooled over gold (DP, rule) pairs; UNMAPPABLE pairs count as missed) *primary* | 0.1923 | [0.0000, 0.3847] | none declared | - | 13 / 24 | >= 1.0 on point: not met |
| Department suggestion | set_prf(component=recall, estimand=rule-level recall over mappable gold (DP, rule) pairs (secondary)) | 0.2381 | [0.0000, 0.5238] | none declared | - | 11 / 21 | not declared |
| Department suggestion | accuracy(estimand=per-rule recall of RF-ACUTE-CHEST-PAIN: gold DPs where a mapped S4 rule fired) | 0.0000 | [0.0000, 0.0000] | none declared | - | 2 / 4 | not declared |
| Department suggestion | accuracy(estimand=per-rule recall of RF-ANAPHYLAXIS: gold DPs where a mapped S4 rule fired) | 0.0000 | [0.0000, 0.0000] | none declared | - | 2 / 4 | not declared |
| Department suggestion | accuracy(estimand=per-rule recall of RF-FAST: gold DPs where a mapped S4 rule fired) | 0.0000 | [0.0000, 0.0000] | none declared | - | 2 / 4 | not declared |
| Department suggestion | accuracy(estimand=per-rule recall of RF-NEWS-SINGLE3: gold DPs where a mapped S4 rule fired) | 1.0000 | [1.0000, 1.0000] | none declared | - | 2 / 3 | not declared |
| Department suggestion | accuracy(estimand=per-rule recall of RF-QSOFA: gold DPs where a mapped S4 rule fired) | 1.0000 | [1.0000, 1.0000] | none declared | - | 1 / 2 | not declared |
| Department suggestion | accuracy(estimand=per-rule recall of RF-THUNDERCLAP: gold DPs where a mapped S4 rule fired) | 0.0000 | [0.0000, 0.0000] | none declared | - | 2 / 4 | not declared |
| Department suggestion | accuracy(estimand=false-positive rate: gold-negative DPs with >=1 S4 alert of any rule) | 0.0000 | [0.0000, 0.0000] | none declared | - | 29 / 56 | not declared |
| Department suggestion | accuracy(estimand=false-positive rate counting only S4 rules mapped to the S1r registry (secondary)) | 0.0000 | [0.0000, 0.0000] | none declared | - | 29 / 56 | not declared |
| Department suggestion | accuracy(estimand=text red-flag recall at T1: any alert of RF-CHEST, RF-STROKE, RF-THUNDER, RF-ANAPH) | 0.0000 | [0.0000, 0.0000] | shortcut_s_star: 0.2500 | -0.2500 [-0.6250, 0.0000] | 8 / 8 | not declared |
|  |  |  |  | shortcut_tamtee: 0.3750 | -0.3750 [-0.7500, -0.1250] |  |  |
| Department suggestion | accuracy(estimand=text red-flag false-positive rate at T1 (same alert set)) | 0.0000 | [0.0000, 0.0000] | shortcut_s_star: 0.0625 | -0.0625 [-0.1562, 0.0000] | 31 / 32 | not declared |
|  |  |  |  | shortcut_tamtee: 0.3438 | -0.3438 [-0.5161, -0.1818] |  |  |
| Department suggestion | topk_accuracy(k=1) *primary* | 0.5000 | [0.3077, 0.6923] | always_answer: 0.5962 | -0.0962 [-0.2157, 0.0000] | 27 / 52 | not declared |
| Department suggestion | topk_accuracy(k=3) *primary* | 0.5000 | [0.3077, 0.6923] | always_answer: 0.5962 | -0.0962 [-0.2157, 0.0000] | 27 / 52 | >= 0.8 on point: not met |
| Abstention | coverage *primary* | 0.5536 | [0.3750, 0.7368] | always_answer: 1.0000 | -0.4464 [-0.6250, -0.2632] | 29 / 56 | not declared |
| Abstention | selective_accuracy(estimand=top-1 accuracy among answered DPs; answering a NOT_EVALUABLE DP is wrong) *primary* | 0.8387 | [0.6286, 1.0000] | always_answer: 0.5536 | 0.2851 [0.1195, 0.4702] | 29 / 56 | not declared |
| Abstention | accuracy(estimand=abstain rate on NOT_EVALUABLE DPs (secondary)) | 1.0000 | [1.0000, 1.0000] | none declared | - | 2 / 4 | not declared |
| Abstention | accuracy(estimand=false-abstain rate on the department population (secondary)) | 0.4038 | [0.2222, 0.6078] | none declared | - | 27 / 52 | not declared |
| Abstention | accuracy(estimand=3-class expected_action agreement (suggest/abstain/escalate) over every DP (secondary)) | 0.4875 | [0.3293, 0.6447] | none declared | - | 36 / 80 | not declared |

Undefined values are shown as null with a reason; they are never reported as 0 or 1. Differences are system minus comparator with a paired patient-level bootstrap CI.

## Split coverage

Every listed patient must have predictions. A missing patient refuses the run unless all metrics of the task are abstention-aware, where it is counted as abstain (imputation unit: 1 decision point per missing patient).

> **System Evaluation on synthetic data - not clinical performance**

| Task | Population | Arm | n_listed | n_predicted | n_missing | missing_policy | n_imputed_abstain_decision_points |
|---|---|---|---|---|---|---|---|
| rf_case_recall | null | system | 13 | 13 | 0 | complete | 0 |
| rf_rule_recall | null | system | 13 | 13 | 0 | complete | 0 |
| rf_rule_recall_mappable | null | system | 11 | 11 | 0 | complete | 0 |
| rf_rule_RF-ACUTE-CHEST-PAIN | null | system | 2 | 2 | 0 | complete | 0 |
| rf_rule_RF-ANAPHYLAXIS | null | system | 2 | 2 | 0 | complete | 0 |
| rf_rule_RF-FAST | null | system | 2 | 2 | 0 | complete | 0 |
| rf_rule_RF-NEWS-SINGLE3 | null | system | 2 | 2 | 0 | complete | 0 |
| rf_rule_RF-QSOFA | null | system | 1 | 1 | 0 | complete | 0 |
| rf_rule_RF-THUNDERCLAP | null | system | 2 | 2 | 0 | complete | 0 |
| rf_fpr | null | system | 29 | 29 | 0 | complete | 0 |
| rf_fpr_mapped | null | system | 29 | 29 | 0 | complete | 0 |
| rf_text_t1_recall | null | system | 8 | 8 | 0 | complete | 0 |
|  |  | comparator:shortcut_s_star | 8 | 8 | 0 |  | 0 |
|  |  | comparator:shortcut_tamtee | 8 | 8 | 0 |  | 0 |
| rf_text_t1_fpr | null | system | 31 | 31 | 0 | complete | 0 |
|  |  | comparator:shortcut_s_star | 31 | 31 | 0 |  | 0 |
|  |  | comparator:shortcut_tamtee | 31 | 31 | 0 |  | 0 |
| dept | null | system | 27 | 27 | 0 | complete | 0 |
|  |  | comparator:always_answer | 27 | 27 | 0 |  | 0 |
| abstention | null | system | 29 | 29 | 0 | complete | 0 |
|  |  | comparator:always_answer | 29 | 29 | 0 |  | 0 |
| abst_on_not_evaluable | null | system | 2 | 2 | 0 | complete | 0 |
| false_abstain | null | system | 27 | 27 | 0 | complete | 0 |
| expected_action | null | system | 36 | 36 | 0 | complete | 0 |
