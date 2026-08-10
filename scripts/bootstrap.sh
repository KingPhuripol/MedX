#!/usr/bin/env bash
set -euo pipefail

PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$PROJECT_DIR"

if ! git rev-parse --is-inside-work-tree >/dev/null 2>&1; then
  if ! git init -b main; then
    git init
  fi
fi

mkdir -p \
  artifacts/experiments \
  checkpoints \
  data/raw \
  data/interim \
  data/processed \
  logs

chmod +x scripts/*.py scripts/*.sh .claude/hooks/*.py

python3 scripts/verify_harness.py

echo "BOOTSTRAP COMPLETE"
echo "Next: review Group Application status, advisor identity, team ownership, then run 'claude'."
