---
name: hf-release-check
description: Perform a read-only Hugging Face/model release readiness audit for weights, code, model/evaluation cards, licenses, lineage, safety, secrets/PHI, reproducibility, and approval. This skill never uploads or publishes.
argument-hint: <release-directory>
---

# Hugging Face Release Check

Release directory: `$ARGUMENTS`.

This workflow never calls upload, publish, push, deploy, or release commands.

1. Read Success Criteria G6-G7, Benchmark/Evaluation/Data/API/Approval contracts, Safety Spec, Decision Log, release task/manifest/evaluation records, and repository license policy.
2. Freeze release version, code revision, checkpoint/config/tokenizer/processor/adapter versions, graph/operator/contract versions, and checksums.
3. Verify weights and all derivatives are permitted for redistribution; record base model/data/code licenses, attribution, restrictions, acceptable-use terms, and unresolved incompatibilities. Withhold artifacts when rights are unclear.
4. Scan release tree for secrets, credentials, raw/derived patient data, identifiers, private paths/URLs, internal logs, dataset samples not permitted for redistribution, and oversized/unintended files.
5. Verify model card: research/decision-support purpose; no autonomous diagnosis/treatment; intended users/use/non-use; architecture; data summary within license; training stages/resources; frozen evaluations with denominators/uncertainty; safety/robustness/bias; limitations; human review; citation/license/contact/version.
6. Verify reproducibility: inference example using synthetic data, environment/dependencies, hardware notes, deterministic config, load/checksum test, graph export/replay where applicable, evaluation commands and expected artifact references.
7. Verify release artifacts: weights/index, config, tokenizer/processor, generation/inference config, adapter if applicable, code/commit/tag plan, model/evaluation card, license, citations, checksums, compatibility matrix, changelog, known issues.
8. Verify team model passes Model API fixtures and independent safety/integration verdicts contain no unresolved critical/high release blocker.
9. Confirm no claimed metric depends on leakage, unapproved test access, invalid run, or undocumented post-hoc selection.
10. Produce `PASS`, `CONDITIONAL_PASS`, or `FAIL`. Even `PASS` requires a separate exact human approval before upload/publish.

Return release version/revision, artifact inventory/checksums, license/provenance verdict, secret/PHI scan, card/reproducibility/API/safety/integration findings, missing files, verdict, exact approval required, and a staging-only next step. Do not upload.
