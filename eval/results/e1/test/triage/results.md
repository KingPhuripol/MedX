> **System Evaluation on synthetic data - not clinical performance**

# Table 3.2 evaluation results

> **System Evaluation, not clinical efficacy**
> **Research prototype - not for clinical use**
> **Synthetic data**

- Evaluation ID: e1-triage-test-v1 (slice e1)
- Dataset: s1r-synthetic vs1r-1.1.1+tree:e76e38cc67d6317d82196f105cb9781bedf3451b9ba74a1585b19662d4d1162b (synthetic); split: test (fb9454a2bc7433b663c6d921ebd68d3a1897bdbffb02dc3849e9d37976c828e9); frozen: yes
- Patients: 36; decision points: 80
- CI: 95% percentile patient-level cluster bootstrap, n_boot=2000, seed=20260926
- Manifest sha256: d9be1b73ce9c4b863a9c5a9f23bebc13fa8e8e349359e510918d1639f138f691
- Frozen ledger entry hash: c884b4178599bb283189140a1ffdd2209a1ce4c7cdb65197f8e81168b22dac5a
- Predictions sha256: 6c66d654a5beb666e06c0b9339407ac35c7dda6f6ba79803b4be2fdb200a6207
- Comparator sha256: a5994725dec09b73705ea0c7f3dda6d5704cbd387b589f2b8e57f11cba278762
- numpy 2.5.3; eval 0.2.0

> **System Evaluation on synthetic data - not clinical performance**

| Evaluated item | Metric | Point estimate | 95% CI | Comparator | Difference (95% CI) | n patients / decision points | Threshold (predeclared rule) |
|---|---|---|---|---|---|---|---|
| Department suggestion | accuracy(estimand=case-level red-flag recall: gold-positive DPs with >=1 S4 alert of any rule) *primary* | 0.4091 | [0.1364, 0.6842] | none declared | - | 13 / 22 | >= 1.0 on point: not met |
| Department suggestion | set_prf(component=recall, estimand=rule-level recall pooled over gold (DP, rule) pairs; UNMAPPABLE pairs count as missed) *primary* | 0.3103 | [0.1304, 0.4828] | none declared | - | 13 / 22 | >= 1.0 on point: not met |
| Department suggestion | set_prf(component=recall, estimand=rule-level recall over mappable gold (DP, rule) pairs (secondary)) | 0.4286 | [0.1818, 0.7000] | none declared | - | 11 / 19 | not declared |
| Department suggestion | accuracy(estimand=per-rule recall of RF-ACUTE-CHEST-PAIN: gold DPs where a mapped S4 rule fired) | 0.0000 | [0.0000, 0.0000] | none declared | - | 2 / 4 | not declared |
| Department suggestion | accuracy(estimand=per-rule recall of RF-ANAPHYLAXIS: gold DPs where a mapped S4 rule fired) | 0.0000 | [0.0000, 0.0000] | none declared | - | 1 / 2 | not declared |
| Department suggestion | accuracy(estimand=per-rule recall of RF-FAST: gold DPs where a mapped S4 rule fired) | 0.0000 | [0.0000, 0.0000] | none declared | - | 2 / 4 | not declared |
| Department suggestion | accuracy(estimand=per-rule recall of RF-NEWS-SINGLE3: gold DPs where a mapped S4 rule fired) | 1.0000 | [1.0000, 1.0000] | none declared | - | 3 / 5 | not declared |
| Department suggestion | accuracy(estimand=per-rule recall of RF-QSOFA: gold DPs where a mapped S4 rule fired) | 1.0000 | [1.0000, 1.0000] | none declared | - | 3 / 4 | not declared |
| Department suggestion | accuracy(estimand=per-rule recall of RF-THUNDERCLAP: gold DPs where a mapped S4 rule fired) | 0.0000 | [0.0000, 0.0000] | none declared | - | 1 / 2 | not declared |
| Department suggestion | accuracy(estimand=false-positive rate: gold-negative DPs with >=1 S4 alert of any rule) | 0.0000 | [0.0000, 0.0000] | none declared | - | 28 / 58 | not declared |
| Department suggestion | accuracy(estimand=false-positive rate counting only S4 rules mapped to the S1r registry (secondary)) | 0.0000 | [0.0000, 0.0000] | none declared | - | 28 / 58 | not declared |
| Department suggestion | accuracy(estimand=text red-flag recall at T1: any alert of RF-CHEST, RF-STROKE, RF-THUNDER, RF-ANAPH) | 0.0000 | [0.0000, 0.0000] | shortcut_s_star: 0.6667 | -0.6667 [-1.0000, -0.3333] | 6 / 6 | not declared |
|  |  |  |  | shortcut_tamtee: 0.5000 | -0.5000 [-0.8333, -0.1667] |  |  |
| Department suggestion | accuracy(estimand=text red-flag false-positive rate at T1 (same alert set)) | 0.0000 | [0.0000, 0.0000] | shortcut_s_star: 0.0294 | -0.0294 [-0.0882, 0.0000] | 31 / 34 | not declared |
|  |  |  |  | shortcut_tamtee: 0.3235 | -0.3235 [-0.4848, -0.1818] |  |  |
| Department suggestion | topk_accuracy(k=1) *primary* | 0.3673 | [0.2041, 0.5491] | always_answer: 0.5102 | -0.1429 [-0.2642, -0.0227] | 23 / 49 | not declared |
| Department suggestion | topk_accuracy(k=3) *primary* | 0.4082 | [0.2400, 0.5918] | always_answer: 0.5510 | -0.1429 [-0.2642, -0.0227] | 23 / 49 | >= 0.8 on point: not met |
| Abstention | coverage *primary* | 0.4151 | [0.2500, 0.5958] | always_answer: 1.0000 | -0.5849 [-0.7500, -0.4042] | 25 / 53 | not declared |
| Abstention | selective_accuracy(estimand=top-1 accuracy among answered DPs; answering a NOT_EVALUABLE DP is wrong) *primary* | 0.8182 | [0.5714, 1.0000] | always_answer: 0.4717 | 0.3465 [0.1582, 0.5769] | 25 / 53 | not declared |
| Abstention | accuracy(estimand=abstain rate on NOT_EVALUABLE DPs (secondary)) | 1.0000 | [1.0000, 1.0000] | none declared | - | 2 / 4 | not declared |
| Abstention | accuracy(estimand=false-abstain rate on the department population (secondary)) | 0.5510 | [0.3658, 0.7241] | none declared | - | 23 / 49 | not declared |
| Abstention | accuracy(estimand=3-class expected_action agreement (suggest/abstain/escalate) over every DP (secondary)) | 0.4750 | [0.3293, 0.6250] | none declared | - | 36 / 80 | not declared |

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
| rf_rule_RF-ANAPHYLAXIS | null | system | 1 | 1 | 0 | complete | 0 |
| rf_rule_RF-FAST | null | system | 2 | 2 | 0 | complete | 0 |
| rf_rule_RF-NEWS-SINGLE3 | null | system | 3 | 3 | 0 | complete | 0 |
| rf_rule_RF-QSOFA | null | system | 3 | 3 | 0 | complete | 0 |
| rf_rule_RF-THUNDERCLAP | null | system | 1 | 1 | 0 | complete | 0 |
| rf_fpr | null | system | 28 | 28 | 0 | complete | 0 |
| rf_fpr_mapped | null | system | 28 | 28 | 0 | complete | 0 |
| rf_text_t1_recall | null | system | 6 | 6 | 0 | complete | 0 |
|  |  | comparator:shortcut_s_star | 6 | 6 | 0 |  | 0 |
|  |  | comparator:shortcut_tamtee | 6 | 6 | 0 |  | 0 |
| rf_text_t1_fpr | null | system | 31 | 31 | 0 | complete | 0 |
|  |  | comparator:shortcut_s_star | 31 | 31 | 0 |  | 0 |
|  |  | comparator:shortcut_tamtee | 31 | 31 | 0 |  | 0 |
| dept | null | system | 23 | 23 | 0 | complete | 0 |
|  |  | comparator:always_answer | 23 | 23 | 0 |  | 0 |
| abstention | null | system | 25 | 25 | 0 | complete | 0 |
|  |  | comparator:always_answer | 25 | 25 | 0 |  | 0 |
| abst_on_not_evaluable | null | system | 2 | 2 | 0 | complete | 0 |
| false_abstain | null | system | 23 | 23 | 0 | complete | 0 |
| expected_action | null | system | 36 | 36 | 0 | complete | 0 |
