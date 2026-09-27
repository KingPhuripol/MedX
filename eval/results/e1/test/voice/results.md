> **System Evaluation on synthetic data - not clinical performance**

# Table 3.2 evaluation results

> **System Evaluation, not clinical efficacy**
> **Research prototype - not for clinical use**
> **Synthetic data**

- Evaluation ID: e1-voice-test-v1 (slice e1)
- Dataset: s1r-synthetic vs1r-1.1.1+tree:e76e38cc67d6317d82196f105cb9781bedf3451b9ba74a1585b19662d4d1162b (synthetic); split: test (fb9454a2bc7433b663c6d921ebd68d3a1897bdbffb02dc3849e9d37976c828e9); frozen: yes
- Patients: 36; decision points: 40
- CI: 95% percentile patient-level cluster bootstrap, n_boot=2000, seed=20260926
- Manifest sha256: 460389615be2190180e37c30b6bd1a593c380c40153e31814a54e97358b387b0
- Frozen ledger entry hash: 97cbdee3bbbec4c07b9310024015b2fccd52ab67964607a9fb0a36eb59abc818
- Predictions sha256: ed5e514eebdb5d3c8ea30c5f71db6323df7787c43dca1857d2640fd5dbb8864e
- Comparator sha256: none
- numpy 2.5.3; eval 0.2.0

> **System Evaluation on synthetic data - not clinical performance**

| Evaluated item | Metric | Point estimate | 95% CI | Comparator | Difference (95% CI) | n patients / decision points | Threshold (predeclared rule) |
|---|---|---|---|---|---|---|---|
| Voice Agent | field_prf(component=precision, field=chief_complaint) | 1.0000 | [1.0000, 1.0000] | none declared | - | 23 / 24 | not declared |
| Voice Agent | field_prf(component=recall, field=chief_complaint) | 0.8636 | [0.6957, 1.0000] | none declared | - | 23 / 24 | not declared |
| Voice Agent | field_prf(component=f1, field=chief_complaint) *primary* | 0.9268 | [0.8205, 1.0000] | none declared | - | 23 / 24 | >= 0.8 on point: met |
| Voice Agent | field_prf(component=precision, field=onset_duration) | 1.0000 | [1.0000, 1.0000] | none declared | - | 36 / 40 | not declared |
| Voice Agent | field_prf(component=recall, field=onset_duration) | 1.0000 | [1.0000, 1.0000] | none declared | - | 36 / 40 | not declared |
| Voice Agent | field_prf(component=f1, field=onset_duration) *primary* | 1.0000 | [1.0000, 1.0000] | none declared | - | 36 / 40 | >= 0.8 on point: met |
| Voice Agent | field_prf(component=precision, field=allergy_status) | 1.0000 | [1.0000, 1.0000] | none declared | - | 36 / 40 | not declared |
| Voice Agent | field_prf(component=recall, field=allergy_status) | 1.0000 | [1.0000, 1.0000] | none declared | - | 36 / 40 | not declared |
| Voice Agent | field_prf(component=f1, field=allergy_status) *primary* | 1.0000 | [1.0000, 1.0000] | none declared | - | 36 / 40 | >= 0.8 on point: met |
| Voice Agent | field_prf(component=precision) | 1.0000 | [1.0000, 1.0000] | none declared | - | 36 / 40 | not declared |
| Voice Agent | field_prf(component=recall) | 0.9681 | [0.9310, 1.0000] | none declared | - | 36 / 40 | not declared |
| Voice Agent | field_prf(component=f1) | 0.9838 | [0.9643, 1.0000] | none declared | - | 36 / 40 | not declared |
| Voice Agent | accuracy(estimand=false-none rate: share of cases with gold allergy known or MISSING where S3 records KNOWN none) *primary* | 0.0000 | [0.0000, 0.0000] | none declared | - | 18 / 22 | <= 0 on point: met |

Undefined values are shown as null with a reason; they are never reported as 0 or 1. Differences are system minus comparator with a paired patient-level bootstrap CI.

## Split coverage

Every listed patient must have predictions. A missing patient refuses the run unless all metrics of the task are abstention-aware, where it is counted as abstain (imputation unit: 1 decision point per missing patient).

> **System Evaluation on synthetic data - not clinical performance**

| Task | Population | Arm | n_listed | n_predicted | n_missing | missing_policy | n_imputed_abstain_decision_points |
|---|---|---|---|---|---|---|---|
| voice_cc | null | system | 23 | 23 | 0 | complete | 0 |
| voice_intake | null | system | 36 | 36 | 0 | complete | 0 |
| voice_allergy_false_none | null | system | 18 | 18 | 0 | complete | 0 |
