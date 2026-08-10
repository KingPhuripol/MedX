# Coding Conventions

**Analysis Date:** 2026-08-11

## Naming Patterns

**Files:**
- Python executables: `snake_case.py` (e.g., `verify_harness.py`, `temporal_leakage_audit.py`)
- Hook files: `snake_case.py` in `.claude/hooks/` (e.g., `approval_gate.py`, `post_edit_checks.py`)
- Shell scripts: `snake_case.sh` (e.g., `run_smoke_test.sh`, `bootstrap.sh`)

**Functions:**
- `snake_case` (e.g., `semantic_errors()`, `journey_files()`, `git_state()`, `next_id()`)
- Private functions prefixed with `_` (e.g., `_matches_type()`, `_format_ok()`)

**Variables:**
- `snake_case` for local and module-level variables
- Descriptive names: `errors`, `checks`, `payload`, `manifest`, `events`
- Constants are `UPPER_CASE` (e.g., `ROOT`, `SCHEMA`, `SOURCE_DOCS`, `AGENT_NAMES`)

**Types & Classes:**
- Classes in `PascalCase` (e.g., `ValidationError`, `Checks`)
- Custom exceptions inherit from stdlib exceptions: `class ValidationError(ValueError)`

## Code Style

**Formatting:**
- No configuration file (no `.flake8`, `ruff.toml`, `mypy.ini`, `eslint.config.js`, `.prettierrc`)
- De facto style observed across `scripts/` and `.claude/hooks/`:
  - 4-space indentation (implicit Python standard)
  - Line length appears unrestricted (longest lines ~100 chars, no visible enforcement)
  - f-strings for formatting (all examples use f-strings, not `.format()` or `%`)

**Linting:**
- None configured; `.gitignore` pre-emptively ignores `.mypy_cache/`, `.ruff_cache/`, `.pytest_cache/`
- No continuous validation of style — only structural validation via `verify_harness.py`

## Import Organization

**Order:**
1. Shebang: `#!/usr/bin/env python3`
2. Module docstring: `"""Purpose of script."""`
3. `from __future__ import annotations` (always first import)
4. Standard library imports (organized alphabetically)
5. Custom imports from this project (e.g., `from harness_lib import ...`)

**Example from `verify_harness.py`:**
```python
#!/usr/bin/env python3
"""Validate the complete Claude Code Harness using only the Python standard library."""

from __future__ import annotations

import argparse
import json
import os
import py_compile
import sys
from pathlib import Path

from harness_lib import ValidationError, iso_datetime, load_json, parse_frontmatter, validate_file
```

**Path Aliases:**
- None used; `Path.resolve()` and relative path construction are standard
- Example: `ROOT = Path(__file__).resolve().parents[1]` (used in all scripts)

## Error Handling

**Patterns:**
- Custom `ValidationError(ValueError)` for contract/schema failures (`scripts/harness_lib.py:13`)
- Standard library exceptions caught explicitly: `FileNotFoundError`, `json.JSONDecodeError`, `KeyError`, `TypeError`, `OSError`
- Exit codes follow Unix convention:
  - Return `0` on success
  - Return `1` on validation/execution failure
  - Return `2` on catastrophic hook failure (e.g., `post_edit_checks.py:48`)

**Example from `validate_manifest.py:38-56`:**
```python
def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("manifests", nargs="+", type=Path)
    args = parser.parse_args()
    failed = False
    for path in args.manifests:
        absolute = path if path.is_absolute() else ROOT / path
        try:
            errors = validate_file(absolute, SCHEMA) + semantic_errors(absolute)
        except (ValidationError, KeyError, TypeError) as exc:
            errors = [str(exc)]
        if errors:
            failed = True
            print(f"INVALID {absolute.relative_to(ROOT) if absolute.is_relative_to(ROOT) else absolute}")
            for error in errors:
                print(f"- {error}")
        else:
            print(f"VALID {absolute.relative_to(ROOT) if absolute.is_relative_to(ROOT) else absolute}")
    return 1 if failed else 0
```

**SystemExit Usage:**
- Common pattern: `raise SystemExit(message)` for early termination with status 1 (e.g., `new_experiment.py:103-105`)
- Alternative: `return 0` or `return 1` from `main()`, followed by `if __name__ == "__main__": raise SystemExit(main())`

## Logging

**Framework:**
- None; uses only `print()` to stdout and `print(..., file=sys.stderr)` to stderr
- No structured logging or external log handlers

**Patterns:**
- Informational status: `print(f"VERB {path.relative_to(ROOT)}")` (e.g., `VALID ...`, `INVALID ...`)
- Error reporting: Print error count summary first, then list each error
- Example from `verify_harness.py:306-310`:
  ```python
  if checks.errors:
      print(f"HARNESS VERIFICATION FAILED ({len(checks.errors)} errors / {checks.count} checks)")
      for error in checks.errors:
          print(f"- {error}")
  ```

## Comments

**When to Comment:**
- Rarely used; code is generally self-documenting via clear naming
- Comments appear in approval_gate.py for complex regex patterns and in harness_lib.py for algorithm intent

**Docstrings:**
- Module-level docstrings always present (one-liner describing the script's purpose)
- Function docstrings rare; reliance on type hints and clear naming instead
- Example module docstring from `verify_harness.py:1-2`:
  ```python
  """Validate the complete Claude Code Harness using only the Python standard library."""
  ```

## Type Hints

**Usage:**
- Pervasive throughout all scripts
- Uses modern syntax: `dict[str, Any]`, `list[str]`, `tuple[...]`, `set[str]`
- Union types use `|` operator: `str | None`
- Example from `harness_lib.py:17-23`:
  ```python
  def load_json(path: Path) -> Any:
      try:
          return json.loads(path.read_text(encoding="utf-8"))
      except FileNotFoundError as exc:
          raise ValidationError(f"missing JSON file: {path}") from exc
      except json.JSONDecodeError as exc:
          raise ValidationError(f"invalid JSON in {path}: {exc}") from exc
  ```

## Function Design

**Size:**
- Functions are small and focused (most 10-30 lines)
- Larger orchestrators like `check_json_and_state()` ~35 lines; decomposed into named sub-checks

**Parameters:**
- Explicit over implicit; minimal use of mutable defaults
- Use type hints for all parameters and return types

**Return Values:**
- Functions in the harness layer return structured data (lists of errors, tuples of (data, metadata))
- CLI scripts return int (exit code)
- Example from `temporal_leakage_audit.py:26-60`:
  ```python
  def audit_journey(path: Path, as_of: str | None, input_ids: set[str]) -> tuple[list[str], dict]:
      errors = validate_file(path, SCHEMA)
      ...
      return errors, summary
  ```

## Module Design

**Exports:**
- `harness_lib.py` exports public functions and `ValidationError` exception
- Each script is a standalone CLI; `if __name__ == "__main__": raise SystemExit(main())` pattern used consistently

**Module Constants:**
- Defined at module level in ALL_CAPS
- Examples: `ROOT`, `SCHEMA`, `SOURCE_DOCS`, `AGENT_NAMES`, `PROTECTED_EXACT`, `PROTECTED_PREFIXES`

**JSON & Path Handling:**
- Pathlib `Path` is universal; no `os.path`
- Method chaining: `Path(__file__).resolve().parents[1]`
- Path operations: `.glob()`, `.rglob()`, `.is_file()`, `.exists()`, `.relative_to()`, `.as_posix()`
- JSON loaded via `harness_lib.load_json()` which handles errors and raises `ValidationError`

**Validation Pattern:**
- Schema validation centralized in `harness_lib.validate()` and `validate_file()`
- Semantic validation in specialized functions (e.g., `semantic_errors()` in `validate_manifest.py`)
- All validation returns `list[str]` of error messages; empty list = valid

---

*Convention analysis: 2026-08-11*
