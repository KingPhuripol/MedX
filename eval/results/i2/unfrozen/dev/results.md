> **System Evaluation on synthetic data — not clinical performance**
>
> Circularity note: rules, fixtures, extractor lexicon and gold share authors, so these results are circular. One deterministic mock model is used in both arms: the comparison measures graph structure (typed extraction, mandatory red-flag screening, abstention, call count, time), not model reasoning.

# Table 3.2 evaluation results

> **System Evaluation, not clinical efficacy**
> **Research prototype - not for clinical use**
> **Synthetic data**
> **UNFROZEN - exploratory (dev split)**

- Evaluation ID: i2-cg-vs-sp-dev-v1 (slice i2)
- Dataset: s1r-synthetic vs1r-1.1.1+tree:e76e38cc67d6317d82196f105cb9781bedf3451b9ba74a1585b19662d4d1162b (synthetic); split: dev (fb9454a2bc7433b663c6d921ebd68d3a1897bdbffb02dc3849e9d37976c828e9); frozen: no
- Patients: 36; decision points: 80
- CI: 95% percentile patient-level cluster bootstrap, n_boot=2000, seed=20260926
- Manifest sha256: f3dde4829fed55911b3bbe3de7fea50479e9a4487752e2ad2fe013c70bb6fea6
- Frozen ledger entry hash: none (not frozen)
- Predictions sha256: 329d5e8239de121058fa813c7af92ee00bc5ca4008c72fb2ffef2b9e00271564
- Comparator sha256: 23ee55efdb24d5e936369cc1f230a19969f2ea2843e599a381903fd5ce1ec4f0
- numpy 2.5.3; eval 0.2.0

> **System Evaluation on synthetic data — not clinical performance**
>
> Circularity note: rules, fixtures, extractor lexicon and gold share authors, so these results are circular. One deterministic mock model is used in both arms: the comparison measures graph structure (typed extraction, mandatory red-flag screening, abstention, call count, time), not model reasoning.


| Evaluated item | Metric | Point estimate | 95% CI | Comparator | Difference (95% CI) | n patients / decision points | Threshold (predeclared rule) |
|---|---|---|---|---|---|---|---|
| Case Graph | topk_accuracy(estimand=top-1 in E over evaluable DPs with a mappable gold; an abstention counts as wrong, k=1) *primary* | 0.5000 | [0.3077, 0.6923] | single_prompt: 0.5192 | -0.0192 [-0.0612, 0.0000] | 27 / 52 | not declared |
| Case Graph | topk_accuracy(estimand=top-3 in E, same population, k=3) | 0.5000 | [0.3077, 0.6923] | single_prompt: 0.5192 | -0.0192 [-0.0612, 0.0000] | 27 / 52 | not declared |
| Case Graph | coverage(estimand=answered share of the dept population plus the NOT_EVALUABLE DPs) | 0.5536 | [0.3750, 0.7368] | single_prompt: 0.5714 | -0.0179 [-0.0566, 0.0000] | 29 / 56 | not declared |
| Case Graph | selective_accuracy(estimand=top-1 among answered DPs; answering a NOT_EVALUABLE DP is wrong) | 0.8387 | [0.6286, 1.0000] | single_prompt: 0.8438 | -0.0050 [-0.0238, 0.0000] | 29 / 56 | not declared |
| Case Graph | latency_summary(estimand=mean gateway calls per DP, field=n_calls, stat=mean) | 4.6500 | [4.3649, 4.9421] | single_prompt: 1.0000 | 3.6500 [3.3649, 3.9421] | 36 / 80 | not declared |
| Case Graph | accuracy(estimand=Arm A recall of RF-ACUTE-CHEST-PAIN: gold DPs where a mapped S4 rule fired) | 1.0000 | [1.0000, 1.0000] | none declared | - | 2 / 4 | >= 1.0 on point: met |
| Case Graph | accuracy(estimand=Arm A recall of RF-ANAPHYLAXIS: gold DPs where a mapped S4 rule fired) | 1.0000 | [1.0000, 1.0000] | none declared | - | 2 / 4 | >= 1.0 on point: met |
| Case Graph | accuracy(estimand=Arm A recall of RF-FAST: gold DPs where a mapped S4 rule fired) | 1.0000 | [1.0000, 1.0000] | none declared | - | 2 / 4 | >= 1.0 on point: met |
| Case Graph | accuracy(estimand=Arm A recall of RF-NEWS-SINGLE3: gold DPs where a mapped S4 rule fired) | 1.0000 | [1.0000, 1.0000] | none declared | - | 2 / 3 | not declared |
| Case Graph | accuracy(estimand=Arm A recall of RF-QSOFA: gold DPs where a mapped S4 rule fired) | 1.0000 | [1.0000, 1.0000] | none declared | - | 1 / 2 | not declared |
| Case Graph | accuracy(estimand=Arm A recall of RF-THUNDERCLAP: gold DPs where a mapped S4 rule fired) | 1.0000 | [1.0000, 1.0000] | none declared | - | 2 / 4 | >= 1.0 on point: met |

Undefined values are shown as null with a reason; they are never reported as 0 or 1. Differences are system minus comparator with a paired patient-level bootstrap CI.

## Split coverage

Every listed patient must have predictions. A missing patient refuses the run unless all metrics of the task are abstention-aware, where it is counted as abstain (imputation unit: 1 decision point per missing patient).

> **System Evaluation on synthetic data — not clinical performance**
>
> Circularity note: rules, fixtures, extractor lexicon and gold share authors, so these results are circular. One deterministic mock model is used in both arms: the comparison measures graph structure (typed extraction, mandatory red-flag screening, abstention, call count, time), not model reasoning.


| Task | Population | Arm | n_listed | n_predicted | n_missing | missing_policy | n_imputed_abstain_decision_points |
|---|---|---|---|---|---|---|---|
| dept | null | system | 27 | 27 | 0 | complete | 0 |
|  |  | comparator:single_prompt | 27 | 27 | 0 |  | 0 |
| abstention | null | system | 29 | 29 | 0 | complete | 0 |
|  |  | comparator:single_prompt | 29 | 29 | 0 |  | 0 |
| calls | null | system | 36 | 36 | 0 | complete | 0 |
|  |  | comparator:single_prompt | 36 | 36 | 0 |  | 0 |
| rf_rule_RF-ACUTE-CHEST-PAIN | null | system | 2 | 2 | 0 | complete | 0 |
| rf_rule_RF-ANAPHYLAXIS | null | system | 2 | 2 | 0 | complete | 0 |
| rf_rule_RF-FAST | null | system | 2 | 2 | 0 | complete | 0 |
| rf_rule_RF-NEWS-SINGLE3 | null | system | 2 | 2 | 0 | complete | 0 |
| rf_rule_RF-QSOFA | null | system | 1 | 1 | 0 | complete | 0 |
| rf_rule_RF-THUNDERCLAP | null | system | 2 | 2 | 0 | complete | 0 |
