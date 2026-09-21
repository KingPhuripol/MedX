# Case-Adaptive Medical Multimodal Foundation Model

Production repository for one five-member Senior Project:

**Case-Adaptive Medical Multimodal Foundation Model for Clinical Reasoning and Care-Pathway Decision Support**

The project has two coordinated tracks:

- **Research:** an open-weight, multi-disease medical multimodal model with a case-adaptive, discrete, typed, inspectable computation DAG. The flagship target is approximately 4B parameters. A 27B model is a stretch goal only after every 4B gate passes.
- **Innovation:** an API-first AI Clinical Front Door for intake, urgency assessment, care-pathway support, next-information selection, uncertainty handling, escalation, and clinician confirmation.

This repository is a research and decision-support prototype. It must never claim autonomous diagnosis or treatment.

## Start in under five minutes

Prerequisites: Git, Python 3.10 or newer, and a current Claude Code installation.

```bash
bash scripts/bootstrap.sh
claude doctor
claude
```

The bootstrap is idempotent. It initializes Git when needed, makes local scripts executable, and validates the complete Harness. It does not install packages, download data, run training, publish artifacts, or create a commit.

## Everyday commands

```bash
make verify             # validate the Harness and machine-readable state
make smoke              # run lightweight, non-training checks
make leakage-fixture    # prove the temporal audit works on a valid fixture
python3 scripts/new_experiment.py --help
python3 scripts/validate_manifest.py experiments/manifests/exp_0000_harness_smoke.json
```

Useful Claude Code skills:

```text
/new-experiment <short-slug>
/run-smoke-test
/run-benchmark <manifest-path>
/architecture-ablation <manifest-path>
/data-audit <dataset-manifest-or-directory>
/temporal-leakage-audit <journey-file-or-dataset>
/integration-check
/proposal-readiness
/progress-readiness
/hf-release-check <release-directory>
```

Run `/agents` to inspect the project specialists. Code-writing agents use worktree isolation. Clinical safety and integration reviewers are configured for read-only plan mode.

## Repository map

```text
CLAUDE.md                         project constitution loaded every session
.claude/agents/                   project subagents
.claude/skills/                   repeatable workflows
.claude/hooks/                    deterministic approval and validation gates
.claude/rules/                    path-scoped rules
docs/                             human-readable source of truth
schemas/                          machine contracts
project_state/                    validated tasks, risks, decisions, deadlines
experiments/manifests/            one manifest per experiment
scripts/                          bootstrap, audit, status, and verification tools
tests/fixtures/                   safe synthetic validation fixtures
research/                         Research Track implementation area
innovation/                       Clinical Front Door implementation area
shared/                           cross-track code and contracts
```

## Authority and safety

- Official academic dates are immutable. Only a human may approve a correction backed by a new official faculty source.
- Patient splits are patient-level. An input evaluated at time `T` may use only evidence with `available_at_time <= T`.
- Real or identifiable patient data must not be sent to external APIs without explicit recorded authorization.
- Tier 3 controlled runs require declared budget and approval; Tier 4 flagship training always requires human approval.
- Publishing, uploading checkpoints, destructive data changes, and deleting checkpoints require human approval.
- External models may serve only as prototype providers behind the stable Model Gateway contract. Innovation code must not depend directly on a provider SDK.

The authoritative policies are [CLAUDE.md](CLAUDE.md), [HUMAN_APPROVAL_POLICY.md](docs/shared/HUMAN_APPROVAL_POLICY.md), [DATA_CONTRACT.md](docs/shared/DATA_CONTRACT.md), and [SAFETY_SPEC.md](docs/innovation/SAFETY_SPEC.md).

## First commit

After reviewing team names, ownership, and the unknown Group Application status:

```bash
make verify
git status
git add .
git commit -m "chore: bootstrap senior project Claude Code harness"
```

Do not commit secrets, datasets, patient data, checkpoints, or local Claude settings.
