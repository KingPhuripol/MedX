"""List repository files (tracked + untracked-not-ignored) without network access."""

from __future__ import annotations

import subprocess
from pathlib import Path

SKIP_DIRS = {".git", ".venv", "node_modules", ".next", "__pycache__", "test-results", "playwright-report"}


def repo_files(root: Path) -> list[Path]:
    try:
        out = subprocess.run(
            ["git", "ls-files", "--cached", "--others", "--exclude-standard", "-z"],
            cwd=root,
            capture_output=True,
            check=True,
            timeout=30,
        ).stdout
        files = [root / p for p in out.decode().split("\0") if p]
    except (OSError, subprocess.SubprocessError):
        files = [p for p in root.rglob("*") if p.is_file()]
    return [p for p in files if p.is_file() and not (set(p.relative_to(root).parts) & SKIP_DIRS)]


def read_text(path: Path) -> str | None:
    try:
        return path.read_text(encoding="utf-8")
    except (UnicodeDecodeError, OSError):
        return None
