# Benchmark Contract

**Owner:** Thanrada Tungweerapornpong  
**Research approval:** Phurinat Polasa  
**Data approval:** Jakkapat Bunjongruxsa  
**Status:** policy frozen; named public benchmarks are selected only after access/license feasibility evidence
**Feasibility survey:** first pass recorded 2026-08-30 — see "Feasibility constraints" below

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

## Feasibility constraints recorded 2026-08-30

The first dataset feasibility survey (`docs/research/DATASET_FEASIBILITY.md`,
`project_state/dataset_feasibility.json`, TASK-0005) established constraints that bind benchmark
selection. No candidate is yet selected; all seven are `CONDITIONAL`.

**Coverage cannot be assumed uniform across modalities.** Patient-level linkage across modalities
exists only within the MIMIC family (`subject_id` is common to MIMIC-IV and MIMIC-CXR). CheXpert,
BraTS, CT-RATE, VQA-RAD and SLAKE are separate populations. Therefore:

- Longitudinal, multimodal, single-patient evaluation is possible **only** on the MIMIC core, and only
  for clinical text, structured data and 2D imaging.
- 3D evaluation (BraTS for MRI, CT-RATE for CT) is necessarily **unlinked capability evaluation**, not
  patient-journey evaluation. Any table mixing the two must say which it is.
- A single headline score across all modalities would conflate a linked-cohort result with unlinked
  capability results. The reporting template's requirement to label evidence type covers this, and it
  is not optional here.

**Setting constraint, recorded 2026-09-07 (DEC-0016).** The committed care setting is the
emergency-department first-contact triage point. The currently-surveyed cohort is MIMIC-IV `hosp` and
`icu` — a hospital course and an ICU stay, **not a first contact**. These are different populations and
must never be reported as one. Specifically:

- **No Front Door result may be reported on `hosp`/`icu` data as if it were first-contact triage
  evidence.** Every results table names its population, and a table that cannot name it does not ship.
- The fixed-route-set comparison arm added under DEC-0013 runs on that hospital-course cohort. Its
  results are setting-agnostic architecture evidence, explicitly **not** Front Door evidence.
- `CHIEF_COMPLAINT` and `TRIAGE_NOTE` have no recorded data source in the surveyed set. MIMIC-IV-ED is
  the identified candidate and is **unsurveyed** (RISK-0014, TASK-0031). Until DS-0008 exists, every
  Front Door result in this project is synthetic and is labelled as such.
- Care setting and arrival mode are declared reporting strata.

**Time-valid evaluation is available only on the MIMIC core.** `available_at_time` must be derived from
`storetime` (when a result became available), never from `charttime` (when the observation was made);
deriving it from `charttime` would place future information inside the decision snapshot. BraTS,
CT-RATE, VQA-RAD and SLAKE carry no clinical timeline at all, so no simulated decision time can be
constructed on them and the temporal audit does not apply to results drawn from them.

**Licence terms constrain what may be published, not only what may be trained.** Every candidate except
VQA-RAD (CC0) restricts use to non-commercial research. CT-RATE is CC-BY-NC-SA, whose ShareAlike term
plausibly reaches derivative works. Whether the PhysioNet Credentialed Health Data License permits
releasing model weights trained on MIMIC is **undetermined** and must be settled with PhysioNet in
writing before release. Benchmark selection therefore has to account for its effect on the open-weight
release, and RISK-0010 tracks this.

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

