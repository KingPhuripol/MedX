#!/usr/bin/env python3
"""Claude Code PreToolUse gate for costly, external, destructive, and governed actions."""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path


PROTECTED_EXACT = {
    "CLAUDE.md",
    ".claude/settings.json",
    ".claude/hooks/approval_gate.py",
    "docs/PROPOSAL.md",
    "docs/DECISIONS.md",
}
PROTECTED_PREFIXES = ("schemas/", "backend/app/triage/rules/")

COMMAND_GATES: tuple[tuple[str, re.Pattern[str]], ...] = (
    (
        "expensive or distributed compute",
        re.compile(
            r"(?:^|[;&|]\s*)(?:torchrun|deepspeed|sbatch|srun|qsub|bsub)\b"
            r"|\baccelerate\s+launch\b|\bray\s+job\s+submit\b"
            r"|--(?:num[_-]?(?:gpus|nodes)|nproc[_-]?per[_-]?node)\s*[= ]\s*(?:[2-9]|[1-9]\d+)",
            re.IGNORECASE,
        ),
    ),
    (
        "publishing, uploading, deploying, or external state change",
        re.compile(
            r"\bgit\s+push\b|\b(?:hf|huggingface-cli)\s+upload\b|\btwine\s+upload\b"
            r"|\bnpm\s+publish\b|\bdocker\s+push\b|\bgh\s+release\s+create\b"
            r"|\bvercel\s+(?:deploy|--prod)\b|\bkubectl\s+(?:apply|create|replace)\b"
            r"|\b(?:aws\s+s3|gsutil)\s+(?:cp|sync|rsync)\b",
            re.IGNORECASE,
        ),
    ),
    (
        "destructive or difficult-to-recover operation",
        re.compile(
            r"(?:^|[;&|]\s*)(?:rm|rmdir|shred|unlink)\b|\bfind\b[^\n]*\s-delete\b"
            r"|\bgit\s+(?:reset\s+--hard|clean\s+-|branch\s+-D)\b"
            r"|\b(?:drop|truncate)\s+(?:table|database)\b"
            r"|\b(?:aws\s+s3|gsutil)\s+rm\b|\bkubectl\s+delete\b"
            r"|\bdocker\s+system\s+prune\b|\bdd\b[^\n]*\bof=",
            re.IGNORECASE,
        ),
    ),
    (
        "possible patient/research data transfer to an external endpoint",
        re.compile(
            r"\b(?:curl|wget|scp|rsync)\b[^\n]*(?:data/|patient|journey|medical|dataset|checkpoint)",
            re.IGNORECASE,
        ),
    ),
)


def ask(reason: str) -> None:
    print(
        json.dumps(
            {
                "hookSpecificOutput": {
                    "hookEventName": "PreToolUse",
                    "permissionDecision": "ask",
                    "permissionDecisionReason": (
                        f"Senior Project human approval gate: {reason}. Review the exact scope, "
                        "budget/data classification, rollback, and durable approval record before allowing."
                    ),
                }
            }
        )
    )


def relative_path(raw: str, cwd: str) -> str:
    path = Path(raw)
    if not path.is_absolute():
        path = Path(cwd) / path
    try:
        return path.resolve(strict=False).relative_to(Path(cwd).resolve()).as_posix()
    except ValueError:
        return path.resolve(strict=False).as_posix()


def main() -> int:
    try:
        payload = json.load(sys.stdin)
    except (json.JSONDecodeError, TypeError):
        return 0

    tool = str(payload.get("tool_name", ""))
    tool_input = payload.get("tool_input") or {}

    if tool == "Bash":
        command = str(tool_input.get("command", ""))
        for label, pattern in COMMAND_GATES:
            if pattern.search(command):
                ask(label)
                return 0
        return 0

    raw_path = str(
        tool_input.get("file_path")
        or tool_input.get("notebook_path")
        or tool_input.get("path")
        or ""
    )
    if not raw_path:
        return 0
    rel = relative_path(raw_path, str(payload.get("cwd") or Path.cwd()))
    if rel in PROTECTED_EXACT or rel.startswith(PROTECTED_PREFIXES):
        ask(f"editing protected governance/contract file `{rel}`")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

