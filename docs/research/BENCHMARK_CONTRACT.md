# Benchmark Contract

**Owner:** Thanrada Tungweerapornpong  
**Research approval:** Phurinat Polasa  
**Data approval:** Jakkapat Bunjongruxsa  
**Status:** policy frozen; named public benchmarks are selected only after access/license feasibility evidence

## Objective

Separate two claims:

1. **Medical capability:** useful performance across representative text, 2D, 3D, structured/EHR, and longitudinal tasks.
2. **Architecture contribution:** case-adaptive typed computation produces measurable adaptation, utility/efficiency, and causal graph faithfulness under controlled conditions.

One score cannot establish both claims.

## Freeze protocol

Before any result is inspected for model selection, record:

- dataset/task versions and licenses;
- patient-level split IDs/checksums and temporal snapshot policy;
- preprocessing and evaluation code version;
- primary/secondary metrics and direction;
- clinically critical strata and minimum sample reporting;
- baseline versions, parameter/compute matching rules, seeds/search budgets;
- statistical intervals/tests and multiplicity handling;
- exclusion, missing prediction, invalid output, and failure policy;
- final test access policy and evaluator owner.

Changes after seeing test results require an amendment explaining why and must report both original and amended analysis when feasible.

## Required comparison families

| Family | Purpose |
|---|---|
| Strong fixed-path medical/open baseline | establish medical capability and practical reference |
| Same backbone fixed-path | isolate routing/graph contribution |
| Static typed DAG | isolate dynamic topology contribution |
| Random/matched DAG or shuffled router | detect gains unrelated to learned case adaptation |
| Sparse/MoE-style routing where feasible | distinguish topology claim from generic conditional compute |
| Proposed dynamic typed DAG | target method |

Do not rely on one proprietary baseline whose evaluation cannot be reproduced. External API results are prototype context, not the primary research baseline unless version, settings, data handling, and access are stable enough to audit.

## Medical capability coverage

Select feasible public/authorized tasks spanning:

- medical text QA or reasoning;
- structured/EHR reasoning with temporal controls;
- 2D image understanding;
- multimodal image-text understanding;
- 3D CT/MRI understanding;
- longitudinal update or current/prior comparison;
- at least one generation task only if evaluation quality is adequate.

Each task records whether data are truly patient-linked, single-modality capability data, or synthetic/simulated. Never merge identities across datasets to manufacture multimodal cases.

## Architecture metrics

- graph diversity and conditional mutual information/proxy with case/task attributes;
- graph size, depth, active edges, modality reads, operator distribution;
- routing entropy/load and collapse rate;
- invalid graph/fallback rate;
- graph stability under benign perturbation and sensitivity under relevant evidence change;
- replay agreement;
- node/edge/operator/modality/graph-swap intervention effect;
- task quality per FLOP, latency, memory, energy proxy where feasible;
- quality at matched compute and compute at matched quality.

## Clinical Front Door metrics

Primary safety metrics:

- critical-case sensitivity/recall;
- under-triage rate;
- false reassurance rate;
- abstention/escalation quality.

Secondary utility metrics:

- top-1 pathway accuracy and top-k/hierarchical pathway recall;
- wrong-pathway cost and unnecessary referral;
- next-information agreement/information gain proxy and unnecessary-test rate;
- calibration (Brier/ECE with limitations), selective risk/coverage;
- time/steps to correct pathway in simulated journeys;
- human agreement, override reason, usability, and time when approved.

Accuracy cannot compensate for a failed critical safety gate.

## Fairness and strata

Report by available demographic/site/device strata where authorized and sufficiently sized, chief complaint/disease system, modality combination, missingness, temporal stage, urgency, and data source. Suppress or aggregate small cells to protect privacy. Do not claim fairness from missing demographic labels.

## Statistics

- Report numerator/denominator and uncertainty interval, not only percentages.
- Use patient-level resampling when observations are correlated within patient.
- Use paired tests for paired model outputs where appropriate.
- Report seed variability for training comparisons where feasible.
- Predeclare the primary comparison and control multiplicity or label exploratory analyses.
- Include effect size and practical/clinical interpretation, not p-values alone.

## Leakage and test isolation

- Split patient identities before deriving samples.
- Final test labels are unavailable to model developers when practical.
- Do not tune prompts, thresholds, routes, or graph budgets on final test outcomes.
- Check benchmark contamination and duplicated cases where possible.
- Run temporal audit for every simulated decision time.
- Any confirmed leakage invalidates the affected table/figure and derivatives.

## Reporting template

Every table/figure cites manifest IDs, dataset/split/evaluator versions, sample sizes, metric definitions, compute budget, and confidence intervals. Include failed/excluded runs and deviations. Clearly label simulated, retrospective, external, and expert-reviewed evidence.

