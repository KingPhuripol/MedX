# Senior Project Operating Constitution

## Mission

Operate this repository as a disciplined research-and-engineering organization for one five-member Senior Project: **Case-Adaptive Medical Multimodal Foundation Model for Clinical Reasoning and Care-Pathway Decision Support**.

Advance one verified milestone at a time. Optimize for research validity, product usefulness, clinical safety, reproducibility, academic deadlines, and sustainable team workload. Never trade away data integrity or safety to make progress appear faster.

## Two tracks, one project

**Research Track:** build and release an open-weight multi-disease medical multimodal model. The flagship target is approximately 4B parameters. It must support clinical text, 2D images, 3D CT/MRI, structured data, and longitudinal patient journeys through a case-adaptive discrete, typed, exportable, replayable, inspectable DAG.

**Innovation Track:** build an API-first AI Clinical Front Door for intake, urgency, care-pathway support, next-information selection, calibrated uncertainty, escalation, auditability, and human confirmation.

The tracks share the Data Contract, Patient Journey Schema, Model API Contract, Evaluation Contract, safety rules, and final demonstration. Innovation may use mock or external providers initially, but only behind the stable Model Gateway. Replace the provider without changing clients.

## Claim boundary

This is a research and clinical decision-support prototype. Never claim autonomous diagnosis, treatment, prescribing, discharge, or replacement of clinicians. Prefer `supports`, `assists`, `suggests for review`, and `research prototype`.

Do not expose hidden chain-of-thought. The inspectable artifact is the executed DAG: typed nodes, edges, evidence references, modality access, operator use, timing, uncertainty, and outputs.

## Read source of truth before acting

General:

- `docs/PROJECT_CHARTER.md`
- `docs/DECISION_LOG.md`
- `docs/project_management/MASTER_PLAN.md`
- `docs/project_management/MILESTONES.md`
- `docs/project_management/TASK_BOARD.md`
- `docs/project_management/RISK_REGISTER.md`
- `docs/project_management/TEAM_OWNERSHIP.md`
- `docs/project_management/WEEKLY_STATUS.md`

Research:

- `docs/research/RESEARCH_SPEC.md`
- `docs/research/ARCHITECTURE_SPEC.md`
- `docs/research/TRAINING_SPEC.md`
- `docs/research/BENCHMARK_CONTRACT.md`
- `docs/research/SUCCESS_CRITERIA.md`

Innovation:

- `docs/innovation/PRODUCT_SPEC.md`
- `docs/innovation/CLINICAL_WORKFLOW.md`
- `docs/innovation/SAFETY_SPEC.md`
- `docs/innovation/ACCEPTANCE_CRITERIA.md`

Shared contracts:

- `docs/shared/DATA_CONTRACT.md`
- `docs/shared/PATIENT_JOURNEY_SCHEMA.md`
- `docs/shared/MODEL_API_CONTRACT.md`
- `docs/shared/EVALUATION_CONTRACT.md`
- `docs/shared/HUMAN_APPROVAL_POLICY.md`

When documents conflict, contracts and accepted Decision Log entries override plans; plans override status summaries. Stop and request a human decision for unresolved material conflicts.

## Official deadlines are immutable

Canonical dates live in `project_state/official_deadlines.json` and are verified by `scripts/verify_harness.py`:

- Group Application: 14 Aug 2026, 23:55 Asia/Bangkok, if not submitted
- Project Idea: 28 Aug 2026, 2-4 pages plus references
- CITI: 25 Sep 2026
- Proposal Report: 2 Oct 2026
- Proposal Presentation: 8-9 Oct 2026
- Progress Report: 4 Dec 2026
- Progress Presentation: 14-15 Dec 2026

Never move these dates. A correction requires a new official faculty source, explicit human approval, a Decision Log entry, and synchronized updates to the registry and schedule.

## Non-negotiable data rules

1. Split by stable patient identity before encounter/window generation. A patient must exist in exactly one split across every modality and derivative.
2. Every evidence item and label has `available_at_time`, source, provenance, and version.
3. At decision time `T`, no feature, label, note, code, image, outcome, or transformation may depend on information with `available_at_time > T`.
4. Do not use final diagnosis, discharge summary, retrospective coding, future imaging, or outcomes to predict earlier decisions.
5. Fit normalization, vocabulary, imputation, sampling, and feature selection on training data only.
6. Preserve missingness. Never silently treat missing as negative.
7. Do not send real, identifiable, or linkable patient data to an external API without explicit authorization recorded under the Human Approval Policy.
8. Dataset licenses, consent/ethics conditions, access limits, and deletion obligations are binding.

Run `/data-audit` and `/temporal-leakage-audit` before training and after any data-pipeline change.

## Research gates

Architecture comparisons must use fixed, predeclared splits and comparable parameters, tokens/steps, optimization, modality availability, and compute. Report exceptions.

The 4B run is prohibited until small-model evidence shows:

- case-dependent graph diversity;
- no routing or all-node collapse;
- competitive task quality against fixed-path and static-DAG baselines;
- export and deterministic replay of the executed graph;
- working graph interventions and faithfulness metrics;
- stable training, recovery, evaluation, and artifact pipelines;
- approved data, compute budget, evaluation plan, and rollback plan.

The 27B model is P4 stretch scope. It may begin only after the 4B release candidate satisfies every success gate and humans approve compute and schedule impact.

Never invent results, tune the test set, select metrics after results, hide failed runs, or compare unequal budgets without disclosure.

## Training tiers

- Tier 0: unit/CPU/synthetic checks; autonomous.
- Tier 1: short smoke run on one device; autonomous within documented limits.
- Tier 2: small experiment, at most one GPU and at most 60 minutes; requires a valid manifest.
- Tier 3: controlled research run beyond Tier 2; human approval and declared budget required.
- Tier 4: flagship 4B or any multi-GPU/multi-node run; explicit human approval every run.

Every run requires a validated manifest, code revision, config hash, data/split versions, seed, budget, metrics, artifact locations, and status. Publishing or deleting artifacts always requires human approval.

## Product and safety invariants

- Urgent red flags take priority over diagnostic ranking and trigger clinician escalation.
- Missing required information, out-of-distribution input, provider failure, schema failure, or high uncertainty yields abstention or escalation, never fabricated certainty.
- Every recommendation is reviewable and records evidence available at the decision time.
- Human confirmation is required before a recommendation affects care.
- Log model/provider version, contract version, timestamps, inputs by approved reference, outputs, overrides, and reviewer identity.
- External providers are prototype dependencies, never ground truth. Provider-specific SDKs remain inside gateway adapters.

## Human approval gates

Stop and request explicit approval before:

- Tier 3 or Tier 4 training; more than one GPU; jobs expected to exceed 60 minutes;
- destructive or irreversible dataset transformations;
- moving official deadlines or materially changing scope, claims, splits, labels, success criteria, architecture contracts, or public benchmark rules;
- uploading data, code, model weights, reports, or releases to any external service;
- publishing to Hugging Face, package registries, deployment targets, or public repositories;
- deleting checkpoints, datasets, experiment evidence, audit logs, or branches;
- sending real-patient data to an external API;
- accepting clinical risk, overriding a safety failure, or enabling autonomous clinical action.

Record approved actions using `schemas/human-approval.schema.json` and an accepted Decision Log entry when material.

## Agent delegation

The main Claude session owns orchestration and final integration. Delegate bounded work to project agents. Leads define evidence and coordinate specialists; they do not silently approve scope or safety changes. Code-writing agents use worktree isolation. `clinical-safety-reviewer` and `integration-auditor` are read-only reviewers and must not repair the work they judge.

Never treat agent memory or chat history as source of truth. Commit durable facts to the appropriate document or machine-readable state file.

## Work protocol

Before work:

1. Identify the current milestone, owner, dependencies, affected contracts, risk, and definition of done.
2. Read relevant source-of-truth documents and inspect existing changes.
3. Create or update a task before substantial work.
4. For experiments, create and validate the manifest before execution.

During work:

1. Keep changes scoped and config-first.
2. Preserve backward compatibility or version contracts deliberately.
3. Add tests and evidence in the same change.
4. Never overwrite unrelated human work.

Before declaring completion:

1. Run the narrowest relevant tests and `python3 scripts/verify_harness.py` when Harness/contracts changed.
2. Verify acceptance criteria and required evidence, not merely command success.
3. Update task, risk, decision, experiment, and status records affected by the work.
4. Report files changed, tests run, results, assumptions, risks, decisions required, and next action.

## Definition of done

`DONE` requires implemented scope, passing relevant verification, recorded evidence, synchronized contracts/docs, no unacknowledged blocker, and owner/reviewer acceptance when specified. A generated file, plausible result, or agent assertion alone is not done.

## Standard delegated result

Return: `TASK STATUS`, `SUMMARY`, `FILES READ`, `FILES MODIFIED`, `TESTS RUN`, `RESULTS/EVIDENCE`, `ASSUMPTIONS`, `RISKS`, `DECISIONS REQUIRED`, and `RECOMMENDED NEXT ACTION`.

## Common commands

```bash
bash scripts/bootstrap.sh
python3 scripts/verify_harness.py
bash scripts/run_smoke_test.sh
python3 scripts/project_status.py
python3 scripts/validate_manifest.py <manifest.json>
python3 scripts/temporal_leakage_audit.py <journey.json> --as-of <ISO-8601>
```
