# Technology Stack

**Analysis Date:** 2026-08-11

## Current State

This repository is a **research governance and specification scaffold**. It contains:
- Specification documents for a medical multimodal model and clinical decision-support system
- JSON schemas for data validation and contracts
- Python harness tools for governance and project management (stdlib-only)
- Bash automation scripts
- Makefiles for common tasks

No model training, API servers, or application code is currently implemented.

## Languages

**Implemented:**
- **Python** 3.10+ - `scripts/` and `.claude/hooks/` harness tools only; **standard library only, no external packages**
- **Bash** - Bootstrap and automation scripts (`scripts/bootstrap.sh`, `scripts/run_smoke_test.sh`)
- **JSON** - Schema definitions and machine-readable state (`schemas/`, `project_state/`)

**Planned but not implemented:**
- Python (for Medical-DAG training, model implementations)
- TypeScript/JavaScript (for Clinical Front Door web UI, specified in `docs/innovation/`)

## Runtime

**Environment:**
- Python 3.10 or newer (verified in `README.md` prerequisites)
- Bash shell (POSIX-compliant for portability)
- Git for version control

**Package Manager:**
- None currently in use. No `package.json`, `requirements.txt`, `pyproject.toml`, `setup.py`, or `Cargo.toml` exist.
- Lockfile: Not applicable (stdlib-only)

## Frameworks

**Testing:**
- None yet implemented. Harness uses custom JSON-Schema validator in `scripts/harness_lib.py` (stdlib `json`, `re`, `pathlib`)

**Build/Dev:**
- `Makefile` - Simple task automation; `make verify`, `make smoke`, `make status`, `make leakage-fixture`
- No build system (Python is interpreted; JSON is static)

## Core Libraries (Implemented)

All are Python standard library modules used in `scripts/` and `.claude/hooks/`:

- `json` - Load/validate JSON schemas and state files
- `pathlib` - Cross-platform file/path operations
- `argparse` - CLI argument parsing (`verify_harness.py`, `new_experiment.py`, `temporal_leakage_audit.py`, `validate_manifest.py`)
- `subprocess` - Execute shell commands (git integration in hooks)
- `datetime`, `zoneinfo` - Timezone-aware timestamp validation (`iso_datetime()` in `harness_lib.py`)
- `re` - Pattern matching for YAML frontmatter parsing and regex validation
- `py_compile` - Syntax check Python files in `verify_harness.py`
- `os`, `sys` - Process utilities
- `hashlib` - Git hash verification in `new_experiment.py`
- `collections` - Counter/defaultdict for project status and data audit
- `typing` - Type hints (Python 3.10+ annotations)

**No external dependencies.** The harness is intentionally dependency-free for reproducibility and deployment simplicity.

## Configuration

**Environment:**
- No `.env` files or environment variable requirements for harness operation
- Timezone configured as `Asia/Bangkok` in `project_state/official_deadlines.json` (immutable per constitution)
- Python version specified in README as 3.10+; no `.python-version` or `pyproject.toml` lock exists

**Build:**
- `Makefile` - No build compilation; tasks invoke Python scripts and bash directly
- JSON Schema definitions: `schemas/` directory validates all machine-readable state

**Harness Configuration:**
- `.claude/settings.json` - Claude Code session configuration (worktree, hooks, permissions)
- `CLAUDE.md` - Project constitution (max 220 lines per harness requirement)
- `.claude/hooks/` - PreToolUse and PostToolUse gates for approval and validation

## Platform Requirements

**Development:**
- Git (for repository operations and `git log` verification)
- Python 3.10+ (for harness validation and project management scripts)
- Bash shell (POSIX-compliant)
- Text editor or Claude Code IDE
- No GPU, database server, or external services required for harness operation

**Validation/Governance:**
- `python3 scripts/verify_harness.py` - Comprehensive harness validation (agents, skills, state, deadlines, JSON contracts)
- `bash scripts/bootstrap.sh` - Idempotent setup; creates directories, makes scripts executable, runs verification

**Production (Planned, Not Implemented):**
- CUDA/cuDNN (for PyTorch model training; specified in `docs/research/TRAINING_SPEC.md`, not installed)
- Cloud compute (Tier 3/4 training requires explicit human approval per `docs/research/TRAINING_SPEC.md`)
- Database (Audit/decision storage; gateway and API backend unspecified)
- API framework (FastAPI or similar; specified in `docs/innovation/PRODUCT_SPEC.md`, not implemented)

## Module Structure

**Key Files:**

- `scripts/harness_lib.py` - Governance utilities: JSON-Schema subset validator, YAML frontmatter parser, ISO datetime handler; 156 lines, stdlib-only
- `scripts/verify_harness.py` - Full harness validation: file existence, JSON/Python syntax, state consistency, deadline immutability, agent/skill definitions, schema binding, fixture validation
- `scripts/new_experiment.py` - Generate experiment manifests with git hash, timestamp, tier-specific approval requirements
- `scripts/project_status.py` - Print machine-readable project state summary: deadlines, task/risk/decision counts, burndown
- `scripts/temporal_leakage_audit.py` - Audit Patient Journey fixtures for schema, patient split, and `available_at_time` integrity
- `.claude/hooks/approval_gate.py` - PreToolUse gate for costly/external/destructive actions; blocks manifest overwrites, approval gate violations, protected file changes

## No External Integrations in Code

This codebase does **not** currently integrate with:
- External APIs (no SDK imports)
- Databases (no ORM, no connection pools)
- Authentication providers
- Model inference services
- Monitoring/logging platforms
- CI/CD services

All such integrations are **specified** in documentation for future implementation. See `INTEGRATIONS.md` for planned systems.

---

*Stack analysis: 2026-08-11*
