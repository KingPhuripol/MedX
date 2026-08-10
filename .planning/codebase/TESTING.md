# Testing Patterns

**Analysis Date:** 2026-08-11

## CRITICAL FINDING: No Traditional Test Framework

**This repository has no pytest, unittest, or any test discovery framework.**

The only existing verification is a shell script-based integration test that validates the research harness itself — manifests, contracts, schemas, and agent configurations. Individual Python functions in `scripts/` and `.claude/hooks/` are **not unit-tested**.

## Test Framework

**Runner:**
- `bash scripts/run_smoke_test.sh` (invoked via `make smoke`)
- Not pytest, not unittest, not any Python testing framework
- Integration-level contract validation only

**What is tested:**
- JSON schema compliance (test fixtures and project state files)
- Temporal integrity of patient journey data
- Experiment manifest validity
- Python syntax (via `py_compile`)
- Project harness structure (required files, agent/skill configs, deadlines)

**Run Commands:**
```bash
make smoke                                  # Run smoke test
make verify                                 # Run verify_harness.py alone
make leakage-fixture                        # Run temporal_leakage_audit.py on fixture
python3 scripts/run_smoke_test.sh           # Direct invocation
```

## Test File Organization

**Location:**
- No test files in traditional sense
- Test data (fixtures) only: `tests/fixtures/`

**Fixtures:**
- `tests/fixtures/patient_journey/valid.json` — Patient journey schema and temporal integrity test
- `tests/fixtures/model_api/request.json` — Model API request contract example
- `tests/fixtures/model_api/response.json` — Model API response contract example

**Test execution chain (from `scripts/run_smoke_test.sh`):**
```bash
python3 scripts/verify_harness.py
python3 scripts/validate_manifest.py experiments/manifests/exp_0000_harness_smoke.json
python3 scripts/temporal_leakage_audit.py tests/fixtures/patient_journey/valid.json \
  --as-of 2026-01-01T09:15:00Z \
  --input-event-id ev-001 \
  --input-event-id ev-002
```

## De-Facto Test Suite: Harness Verification

**Primary test mechanism:** `scripts/verify_harness.py`

This script validates the research scaffold structure, not application business logic:

**Checks performed (from `verify_harness.py:135-251`):**

1. **File existence** — All required source documents, schemas, and scripts present
2. **JSON schema compliance** — State files and fixtures validate against `schemas/*.schema.json`
3. **State consistency**:
   - Task IDs unique; dependencies resolved
   - Risk IDs unique; linked tasks exist
   - Decision IDs unique
   - DONE tasks must have evidence
4. **Deadlines registry** — Immutable, correct timezone, matches canonical dates
5. **Agent & skill configuration**:
   - All 12 agents present (defined in `AGENT_NAMES`)
   - All 11 skills present (defined in `SKILL_NAMES`)
   - Code-writing agents have worktree isolation
   - Read-only reviewers use plan mode, have no write tools
6. **Settings & scripts**:
   - `.claude/settings.json` has required hooks
   - `.claude/settings.json` protects source files
   - All Python scripts compile without syntax errors
   - All scripts are executable
7. **Test fixtures**:
   - Patient journey event IDs unique
   - Event availability >= observation time
   - No AVAILABLE events without value/payload_ref
   - API request/response IDs match
   - Human review required in response

**Example check function (from `verify_harness.py:135-142`):**
```python
def check_files(checks: Checks) -> None:
    required = ["README.md", "CLAUDE.md", ".claude/settings.json", "Makefile"] + SOURCE_DOCS + SCRIPT_FILES
    for path in required:
        checks.require((ROOT / path).is_file(), f"missing required file: {path}")
    claude = ROOT / "CLAUDE.md"
    if claude.exists():
        checks.require(len(claude.read_text(encoding="utf-8").splitlines()) <= 220, "CLAUDE.md exceeds 220 lines; move detail to scoped docs/rules")
```

## Validation Pattern

**Error accumulation model:** `Checks` class collects all errors before failing

Example from `verify_harness.py:120-132`:
```python
class Checks:
    def __init__(self) -> None:
        self.errors: list[str] = []
        self.count = 0

    def require(self, condition: bool, message: str) -> None:
        self.count += 1
        if not condition:
            self.errors.append(message)

    def extend(self, errors: list[str]) -> None:
        self.count += 1
        self.errors.extend(errors)
```

All errors reported at the end; does not stop at first failure.

## Manifest Validation

**Tool:** `scripts/validate_manifest.py`

Performs two layers of validation:

1. **JSON schema** — Against `schemas/experiment-manifest.schema.json`
2. **Semantic rules** — Business logic from `semantic_errors()` function

Example checks from `validate_manifest.py:16-35`:
```python
def semantic_errors(path: Path) -> list[str]:
    manifest = load_json(path)
    errors: list[str] = []
    tier = manifest["run_tier"]
    required = manifest["approvals"]["required"]
    if required != (tier >= 3):
        errors.append(f"{path}: approvals.required must be {tier >= 3} for Tier {tier}")
    if tier >= 3 and manifest["status"] in {"approved", "running", "completed"} and not manifest["approvals"]["approval_ids"]:
        errors.append(f"{path}: Tier {tier} status {manifest['status']} requires an approval ID")
    if manifest["resources"]["gpu_count"] > 1 and tier < 3:
        errors.append(f"{path}: multi-GPU work cannot be Tier {tier}")
    if manifest["resources"]["estimated_minutes"] > 60 and tier < 2:
        errors.append(f"{path}: runs over 60 minutes cannot be Tier {tier}")
    ...
    return errors
```

## Temporal Leakage Audit

**Tool:** `scripts/temporal_leakage_audit.py`

Validates patient journey data for temporal integrity — core research gate to prevent label leakage.

**Checks (from `temporal_leakage_audit.py:26-60`):**
- Event IDs unique
- `available_at_time` >= `observed_at` (data must not exist before it was observed)
- AVAILABLE events have value or payload_ref
- If `--as-of` specified, events with `available_at_time > as_of` are flagged if used as model input
- Patients appear in exactly one split (across all journey files)

**Example:**
```python
def audit_journey(path: Path, as_of: str | None, input_ids: set[str]) -> tuple[list[str], dict]:
    errors = validate_file(path, SCHEMA)
    ...
    for event in payload["events"]:
        observed = iso_datetime(event["observed_at"])
        available = iso_datetime(event["available_at_time"])
        if available < observed:
            errors.append(f"{path}: {event['event_id']} available_at_time precedes observed_at")
        if cutoff:
            if available <= cutoff:
                eligible.append(event["event_id"])
            else:
                future.append(event["event_id"])
                if event["event_id"] in input_ids:
                    errors.append(f"{path}: future event {event['event_id']} was selected as model input")
    ...
    return errors, summary
```

## Schema Validation Framework

**Location:** `scripts/harness_lib.py:55-126`

Handwritten JSON Schema validator (no `jsonschema` dependency).

**Supports:**
- Type checking (`object`, `array`, `string`, `integer`, `number`, `boolean`, `null`)
- Format validation (`date`, `date-time`)
- Constraints (`minLength`, `minimum`, `maximum`, `minItems`, `uniqueItems`)
- Enum and const
- Required properties
- Pattern matching (regex)
- Nested validation via recursion

**Example from harness_lib.py:55-72:**
```python
def validate(instance: Any, schema: dict[str, Any], location: str = "$") -> list[str]:
    """Validate the JSON-Schema subset used by this repository."""
    errors: list[str] = []
    if not schema:
        return errors

    if "const" in schema and instance != schema["const"]:
        errors.append(f"{location}: expected constant {schema['const']!r}, got {instance!r}")
    if "enum" in schema and instance not in schema["enum"]:
        errors.append(f"{location}: {instance!r} is not one of {schema['enum']!r}")
    ...
```

## Python Compilation Check

**In verify_harness.py:244-251:**
```python
for relative in SCRIPT_FILES:
    path = ROOT / relative
    if path.suffix == ".py" and path.exists():
        try:
            py_compile.compile(str(path), doraise=True)
        except py_compile.PyCompileError as exc:
            checks.errors.append(f"Python compile failed for {relative}: {exc.msg}")
    if path.exists():
        checks.require(os.access(path, os.X_OK), f"script is not executable: {relative}")
```

All Python files in SCRIPT_FILES are syntax-checked. Not a true unit test, but catches basic errors.

## Test Coverage Gaps

**What is NOT tested:**
- Individual function logic in `scripts/`
  - `git_state()` in `new_experiment.py` — not tested
  - `slug_value()` validation — not tested
  - Manifest creation logic — not tested
  - JSON validation implementation — not tested (beyond schema application)
  - Temporal audit logic — not tested beyond the fixture

- Individual function logic in `.claude/hooks/`
  - `approval_gate.py` regex patterns — not tested
  - `session_context.py` deadline parsing — not tested
  - `post_edit_checks.py` subprocess handling — not tested

- Negative cases
  - Invalid manifests only if they fail schema/semantic checks; no fuzzing
  - Error handling paths mostly untested

- Integration scenarios
  - Hook execution in Claude Code context not tested
  - Agent/skill routing behavior not tested

## When to Expand Testing

If new functions are added to `scripts/` or `hooks/`:

1. **Minimal:** Add fixture to `tests/fixtures/` and integrate into `verify_harness.py` checks
2. **Recommended:** Create unit tests using stdlib `unittest` module (no external deps, follows project convention)
3. **Critical paths:** Temporal audit and manifest validation should have exhaustive negative cases (currently missing)

---

*Testing analysis: 2026-08-11*
