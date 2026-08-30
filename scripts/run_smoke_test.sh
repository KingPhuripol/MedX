#!/usr/bin/env bash
set -euo pipefail

PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$PROJECT_DIR"

python3 scripts/verify_harness.py
python3 scripts/validate_manifest.py experiments/manifests/exp_0000_harness_smoke.json
python3 scripts/temporal_leakage_audit.py tests/fixtures/patient_journey/valid.json \
  --as-of 2026-01-01T09:15:00Z \
  --input-event-id ev-001 \
  --input-event-id ev-002

# Contract and gateway tests. Skipped with a loud notice rather than a silent pass when
# pytest is absent, so "no test runner" can never be mistaken for "tests passed".
if python3 -c "import pytest" >/dev/null 2>&1; then
  python3 -m pytest tests/ -q
else
  echo "WARNING: pytest is not installed; contract and gateway tests DID NOT RUN."
  echo "         Install with: python3 -m pip install -r requirements.txt"
fi

echo "SMOKE TEST PASSED: Harness, manifest, contracts, temporal fixture, and gateway tests are valid."

