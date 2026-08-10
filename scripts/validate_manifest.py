#!/usr/bin/env python3
"""Validate one or more experiment manifests against the repository contract."""

from __future__ import annotations

import argparse
from pathlib import Path

from harness_lib import ValidationError, load_json, validate_file


ROOT = Path(__file__).resolve().parents[1]
SCHEMA = ROOT / "schemas" / "experiment-manifest.schema.json"


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
    if manifest["resources"]["estimated_minutes"] > 60 and tier < 3:
        errors.append(f"{path}: runs over 60 minutes cannot be Tier {tier}")
    if manifest["data"]["license_status"] == "unresolved" and manifest["status"] in {"approved", "running", "completed"}:
        errors.append(f"{path}: unresolved data license blocks execution/completion")
    if manifest["status"] in {"completed", "failed", "stopped", "invalidated"} and not manifest.get("result"):
        errors.append(f"{path}: terminal status requires result metadata")
    if manifest["status"] in {"planned", "approved", "running"} and manifest.get("result") is not None:
        errors.append(f"{path}: non-terminal status must not contain a final result")
    return errors


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


if __name__ == "__main__":
    raise SystemExit(main())

