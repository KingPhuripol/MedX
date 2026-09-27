# i2: Case Graph vs single prompt

> **System Evaluation on synthetic data — not clinical performance**

Circularity note: rules, fixtures, extractor lexicon and gold share authors, so these results are circular. One deterministic mock model is used in both arms: the comparison measures graph structure (typed extraction, mandatory red-flag screening, abstention, call count, time), not model reasoning.

Research question: With the same mock model, how does the Case Graph compare with one prompt over the whole snapshot? (PROPOSAL Table 3.2, row Case Graph)

Predeclared expectation: Equal accuracy on DPs where both arms answer; the Case Graph abstains on NOT_EVALUABLE DPs where the single prompt answers; the Case Graph makes more model calls.

## dev

UNFROZEN - exploratory (dev split); n_dp=80, n_patients=36; manifest `f3dde4829fed`

> **System Evaluation on synthetic data — not clinical performance**
>
> Circularity note: rules, fixtures, extractor lexicon and gold share authors, so these results are circular. One deterministic mock model is used in both arms: the comparison measures graph structure (typed extraction, mandatory red-flag screening, abstention, call count, time), not model reasoning.

| metric | Case Graph | CI | single prompt | CI | A - B | paired CI (patient bootstrap) |
|---|---|---|---|---|---|---|
| calls_per_dp | 4.6500 | [4.3649, 4.9421] | 1.0000 | [1.0000, 1.0000] | 3.6500 | [3.3649, 3.9421] |
| coverage | 0.5536 | [0.3750, 0.7368] | 0.5714 | [0.3929, 0.7500] | -0.0179 | [-0.0566, 0.0000] |
| dept_top1 | 0.5000 | [0.3077, 0.6923] | 0.5192 | [0.3269, 0.7143] | -0.0192 | [-0.0612, 0.0000] |
| dept_top3 | 0.5000 | [0.3077, 0.6923] | 0.5192 | [0.3269, 0.7143] | -0.0192 | [-0.0612, 0.0000] |
| selective_top1 | 0.8387 | [0.6286, 1.0000] | 0.8438 | [0.6452, 1.0000] | -0.0050 | [-0.0238, 0.0000] |

> **System Evaluation on synthetic data — not clinical performance**
>
> Circularity note: rules, fixtures, extractor lexicon and gold share authors, so these results are circular. One deterministic mock model is used in both arms: the comparison measures graph structure (typed extraction, mandatory red-flag screening, abstention, call count, time), not model reasoning.

| arm | calls total | calls per DP | per node |
|---|---|---|---|
| Case Graph | 372 | 4.6500 | human_checkpoint=0, pharma_agent=0, reader_text=280, reader_vitals_labs=0, reasoning=92, red_flag=0 |
| single prompt | 80 | 1.0000 | single_prompt |

Arms matched: identical handler versions = True; identical top-3 on 46 of 46 DPs where both answer. Wall time: see `timing.json`.

Red-flag recall per S1r rule (Case Graph). Single prompt: null: Arm B runs without a Red-flag node by design, so it emits no screening output; the screening is not compared between arms and its absence in Arm B is not a safety result.

> **System Evaluation on synthetic data — not clinical performance**
>
> Circularity note: rules, fixtures, extractor lexicon and gold share authors, so these results are circular. One deterministic mock model is used in both arms: the comparison measures graph structure (typed extraction, mandatory red-flag screening, abstention, call count, time), not model reasoning.

| S1r rule | x | n | n_patients | recall | Wilson | Clopper-Pearson | bootstrap | reported |
|---|---|---|---|---|---|---|---|---|
| RF-ACUTE-CHEST-PAIN | 4 | 4 | 2 | 1.0000 | [0.5101, 1.0000] | [0.3976, 1.0000] | [1.0000, 1.0000] | clopper_pearson |
| RF-ANAPHYLAXIS | 4 | 4 | 2 | 1.0000 | [0.5101, 1.0000] | [0.3976, 1.0000] | [1.0000, 1.0000] | clopper_pearson |
| RF-FAST | 4 | 4 | 2 | 1.0000 | [0.5101, 1.0000] | [0.3976, 1.0000] | [1.0000, 1.0000] | clopper_pearson |
| RF-NEWS-AGG5 | null | null | 3 | null | null | null | null | unmappable (e1 mapping v1: S4 has no aggregate-NEWS rule) |
| RF-NEWS-SINGLE3 | 3 | 3 | 2 | 1.0000 | [0.4385, 1.0000] | [0.2924, 1.0000] | [1.0000, 1.0000] | clopper_pearson |
| RF-QSOFA | 2 | 2 | 1 | 1.0000 | [0.3424, 1.0000] | [0.1581, 1.0000] | [1.0000, 1.0000] | clopper_pearson |
| RF-THUNDERCLAP | 4 | 4 | 2 | 1.0000 | [0.5101, 1.0000] | [0.3976, 1.0000] | [1.0000, 1.0000] | clopper_pearson |

> **System Evaluation on synthetic data — not clinical performance**
>
> Circularity note: rules, fixtures, extractor lexicon and gold share authors, so these results are circular. One deterministic mock model is used in both arms: the comparison measures graph structure (typed extraction, mandatory red-flag screening, abstention, call count, time), not model reasoning.

| population | n_dps | alerts per S4 rule |
|---|---|---|
| gold_negative_dps | 56 | none |
| text_near_miss_dps | 14 | none |

> **System Evaluation on synthetic data — not clinical performance**
>
> Circularity note: rules, fixtures, extractor lexicon and gold share authors, so these results are circular. One deterministic mock model is used in both arms: the comparison measures graph structure (typed extraction, mandatory red-flag screening, abstention, call count, time), not model reasoning.

| missed DP | S1r rule | reason |
|---|---|---|
| SYNE-0030/T1 | RF-NEWS-AGG5 | unmappable |
| SYNE-0030/T2 | RF-NEWS-AGG5 | unmappable |
| SYNE-0107/T1 | RF-NEWS-AGG5 | unmappable |
| SYNE-0107/T2 | RF-NEWS-AGG5 | unmappable |
| SYNE-0165/T2 | RF-NEWS-AGG5 | unmappable |

Predeclared targets (reported, not gating): {"text_rule_alerts_on_text_near_miss_dps": 0, "text_rule_recall_equals_1": {"RF-ACUTE-CHEST-PAIN": "PASS", "RF-ANAPHYLAXIS": "PASS", "RF-FAST": "PASS", "RF-THUNDERCLAP": "PASS"}, "zero_text_rule_alerts_on_text_near_miss_dps": "PASS"}

Not evaluated: {"CareSuggestion": "not evaluated: the mock proposes no care items and S1r has no care gold"}

## test

Not run: the test split runs once, inside the frozen run after both i2 manifests are frozen and committed

