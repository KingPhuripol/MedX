# Research Success Criteria and Gates

Success is cumulative. A later gate cannot compensate for an earlier integrity failure.

## G0 - Governance and contracts

Status as of 30 Aug 2026: **all five closed. G0 is closed, with two residuals tracked below.**

- [x] Research questions and claim boundaries accepted.
      Evidence: `docs/research/RESEARCH_SPEC.md` RQ1-RQ3; claim boundary in `docs/PROJECT_CHARTER.md`
      and `CLAUDE.md` §Claim boundary; DEC-0001 and DEC-0005 accepted.
- [x] Data, Patient Journey, Model API, Evaluation, and Approval contracts versioned.
      Evidence: `project_state/contract_versions.json` registers all five at 1.0.0 with status
      ACCEPTED, validated against `schemas/contract-versions.schema.json` by the harness.
- [x] Dataset access/license/ethics feasibility recorded.
      Evidence: `project_state/dataset_feasibility.json` records seven candidates (DS-0007 CT-RATE added
      2026-08-30 to cover the 3D CT modality the original six did not supply), each `CONDITIONAL` with a
      named condition and each citing its sources. `docs/research/DATASET_FEASIBILITY.md` carries the
      findings; the resulting constraints are written into `BENCHMARK_CONTRACT.md`. The harness refuses
      any `VERIFIED` dimension or non-`UNDER_REVIEW` verdict that cites no evidence.
      The gate asks that feasibility be **recorded**, and it now is — including the negative findings,
      which are the substantive ones: patient-level cross-modality linkage exists only inside the MIMIC
      family, and every candidate except VQA-RAD is non-commercial.

- [x] Experiment manifest validation and evidence lineage work.
      Evidence: `scripts/validate_manifest.py` accepts `experiments/manifests/exp_0000_harness_smoke.json`;
      `bash scripts/run_smoke_test.sh` passes end to end.
- [x] Official academic plan and owners accepted.
      Evidence: accepted 2026-08-30 against DEC-0007, verified by the harness at the time.
      The plan, milestone and ownership documents and the deadline registry that held this
      evidence were removed from the repository on 2026-09-21 at the owner's instruction;
      schedule tracking now lives outside this repository. See git history at `4d6bbbe` for
      the last state of those files.
      Residual: the Group Application receipt was never archived and is unrecoverable. That is
      an evidence gap in the original submission, not a defect in the plan itself.

**Residuals — G0 is closed, these are not:**

1. **Owner sign-off is outstanding (TASK-0019).** `reviewed_by` is `null` on all seven records. Evidence
   was gathered on the owner's behalf; acceptance is the owner's. Dimensions resolved only from secondary
   sources remain `UNVERIFIED` and are listed for confirmation.
2. **RISK-0002 and RISK-0010 were raised, not retired, by this evidence.** G0 required feasibility to be
   recorded; it never required the answer to be favourable. The finding that a single-patient
   five-modality journey is unavailable, and that the open-weight release faces a non-commercial ceiling,
   flows into G1 and into the Proposal — it does not reopen G0.

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
