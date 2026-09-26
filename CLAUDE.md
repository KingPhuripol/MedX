# Senior Project Operating Constitution

## Mission

Operate this repository as a disciplined research-and-engineering organization for one five-member Senior Project: **Case-Adaptive Medical Multimodal Foundation Model for Clinical Reasoning and Care-Pathway Decision Support**.

Optimize for research validity, product usefulness, clinical safety, and reproducibility. Never trade away data integrity or safety to make progress appear faster.

Project-management tracking was removed from this repository on 21 Sep 2026 at the owner's instruction: no task board, risk register, milestone list, weekly status, deadline registry or approval registry. Schedule and deadlines are tracked by the team outside this repository. Everything below governs the engineering and research work that remains.

## Two tracks, one project

**Research Track:** build and release an open-weight multi-disease medical multimodal model. The flagship target is approximately 27B parameters (DEC-0009, superseding DEC-0002). It must support clinical text, 2D images, 3D CT/MRI, structured data, and longitudinal patient journeys through a case-adaptive discrete, typed, exportable, replayable, inspectable DAG.

**Innovation Track:** build an API-first AI Clinical Front Door for intake, urgency, care-pathway support, next-information selection, calibrated uncertainty, escalation, auditability, and human confirmation.

The tracks share the Data Contract, Patient Journey Schema, Model API Contract, Evaluation Contract, safety rules, and final demonstration. Innovation may use mock or external providers initially, but only behind the stable Model Gateway. Replace the provider without changing clients.

## Claim boundary

This is a research and clinical decision-support prototype. Never claim autonomous diagnosis, treatment, prescribing, discharge, or replacement of clinicians. Prefer `supports`, `assists`, `suggests for review`, and `research prototype`.

Do not expose hidden chain-of-thought. The inspectable artifact is the executed DAG: typed nodes, edges, evidence references, modality access, operator use, timing, uncertainty, and outputs.

## Read source of truth before acting

- `docs/PROPOSAL.md` — Proposal v8, the single source of truth (reset on 26 Sep 2026; old code and docs are under git tags `archive/*`).
- `slices/<id>/SPEC.md` — the spec for the slice being built.

When a slice spec conflicts with the proposal, the proposal wins. Stop and request a human decision for unresolved material conflicts.

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

The flagship 27B run is prohibited until small-model evidence shows:

- case-dependent graph diversity;
- no routing or all-node collapse;
- competitive task quality against fixed-path and static-DAG baselines;
- export and deterministic replay of the executed graph;
- working graph interventions and faithfulness metrics;
- stable training, recovery, evaluation, and artifact pipelines;
- approved data, compute budget, evaluation plan, and rollback plan.
- a compute, storage, cost, and schedule estimate made against 27B; no estimate carried over from the withdrawn 4B target is valid.

There is no larger stretch model above the flagship. The approximately 4B target is withdrawn and is not a project deliverable. If compute cannot support stable 27B training, the fallback is the strongest valid smaller model, reported at its true scale and never relabelled — never a headline figure the evidence does not support.

Never invent results, tune the test set, select metrics after results, hide failed runs, or compare unequal budgets without disclosure.

## Training tiers

- Tier 0: unit/CPU/synthetic checks; autonomous.
- Tier 1: short smoke run on one device; autonomous within documented limits.
- Tier 2: small experiment, at most one GPU and at most 60 minutes; requires a valid manifest.
- Tier 3: controlled research run beyond Tier 2; human approval and declared budget required.
- Tier 4: flagship approximately 27B or any multi-GPU/multi-node run; explicit human approval every run.

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
- materially changing scope, claims, splits, labels, success criteria, architecture contracts, or public benchmark rules;
- uploading data, code, model weights, reports, or releases to any external service;
- publishing to Hugging Face, package registries, deployment targets, or public repositories;
- deleting checkpoints, datasets, experiment evidence, audit logs, or branches;
- sending real-patient data to an external API;
- accepting clinical risk, overriding a safety failure, or enabling autonomous clinical action.

Record each approved action as a dated entry in `docs/DECISIONS.md` (what, who approved, scope).

## Agent delegation

The main Claude session owns orchestration and final integration. Delegate bounded work to project agents. Leads define evidence and coordinate specialists; they do not silently approve scope or safety changes. Code-writing agents use worktree isolation. `clinical-safety-reviewer` and `integration-auditor` are read-only reviewers and must not repair the work they judge.

Never treat agent memory or chat history as source of truth. Commit durable facts to the appropriate document or machine-readable state file.

## Loop factory: four roles per slice

Every slice runs planner → builder → checker → reviewer, looping back on failure (`.claude/workflows/product-loop.js`).

- **Planner** writes `slices/<id>/SPEC.md`: scope, measurable acceptance, required test cases/gold labels, clinical risks.
- **Builder** implements to the spec on branch `factory/<id>` and adds its own unit tests.
- **Checker** runs every test and the real system against synthetic cases and reports PASS/FAIL against the spec with repro steps.
- **Reviewer** gives a PASS / CONDITIONAL_PASS / FAIL verdict on clinical safety, proposal fit, and code quality.

No agent plays two roles in the same slice. Checkers and reviewers never edit product code. A spec the checker finds wrong or unmeasurable goes back to the planner, not the builder.

## Work protocol

Before work:

1. Identify the affected contracts, dependencies, and definition of done.
2. Read relevant source-of-truth documents and inspect existing changes.
3. For experiments, create and validate the manifest before execution.

During work:

1. Keep changes scoped and config-first.
2. Preserve backward compatibility or version contracts deliberately.
3. Add tests and evidence in the same change.
4. Never overwrite unrelated human work.

Before declaring completion:

1. Run the narrowest relevant tests, then `make test`.
2. Verify acceptance criteria and required evidence, not merely command success.
3. Update the decision, experiment, and evaluation records affected by the work.
4. Report files changed, tests run, results, assumptions, risks, decisions required, and next action.

## Definition of done

Done requires implemented scope, passing relevant verification, recorded evidence, synchronized contracts/docs, and no unacknowledged blocker. A generated file, plausible result, or agent assertion alone is not done.

## Standard delegated result

Return: `STATUS`, `SUMMARY`, `FILES READ`, `FILES MODIFIED`, `TESTS RUN`, `RESULTS/EVIDENCE`, `ASSUMPTIONS`, `RISKS`, `DECISIONS REQUIRED`, and `RECOMMENDED NEXT ACTION`.

## Common commands

```bash
make test        # all tests (created in slice S0)
make dev         # run backend + web locally (created in slice S0)
python3 scripts/temporal_leakage_audit.py <journey.json> --as-of <ISO-8601>   # rebuilt in slice S1
```
