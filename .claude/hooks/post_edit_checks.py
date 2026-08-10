#!/usr/bin/env python3
"""Run fast structural validation after Claude Code edits a file."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path


def main() -> int:
    try:
        payload = json.load(sys.stdin)
    except (json.JSONDecodeError, TypeError):
        return 0

    tool_input = payload.get("tool_input") or {}
    changed = (
        tool_input.get("file_path")
        or tool_input.get("notebook_path")
        or tool_input.get("path")
    )
    if not changed:
        return 0

    project = Path(payload.get("cwd") or Path.cwd()).resolve()
    verifier = project / "scripts" / "verify_harness.py"
    if not verifier.exists():
        return 0

    try:
        result = subprocess.run(
            [sys.executable, str(verifier), "--changed", str(changed)],
            cwd=project,
            text=True,
            capture_output=True,
            timeout=55,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        print(f"Post-edit validation could not run: {exc}", file=sys.stderr)
        return 1

    if result.returncode != 0:
        details = (result.stdout + "\n" + result.stderr).strip()
        print(f"Post-edit validation failed for {changed}:\n{details}", file=sys.stderr)
        return 2
    if result.stdout.strip():
        print(result.stdout.strip())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

