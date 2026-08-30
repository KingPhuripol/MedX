# Research Success Criteria and Gates

Success is cumulative. A later gate cannot compensate for an earlier integrity failure.

## G0 - Governance and contracts

Status as of 30 Aug 2026: **four of five closed; the gate is open on dataset feasibility.**

- [x] Research questions and claim boundaries accepted.
      Evidence: `docs/research/RESEARCH_SPEC.md` RQ1-RQ3; claim boundary in `docs/PROJECT_CHARTER.md`
      and `CLAUDE.md` §Claim boundary; DEC-0001 and DEC-0005 accepted.
- [x] Data, Patient Journey, Model API, Evaluation, and Approval contracts versioned.
      Evidence: `project_state/contract_versions.json` registers all five at 1.0.0 with status
      ACCEPTED, validated against `schemas/contract-versions.schema.json` by the harness.
- [ ] Dataset access/license/ethics feasibility recorded.
      **Open.** The inventory and its schema now exist (`project_state/dataset_feasibility.json`,
      `docs/research/DATASET_FEASIBILITY.md`), but all six candidates are `UNDER_REVIEW` and no
      dimension is `VERIFIED`. A structure to record findings is not a finding. Closes with TASK-0005;
      RISK-0002 stays live until it does.
- [x] Experiment manifest validation and evidence lineage work.
      Evidence: `scripts/validate_manifest.py` accepts `experiments/manifests/exp_0000_harness_smoke.json`;
      `bash scripts/run_smoke_test.sh` passes end to end.
- [x] Official academic plan and owners accepted.
      Evidence: `project_state/official_deadlines.json` verified by the harness against DEC-0007;
      `docs/project_management/MASTER_PLAN.md`, `MILESTONES.md` and `TEAM_OWNERSHIP.md`.
      Residual: the Group Application receipt is still unarchived (TASK-0001) — that is an M0 evidence
      gap, not a defect in the plan itself.

## G1 - Data integrity

- [ ] Stable patient identity and disjoint patient-level splits.
- [ ] Every evidence/label item has source, version, and `available_at_time`.
- [ ] Training-only fitting for preprocessing and sampling.
- [ ] Temporal leakage, duplication, label provenance, missingness, and license audits pass.
- [ ] A dataset card states population, exclusions, modality pairing, limitations, and permitted use.

Any patient overlap or future evidence in a reported evaluation is a hard failure.

## G2 - Executor and reproducibility

- [ ] Graph type, acyclicity, budget, authorization, serialization, and replay tests pass.
- [ ] Same inputs/version/config reproduce graph and output within tolerance.
- [ ] Fixed-path baseline pipeline and evaluator work end-to-end.
- [ ] Checkpoint round-trip and recovery smoke tests pass.
- [ ] Every result traces to a valid manifest and artifact checksums.

## G3 - Adaptation and collapse

- [ ] Graphs vary by predeclared case/task/modality/temporal attributes beyond seed noise.
- [ ] No all-node, single-route, single-operator, or unavailable-modality collapse.
- [ ] Variation is not primarily patient/site/file identifiers.
- [ ] Graph cost respects declared budgets with low invalid/fallback rate.
- [ ] Benign perturbations are stable and relevant evidence changes cause plausible graph changes.

## G4 - Controlled utility and faithfulness

- [ ] Proposed model is competitive with same-backbone fixed/static controls on primary tasks or provides a predeclared efficiency/calibration advantage.
- [ ] Equal-budget comparisons and search budgets are documented.
- [ ] Node/edge/operator/modality/graph-swap interventions affect outputs in predicted directions often enough to support the scoped faithfulness claim.
- [ ] Replay agreement meets declared tolerance.
- [ ] Missing-modality and temporal-update evaluations pass defined safety/quality gates.
- [ ] Negative results and failed hypotheses are reported.

## G5 - Approximately 27B authorization

Requires G0-G4 plus:

- [ ] Tier 4 manifest, compute/cost/storage estimate, hardware reservation, and human approval.
- [ ] Small-scale recipe has stable loss, routing, checkpoint/recovery, and evaluation.
- [ ] Stop criteria and rollback plan are explicit.
- [ ] Schedule impact does not endanger academic deliverables.
- [ ] Data volume/quality and license permit the intended training/release.

## G6 - Approximately 27B release candidate

- [ ] Base and derived checkpoints have complete lineage and checksums.
- [ ] Frozen medical and architecture evaluations complete with valid statistics.
- [ ] Safety, calibration, robustness, subgroup, contamination, and limitations analyses complete.
- [ ] Model can be served through the stable Model API Contract.
- [ ] Model card, code, inference, evaluation, environment, and license artifacts are complete.
- [ ] Independent integration and clinical safety verdicts contain no unresolved critical failure.

## G7 - Hugging Face/public release

- [ ] `/hf-release-check` passes.
- [ ] No secrets, PHI, prohibited dataset content, or unlicensed derivative.
- [ ] Usage limitations and research-only/decision-support boundary are prominent.
- [ ] Release version is immutable and reproducible from approved artifacts.
- [ ] A human explicitly approves publishing.

## 27B stretch gate

Only after G6 and an approved decision showing additional research value, available compute, no schedule threat, a separate manifest, and explicit human approval. Failure to attempt 27B does not reduce project success.

## Minimum defensible outcome if scaling fails

A smaller open-weight model may still constitute a valid outcome only if G0-G4, product integration, data/safety integrity, honest limitation reporting, and reproducibility pass. The project must not relabel a smaller model as approximately 27B or hide the scale shortfall.
