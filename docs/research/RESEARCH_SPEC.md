# Research Specification

**Owner:** Phurinat Polasa  
**Implementation lead:** Thanapol Popit  
**Independent evaluation:** Thanrada Tungweerapornpong  
**Status:** baseline for feasibility and proposal; benchmark/dataset identifiers require evidence before acceptance

## Core hypothesis

Medical cases should not all use an identical fixed computation path. A model that compiles available, time-valid evidence and task context into a sparse, typed, inspectable computation DAG may achieve a better quality-efficiency-auditability trade-off than fixed-path or static-graph alternatives, especially under missing modalities and evolving longitudinal information.

The project does not assume the hypothesis is true. The research program is designed to falsify it early at small scale.

## Research questions

### RQ1 - Adaptation

Does the learned executed graph vary meaningfully with case evidence, modality availability, temporal stage, complexity, and task rather than with noise or identifiers?

**Evidence:** graph diversity by clinically relevant strata; graph similarity within perturbation pairs; operator/modality access distributions; all-node and single-route collapse tests.

### RQ2 - Controlled utility

Under comparable parameter, data, optimization, token/step, and compute budgets, does dynamic typed computation improve task quality, efficiency, robustness, or calibration relative to fixed-path, static-DAG, random-routing, and appropriate sparse/MoE baselines?

**Evidence:** predeclared primary metrics, uncertainty intervals, compute-normalized comparisons, seed variation, and negative results.

### RQ3 - Faithfulness and inspectability

Does the exported graph reflect computation that causally affects output rather than a decorative explanation?

**Evidence:** node/edge removal, graph swap, modality removal, operator substitution, replay consistency, counterfactual evidence changes, and effect-size correspondence.

### RQ4 - Temporal and missing-modality robustness

Can the model operate using only evidence available at the simulated decision time, update when new evidence arrives, and degrade safely when modalities are missing or corrupted?

**Evidence:** temporal snapshots, future-evidence denial tests, missingness patterns, longitudinal update consistency, abstention/calibration, and no patient leakage.

### RQ5 - Multi-disease generalization

Does the approach retain useful capability across representative disease systems, tasks, and unseen modality combinations rather than overfitting a single complaint or dataset?

**Evidence:** predeclared strata, leave-domain/task tests where feasible, and transparent scope limits.

## Research artifact

The target family is:

- `Medical-DAG-Base`: small architecture-validation model, expected 300M-700M class.
- `Medical-DAG-4B`: flagship base model, approximately 4B, conditional on gates.
- `Medical-DAG-4B-Instruct`: instruction/safety tuned research derivative.
- `Medical-DAG-4B-FrontDoor`: contract-aligned downstream adapter or tuned variant.
- `Medical-DAG-Large`: 27B-class stretch only after a separate decision.

Names are working identifiers, not public claims. They may change without altering the charter if contracts and lineage remain intact.

## Required modality interfaces

1. Clinical text: complaint, notes, history, questions, reports.
2. 2D imaging: radiograph and other justified public medical image tasks.
3. 3D imaging: CT/MRI volume or slice/patch representation with explicit geometry and temporal metadata.
4. Structured data: demographics, vitals, labs, coded events with units and provenance.
5. Longitudinal journey: ordered timepoints with evidence availability, current/prior comparison, and outcomes withheld until valid.

Not every dataset must contain every modality. The model and evaluation must distinguish paired patient-level multimodal evidence from capability datasets that are not patient-linked. No synthetic cross-patient pairing may be presented as real patient multimodality.

## Inputs and outputs

Inputs comply with `DATA_CONTRACT.md` and `PATIENT_JOURNEY_SCHEMA.md`. At inference time they include a declared `decision_time`, task, available evidence references, missingness, and authorization context.

Outputs comply with `MODEL_API_CONTRACT.md` and may include:

- task-specific predictions or representations;
- urgency and pathway support for approved simulations;
- critical-condition categories for review, not diagnoses asserted as fact;
- next-information candidates with rationale codes;
- calibrated confidence/uncertainty and abstention;
- executed graph with typed nodes/edges, evidence references, timing, cost, and version.

## Contribution boundaries

The project may claim only what frozen evaluation supports. It must not claim:

- clinical deployment readiness or replacement of staff;
- comprehensive medical knowledge because multiple tasks were evaluated;
- causally faithful reasoning from graph visualization alone;
- superiority over a model under unequal compute/data without qualification;
- generalization beyond represented populations, modalities, sites, or tasks;
- a foundation model release when weights/recipe are not reusable and documented.

## Development ladder

### Stage A - Contract and synthetic executor

Build schemas, typed graph objects, acyclicity checks, serialization/replay, synthetic operators, and deterministic contract fixtures.

### Stage B - Fixed and static baselines

Establish data/evaluation pipelines and at least one strong fixed-path baseline before interpreting dynamic results.

### Stage C - Small adaptive model

Train/evaluate a small soft/sparse router, measure collapse and graph behavior, then introduce discrete execution with a defined estimator/curriculum.

### Stage D - Controlled ablation suite

Freeze splits/config families and run required comparisons and interventions. Stop if core hypotheses fail and document why.

### Stage E - Approximately 4B scaling

Proceed only after `SUCCESS_CRITERIA.md` G0-G4 and Training Spec approvals. Continual pretraining and instruction/safety tuning are separate, traceable stages.

### Stage F - Public release and integration

Freeze results, run release and safety audits, prepare model/evaluation cards, and connect through the same Model API Contract used by mock providers.

## Small-model kill tests

Do not scale while any of these persists after the predeclared remediation budget:

- graphs do not vary beyond seed/noise or vary primarily by patient/site identifiers;
- every case activates nearly all nodes or one route dominates without task justification;
- dynamic model is materially worse than controlled baselines without an efficiency/calibration benefit;
- exported graphs cannot replay within tolerance;
- graph interventions do not affect outputs in the predicted direction;
- training is unrecoverable, unstable, or irreproducible;
- data/label provenance or temporal validity is unresolved.

Stopping or reframing is a valid research outcome. Reframing the claim requires human approval and a Decision Log entry.

## Reproducibility

Every reported number traces to a valid experiment manifest, immutable data/split version, code commit, config hash, seed, environment, log, checkpoint or output artifact, evaluation record, and report table/figure. Failed and excluded runs retain an exclusion reason selected before aggregate results are finalized.

## Ethics and safety

Use only authorized data and comply with CITI/ethics requirements. Dataset access does not imply permission to send data to a model vendor or redistribute derivatives. Report demographic/site limitations and clinically asymmetric errors. All Clinical Front Door outputs remain supervised decision support.

