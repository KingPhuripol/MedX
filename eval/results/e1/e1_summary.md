# e1 System Evaluation: Voice (S3) and Triage (S4) on S1r

> **System Evaluation on synthetic data - not clinical performance**
> **Research prototype - not for clinical use**

System Evaluation of the as-built S3 and S4 on synthetic S1r data; not clinical performance; not expert-reviewed. Outcome thresholds are reported as PASS/FAIL and do not gate the slice.

## Red-flag recall verdicts (predeclared: point >= 1.00)

> **System Evaluation on synthetic data - not clinical performance**

| Split | Metric | x / n | Point | Interval (method) | Verdict |
|---|---|---|---|---|---|
| dev | rf_case_recall | 5 / 24 | 0.2083 | [0.0000, 0.4545] (bootstrap_percentile) | FAIL |
| dev | rf_rule_recall | 5 / 26 | 0.1923 | [0.0000, 0.3847] (bootstrap_percentile) | FAIL |
| test | rf_case_recall | null / null | null | null (None) | NOT RUN |
| test | rf_rule_recall | null / null | null | null (None) | NOT RUN |

Wilson and Clopper-Pearson intervals assume independent decision points; decision points of one patient are not independent, so they ignore patient clustering. They are shown next to the patient-level bootstrap CI and n_patients.

A bootstrap CI is degenerate when the S8r flag 'unstable' is set, ci_low == ci_high, or x is 0 or n; the reported interval is then Clopper-Pearson (interval_method='clopper_pearson'). Otherwise the patient-level bootstrap percentile interval is reported.

## Split: dev

- Evaluation IDs: e1-triage-dev-v1, e1-voice-dev-v1; frozen: yes
- Patients in split: 36

### Threshold verdicts (predeclared rule only)

> **System Evaluation on synthetic data - not clinical performance**

| Metric | Rule | Compared value | Verdict |
|---|---|---|---|
| voice_cc_f1 | >= 0.8 on point | 0.9796 | PASS |
| voice_dur_f1 | >= 0.8 on point | 1.0000 | PASS |
| voice_allergy_f1 | >= 0.8 on point | 1.0000 | PASS |
| voice_allergy_false_none_rate | <= 0 on point | 0.0000 | PASS |
| rf_case_recall | >= 1.0 on point | 0.2083 | FAIL |
| rf_rule_recall | >= 1.0 on point | 0.1923 | FAIL |
| dept_top3 | >= 0.8 on point | 0.5000 | FAIL |

### Metric rows

> **System Evaluation on synthetic data - not clinical performance**

| Metric | Arm | Estimand | x / n | Point | Bootstrap 95% CI | Wilson | Clopper-Pearson | Reported interval (method) | n patients / n units | Paired diff (sys - comp) |
|---|---|---|---|---|---|---|---|---|---|---|
| voice_cc_precision | system | component=precision, field=chief_complaint | 24 / 24 | 1.0000 | [1.0000, 1.0000] | [0.8620, 1.0000] | [0.8575, 1.0000] | [0.8575, 1.0000] (clopper_pearson) | 27 / 27 | - |
| voice_cc_recall | system | component=recall, field=chief_complaint | 24 / 25 | 0.9600 | [0.8749, 1.0000] | [0.8046, 0.9929] | [0.7965, 0.9990] | [0.8749, 1.0000] (bootstrap_percentile) | 27 / 27 | - |
| voice_cc_f1 | system | component=f1, field=chief_complaint | 48 / 49 | 0.9796 | [0.9333, 1.0000] | null | null | [0.9333, 1.0000] (bootstrap_percentile) | 27 / 27 | - |
| voice_dur_precision | system | component=precision, field=onset_duration | 36 / 36 | 1.0000 | [1.0000, 1.0000] | [0.9036, 1.0000] | [0.9026, 1.0000] | [0.9026, 1.0000] (clopper_pearson) | 36 / 40 | - |
| voice_dur_recall | system | component=recall, field=onset_duration | 36 / 36 | 1.0000 | [1.0000, 1.0000] | [0.9036, 1.0000] | [0.9026, 1.0000] | [0.9026, 1.0000] (clopper_pearson) | 36 / 40 | - |
| voice_dur_f1 | system | component=f1, field=onset_duration | 72 / 72 | 1.0000 | [1.0000, 1.0000] | null | null | [1.0000, 1.0000] (bootstrap_percentile) | 36 / 40 | - |
| voice_allergy_precision | system | component=precision, field=allergy_status | 36 / 36 | 1.0000 | [1.0000, 1.0000] | [0.9036, 1.0000] | [0.9026, 1.0000] | [0.9026, 1.0000] (clopper_pearson) | 36 / 40 | - |
| voice_allergy_recall | system | component=recall, field=allergy_status | 36 / 36 | 1.0000 | [1.0000, 1.0000] | [0.9036, 1.0000] | [0.9026, 1.0000] | [0.9026, 1.0000] (clopper_pearson) | 36 / 40 | - |
| voice_allergy_f1 | system | component=f1, field=allergy_status | 72 / 72 | 1.0000 | [1.0000, 1.0000] | null | null | [1.0000, 1.0000] (bootstrap_percentile) | 36 / 40 | - |
| voice_micro_precision | system | component=precision | 96 / 96 | 1.0000 | [1.0000, 1.0000] | [0.9615, 1.0000] | [0.9623, 1.0000] | [0.9623, 1.0000] (clopper_pearson) | 36 / 40 | - |
| voice_micro_recall | system | component=recall | 96 / 97 | 0.9897 | [0.9677, 1.0000] | [0.9439, 0.9982] | [0.9439, 0.9997] | [0.9677, 1.0000] (bootstrap_percentile) | 36 / 40 | - |
| voice_micro_f1 | system | component=f1 | 192 / 193 | 0.9948 | [0.9836, 1.0000] | null | null | [0.9836, 1.0000] (bootstrap_percentile) | 36 / 40 | - |
| voice_allergy_false_none_rate | system | false-none rate: share of cases with gold allergy known or MISSING where S3 records KNOWN none | 0 / 18 | 0.0000 | [0.0000, 0.0000] | [0.0000, 0.1759] | [0.0000, 0.1853] | [0.0000, 0.1853] (clopper_pearson) | 17 / 18 | - |
| rf_case_recall | system | case-level red-flag recall: gold-positive DPs with >=1 S4 alert of any rule | 5 / 24 | 0.2083 | [0.0000, 0.4545] | [0.0924, 0.4047] | [0.0713, 0.4215] | [0.0000, 0.4545] (bootstrap_percentile) | 13 / 24 | - |
| rf_rule_recall | system | rule-level recall pooled over gold (DP, rule) pairs; UNMAPPABLE pairs count as missed | 5 / 26 | 0.1923 | [0.0000, 0.3847] | [0.0851, 0.3788] | [0.0655, 0.3935] | [0.0000, 0.3847] (bootstrap_percentile) | 13 / 24 | - |
| rf_rule_recall_mappable | system | rule-level recall over mappable gold (DP, rule) pairs (secondary) | 5 / 21 | 0.2381 | [0.0000, 0.5238] | [0.1063, 0.4509] | [0.0822, 0.4717] | [0.0000, 0.5238] (bootstrap_percentile) | 11 / 21 | - |
| rf_rule_RF-ACUTE-CHEST-PAIN | system | per-rule recall of RF-ACUTE-CHEST-PAIN: gold DPs where a mapped S4 rule fired | 0 / 4 | 0.0000 | [0.0000, 0.0000] | [0.0000, 0.4899] | [0.0000, 0.6024] | [0.0000, 0.6024] (clopper_pearson) | 2 / 4 | - |
| rf_rule_RF-ANAPHYLAXIS | system | per-rule recall of RF-ANAPHYLAXIS: gold DPs where a mapped S4 rule fired | 0 / 4 | 0.0000 | [0.0000, 0.0000] | [0.0000, 0.4899] | [0.0000, 0.6024] | [0.0000, 0.6024] (clopper_pearson) | 2 / 4 | - |
| rf_rule_RF-FAST | system | per-rule recall of RF-FAST: gold DPs where a mapped S4 rule fired | 0 / 4 | 0.0000 | [0.0000, 0.0000] | [0.0000, 0.4899] | [0.0000, 0.6024] | [0.0000, 0.6024] (clopper_pearson) | 2 / 4 | - |
| rf_rule_RF-NEWS-SINGLE3 | system | per-rule recall of RF-NEWS-SINGLE3: gold DPs where a mapped S4 rule fired | 3 / 3 | 1.0000 | [1.0000, 1.0000] | [0.4385, 1.0000] | [0.2924, 1.0000] | [0.2924, 1.0000] (clopper_pearson) | 2 / 3 | - |
| rf_rule_RF-QSOFA | system | per-rule recall of RF-QSOFA: gold DPs where a mapped S4 rule fired | 2 / 2 | 1.0000 | [1.0000, 1.0000] | [0.3424, 1.0000] | [0.1581, 1.0000] | [0.1581, 1.0000] (clopper_pearson) | 1 / 2 | - |
| rf_rule_RF-THUNDERCLAP | system | per-rule recall of RF-THUNDERCLAP: gold DPs where a mapped S4 rule fired | 0 / 4 | 0.0000 | [0.0000, 0.0000] | [0.0000, 0.4899] | [0.0000, 0.6024] | [0.0000, 0.6024] (clopper_pearson) | 2 / 4 | - |
| rf_fpr | system | false-positive rate: gold-negative DPs with >=1 S4 alert of any rule | 0 / 56 | 0.0000 | [0.0000, 0.0000] | [0.0000, 0.0642] | [0.0000, 0.0638] | [0.0000, 0.0638] (clopper_pearson) | 29 / 56 | - |
| rf_fpr_mapped | system | false-positive rate counting only S4 rules mapped to the S1r registry (secondary) | 0 / 56 | 0.0000 | [0.0000, 0.0000] | [0.0000, 0.0642] | [0.0000, 0.0638] | [0.0000, 0.0638] (clopper_pearson) | 29 / 56 | - |
| rf_text_t1_recall | system | text red-flag recall at T1: any alert of RF-CHEST, RF-STROKE, RF-THUNDER, RF-ANAPH | 0 / 8 | 0.0000 | [0.0000, 0.0000] | [0.0000, 0.3244] | [0.0000, 0.3694] | [0.0000, 0.3694] (clopper_pearson) | 8 / 8 | - |
| rf_text_t1_recall | comparator:shortcut_s_star | text red-flag recall at T1: any alert of RF-CHEST, RF-STROKE, RF-THUNDER, RF-ANAPH | 2 / 8 | 0.2500 | [0.0000, 0.6250] | [0.0715, 0.5907] | [0.0319, 0.6509] | [0.0000, 0.6250] (bootstrap_percentile) | 8 / 8 | -0.2500 [-0.6250, 0.0000] |
| rf_text_t1_recall | comparator:shortcut_tamtee | text red-flag recall at T1: any alert of RF-CHEST, RF-STROKE, RF-THUNDER, RF-ANAPH | 3 / 8 | 0.3750 | [0.1250, 0.7500] | [0.1368, 0.6943] | [0.0852, 0.7551] | [0.1250, 0.7500] (bootstrap_percentile) | 8 / 8 | -0.3750 [-0.7500, -0.1250] |
| rf_text_t1_fpr | system | text red-flag false-positive rate at T1 (same alert set) | 0 / 32 | 0.0000 | [0.0000, 0.0000] | [0.0000, 0.1072] | [0.0000, 0.1089] | [0.0000, 0.1089] (clopper_pearson) | 31 / 32 | - |
| rf_text_t1_fpr | comparator:shortcut_s_star | text red-flag false-positive rate at T1 (same alert set) | 2 / 32 | 0.0625 | [0.0000, 0.1562] | [0.0173, 0.2015] | [0.0077, 0.2081] | [0.0000, 0.1562] (bootstrap_percentile) | 31 / 32 | -0.0625 [-0.1562, 0.0000] |
| rf_text_t1_fpr | comparator:shortcut_tamtee | text red-flag false-positive rate at T1 (same alert set) | 11 / 32 | 0.3438 | [0.1818, 0.5161] | [0.2041, 0.5169] | [0.1857, 0.5319] | [0.1818, 0.5161] (bootstrap_percentile) | 31 / 32 | -0.3438 [-0.5161, -0.1818] |
| dept_top1 | system | k=1 | 26 / 52 | 0.5000 | [0.3077, 0.6923] | [0.3689, 0.6311] | [0.3581, 0.6419] | [0.3077, 0.6923] (bootstrap_percentile) | 27 / 52 | - |
| dept_top1 | comparator:always_answer | k=1 | 31 / 52 | 0.5962 | [0.4038, 0.7843] | [0.4607, 0.7184] | [0.4510, 0.7299] | [0.4038, 0.7843] (bootstrap_percentile) | 27 / 52 | -0.0962 [-0.2157, 0.0000] |
| dept_top3 | system | k=3 | 26 / 52 | 0.5000 | [0.3077, 0.6923] | [0.3689, 0.6311] | [0.3581, 0.6419] | [0.3077, 0.6923] (bootstrap_percentile) | 27 / 52 | - |
| dept_top3 | comparator:always_answer | k=3 | 31 / 52 | 0.5962 | [0.4038, 0.7843] | [0.4607, 0.7184] | [0.4510, 0.7299] | [0.4038, 0.7843] (bootstrap_percentile) | 27 / 52 | -0.0962 [-0.2157, 0.0000] |
| abst_coverage | system |  | 31 / 56 | 0.5536 | [0.3750, 0.7368] | [0.4241, 0.6761] | [0.4147, 0.6866] | [0.3750, 0.7368] (bootstrap_percentile) | 29 / 56 | - |
| abst_coverage | comparator:always_answer |  | 56 / 56 | 1.0000 | [1.0000, 1.0000] | [0.9358, 1.0000] | [0.9362, 1.0000] | [0.9362, 1.0000] (clopper_pearson) | 29 / 56 | -0.4464 [-0.6250, -0.2632] |
| abst_selective_top1 | system | top-1 accuracy among answered DPs; answering a NOT_EVALUABLE DP is wrong | 26 / 31 | 0.8387 | [0.6286, 1.0000] | [0.6737, 0.9291] | [0.6627, 0.9455] | [0.6286, 1.0000] (bootstrap_percentile) | 29 / 56 | - |
| abst_selective_top1 | comparator:always_answer | top-1 accuracy among answered DPs; answering a NOT_EVALUABLE DP is wrong | 31 / 56 | 0.5536 | [0.3683, 0.7323] | [0.4241, 0.6761] | [0.4147, 0.6866] | [0.3683, 0.7323] (bootstrap_percentile) | 29 / 56 | 0.2851 [0.1195, 0.4702] |
| abst_rate_not_evaluable | system | abstain rate on NOT_EVALUABLE DPs (secondary) | 4 / 4 | 1.0000 | [1.0000, 1.0000] | [0.5101, 1.0000] | [0.3976, 1.0000] | [0.3976, 1.0000] (clopper_pearson) | 2 / 4 | - |
| abst_false_abstain_rate | system | false-abstain rate on the department population (secondary) | 21 / 52 | 0.4038 | [0.2222, 0.6078] | [0.2816, 0.5393] | [0.2701, 0.5490] | [0.2222, 0.6078] (bootstrap_percentile) | 27 / 52 | - |
| abst_expected_action_agreement | system | 3-class expected_action agreement (suggest/abstain/escalate) over every DP (secondary) | 39 / 80 | 0.4875 | [0.3293, 0.6447] | [0.3811, 0.5951] | [0.3741, 0.6019] | [0.3293, 0.6447] (bootstrap_percentile) | 36 / 80 | - |

### Null rows

> **System Evaluation on synthetic data - not clinical performance**

| Metric | Point | n | Reason |
|---|---|---|---|
| rf_rule_RF-NEWS-AGG5 | null | 5 | UNMAPPABLE: S4 has no counterpart rule; its gold pairs count as missed in rf_rule_recall |

### Populations (n_total = n_scored + excluded)

> **System Evaluation on synthetic data - not clinical performance**

| Population | Definition | Unit | n_total | n_scored | Excluded by reason | n patients |
|---|---|---|---|---|---|---|
| voice_intake | every case at T1 (onset_duration, allergy_status, micro-average) | case | 40 | 40 | none | 36 |
| voice_cc | cases whose gold CC is mappable to S3 or MISSING (chief_complaint field) | case | 40 | 27 | UNMAPPABLE: 13 | 27 |
| voice_allergy_false_none | cases with gold allergy known or MISSING | case | 40 | 18 | gold_no_known_allergy: 22 | 17 |
| rf_case_recall | gold red-flag-positive DPs | decision point | 80 | 24 | gold_negative (scored by rf_fpr): 56 | 13 |
| rf_fpr | gold red-flag-negative DPs | decision point | 80 | 56 | gold_positive (scored by rf_case_recall): 24 | 29 |
| rf_rule_recall | gold (DP, rule) pairs; UNMAPPABLE pairs scored as missed | (DP, rule) pair | 26 | 26 | none | 13 |
| rf_rule_recall_mappable | gold (DP, rule) pairs with a mapped S4 rule | (DP, rule) pair | 26 | 21 | UNMAPPABLE: 5 | 11 |
| rf_rule:RF-ACUTE-CHEST-PAIN | gold DPs with RF-ACUTE-CHEST-PAIN | decision point | 4 | 4 | none | 2 |
| rf_rule:RF-ANAPHYLAXIS | gold DPs with RF-ANAPHYLAXIS | decision point | 4 | 4 | none | 2 |
| rf_rule:RF-FAST | gold DPs with RF-FAST | decision point | 4 | 4 | none | 2 |
| rf_rule:RF-NEWS-AGG5 | gold DPs with RF-NEWS-AGG5 | decision point | 5 | 0 | UNMAPPABLE: 5 | 0 |
| rf_rule:RF-NEWS-SINGLE3 | gold DPs with RF-NEWS-SINGLE3 | decision point | 3 | 3 | none | 2 |
| rf_rule:RF-QSOFA | gold DPs with RF-QSOFA | decision point | 2 | 2 | none | 1 |
| rf_rule:RF-THUNDERCLAP | gold DPs with RF-THUNDERCLAP | decision point | 4 | 4 | none | 2 |
| rf_text_t1_recall | T1 DPs with a gold text red flag | decision point | 80 | 8 | T1 text-negative (scored by rf_text_t1_fpr): 32; not T1: 40 | 8 |
| rf_text_t1_fpr | T1 DPs without a gold text red flag | decision point | 80 | 32 | T1 text-positive (scored by rf_text_t1_recall): 8; not T1: 40 | 31 |
| dept | DPs with department_evaluable and a gold department in E | decision point | 80 | 52 | 11: 2; 12: 22; NOT_EVALUABLE: 4; UNMAPPABLE: 0 | 27 |
| false_abstain | department population | decision point | 80 | 52 | 11: 2; 12: 22; NOT_EVALUABLE: 4; UNMAPPABLE: 0 | 27 |
| abstention | department population + NOT_EVALUABLE DPs | decision point | 80 | 56 | 11: 2; 12: 22 | 29 |
| abst_on_not_evaluable | NOT_EVALUABLE DPs | decision point | 80 | 4 | 11: 2; 12: 22; department population: 52 | 2 |
| expected_action | every DP (the 3-class label is defined on every DP) | decision point | 80 | 80 | none | 36 |

### Missed gold red flags: DPs with no alert at all

> **System Evaluation on synthetic data - not clinical performance**

| Case | DP | T | Gold rule |
|---|---|---|---|
| SYNE-0071 | T1 | 2030-05-12T09:35:32+07:00 | RF-ANAPHYLAXIS |
| SYNE-0071 | T2 | 2030-05-12T11:05:32+07:00 | RF-ANAPHYLAXIS |
| SYNE-0081 | T1 | 2030-07-07T16:05:33+07:00 | RF-ACUTE-CHEST-PAIN |
| SYNE-0081 | T2 | 2030-07-07T17:35:33+07:00 | RF-ACUTE-CHEST-PAIN |
| SYNE-0089 | T1 | 2030-09-23T08:46:10+07:00 | RF-ACUTE-CHEST-PAIN |
| SYNE-0089 | T2 | 2030-09-23T10:16:10+07:00 | RF-ACUTE-CHEST-PAIN |
| SYNE-0107 | T1 | 2030-04-22T15:54:43+07:00 | RF-NEWS-AGG5 |
| SYNE-0107 | T2 | 2030-04-22T17:24:43+07:00 | RF-NEWS-AGG5 |
| SYNE-0108 | T1 | 2030-08-26T12:20:09+07:00 | RF-THUNDERCLAP |
| SYNE-0108 | T2 | 2030-08-26T13:50:09+07:00 | RF-THUNDERCLAP |
| SYNE-0119 | T1 | 2030-09-15T13:14:24+07:00 | RF-ANAPHYLAXIS |
| SYNE-0119 | T2 | 2030-09-15T14:44:24+07:00 | RF-ANAPHYLAXIS |
| SYNE-0127 | T1 | 2030-01-28T12:25:31+07:00 | RF-THUNDERCLAP |
| SYNE-0127 | T2 | 2030-01-28T13:55:31+07:00 | RF-THUNDERCLAP |
| SYNE-0165 | T2 | 2030-05-16T12:42:17+07:00 | RF-NEWS-AGG5 |
| SYNE-0166 | T1 | 2030-10-26T15:56:24+07:00 | RF-FAST |
| SYNE-0166 | T2 | 2030-10-26T17:26:24+07:00 | RF-FAST |
| SYNE-0196 | T1 | 2030-12-05T12:10:51+07:00 | RF-FAST |
| SYNE-0196 | T2 | 2030-12-05T13:40:51+07:00 | RF-FAST |

### Missed gold (DP, rule) pairs

> **System Evaluation on synthetic data - not clinical performance**

| Case | DP | T | Gold rule | Reason |
|---|---|---|---|---|
| SYNE-0030 | T1 | 2030-04-14T10:10:13+07:00 | RF-NEWS-AGG5 | UNMAPPABLE (no S4 counterpart) |
| SYNE-0030 | T2 | 2030-04-14T11:40:13+07:00 | RF-NEWS-AGG5 | UNMAPPABLE (no S4 counterpart) |
| SYNE-0071 | T1 | 2030-05-12T09:35:32+07:00 | RF-ANAPHYLAXIS | no alert at this DP |
| SYNE-0071 | T2 | 2030-05-12T11:05:32+07:00 | RF-ANAPHYLAXIS | no alert at this DP |
| SYNE-0081 | T1 | 2030-07-07T16:05:33+07:00 | RF-ACUTE-CHEST-PAIN | no alert at this DP |
| SYNE-0081 | T2 | 2030-07-07T17:35:33+07:00 | RF-ACUTE-CHEST-PAIN | no alert at this DP |
| SYNE-0089 | T1 | 2030-09-23T08:46:10+07:00 | RF-ACUTE-CHEST-PAIN | no alert at this DP |
| SYNE-0089 | T2 | 2030-09-23T10:16:10+07:00 | RF-ACUTE-CHEST-PAIN | no alert at this DP |
| SYNE-0107 | T1 | 2030-04-22T15:54:43+07:00 | RF-NEWS-AGG5 | UNMAPPABLE (no S4 counterpart) |
| SYNE-0107 | T2 | 2030-04-22T17:24:43+07:00 | RF-NEWS-AGG5 | UNMAPPABLE (no S4 counterpart) |
| SYNE-0108 | T1 | 2030-08-26T12:20:09+07:00 | RF-THUNDERCLAP | no alert at this DP |
| SYNE-0108 | T2 | 2030-08-26T13:50:09+07:00 | RF-THUNDERCLAP | no alert at this DP |
| SYNE-0119 | T1 | 2030-09-15T13:14:24+07:00 | RF-ANAPHYLAXIS | no alert at this DP |
| SYNE-0119 | T2 | 2030-09-15T14:44:24+07:00 | RF-ANAPHYLAXIS | no alert at this DP |
| SYNE-0127 | T1 | 2030-01-28T12:25:31+07:00 | RF-THUNDERCLAP | no alert at this DP |
| SYNE-0127 | T2 | 2030-01-28T13:55:31+07:00 | RF-THUNDERCLAP | no alert at this DP |
| SYNE-0165 | T2 | 2030-05-16T12:42:17+07:00 | RF-NEWS-AGG5 | UNMAPPABLE (no S4 counterpart) |
| SYNE-0166 | T1 | 2030-10-26T15:56:24+07:00 | RF-FAST | no alert at this DP |
| SYNE-0166 | T2 | 2030-10-26T17:26:24+07:00 | RF-FAST | no alert at this DP |
| SYNE-0196 | T1 | 2030-12-05T12:10:51+07:00 | RF-FAST | no alert at this DP |
| SYNE-0196 | T2 | 2030-12-05T13:40:51+07:00 | RF-FAST | no alert at this DP |

### Alerts on gold-negative DPs, by S4 rule

> **System Evaluation on synthetic data - not clinical performance**

| S4 rule | n | DPs |
|---|---|---|
| (none) |  |  |

### Alerts from S4 rules outside the S1r registry (all DPs)

> **System Evaluation on synthetic data - not clinical performance**

| S4 rule | n alerts | DPs |
|---|---|---|
| RF-ECTOPIC | 0 | - |
| RF-GIBLEED | 0 | - |
| RF-HYPOGLY | 0 | - |
| RF-MENING | 0 | - |
| RF-SUICIDE | 0 | - |

### expected_action confusion (rows gold, columns system)

> **System Evaluation on synthetic data - not clinical performance**

| gold \ system | abstain | escalate | suggest |
|---|---|---|---|
| abstain | 5 | 0 | 2 |
| escalate | 11 | 5 | 8 |
| suggest | 20 | 0 | 29 |

### Unmapped items per mapping section

> **System Evaluation on synthetic data - not clinical performance**

| Section | Item | Count |
|---|---|---|
| chief_complaint_s1r_to_s3 | UNMAPPABLE codes met | {"CC-ABSCESS": 1, "CC-CARIES": 1, "CC-DISCHARGE": 1, "CC-EAR-PAIN": 1, "CC-EPISTAXIS": 1, "CC-GROIN-LUMP": 1, "CC-LOW-MOOD": 1, "CC-PALPITATION": 1, "CC-PREG-ITCH": 1, "CC-RF-FAST-2": 1, "CC-RF-FAST-3": 1, "CC-TNM-DEFICIT-1": 1, "CC-TNM-NUMB-1": 1} |
| chief_complaint_s1r_to_s3 | cases with UNMAPPABLE gold CC | 13 |
| consciousness | C values mapped to avpu A + new_confusion | 3 |
| department_s1r | 11 (UNMAPPABLE, excluded) | 2 |
| department_s1r | 12 (scored by red-flag metrics) | 22 |
| department_s1r | NOT_EVALUABLE (abstention only) | 4 |
| red_flag_s1r | RF-NEWS-AGG5 gold pairs (UNMAPPABLE) | 5 |
| s3_cc_to_s4_symptom | S3 CC codes with no S4 symptom (per case) | {"chest_pain": 4, "diarrhea": 2, "fatigue": 2, "rash": 2, "runny_nose": 2} |
| s3_field_to_s4_fact | S3 fields not KNOWN -> no S4 fact (per case, T1) | {"chief_complaint:MISSING": 13, "chief_complaint:UNKNOWN": 1, "onset_duration:MISSING": 1, "onset_duration:UNKNOWN": 3} |
| vitals_demographics | null vital values (no fact) | 2 |
| vitals_demographics | on_oxygen values not passed (UNMAPPABLE) | 120 |
| vitals_demographics | pregnancy_status (no S1r item) | 80 |
| vitals_demographics | unit | per S4 case built (one per DP) |

### Comparators

> **System Evaluation on synthetic data - not clinical performance**

| Comparator | Definition | Train-split selection evidence |
|---|---|---|
| shortcut_s_star | contains('ทีค') | {"f1": 0.7222222222222223, "n_candidates": 57531, "n_cases": 120, "n_positive": 20, "precision": 0.8125, "recall": 0.65, "support": 16} |
| shortcut_tamtee | contains('ทันที') | {"f1": 0.3225806451612903, "precision": 0.23809523809523808, "recall": 0.5, "support": 42} |
| always_answer | S4 baseline.rank, fallback E-MED | {"E-ENT": 16, "E-EYE": 8, "E-MED": 80, "E-OBGYN": 22, "E-ORTHO": 10, "E-PSY": 10, "E-SURG": 10} |

### S3 final field states (per case)

> **System Evaluation on synthetic data - not clinical performance**

| Field | States |
|---|---|
| allergy_status | {"KNOWN": 36, "MISSING": 4} |
| chief_complaint | {"KNOWN": 26, "MISSING": 13, "UNKNOWN": 1} |
| onset_duration | {"KNOWN": 36, "MISSING": 1, "UNKNOWN": 3} |

## Split: test

Not run: the test split runs once, after all 4 e1 manifests are frozen and committed (spec scope 6)

## Not evaluated

> **System Evaluation on synthetic data - not clinical performance**

| Row | Reason |
|---|---|
| Voice Agent: comparison with form filling | needs a human-factors study with users; S3 out of scope (no form-filling comparator can be simulated honestly) |
| Voice Agent: response latency and total time | in-process mock timing is not representative of a deployed system, and recording wall-clock time would break byte reproducibility |
