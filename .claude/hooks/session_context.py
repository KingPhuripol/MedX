#!/usr/bin/env python3
"""Inject the next immutable deadline and active governance reminder at session start."""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo


def parse_deadline(item: dict, timezone: ZoneInfo) -> datetime:
    value = item["planning_deadline"]
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone)
    return parsed.astimezone(timezone)


def main() -> int:
    root = Path(__file__).resolve().parents[2]
    registry = root / "project_state" / "official_deadlines.json"
    if not registry.exists():
        print("Senior Project reminder: official deadline registry is missing; run Harness verification.")
        return 0

    try:
        payload = json.loads(registry.read_text(encoding="utf-8"))
        timezone = ZoneInfo(payload["timezone"])
        now = datetime.now(timezone)
        upcoming = [
            (parse_deadline(item, timezone), item)
            for item in payload["deadlines"]
            if parse_deadline(item, timezone) >= now
            and item.get("status") not in {"SUBMITTED", "COMPLETE"}
        ]
    except Exception as exc:  # session must still start; verifier reports details
        print(f"Senior Project reminder: deadline registry is invalid ({exc}); run Harness verification.")
        return 0

    if not upcoming:
        print("Senior Project reminder: no incomplete Semester 1 deadline remains in the registry.")
        return 0

    deadline, item = min(upcoming, key=lambda pair: pair[0])
    remaining = deadline - now
    days = remaining.total_seconds() / 86400
    condition = f" Condition: {item['condition']}." if item.get("condition") else ""
    print(
        "Senior Project session context: "
        f"next official deadline is {item['name']} at {deadline.isoformat()} "
        f"({days:.1f} days remaining).{condition} Official dates are immutable. "
        "Read source-of-truth contracts, use patient-level/available_at_time rules, "
        "and request human approval for expensive, publishing, destructive, sensitive-data, or safety actions."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
