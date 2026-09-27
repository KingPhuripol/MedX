# S6 care suggestion: dev before/after (System Evaluation on synthetic data — not clinical performance)

- before: s6-care-dev-0001 (care-rules-1.0.0), dataset 19033a7270f850852378834e4f76ffb5e90314ee88d0a303582999f6398c3e4d
- after: s6-care-dev-0002 (care-rules-1.1.0), dataset 518463d363934997be2b96a70ea8387564c9c94934dbae2f8e0ade0528072010
- point [patient-level bootstrap 95% CI]; exact = Clopper-Pearson patient-level when triggered; n patients / decision points (scored subset)

| Metric | dev-0001 | dev-0002 | Δ point |
|---|---|---|---|
| coverage | 0.7875 [0.6538, 0.9048]; n 36 / 80 (scored 36 / 80) | 0.7875 [0.6538, 0.9048]; n 36 / 80 (scored 36 / 80) | +0.0000 |
| selective_hit3 | 1.0000 [1.0000, 1.0000]; exact 15/15 [0.7820, 1.0000]; n 21 / 42 (scored 15 / 31) | 1.0000 [1.0000, 1.0000]; exact 15/15 [0.7820, 1.0000]; n 21 / 42 (scored 15 / 31) | +0.0000 |
| always_answer_hit3_all_evaluable | 1.0000 [1.0000, 1.0000]; exact 21/21 [0.8389, 1.0000]; n 21 / 42 (scored 21 / 42) | 1.0000 [1.0000, 1.0000]; exact 21/21 [0.8389, 1.0000]; n 21 / 42 (scored 21 / 42) | +0.0000 |
| always_answer_hit3_on_answered | 1.0000 [1.0000, 1.0000]; exact 15/15 [0.7820, 1.0000]; n 21 / 42 (scored 15 / 31) | 1.0000 [1.0000, 1.0000]; exact 15/15 [0.7820, 1.0000]; n 21 / 42 (scored 15 / 31) | +0.0000 |
| train_prior_hit3 | 0.5806 [0.3077, 0.8148]; n 21 / 42 (scored 15 / 31) | 0.5806 [0.3077, 0.8148]; n 21 / 42 (scored 15 / 31) | +0.0000 |
| ordered_proxy_hit3 | 0.0323 [0.0000, 0.1111]; n 36 / 40 (scored 27 / 31) | 0.0645 [0.0000, 0.1667]; n 36 / 40 (scored 27 / 31) | +0.0323 |
| pathway_top1 | 0.9394 [0.7931, 1.0000]; n 22 / 45 (scored 16 / 33) | 1.0000 [1.0000, 1.0000]; exact 16/16 [0.7941, 1.0000]; n 22 / 45 (scored 16 / 33) | +0.0606 |

Hit@3 is lenient (any one of the top 3 in the gold set counts). Labels are synthetic reference labels, not expert-reviewed (D1). Dev only; no test data was used for any rule change.
