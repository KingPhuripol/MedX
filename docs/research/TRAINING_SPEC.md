# Training Specification

**Owner:** Thanapol Popit  
**Compute approval:** Phurinat Polasa plus a human budget owner  
**Status:** operational baseline; dataset- and hardware-specific values belong in manifests

## Run tiers and authority

| Tier | Maximum autonomous scope | Examples | Approval |
|---|---|---|---|
| 0 | CPU/synthetic/unit, under 15 minutes | shape checks, one batch, schema/evaluator unit tests | no additional approval |
| 1 | one device, under 20 minutes, tiny data | overfit batch, forward/backward, checkpoint round trip | no additional approval if manifest or smoke record exists |
| 2 | one GPU, at most 60 minutes | small pilot/ablation shard | valid manifest and owner authorization |
| 3 | beyond Tier 2 but not flagship | controlled experiment, long single-GPU run | explicit human approval with budget |
| 4 | approximately 4B, multi-GPU, multi-node, or flagship | continual pretraining, full tuning | explicit human approval for every run |

Any multi-GPU, multi-node, scheduled cluster job, expected duration over 60 minutes, or substantial cloud charge is Tier 3/4 regardless of label. The 27B stretch is always Tier 4 plus a separate scope decision.

## Pre-flight contract

Before Tier 2-4 execution, the manifest must contain:

- experiment ID, owner, research question, hypothesis, run tier, status;
- code revision and dirty-tree policy;
- model/config version, parameter count, initialization/checkpoint and license;
- data, split, preprocessing, tokenizer, modality, and temporal-audit versions;
- seed(s), optimizer, scheduler, precision, batch/accumulation, steps/tokens;
- graph mode, operator version, routing/budget objectives;
- estimated devices, GPU-hours, cost, storage, duration, and checkpoint count;
- primary/secondary metrics, baselines, exclusion/stop rules;
- output/checkpoint/log locations and retention;
- required approval ID for Tier 3/4.

The pre-flight command validates the manifest, repository state, availability audit, sample batch, disk capacity, resume path, and evaluation smoke test. A failed pre-flight blocks the run.

## Reproducibility policy

- Freeze configuration in the manifest; CLI overrides are recorded in the resulting manifest.
- Record environment lock, CUDA/driver/framework versions, hardware model, and distributed topology.
- Seed data order, initialization, router sampling, and evaluation where supported.
- Preserve exact code revision. A dirty tree requires a diff artifact and explicit declaration.
- Do not overwrite runs. Experiment IDs and artifact directories are unique.
- Checkpoints are content-addressed or accompanied by checksums.

## Stage plan

1. **Executor validation:** synthetic data, deterministic replay, one-batch gradient test.
2. **Fixed baseline:** train/evaluate pipeline before dynamic claims.
3. **Soft/sparse routing pilot:** diagnose gradients, balance, graph statistics.
4. **Discrete routing pilot:** verify estimator and inference equivalence.
5. **Controlled small experiments:** frozen comparison family and multiple seeds where feasible.
6. **Approximately 4B base stage:** approved continual pretraining with periodic frozen evaluation.
7. **Instruction/safety stage:** separate lineage, data, objective, and evaluation.
8. **FrontDoor adaptation:** contract-specific head/adapter without weakening general capability evidence.

## Checkpoint and recovery

Every Tier 3/4 run must demonstrate a checkpoint save/load/resume smoke test before full execution. Retain last-known-good and periodic recovery checkpoints. Validate checksums and optimizer/scheduler/router state. Never delete checkpoints automatically because a newer one exists.

Recovery procedure:

1. stop safely; preserve logs and failing batch reference when authorized;
2. classify failure and record it in manifest/result;
3. validate last checkpoint integrity;
4. reproduce at smaller scale where possible;
5. change one causal factor per remediation run;
6. request renewed approval when budget/tier changes.

## Failure policies

- **NaN/Inf:** stop, save diagnostics, check inputs/precision/loss terms; do not auto-resume repeatedly.
- **OOM:** stop, record peak memory/config, lower declared batch or use approved technique; do not silently change comparable budgets.
- **Loss spike/divergence:** retain window logs/checkpoint; compare data batch and optimizer state.
- **Routing collapse:** trigger graph diagnostics; do not continue expensive scale hoping it resolves.
- **Checkpoint corruption:** quarantine, verify earlier checkpoint; never delete evidence.
- **Temporal/data audit failure:** invalidate the run and every derivative; rebuild from an approved data version.
- **Evaluation regression:** stop at predeclared gate when safety/primary thresholds fail.

## Monitoring

Track loss components, gradients, learning rate, throughput, tokens, device utilization, memory, graph size/depth, operator/modality usage, routing entropy/load, invalid graph rate, abstention, calibration proxy, and validation metrics. For privacy, logs contain approved identifiers or aggregates, never raw PHI by default.

## Comparison fairness

Dynamic and baseline runs use the Benchmark Contract. Match data, split, preprocessing, optimization opportunity, tokens/steps, seed policy, and parameter/compute budget. Report compiler overhead and any unmatched advantage. Hyperparameter search budgets are also part of compute fairness.

## Artifact completion

A run is complete only when its result section records terminal status, timestamps, revision/config/data hashes, actual compute/cost, artifacts/checksums, metrics, failure/exclusion reason, and evaluator version. A job exit code is not sufficient.

