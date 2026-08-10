---
name: run-benchmark
description: Execute or prepare a frozen, manifest-driven benchmark with data integrity, comparison fairness, resource, statistical, and approval gates. Manual workflow due to compute and test-set sensitivity.
argument-hint: <experiment-manifest.json>
disable-model-invocation: true
---

# Run Benchmark Workflow

Manifest: `$ARGUMENTS`.

1. Validate the manifest with `scripts/validate_manifest.py` and require `planned`/approved status, exact data/split/evaluator/model versions, primary metric, baselines, exclusion/stop rules, artifact paths, and code revision.
2. Read Benchmark/Evaluation/Data/Training contracts and Success Criteria.
3. Verify patient-level split checksum, temporal audit for every snapshot, train-only preprocessing/threshold/calibration, license/authorization, and test isolation.
4. Verify fairness: same data/preprocessing, tokens/steps, optimization/search opportunity, seed policy, comparable parameters/compute, and reported compiler/provider overhead. Record unavoidable mismatches.
5. Determine tier and approval. Tier 3/4, multi-GPU, >60m, material paid service, or protected final test requires exact human authorization. Without it, perform dry-run only and stop.
6. Run a tiny evaluator smoke on synthetic/validation data before the frozen benchmark.
7. Present the exact command, expected devices/time/cost/storage, stop conditions, and artifacts before execution. Do not construct a hidden shell pipeline that bypasses the approval hook.
8. During an approved run, preserve raw predictions, schema failures, abstentions, timeouts, logs, environment, and actual resource usage. Do not drop failures from denominators.
9. Aggregate using the frozen evaluator. Report numerator/denominator, uncertainty, effect size, patient/site clustering, strata, deviations, and exploratory labels.
10. Complete the manifest result without overwriting the planned section and link the evaluation record.

Return pre-flight verdict, approval status, exact command or reason not run, resource actuals, frozen results, safety/data failures, fairness deviations, claim supported/not supported, artifact/checksum paths, and required independent audits.

