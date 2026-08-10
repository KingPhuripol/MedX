# Codebase Structure

**Analysis Date:** 2026-08-11

## Directory Layout

```
Full-Agent/
├── .claude/                          # Claude Code configuration & hooks
│   ├── settings.json                 # Permissions, hooks, worktree config
│   ├── settings.local.json           # Local overrides (not in git)
│   ├── hooks/                        # PreToolUse/PostToolUse/SessionStart scripts
│   │   ├── approval_gate.py          # PreToolUse gate for risky operations
│   │   ├── post_edit_checks.py       # PostToolUse validation after edits
│   │   └── session_context.py        # SessionStart deadline reminder injection
│   ├── agents/                       # 12 agent definitions with prompts
│   │   └── *.md                      # Agent prompt files (not explored in detail)
│   ├── skills/                       # 11 project skills
│   │   └── */SKILL.md                # Skill index and workflow
│   └── rules/                        # Project constraint rules
│       ├── data.md                   # Data split, provenance, temporal rules
│       ├── project-management.md     # Deadline immutability, task evidence
│       ├── research.md               # Contract, manifest, baseline, tier rules
│       └── innovation.md             # Gateway, mock provider, approval rules
│
├── .planning/                        # Planning output (GSD)
│   └── codebase/                     # Codebase maps written here
│       ├── ARCHITECTURE.md           # System architecture (this analysis)
│       ├── STRUCTURE.md              # Directory layout (this file)
│       ├── STACK.md                  # Technology stack (not generated)
│       ├── INTEGRATIONS.md           # External APIs (not generated)
│       ├── CONVENTIONS.md            # Coding conventions (not generated)
│       ├── TESTING.md                # Testing patterns (not generated)
│       └── CONCERNS.md               # Technical debt (not generated)
│
├── .git/                             # Git repository
│
├── docs/                             # Source-of-truth documentation
│   ├── PROJECT_CHARTER.md            # Project scope, mission, success criteria
│   ├── DECISION_LOG.md               # Chronological decisions with rationale
│   ├── project_management/
│   │   ├── OFFICIAL_DEADLINES.md     # Immutable semester deadline registry
│   │   ├── MASTER_PLAN.md            # High-level roadmap and milestones
│   │   ├── MILESTONES.md             # M0-M3+ milestone definitions and gates
│   │   ├── TASK_BOARD.md             # Readable task reference (mirrors tasks.json)
│   │   ├── RISK_REGISTER.md          # Readable risk reference (mirrors risks.json)
│   │   ├── TEAM_OWNERSHIP.md         # Team members, roles, responsibilities
│   │   └── WEEKLY_STATUS.md          # Status updates (readable, not parsed)
│   ├── research/
│   │   ├── README.md                 # Pointer to architecture/implementation
│   │   ├── RESEARCH_SPEC.md          # Research problem, approach, success criteria
│   │   ├── ARCHITECTURE_SPEC.md      # Proposed 4B model architecture (not implemented)
│   │   ├── TRAINING_SPEC.md          # Training pipeline specification
│   │   ├── BENCHMARK_CONTRACT.md     # Baseline comparisons and public benchmarks
│   │   └── SUCCESS_CRITERIA.md       # Research gate requirements for 4B/27B
│   ├── innovation/
│   │   ├── README.md                 # Pointer to implementation area
│   │   ├── PRODUCT_SPEC.md           # Clinical Front Door product specification
│   │   ├── CLINICAL_WORKFLOW.md      # Clinician workflows and use cases
│   │   ├── SAFETY_SPEC.md            # Safety guardrails and escalation rules
│   │   └── ACCEPTANCE_CRITERIA.md    # Product acceptance tests
│   └── shared/
│       ├── README.md                 # Pointer to shared runtime code area
│       ├── DATA_CONTRACT.md          # Patient journey, split, temporal rules
│       ├── PATIENT_JOURNEY_SCHEMA.md # Patient journey data model
│       ├── MODEL_API_CONTRACT.md     # Model gateway request/response contract
│       ├── EVALUATION_CONTRACT.md    # Evaluation metrics and reporting
│       └── HUMAN_APPROVAL_POLICY.md  # Approval authority, scope, evidence
│
├── project_state/                    # Machine-readable immutable state
│   ├── official_deadlines.json       # Canonical deadline registry (immutable)
│   ├── tasks.json                    # Workstream tasks with deps, owners, evidence
│   ├── risks.json                    # Risk register with probability/impact matrix
│   ├── decisions.json                # Decision log entries (appended only)
│   ├── approvals.json                # Human approval records for Tier 3/4
│   └── evaluations.json              # Experiment evaluation records
│
├── schemas/                          # JSON-Schema contracts
│   ├── official-deadlines.schema.json # Deadline registry schema
│   ├── task.schema.json              # Task object schema
│   ├── risk.schema.json              # Risk object schema
│   ├── decision.schema.json          # Decision log entry schema
│   ├── human-approval.schema.json    # Approval record schema
│   ├── evaluation-record.schema.json # Evaluation record schema
│   ├── experiment-manifest.schema.json # Experiment manifest schema
│   ├── patient-journey.schema.json   # Patient journey schema
│   ├── model-api-request.schema.json # Model API request schema
│   └── model-api-response.schema.json # Model API response schema
│
├── scripts/                          # Harness and utility scripts
│   ├── bootstrap.sh                  # Initialize project directories and git hooks
│   ├── run_smoke_test.sh             # Run minimal smoke tests
│   ├── harness_lib.py                # Dependency-free JSON-Schema validator
│   ├── verify_harness.py             # Main harness verification script
│   ├── project_status.py             # Display active tasks, risks, deadlines
│   ├── temporal_leakage_audit.py    # Audit Patient Journey temporal integrity
│   ├── validate_manifest.py          # Validate experiment manifest
│   └── new_experiment.py             # Scaffold new experiment manifest
│
├── experiments/                      # Experiment tracking
│   └── manifests/
│       └── exp_NNNN_slug.json       # Experiment manifests (one per run)
│
├── tests/                            # Test fixtures and test code (TBD)
│   └── fixtures/
│       ├── patient_journey/
│       │   └── valid.json            # Example Patient Journey for audit testing
│       └── model_api/
│           ├── request.json          # Example Model API request fixture
│           └── response.json         # Example Model API response fixture
│
├── research/                         # Research implementation area (placeholder)
│   └── README.md                     # Pointer; actual modules not yet created
│
├── innovation/                       # Innovation implementation area (placeholder)
│   └── README.md                     # Pointer; actual modules not yet created
│
├── shared/                           # Shared runtime code area (placeholder)
│   └── README.md                     # Pointer; actual modules not yet created
│
├── data/                             # Data directories (not tracked in git)
│   ├── raw/                          # Original unprocessed data
│   ├── interim/                      # Intermediate transformed data
│   └── processed/                    # Final processed data
│
├── artifacts/                        # Experiment outputs (not tracked)
│   └── experiments/                  # Run artifacts indexed by exp_NNNN
│
├── checkpoints/                      # Model checkpoints (not tracked)
│
├── logs/                             # Run logs (not tracked)
│
├── sources/                          # External data sources (synced, read-only)
│   └── [synced data files]
│
├── Makefile                          # Common CLI commands (verify, smoke, status)
├── README.md                         # Project overview
├── CLAUDE.md                         # Operating constitution and governance rules
└── .gitignore                        # Excludes data/, checkpoints/, logs/, etc.
```

## Directory Purposes

**`.claude/`** — Claude Code harness configuration
- `settings.json`: Main configuration with permissions, hooks, and worktree settings
- `hooks/*.py`: PreToolUse (approval gate), PostToolUse (validation), SessionStart (reminder)
- `agents/*.md`: Agent definitions (not parsed in detail; checked by verify_harness.py)
- `skills/*/SKILL.md`: Skill index files (checked by verify_harness.py)
- `rules/*.md`: Scoped constraint rules for data/project-management/research/innovation

**`.planning/codebase/`** — GSD codebase mapping output
- Holds ARCHITECTURE.md, STRUCTURE.md, and other analysis documents
- Created and maintained by `/gsd-map-codebase` command

**`docs/`** — Source-of-truth documentation
- Organized into: project_management, research, innovation, shared subdirectories
- Human-readable versions of state and contracts
- Linked in CLAUDE.md as required reading

**`project_state/`** — Machine-readable immutable state (highest precedence)
- JSON files bound to schemas in `schemas/`
- Drives verification, approval gates, and status reporting
- Append-only for decisions, approvals, evaluations
- Immutable for official deadlines (governance layer)

**`schemas/`** — JSON-Schema contracts for all state and fixtures
- 10+ schema files defining valid structure for state, manifests, fixtures
- Bound to specific file paths in `SCHEMA_BINDINGS` (verify_harness.py)
- Updated when adding fields to state; changes require human decision and Decision Log entry

**`scripts/`** — Verification, validation, and reporting harness
- `verify_harness.py`: Main integrity check; called by PostToolUse hook
- `harness_lib.py`: Dependency-free JSON-Schema validator
- `project_status.py`: Display active tasks, risks, workload balance
- `temporal_leakage_audit.py`: Detect future-information leakage in Patient Journeys
- `bootstrap.sh`, `run_smoke_test.sh`: Setup and minimal testing

**`experiments/manifests/`** — Experiment declaration and tracking
- One JSON manifest file per experiment (exp_NNNN_slug.json)
- Declares model, data, training, graph, resource, and approval parameters
- Validated by `validate_manifest.py` and verify_harness.py
- Manifest status drives approval gate and execution authorization

**`tests/fixtures/`** — Canonical test data for validation and audit testing
- `patient_journey/valid.json`: Valid Patient Journey example with multiple events and modalities
- `model_api/request.json`: Model API request with evidence and decision_time
- `model_api/response.json`: Model API response with human_review flag
- Used by `temporal_leakage_audit.py` and integration tests (to be written)

**`research/`, `innovation/`, `shared/`** — Application code areas (specified but not implemented)
- `research/`: Data interfaces, encoders, case-adaptive graph, models, training, evaluation
  - Recommended structure (per README.md): `data_interfaces/`, `encoders/`, `graph/`, `models/`, `training/`, `evaluation/`, `configs/` with tests
- `innovation/`: Client UI/API, Front Door orchestration, safety layer, Model Gateway, provider adapters, audit store
  - Recommended structure (per README.md): keep client, API, policy layer, gateway, adapters, audit store separated
- `shared/`: Contract models, Patient Journey snapshot logic, serialization, versioned API models

**`data/`**, **`artifacts/`**, **`checkpoints/`**, **`logs/`** — Runtime outputs (not tracked)
- Excluded by `.gitignore`
- Organized by dataset version, experiment ID, run date
- Never committed; references via manifest metadata (dataset_version, artifact paths)

**`sources/`** — Synced external data (read-only)
- Write/Edit permissions denied by `.claude/settings.json`
- Used for reference documentation or license text only

## Key File Locations

**Entry Points:**
- `Makefile` — CLI commands: verify, smoke, status, leakage-fixture
- `.claude/hooks/session_context.py` — SessionStart hook; prints deadline reminder
- `.claude/hooks/approval_gate.py` — PreToolUse hook; blocks risky commands
- `.claude/hooks/post_edit_checks.py` — PostToolUse hook; validates JSON/Python after edits

**Configuration:**
- `.claude/settings.json` — Permissions, hook definitions, worktree config
- `.claude/rules/*.md` — Constraint rules for data, project management, research, innovation
- `CLAUDE.md` — Operating constitution; governance boundaries and delegation rules

**Core Logic:**
- `scripts/verify_harness.py` — Main verification entry point
- `scripts/harness_lib.py` — JSON-Schema validation implementation
- `scripts/project_status.py` — Status display and workload balance report
- `scripts/temporal_leakage_audit.py` — Temporal integrity audit

**Testing:**
- `tests/fixtures/patient_journey/valid.json` — Valid journey example
- `tests/fixtures/model_api/request.json` — Valid request example
- `tests/fixtures/model_api/response.json` — Valid response example
- `scripts/run_smoke_test.sh` — Minimal smoke test suite

## Naming Conventions

**Files:**
- Python scripts: `snake_case.py` (e.g., `temporal_leakage_audit.py`)
- JSON config/state: `kebab-case.json` or `snake_case.json` (e.g., `official_deadlines.json`, `human-approval.schema.json`)
- Documentation: `UPPERCASE.md` (e.g., `PROJECT_CHARTER.md`, `RESEARCH_SPEC.md`)
- Experiment manifests: `exp_NNNN_slug.json` (e.g., `exp_0000_harness_smoke.json`)

**Directories:**
- Feature areas: `snake_case/` (e.g., `project_management/`, `patient_journey/`)
- System directories: lowercase descriptive (e.g., `scripts/`, `schemas/`, `experiments/`)
- Top-level tracks: `research/`, `innovation/`, `shared/`

**JSON Keys:**
- camelCase for most fields (e.g., `task_id`, `available_at_time`, `planning_deadline`)
- Enum values: UPPERCASE_SNAKE_CASE (e.g., `status: "IN_PROGRESS"`, `priority: "P0"`)
- Timestamps: ISO-8601 with timezone (e.g., `"2026-08-11T04:00:00+07:00"`)

**IDs & Slugs:**
- Task IDs: `TASK-NNNN` (e.g., `TASK-0001`)
- Risk IDs: `RISK-NNNN` (e.g., `RISK-0001`)
- Deadline IDs: `DL-NNNN` (e.g., `DL-0001`)
- Decision IDs: `DECISION-NNNN`
- Experiment IDs: `exp_NNNN` (e.g., `exp_0000`)
- Experiment slugs: `lowercase-kebab-case` (e.g., `harness-smoke`)

## Where to Add New Code

**New Governance/PM Task:**
- Add entry to `project_state/tasks.json` with task_id (next TASK-NNNN), owner, workstream, priority, status, due_date, dependencies
- Run `make verify` to ensure task_id is unique and dependencies resolve
- Update `docs/project_management/TASK_BOARD.md` for human reference
- If blocking others or critical risk: link from `project_state/risks.json`

**New Research Experiment:**
1. Create task in `project_state/tasks.json`
2. Run `python3 scripts/new_experiment.py` to scaffold manifest
3. Fill manifest: model name/version, data version, training config, graph mode, resource budget, comparisons, evaluation criteria
4. Run `python3 scripts/validate_manifest.py experiments/manifests/exp_NNNN_slug.json` to validate
5. Place code in `research/` subdirectory matching architecture (e.g., `research/models/my_model.py`)
6. Write integration tests in `tests/` that use fixtures
7. Commit manifest, code, and tests together

**New Innovation Feature (Front Door Module):**
1. Create feature task in `project_state/tasks.json`
2. Place code in `innovation/` with clear separation: client, gateway, adapter, audit
3. Validate against Model API Contract (`docs/shared/MODEL_API_CONTRACT.md`)
4. Mock provider is default; external provider calls wrapped in adapter
5. Include safety/escalation logic for red flags; human review mandatory before commit
6. Write tests that validate temporal input and provider output
7. Update `docs/innovation/CLINICAL_WORKFLOW.md` if workflow changes

**New Shared Contract or Model:**
1. Define structure in new schema file (e.g., `schemas/my-contract.schema.json`)
2. Add to `SCHEMA_BINDINGS` in `verify_harness.py` if it's a critical fixture
3. Create example in `tests/fixtures/` if used in validation
4. Implement contract model in `shared/` module
5. Document in `docs/shared/` with version and migration guidance
6. Update Decision Log entry when adding material contracts

**New Agent or Skill:**
1. Agent: Create `.claude/agents/agent_name.md` with frontmatter (name, description, isolation, tools, permissionMode) and prompt >= 500 chars
   - Add agent_name to AGENT_NAMES set in `verify_harness.py`
   - Ensure code-writing agents have `isolation: worktree`; reviewers have `permissionMode: plan` and no Write/Edit/NotebookEdit
2. Skill: Create `.claude/skills/skill_name/SKILL.md` with frontmatter and workflow >= 500 chars
   - Add skill_name to SKILL_NAMES set in `verify_harness.py`
   - Skill name must match directory name

**New Test Fixture:**
1. Place JSON fixture in `tests/fixtures/` subdirectory matching domain (e.g., `tests/fixtures/patient_journey/my_case.json`)
2. If bound to schema: add to `SCHEMA_BINDINGS` in verify_harness.py
3. Run `make verify` to ensure fixture validates
4. If used for audit testing: include `--as-of` cutoff in Makefile example or test command

**New Validation Rule or Gate:**
1. Governance rule: Add to `.claude/rules/domain.md` and reference in agent prompts
2. Approval gate: Add regex to COMMAND_GATES in `approval_gate.py`; test with `Bash` command examples
3. Schema constraint: Add field to appropriate schema in `schemas/`, update instance in `project_state/`, run verify

**Breaking Change to Contract/Schema:**
1. Update schema file in `schemas/`
2. Create migration fixture in `tests/fixtures/`
3. Add migration logic to `harness_lib.py` or separate script if needed
4. Update instance files in `project_state/`
5. Document in `docs/shared/` with version bump and migration guide
6. Create Decision Log entry with human approval (`project_state/decisions.json`)
7. Update schema_version in all affected instance files
8. Run `make verify` before commit

## Special Directories

**`.git/`** — Version control
- Tracks all code, documentation, schemas, state (except data/, checkpoints/, logs/)
- Hooks configured in bootstrap.sh
- Protected: `CLAUDE.md`, contract/schema files, deadline registry

**`data/`, `artifacts/`, `checkpoints/`, `logs/`** — Runtime outputs
- Generated: Yes (by training/inference pipelines, not in git)
- Committed: No (excluded by .gitignore)
- Versioning: Tracked via manifest metadata (dataset_version, experiment_id, artifact paths)
- Cleanup: Handled by experiment lifecycle management (Tier 4 runs require rollback plan)

**`.planning/codebase/`** — GSD analysis output
- Generated: Yes (by `/gsd-map-codebase` command)
- Committed: Yes (for planning and review)
- Overwritten: Each run completely regenerates all documents; use `--paths` to scope incremental updates

**`sources/`** — Synced external references
- Generated: No (manually synced or CI-driven)
- Committed: Yes (reference only, no modifications)
- Protected: Write/Edit denied by `.claude/settings.json`

---

*Structure analysis: 2026-08-11*
