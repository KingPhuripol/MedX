---
name: temporal-leakage-audit
description: Prove that every model input, retrieval, feature, transformation, and label respects available_at_time for each simulated decision snapshot. Use before training/evaluation and after data-pipeline changes.
argument-hint: <journey-file-or-dataset> [--as-of ISO-8601]
---

# Temporal Leakage Audit

Target/arguments: `$ARGUMENTS`.

1. Read the evidence types in `casegraph/types.py`, the dataset manifest/DATACARD, snapshot builder, feature/retrieval/preprocessing code, and dependent manifests.
2. Define the audited decision time(s), task, and exact input evidence IDs/checksum.
3. Validate journey schema, unique event IDs, timestamp formats/order, patient/split identity, source/provenance, and label definitions.
4. For every input and transitive dependency prove `available_at_time <= decision_time`. Include retrieved notes, derived features, image reports, terminology mappings, cache content, prompt examples, thresholds, imputation, normalization, and sampling.
5. Treat final diagnosis, discharge summary, retrospective coding/annotation, disposition, intervention, deterioration/outcome, and later tests or images as forbidden until their actual availability.
6. When timestamps are ambiguous, use the conservative latest plausible time or exclude the field; never assume early availability for convenience.
7. Run the standard file audit when applicable:

```bash
python3 scripts/temporal_leakage_audit.py <journey.json> --as-of <ISO-8601>
```

8. Add adversarial tests with a deliberately future event/label and prove it is excluded/rejected. Check caches and derived tables built before/after split.
9. Trace any violation to every dataset version, experiment, evaluation, report table/figure, product fixture, and release that consumed it.
10. Verdict:
    - `PASS`: all dependencies are time-valid and ambiguity is documented conservatively.
    - `FAIL`: a future/ambiguous dependency can enter the model/evaluator.
    - `CRITICAL_FAIL`: affected invalid evidence is reported, released, or used in safety claims.

On failure, stop affected work and rebuild a new version. Do not remove the event merely to pass without correcting lineage.

Return decision times, eligible/ineligible counts and IDs, transitive dependency checks, ambiguous fields, adversarial result, affected artifacts, verdict/severity, remediation, and re-audit evidence.

