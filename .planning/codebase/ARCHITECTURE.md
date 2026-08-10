<!-- refreshed: 2026-08-11 -->
# Architecture

**Analysis Date:** 2026-08-11

## System Overview

This is a research-governance scaffold implementing a **Verification Harness Architecture**. The system validates project state integrity, enforces approval gates, manages deadlines, and supports multi-agent orchestration. **Implementation status: Governance layer and contract model are complete. Research/Innovation application code is not yet implemented.**

```text
┌─────────────────────────────────────────────────────────────┐
│                    Claude Code Session                       │
│           (Agent Orchestration and Planning)                 │
└────────────────────┬────────────────────────────────────────┘
                     │
┌────────────────────▼────────────────────────────────────────┐
│              Verification & Approval Gates                   │
│  `.claude/hooks/approval_gate.py` (PreToolUse)              │
│  `.claude/hooks/post_edit_checks.py` (PostToolUse)          │
│  `.claude/hooks/session_context.py` (SessionStart)          │
└────────────────────┬────────────────────────────────────────┘
                     │
┌────────────────────▼────────────────────────────────────────┐
│          Harness Validation & Schema Binding                │
│  `scripts/verify_harness.py` (integration entry point)      │
│  `scripts/harness_lib.py` (JSON-Schema validator)           │
│  `scripts/project_status.py` (state display)                │
│  `scripts/temporal_leakage_audit.py` (temporal integrity)   │
│  `scripts/validate_manifest.py` (experiment manifest check) │
└────────────────────┬────────────────────────────────────────┘
                     │
┌────────────────────▼────────────────────────────────────────┐
│             Machine-Readable Project State                   │
│  `project_state/` - immutable records:                      │
│  - official_deadlines.json (governance calendars)           │
│  - tasks.json (workstream definitions)                      │
│  - risks.json (risk register)                               │
│  - decisions.json (decision log entries)                    │
│  - approvals.json (human approval records)                  │
│  - evaluations.json (experiment evaluation records)         │
└────────────────────┬────────────────────────────────────────┘
                     │
          ┌──────────┴─────────────┬──────────────────────┐
          ▼                        ▼                      ▼
┌─────────────────────┐ ┌──────────────────┐ ┌────────────────┐
│ Contract Schemas    │ │ Test Fixtures    │ │ Experiment     │
│  `schemas/*.json`   │ │ `tests/fixtures` │ │ Manifests      │
│  (JSON-Schema)      │ │ - valid.json     │ │ `experiments/  │
│                     │ │ - request.json   │ │  manifests`    │
│ 10 domain schemas   │ │ - response.json  │ └────────────────┘
│ bound to state      │ └──────────────────┘
└─────────────────────┘
          │
          ▼
┌─────────────────────────────────────────────────────────────┐
│           Application Code (Specified, Not Implemented)     │
│                                                              │
│ `research/` - placeholder stub                              │
│   (Data interfaces, Encoders, Graph, Models, Training,      │
│    Evaluation, Configs - to be implemented)                 │
│                                                              │
│ `innovation/` - placeholder stub                            │
│   (Client, Front Door API, Safety/Policy, Model Gateway,    │
│    Provider Adapters, Audit Store - to be implemented)      │
│                                                              │
│ `shared/` - placeholder stub                                │
│   (Patient Journey logic, Contract models, Serialization)   │
└─────────────────────────────────────────────────────────────┘
```

## Component Responsibilities

| Component | Responsibility | File |
|-----------|----------------|------|
| **Harness Validator** | Verify complete contract integrity, schema bindings, agent/skill definitions, deadline immutability, state uniqueness, manifest consistency | `scripts/verify_harness.py` |
| **JSON-Schema Validator** | Dependency-free validation of JSON state and fixtures against schema subset (type, enum, const, required, format, pattern, minLength, minItems, uniqueItems, min/max) | `scripts/harness_lib.py` |
| **Approval Gate** | PreToolUse gate enforcing human approval for compute, publishing, destructive, and patient-data operations via regex detection | `.claude/hooks/approval_gate.py` |
| **Post-Edit Validator** | PostToolUse verification that changed JSON/Python files remain valid; fails edit if syntax/schema broken | `.claude/hooks/post_edit_checks.py` |
| **Session Context** | SessionStart hook injecting immutable deadline, days remaining, and governance reminder before work begins | `.claude/hooks/session_context.py` |
| **Project Status Reporter** | Machine-readable summary of active tasks, critical risks, workload balance, and project health status | `scripts/project_status.py` |
| **Temporal Audit** | Validate Patient Journey event availability and decision-time integrity; detect future-information leakage | `scripts/temporal_leakage_audit.py` |
| **Manifest Validator** | Verify experiment manifests declare valid task ID, data version, risk links, approval tier, code hash, and resource budget | `scripts/validate_manifest.py` |

## Pattern Overview

**Overall:** Governance-First Contract-Driven Research Scaffold

**Key Characteristics:**
- **Immutable Deadline Registry**: Official deadlines fixed in `project_state/official_deadlines.json` with timezone, status tracking, and human approval gates
- **Multi-Schema Contracts**: JSON-Schema binding defines Patient Journey, Model API Request/Response, Experiment Manifests, Tasks, Risks, Decisions, Approvals, Evaluations
- **Temporal Integrity Enforcement**: Every event tracks `observed_at` and `available_at_time`; audit prevents using future information for past decisions
- **Approval Gates at Two Layers**: PreToolUse (approval_gate.py) blocks risky commands; PostToolUse verifies edits don't break contracts
- **Dependency-Free Validation**: `harness_lib.py` implements JSON-Schema subset without external libraries; all verification runs offline
- **Agent & Skill Registry**: 12 defined agents (code-writing, review-only) and 11 skills; `verify_harness.py` enforces naming, isolation, and permissions
- **Scoped Rules**: `.claude/rules/` define project-management, data, research, and innovation constraints loaded into agent context

## Layers

**Governance & Approval Layer:**
- Purpose: Enforce deadlines, approve costly/risky actions, maintain immutable decision records
- Location: `.claude/hooks/`, `project_state/official_deadlines.json`, `.claude/rules/`
- Contains: PreToolUse/PostToolUse/SessionStart hooks; human-approval records; deadline/risk/task/decision state
- Depends on: Nothing (bootstrap layer)
- Used by: All Claude Code sessions; orchestrator agent

**Harness Validation Layer:**
- Purpose: Verify project state integrity, schema compliance, manifest validity, temporal leakage
- Location: `scripts/verify_harness.py`, `scripts/harness_lib.py`, `scripts/temporal_leakage_audit.py`, `scripts/validate_manifest.py`
- Contains: Core validator; schema loader; state duplication checker; agent/skill registry verifier; deadline canonical registry check
- Depends on: JSON files in `project_state/`, `schemas/`, `experiments/manifests/`, `.claude/agents/`, `.claude/skills/`
- Used by: PostToolUse hook; manual verification (`make verify`); pre-execution gates

**Contract Model Layer:**
- Purpose: Define canonical data contracts for all state, fixtures, and experiment tracking
- Location: `schemas/*.json`
- Contains: 10+ JSON schemas with type, format, pattern, enum constraints; bound to `project_state/`, `tests/fixtures/`, `experiments/manifests/`
- Depends on: JSON-Schema draft 2020-12 specification
- Used by: Harness validator; application code (to be implemented)

**Project State Layer:**
- Purpose: Store immutable/semi-immutable project records
- Location: `project_state/`
- Contains: 
  - `official_deadlines.json` — immutable registry; blocks date changes without human approval
  - `tasks.json` — workstream tasks with owners, dependencies, priorities, status, evidence
  - `risks.json` — risk register with probability/impact matrix; linked to tasks
  - `decisions.json` — decision log entries with rationale and timestamp
  - `approvals.json` — human approval records for Tier 3/4 experiments, data transfers, publishing
  - `evaluations.json` — experiment evaluation records with metrics and conclusions
- Depends on: Nothing (data-only)
- Used by: `verify_harness.py`, `project_status.py`, `temporal_leakage_audit.py`, all downstream application code

**Fixtures & Test Data Layer:**
- Purpose: Provide canonical valid/invalid examples for schema and temporal audit testing
- Location: `tests/fixtures/`
- Contains:
  - `patient_journey/valid.json` — example Patient Journey with events, modalities, timestamps
  - `model_api/request.json` — example Model API request with evidence and decision_time
  - `model_api/response.json` — example Model API response with uncertainty and human_review flag
- Depends on: Nothing (data-only)
- Used by: `temporal_leakage_audit.py` (includes command `make leakage-fixture`), integration tests (to be written)

**Experiment Manifest Layer:**
- Purpose: Declare experiment parameters, resource budget, risks, and approval requirements before execution
- Location: `experiments/manifests/exp_NNNN.json`
- Contains: Schema version, experiment ID, task link, research question, hypothesis, model/data/training/graph/resources/comparisons/evaluation/stop-rules/artifacts/approvals/risks declarations
- Depends on: Project state (task_id, risk_id references); schema (experiment-manifest.schema.json)
- Used by: Training pipeline (not yet implemented); resource budgeting; Tier 3/4 approval gate

**Documentation & Rules Layer:**
- Purpose: Encode project governance, data rules, research gates, innovation constraints, and agent delegation patterns
- Location: `docs/`, `.claude/rules/`, `.claude/agents/`, `.claude/skills/`
- Contains: Project charter, decision log, milestone/task board, risk register, research/innovation/data contracts, agent prompts, skill workflows, scoped constraint rules
- Depends on: Nothing (documentation-only)
- Used by: Agent context loading; human review; decision justification

**Application Code Layers (Specified but Not Implemented):**
- **Research (`research/`):** Data interfaces, encoders, case-adaptive graph, model definitions, training loop, evaluation metrics
  - See: `docs/research/ARCHITECTURE_SPEC.md`, `docs/research/TRAINING_SPEC.md`
- **Innovation (`innovation/`):** Client UI/API, Front Door orchestration, safety policy layer, Model Gateway adapter, provider backends, audit store
  - See: `docs/innovation/PRODUCT_SPEC.md`, `docs/innovation/CLINICAL_WORKFLOW.md`
- **Shared (`shared/`):** Patient Journey snapshot logic, Patient Journey serialization, Contract models, Graph serialization, Versioned API models
  - See: `docs/shared/PATIENT_JOURNEY_SCHEMA.md`, `docs/shared/MODEL_API_CONTRACT.md`

## Data Flow

### Primary Request Path: Verification & Approval

1. **Session Start** (`hooks/session_context.py`) — Load next deadline and governance reminder from `project_state/official_deadlines.json`, print days remaining and any conditions
2. **User Action/Agent Tool Use** — Claude or agent requests `Bash`, `Write`, `Edit`, or `NotebookEdit`
3. **PreToolUse Approval Gate** (`hooks/approval_gate.py`) — Check command or file path against PROTECTED_EXACT, PROTECTED_PREFIXES, and COMMAND_GATES regexes; if match, ask human approval via JSON response
4. **Tool Execution** — If approved or unmatched, execute tool
5. **PostToolUse Validation** (`hooks/post_edit_checks.py`) — If Write/Edit/Notebook, call `verify_harness.py --changed <file>` to validate JSON syntax, Python compile, and schema compliance
6. **Feedback** — Report validation result or error; if critical failure, prevent save

### Harness Verification Flow

1. **Entry Point** (`verify_harness.py main()`) — Parse args (optional `--changed` file for incremental check)
2. **File Existence** — Check 23+ required files (documentation, agents, skills, scripts) exist
3. **JSON & State Integrity** (`check_json_and_state()`) — For each SCHEMA_BINDINGS entry:
   - Load instance and schema via `harness_lib.load_json()`
   - Call `validate_file()` — parse schema, recursively validate instance against JSON-Schema subset
   - Check task/risk/decision IDs are unique and dependencies resolve
   - Verify manifests reference valid task IDs and risk IDs
   - Check Tier 3+ experiments have approval records
4. **Deadline Registry** (`check_deadlines()`) — Verify immutable flag, timezone, and observed deadlines match CANONICAL_DEADLINES list
5. **Agents & Skills** (`check_agents_and_skills()`) — Parse `.claude/agents/*.md` and `.claude/skills/*/SKILL.md` frontmatter; verify:
   - Agent count matches AGENT_NAMES; frontmatter has description and body >= 500 chars
   - Code-writing agents use worktree isolation; read-only reviewers use plan mode, no Write/Edit/NotebookEdit
   - Skill count matches SKILL_NAMES; directory name matches frontmatter name
6. **Settings & Scripts** (`check_settings_and_scripts()`) — Verify hooks, worktree baseRef, permissions, and script executability; Python compile check
7. **Fixtures** (`check_fixtures()`) — Load patient journey, model request/response fixtures; validate event IDs unique, timestamps monotonic, and decision-time <= available-at-time
8. **Report** — If any errors, print count and list; exit 1. Otherwise print pass count and agent/skill roster; exit 0

### Temporal Leakage Audit Flow

1. **Entry Point** (`temporal_leakage_audit.py`) — Accept `target` (file or dir), optional `--as-of` decision time, optional `--input-event-id` list
2. **Journey Loading** — Discover all `*.json` files under target
3. **Schema Validation** — Call `validate_file(path, patient-journey.schema.json)` for each journey
4. **Event ID Uniqueness** — Collect all event_id values; error if duplicates
5. **Temporal Checks** (`audit_journey()`) — For each event:
   - Verify `available_at_time >= observed_at` (availability must not precede observation)
   - If AVAILABLE, require value or payload_ref
   - If `--as-of` cutoff specified, classify events as eligible (available <= cutoff) or future
   - If future event appears in `--input-event-id` list, error: future information used for decision
6. **Report** — Print or JSON output: journey_id, patient_id, split, eligible/future event counts, any errors
7. **Exit** — Return 0 if no errors, 1 otherwise

### Project Status Display Flow

1. **Entry Point** (`project_status.py main()`) — Load all state: deadlines, tasks, risks
2. **Next Deadline** — Find first incomplete (not SUBMITTED/COMPLETE) deadline with planning_deadline >= now
3. **Active Tasks** — Filter tasks where status not in {DONE, BACKLOG}; count P0/P1 subset
4. **Critical Risks** — Filter risks with status in {OPEN, MONITORING, REALIZED} and impact == CRITICAL
5. **Print Summary** —
   - Current time and timezone
   - Next deadline name, official date, time, condition, days remaining
   - Count of active and P0/P1 tasks; list each P0/P1 with priority, status, due date, owner
   - Count of open and critical risks; list critical risks with probability/impact and owner
   - If P0/P1 workload: identify busiest owner; warn if concentration > 40%
   - Overall project health: RED if critical risks or P0 active; else YELLOW

## Key Abstractions

**Immutable Deadline Contract:**
- Purpose: Ground truth for semester dates, deliverables, and planning deadlines
- Examples: `project_state/official_deadlines.json`
- Pattern: Fixed list of objects with canonical ISO-8601 dates, immutable flag, status enum (NEEDS_CONFIRMATION, IN_PROGRESS, NOT_STARTED, SUBMITTED, COMPLETE)

**Patient Journey:**
- Purpose: Represent a single patient's medical encounter with events at multiple observation and availability timestamps
- Examples: `tests/fixtures/patient_journey/valid.json`, `schemas/patient-journey.schema.json`
- Pattern: Object with journey_id, patient_id, encounter_id, split, events array; each event has event_id, event_type, modality, observed_at, available_at_time, status, payload_ref/value, authorization_tags

**Experiment Manifest:**
- Purpose: Declare a controlled run with model, data, training, graph, resource, and approval parameters before execution
- Examples: `experiments/manifests/exp_0000_harness_smoke.json`, `schemas/experiment-manifest.schema.json`
- Pattern: Object with experiment_id (exp_NNNN), task_id link, research_question/hypothesis/decision_informed, status enum, run_tier (0-4), code/model/data/training/graph/resources/comparisons/evaluation sections, approvals object with required bool and approval_ids array

**Task & Dependency DAG:**
- Purpose: Organize work across workstreams with priority, owner, status, and evidence tracking
- Examples: `project_state/tasks.json`, `schemas/task.schema.json`
- Pattern: Object with task_id (TASK-NNNN), title, owner, priority (P0-P4), status (READY, IN_PROGRESS, DONE, BACKLOG, BLOCKED), dependencies array (task_id list), due_date, definition_of_done array, evidence_required array, evidence array, blocker text, risk_level

**Risk Register:**
- Purpose: Track identified threats with probability, impact, owner, and linked tasks
- Examples: `project_state/risks.json`, `schemas/risk.schema.json`
- Pattern: Object with risk_id (RISK-NNNN), description, category, probability (LOW/MEDIUM/HIGH), impact (LOW/MEDIUM/HIGH/CRITICAL), owner, status (OPEN/MONITORING/MITIGATED/REALIZED/RESOLVED), linked_tasks array, mitigation_plan

**Human Approval Record:**
- Purpose: Log explicit human approvals for Tier 3/4 experiments, data transfers, or safety exceptions
- Examples: `project_state/approvals.json`, `schemas/human-approval.schema.json`
- Pattern: Object with approval_id, approved_by (name), approved_at (ISO-8601), reason, scope (experiment ID / task ID / data transfer), evidence_url/file path

## Entry Points

**Command-Line: `make verify`**
- Location: `Makefile` → `scripts/verify_harness.py`
- Triggers: Manual verification or PostToolUse hook after edit
- Responsibilities: Full harness integrity check; report pass/fail and error count

**Command-Line: `make smoke`**
- Location: `Makefile` → `scripts/run_smoke_test.sh`
- Triggers: Quick validation before committing changes
- Responsibilities: Run minimal test suite (currently defined in script)

**Command-Line: `make leakage-fixture`**
- Location: `Makefile` → `scripts/temporal_leakage_audit.py tests/fixtures/patient_journey/valid.json --as-of 2026-01-01T09:15:00Z`
- Triggers: Test temporal audit on fixture data
- Responsibilities: Validate fixture integrity and audit implementation

**Command-Line: `make status`**
- Location: `Makefile` → `scripts/project_status.py`
- Triggers: Display project health
- Responsibilities: Print active tasks, risks, deadlines, and workload summary

**Session Start Hook**
- Location: `.claude/hooks/session_context.py`
- Triggers: At session startup or resume
- Responsibilities: Inject deadline context reminder

**PreToolUse Hook**
- Location: `.claude/hooks/approval_gate.py`
- Triggers: Before any Bash/Write/Edit/NotebookEdit
- Responsibilities: Ask human approval for expensive, publishing, destructive, or data-transfer commands

**PostToolUse Hook**
- Location: `.claude/hooks/post_edit_checks.py`
- Triggers: After any Write/Edit/NotebookEdit completes
- Responsibilities: Validate changed file JSON/Python syntax and schema compliance

## Architectural Constraints

- **Offline-First Validation:** `harness_lib.py` implements JSON-Schema without external dependencies. All verification must run in < 60 seconds and complete offline.
- **Immutable Deadlines:** Dates in `project_state/official_deadlines.json` cannot be changed without explicit human approval and Decision Log entry.
- **Temporal Monotonicity:** Every event in a Patient Journey must satisfy `available_at_time >= observed_at`. Audit enforces this.
- **Schema Binding:** Every file in `SCHEMA_BINDINGS` dict (verify_harness.py line 83-92) is bound to exactly one schema. Validation fails if binding changes without human decision and harness update.
- **No Circular Dependencies:** Task dependency graph must be a DAG. verify_harness.py does not cycle-check; cycles must be prevented at task creation time.
- **Agent Isolation:** Code-writing agents (6 agents) must use worktree isolation; read-only reviewers (2 agents) must use plan mode.
- **Approval Tiers:** Tier 3+ experiments, multi-GPU runs, publishing, and sensitive-data operations require recorded human approvals before execution.
- **Deadline Timezone:** All official dates are in Asia/Bangkok timezone (UTC+7). Conversion to other zones must preserve Bangkok midnight as the boundary.

## Anti-Patterns

### Silent Schema Drift

**What happens:** Application code uses fields not in the schema, or validation is skipped for speed.

**Why it's wrong:** Contract integrity becomes unreliable. When a CI/CD system or reviewer tries to validate a record, it silently fails or passes incorrectly. Data consistency degrades over months.

**Do this instead:** Always update `schemas/*.json` when adding fields; run `make verify` before committing; use PostToolUse validation to catch errors immediately after edit.

### Bypassing Approval Gates

**What happens:** Agents delete secrets or push code without triggering PreToolUse gate by using workarounds (e.g., piping through xargs).

**Why it's wrong:** Approval gates exist to prevent data leaks and safety violations. Bypassing them undermines governance.

**Do this instead:** Follow the approval_gate.py regex patterns; if a risky action is legitimate, request human approval and record it in `project_state/approvals.json` with rationale.

### Inventing Results

**What happens:** Experiment manifest claims results without running the experiment, or manifest shows different hyperparameters than actual run.

**Why it's wrong:** Reproducibility fails; decisions made on false evidence; research integrity is compromised.

**Do this instead:** Create manifests *before* running experiments; record actual code_hash, seed, timestamps, and resource usage *during* execution; commit evidence artifacts and manifest together.

### Leaking Future Information

**What happens:** A model is trained on Patient Journeys where some events have `available_at_time` after the decision_time, then evaluated on decision-time cutoff.

**Why it's wrong:** Model evaluation is misleading; it appears better than real-time deployment would show. Clinical decisions made on this model are based on false confidence.

**Do this instead:** Run `temporal_leakage_audit.py` on all data splits with the decision time as `--as-of` cutoff; fix any future events; re-train and re-evaluate.

### Mixing Provider SDKs with Application Logic

**What happens:** Client code directly calls `openai.ChatCompletion.create()` or `anthropic.messages.create()` with patient data.

**Why it's wrong:** Swapping providers requires rewriting business logic; data governance is lost; external provider becomes a hard dependency.

**Do this instead:** Encapsulate all provider calls in adapter classes in `innovation/adapters/`. Expose only the versioned Model API Contract through the Model Gateway. Swapping providers requires only adapter changes.

## Error Handling

**Strategy:** Fail fast and loudly; stop work rather than silently proceeding with invalid state.

**Patterns:**
- `ValidationError` (harness_lib.py) — raised when JSON file missing, malformed, or schema validation fails; caught by verify_harness.py and reported with path and error location
- Schema validation errors — include JSON path (e.g., `.events[3].available_at_time`) and expected/actual values for debugging
- PostToolUse failures — prevent file save; print error details to stderr; user must fix and retry
- Manifest tier mismatch — verify_harness.py error if tier 3+ experiment lacks approval records or approval requirement doesn't match tier
- Circular task dependencies — must be caught at task creation time; verify_harness.py will not detect circular references

## Cross-Cutting Concerns

**Logging:** Session context hook prints deadline reminder and days remaining at startup. Project status script prints active tasks and risks. No persistent debug logs in codebase; run timestamps in JSON records and shell scripts.

**Validation:** Every JSON file validated against schema immediately after edit (PostToolUse). Harness verification (make verify) runs complete schema binding check, state uniqueness, deadline registry canonical check, and agent/skill registry audit.

**Approval:** PreToolUse hook blocks commands matching COMMAND_GATES regexes (expensive compute, publishing, destructive, patient data transfer). PostToolUse prevents file save if validation fails. Tier 3/4 experiments require approval_ids recorded in manifest before status moves to "approved"/"running"/"completed".

**Temporal Integrity:** Every event in Patient Journey carries `available_at_time` and `observed_at`. Audit ensures `available_at_time >= observed_at` and prevents using future information for past decisions. Experiment manifests declare data version and preprocessing version; temporal audit must pass before training.

---

*Architecture analysis: 2026-08-11*
