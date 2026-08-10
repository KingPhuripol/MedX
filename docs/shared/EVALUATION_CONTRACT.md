# Evaluation Contract

**Owner:** Thanrada Tungweerapornpong  
**Version:** 1.0.0  
**Machine record:** `schemas/evaluation-record.schema.json`

## Evaluation principles

- Freeze question, cohort/split, temporal snapshot, metric, comparison, and exclusion before viewing final results.
- Treat patient as the independent unit unless the design justifies otherwise.
- Separate model selection (`validation`) from internal/external/expert final tests.
- Report safety first, then utility, architecture behavior, efficiency, calibration, and human factors.
- Preserve failures and deviations. No metric shopping.

## Evaluation layers

### 1. Data integrity

Patient disjointness, temporal availability, provenance/label audit, duplicate/contamination, missingness, preprocessing fit, license/authorization, and dataset counts/checksums. Failure blocks all downstream claims.

### 2. Medical capability

Task-appropriate exact/semantic/classification/generation metrics with sample sizes and uncertainty. Report by modality/task/source and relevant strata. Generated medical text requires carefully scoped automated metrics and human/expert assessment where claims depend on quality.

### 3. Architecture

Controlled baseline comparisons, graph adaptation/collapse, compute and latency, replay, interventions/faithfulness, robustness, and update behavior as defined in the Benchmark Contract.

### 4. Clinical Front Door

Urgency and critical-case sensitivity, under-triage, false reassurance, pathway ranking/cost, next-information selection, abstention/selective risk, calibration, steps/time, provider failures, and human overrides.

### 5. Safety and human factors

Red-flag suppression, unsupported certainty, missing evidence, invalid output handling, privacy payload, automation-bias wording, usability/accessibility, reviewer understanding, agreement/override reasons, and limitations.

## Evaluation unit

An evaluation record contains evaluation ID/version, manifest IDs, code/data/split/model/provider/contract versions, task/cohort, decision-time policy, primary/secondary metrics, baselines, sample sizes, exclusions, seeds/search budget, statistical plan, output artifacts, result status, deviations, and reviewer verdict.

## Temporal protocol

For each journey and decision snapshot:

1. build input only from events available by `T`;
2. hash selected evidence IDs;
3. keep future labels sealed from model/prompt/feature computation;
4. evaluate prediction against targets whose evaluation definition is predeclared;
5. ensure thresholds/calibration were fitted on training/validation only;
6. link later outcome as evaluation evidence, not input.

## Missing prediction and failure policy

- Schema-invalid outputs count as failures, not silently dropped.
- Provider timeout/failure is reported with denominator and operational metric.
- Abstention is scored under selective-risk/coverage and safety policy, not converted to a random prediction.
- Missing ground truth uses predeclared exclusion and remains in cohort accounting.
- Runs stopped by safety/data gate are invalid, not zero or missing by convenience.

## Statistical reporting

For each primary metric, report definition, direction, numerator/denominator, point estimate, patient-level uncertainty interval, comparison/effect size, and practical interpretation. Use paired inference for same cases. If data are clustered by patient/site, resample/model clusters. Label exploratory analyses and account for multiplicity.

No universal p-value or metric threshold is assumed. Thresholds must reflect sample size, clinical asymmetry, baseline, and intended scoped claim; freeze them before final test.

## Review and verdict

Evaluation owner generates evidence. Integration Auditor verifies reproducibility and cross-contract alignment. Clinical Safety Reviewer independently assesses safety. Final status is `PASS`, `CONDITIONAL_PASS`, `FAIL`, or `CRITICAL_FAIL`; critical data/safety failures override aggregate performance.

## Result-to-claim map

Every proposal/report/presentation/public claim cites the evaluation IDs and manifests that support it, plus limitations. If no valid evaluation supports a statement, write it as a hypothesis, design goal, or planned work.

