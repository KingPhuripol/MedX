---
name: data-audit
description: Audit a dataset or manifest for authorization, licenses, patient identity/splits, temporal validity, provenance, labels, preprocessing leakage, missingness, duplicates, quality, and external-transfer safety.
argument-hint: <dataset-manifest-or-directory>
---

# Data Audit Workflow

Target: `$ARGUMENTS`.

Default to read-only inspection. Never print raw patient payloads.

1. Read Data Contract, Patient Journey Schema, Evaluation Contract, Approval Policy, target manifest/schema, and dependent experiment manifests.
2. Establish data classification, legal/ethical/license authority, allowed purposes, external transfer/redistribution, retention/deletion, and owner. Unresolved authority is a blocking finding.
3. Trace stable patient identity before derivation. Verify every patient and all encounters/modalities/derivatives occur in exactly one split. Record counts/checksums and linkage uncertainty.
4. Run exact/near duplicate and source overlap analysis where tools/data permit. Check identifiers, filenames, cache keys, sample ordering, and transformations for label/site/patient leakage.
5. Audit `observed_at`, `available_at_time`, `recorded_at`, and label availability. Run `/temporal-leakage-audit` on representative/all snapshots as appropriate.
6. Verify train-only fitting for normalization, vocabulary, imputation, sampling, feature selection, thresholds, and calibration.
7. Audit source/version/provenance/transforms, label definition/adjudication, missingness semantics, units/ranges, image geometry, corrupt/unsupported records, subgroup/site/device coverage.
8. Verify patient-linked multimodality claims and prevent synthetic cross-patient pairing from being represented as real.
9. Review logs/fixtures/external payload builders for secrets, identifiers, linkable content, and approval IDs.
10. Classify findings `CRITICAL/HIGH/MEDIUM/LOW`, identify affected datasets/experiments/tables/releases, and specify remediation and independent re-audit.

On confirmed patient overlap, future leakage, or unauthorized use: stop the affected pipeline, mark downstream evidence invalid, and escalate. Do not repair data in place or delete evidence.

Return scope/versions/classification, authority, counts/split proof, temporal result, preprocessing/provenance/quality/missingness/duplicate findings, external-transfer verdict, affected artifacts, severity findings, pass/fail verdict, and re-audit criteria.
