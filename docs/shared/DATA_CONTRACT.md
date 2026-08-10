# Data Contract

**Owner:** Jakkapat Bunjongruxsa  
**Evaluation reviewer:** Thanrada Tungweerapornpong  
**Version:** 1.0.0

## Purpose

Define the only acceptable representation and lifecycle for research and Clinical Front Door data. This contract applies to public benchmarks, derived training sets, synthetic cases, retrospective approved data, external-provider fixtures, model inputs, labels, and evaluation records.

## Data classifications

| Class | Meaning | External API default |
|---|---|---|
| `SYNTHETIC` | generated case with no real person linkage | allowed within provider terms/budget |
| `PUBLIC_LICENSED` | public dataset used within license | only if license and provider terms permit |
| `DEIDENTIFIED_APPROVED` | real data processed under explicit governance | denied unless separate approval explicitly covers provider transfer |
| `IDENTIFIABLE_OR_LINKABLE` | direct/quasi identifiers or re-linkable record | denied |
| `RESTRICTED_DERIVATIVE` | embedding, report, crop, or artifact inheriting restrictions | denied unless explicitly cleared |

De-identification does not automatically authorize external transfer or redistribution.

## Identity and split invariants

1. Assign a stable internal `patient_id` before deriving encounters, windows, images, text chunks, or tasks.
2. Split at patient level. All encounters, modalities, duplicates, derivatives, and temporal windows from one patient remain in exactly one of `train`, `validation`, `internal_test`, `external_test`, `expert_test`, or approved special sets.
3. If identities cannot be linked across sources, do not claim guaranteed disjointness; isolate the source and report the limitation.
4. Near-duplicate images/text and shared accession/study identifiers are audited after splitting without moving samples based on labels.
5. Final test split is frozen and access logged.

## Temporal invariants

Every evidence item and label contains:

- `observed_at`: when the underlying event/measurement occurred;
- `available_at_time`: earliest time the simulated decision-maker could have used the normalized item;
- `recorded_at`: when it entered the source system, when available;
- provenance and transformation lineage.

For decision time `T`, every model input, retrieval result, feature, derived variable, preprocessing statistic, and prompt content must depend only on evidence with `available_at_time <= T`.

Examples forbidden at early snapshots:

- final/discharge diagnosis;
- discharge summary or retrospective problem-list update;
- a report signed after the decision time;
- lab/image acquired or released later;
- disposition, procedure, ICU admission, deterioration, mortality, or outcome;
- retrospective billing/coding or manual annotation created with future chart access;
- normalization/imputation/feature selection fitted using validation/test data.

When source timestamps are ambiguous, use the conservative latest plausible availability or exclude the field from temporal evaluation.

## Evidence item requirements

Each item contains a unique `evidence_id`, type/modality, source dataset/system, version, patient/encounter/journey linkage, times, data classification, authorization, missingness/status, and payload reference/checksum. Raw payloads remain outside manifests and logs.

Modality-specific metadata:

- text: language, author/source role where authorized, note type, section, redaction/transformation;
- 2D: study/series/instance, view, device/site when allowed, pixel transformation;
- 3D: study/series, modality, spacing, orientation, shape, series selection, slice/patch transform;
- structured: code system, unit, reference range/source, value status, measurement method where available;
- longitudinal: episode/timepoint semantics and linkage confidence.

## Labels

Labels are evidence too. Record label definition/version, source, annotator/process, `available_at_time`, confidence/adjudication, and whether the label was observable prospectively or only retrospective.

Do not equate final diagnosis with urgency/pathway ground truth. Define separate targets for urgency, pathway, next information, critical categories, outcome, and diagnosis. Derived labels must document rules and be recreated only from authorized source fields.

## Missingness

Represent `NOT_MEASURED`, `MEASURED_UNKNOWN`, `NOT_AVAILABLE_YET`, `WITHHELD`, `UNSUPPORTED`, `CORRUPT`, and `NOT_APPLICABLE` distinctly where relevant. Never convert missing to normal/negative without an explicit, evaluated rule.

## Preprocessing

- Fit trainable transformations on training split only.
- Version every transform and its inputs.
- Preserve original units/geometry metadata and reversible mapping when possible.
- Do not encode labels or future metadata in paths, filenames, sample ordering, padding, or cache keys.
- Cache keys include data/transform version and authorization scope.
- Augmentation must not create clinically impossible combinations without labeling them synthetic.

## Dataset manifest

A dataset version records source/license/citation, access date, governance, population/site/time period, inclusion/exclusion, modalities and pairing, patient/encounter counts by split, target definitions, availability mapping, preprocessing, duplicate audit, quality/missingness, known bias, permitted use/redistribution, retention/deletion, and checksums.

## External API payload

Default to synthetic fixtures. Before any non-synthetic transfer, verify approval ID, provider, purpose, fields, classification, consent/ethics/license, region, retention/training policy, encryption/access, cost cap, deletion date, and audit owner. Minimize fields and use opaque session identifiers.

## Data incident

On patient overlap, future leakage, unauthorized access/transfer, license breach, or corrupt lineage: stop affected pipeline, preserve evidence safely, mark dependent manifests invalid, notify owners, update Risk Register, determine affected results/releases, rebuild from a new version, and independently re-audit.

## Required automated checks

- schema and identifier uniqueness;
- patient disjointness across splits;
- `available_at_time` at each decision snapshot;
- label/input provenance separation;
- duplicate/near-duplicate and source overlap checks;
- unit/range/geometry and missingness checks;
- train-only preprocessing fit;
- payload classification/authorization and no-secret/no-PHI logs;
- manifest counts/checksums and license completeness.

