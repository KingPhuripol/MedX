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

echo "SMOKE TEST PASSED: Harness, manifest, contracts, and temporal fixture are valid."

