# Table 3.2 evaluation results

> **System Evaluation, not clinical efficacy**
> **Research prototype - not for clinical use**
> **Synthetic data**

- Evaluation ID: g2-redflag-retest-0001 (slice g2)
- Dataset: g2-heldout-20260929 vg2-heldout-20260929+tree:527abd73d44af9da07c9e715a68aebb58360de4024a97bd53ecadc7aef2f8417 (synthetic); split: test (44363099d8d8c7e93a4e0ed729fd52412306c0af874dacb21a56e43efe176c91); frozen: yes
- Patients: 72; decision points: 186
- CI: 95% percentile patient-level cluster bootstrap, n_boot=2000, seed=20260929
- Manifest sha256: cedf6bd70f9107397e96a4f282ff4923dead0966b99e9590e5dfd114f0e6503c
- Frozen ledger entry hash: a713fd8888187c68335bb873e3be620e7a8ba12b8a610d0f3f245c604c8c294d
- Predictions sha256: 7a23cf289af0d0153b8d579e8bd1409b4f3a748871f6830249c69d34c094c2f7
- Comparator sha256: none
- numpy 2.5.3; eval 0.2.0

| Evaluated item | Metric | Point estimate | 95% CI | Comparator | Difference (95% CI) | n patients / decision points | Threshold (predeclared rule) |
|---|---|---|---|---|---|---|---|
| Department suggestion | accuracy(estimand=PRIMARY. Mirrors e1 eval/adapters/protocol.py rf_case_recall: gold-positive DPs (>=1 gold red flag) where the Case Graph fired >=1 alert of any rule. Unit: decision point.) *primary* | 1.0000 | [1.0000, 1.0000] | none declared | - | 26 / 46 | >= 1.0 on point: met |
| Department suggestion | accuracy(estimand=Same population; caught iff an alert of a rule mapped to a gold rule of that DP fired.) | 1.0000 | [1.0000, 1.0000] | none declared | - | 26 / 46 | not declared |
| Department suggestion | accuracy(estimand=Unit case: cases with a gold-positive DP; caught iff any such DP has any alert.) | 1.0000 | [1.0000, 1.0000] | none declared | - | 26 / 26 | not declared |
| Department suggestion | accuracy(estimand=Unit case: caught iff any gold-positive DP has a rule-matched alert.) | 1.0000 | [1.0000, 1.0000] | none declared | - | 26 / 26 | not declared |
| Department suggestion | accuracy(estimand=per-rule recall of RF-ACUTE-CHEST-PAIN: Per S1r rule: gold (DP, rule) pairs where a mapped S4 rule fired (e1 mapping v1 + AGG5 overlay).) | 1.0000 | [1.0000, 1.0000] | none declared | - | 3 / 6 | not declared |
| Department suggestion | accuracy(estimand=per-rule recall of RF-ANAPHYLAXIS: Per S1r rule: gold (DP, rule) pairs where a mapped S4 rule fired (e1 mapping v1 + AGG5 overlay).) | 1.0000 | [1.0000, 1.0000] | none declared | - | 3 / 6 | not declared |
| Department suggestion | accuracy(estimand=per-rule recall of RF-FAST: Per S1r rule: gold (DP, rule) pairs where a mapped S4 rule fired (e1 mapping v1 + AGG5 overlay).) | 1.0000 | [1.0000, 1.0000] | none declared | - | 4 / 8 | not declared |
| Department suggestion | accuracy(estimand=per-rule recall of RF-NEWS-AGG5: Per S1r rule: gold (DP, rule) pairs where a mapped S4 rule fired (e1 mapping v1 + AGG5 overlay).) | 1.0000 | [1.0000, 1.0000] | none declared | - | 8 / 12 | not declared |
| Department suggestion | accuracy(estimand=per-rule recall of RF-NEWS-SINGLE3: Per S1r rule: gold (DP, rule) pairs where a mapped S4 rule fired (e1 mapping v1 + AGG5 overlay).) | 1.0000 | [1.0000, 1.0000] | none declared | - | 5 / 7 | not declared |
| Department suggestion | accuracy(estimand=per-rule recall of RF-QSOFA: Per S1r rule: gold (DP, rule) pairs where a mapped S4 rule fired (e1 mapping v1 + AGG5 overlay).) | 1.0000 | [1.0000, 1.0000] | none declared | - | 5 / 8 | not declared |
| Department suggestion | accuracy(estimand=per-rule recall of RF-THUNDERCLAP: Per S1r rule: gold (DP, rule) pairs where a mapped S4 rule fired (e1 mapping v1 + AGG5 overlay).) | 1.0000 | [1.0000, 1.0000] | none declared | - | 3 / 6 | not declared |
| Department suggestion | accuracy(estimand=Gold-negative DPs with >=1 alert of any rule (false-positive rate).) | 0.0000 | [0.0000, 0.0000] | none declared | - | 54 / 114 | not declared |
| Department suggestion | accuracy(estimand=Gold-positive DPs where an alert fired or a gold rule was not_evaluated (input gap surfaced). Silent escalation failure = 1 - surfaced: the screen evaluated, raised nothing, said nothing.) | 1.0000 | [1.0000, 1.0000] | none declared | - | 26 / 46 | not declared |

Undefined values are shown as null with a reason; they are never reported as 0 or 1. Differences are system minus comparator with a paired patient-level bootstrap CI.

## Split coverage

Every listed patient must have predictions. A missing patient refuses the run unless all metrics of the task are abstention-aware, where it is counted as abstain (imputation unit: 1 decision point per missing patient).

| Task | Population | Arm | n_listed | n_predicted | n_missing | missing_policy | n_imputed_abstain_decision_points |
|---|---|---|---|---|---|---|---|
| rf_case_recall | null | system | 26 | 26 | 0 | complete | 0 |
| rf_rulematched_dp | null | system | 26 | 26 | 0 | complete | 0 |
| rf_case_agg | null | system | 26 | 26 | 0 | complete | 0 |
| rf_case_agg_rulematched | null | system | 26 | 26 | 0 | complete | 0 |
| rf_rule_RF-ACUTE-CHEST-PAIN | null | system | 3 | 3 | 0 | complete | 0 |
| rf_rule_RF-ANAPHYLAXIS | null | system | 3 | 3 | 0 | complete | 0 |
| rf_rule_RF-FAST | null | system | 4 | 4 | 0 | complete | 0 |
| rf_rule_RF-NEWS-AGG5 | null | system | 8 | 8 | 0 | complete | 0 |
| rf_rule_RF-NEWS-SINGLE3 | null | system | 5 | 5 | 0 | complete | 0 |
| rf_rule_RF-QSOFA | null | system | 5 | 5 | 0 | complete | 0 |
| rf_rule_RF-THUNDERCLAP | null | system | 3 | 3 | 0 | complete | 0 |
| rf_fpr | null | system | 54 | 54 | 0 | complete | 0 |
| rf_surfaced | null | system | 26 | 26 | 0 | complete | 0 |
