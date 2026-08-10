#!/usr/bin/env python3
"""Audit Patient Journey files for schema, patient split, and available_at_time integrity."""

from __future__ import annotations

import argparse
import json
from collections import defaultdict
from pathlib import Path

from harness_lib import ValidationError, iso_datetime, load_json, validate_file


ROOT = Path(__file__).resolve().parents[1]
SCHEMA = ROOT / "schemas" / "patient-journey.schema.json"


def journey_files(target: Path) -> list[Path]:
    if target.is_file():
        return [target]
    if target.is_dir():
        return sorted(path for path in target.rglob("*.json") if path.is_file())
    raise ValidationError(f"target does not exist: {target}")


def audit_journey(path: Path, as_of: str | None, input_ids: set[str]) -> tuple[list[str], dict]:
    errors = validate_file(path, SCHEMA)
    payload = load_json(path)
    ids = [event["event_id"] for event in payload["events"]]
    if len(ids) != len(set(ids)):
        errors.append(f"{path}: event IDs are not unique")
    if input_ids - set(ids):
        errors.append(f"{path}: requested input IDs not present: {sorted(input_ids - set(ids))}")

    eligible: list[str] = []
    future: list[str] = []
    cutoff = iso_datetime(as_of) if as_of else None
    for event in payload["events"]:
        observed = iso_datetime(event["observed_at"])
        available = iso_datetime(event["available_at_time"])
        if available < observed:
            errors.append(f"{path}: {event['event_id']} available_at_time precedes observed_at")
        if event["status"] == "AVAILABLE" and "value" not in event and not event.get("payload_ref"):
            errors.append(f"{path}: {event['event_id']} is AVAILABLE without payload/value")
        if cutoff:
            if available <= cutoff:
                eligible.append(event["event_id"])
            else:
                future.append(event["event_id"])
                if event["event_id"] in input_ids:
                    errors.append(f"{path}: future event {event['event_id']} was selected as model input")
    summary = {
        "journey_id": payload["journey_id"],
        "patient_id": payload["patient_id"],
        "split": payload["split"],
        "as_of": as_of,
        "eligible_event_ids": eligible,
        "future_event_ids": future,
    }
    return errors, summary


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("target", type=Path)
    parser.add_argument("--as-of", help="ISO-8601 decision time used to classify eligible events")
    parser.add_argument("--input-event-id", action="append", default=[], help="Event ID asserted to be actual model input; repeatable")
    parser.add_argument("--json", action="store_true", dest="as_json")
    args = parser.parse_args()
    target = args.target if args.target.is_absolute() else ROOT / args.target
    try:
        files = journey_files(target)
    except ValidationError as exc:
        print(exc)
        return 1
    if not files:
        print(f"No Patient Journey JSON files found under {target}")
        return 1

    all_errors: list[str] = []
    summaries: list[dict] = []
    patient_splits: dict[str, set[str]] = defaultdict(set)
    for path in files:
        try:
            errors, summary = audit_journey(path, args.as_of, set(args.input_event_id))
        except (ValidationError, KeyError, TypeError) as exc:
            errors, summary = [str(exc)], {"file": str(path)}
        all_errors.extend(errors)
        summaries.append(summary)
        if "patient_id" in summary:
            patient_splits[summary["patient_id"]].add(summary["split"])

    for patient_id, splits in patient_splits.items():
        if len(splits) > 1:
            all_errors.append(f"patient {patient_id} appears in multiple splits: {sorted(splits)}")

    result = {
        "verdict": "FAIL" if all_errors else "PASS",
        "files_audited": len(files),
        "journeys": summaries,
        "errors": all_errors,
    }
    if args.as_json:
        print(json.dumps(result, indent=2, ensure_ascii=False))
    else:
        print(f"TEMPORAL LEAKAGE AUDIT {result['verdict']} ({len(files)} file(s))")
        for summary in summaries:
            if "journey_id" in summary:
                print(f"- {summary['journey_id']}: eligible={summary['eligible_event_ids']} future={summary['future_event_ids']}")
        for error in all_errors:
            print(f"- ERROR: {error}")
    return 1 if all_errors else 0


if __name__ == "__main__":
    raise SystemExit(main())

