#!/usr/bin/env python3
"""Print a deterministic summary from the machine-readable project state."""

from __future__ import annotations

from collections import Counter
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from harness_lib import iso_datetime, load_json


ROOT = Path(__file__).resolve().parents[1]


def main() -> int:
    deadlines = load_json(ROOT / "project_state/official_deadlines.json")
    tasks = load_json(ROOT / "project_state/tasks.json")["tasks"]
    risks = load_json(ROOT / "project_state/risks.json")["risks"]
    timezone = ZoneInfo(deadlines["timezone"])
    now = datetime.now(timezone)
    upcoming = [item for item in deadlines["deadlines"] if item["status"] not in {"SUBMITTED", "COMPLETE"} and iso_datetime(item["planning_deadline"]).astimezone(timezone) >= now]
    next_item = min(upcoming, key=lambda item: iso_datetime(item["planning_deadline"])) if upcoming else None
    active = [item for item in tasks if item["status"] not in {"DONE", "BACKLOG"}]
    p01 = [item for item in active if item["priority"] in {"P0", "P1"}]
    owner_counts = Counter(item["owner"] for item in p01)
    open_risks = [item for item in risks if item["status"] in {"OPEN", "MONITORING", "REALIZED"}]
    critical_risks = [item for item in open_risks if item["impact"] == "CRITICAL"]

    print(f"AS OF: {now.isoformat(timespec='minutes')} ({deadlines['timezone']})")
    if next_item:
        at = iso_datetime(next_item["planning_deadline"]).astimezone(timezone)
        print(f"NEXT OFFICIAL DEADLINE: {next_item['name']} - {next_item['official_date_start']}")
        if next_item["official_date_end"] != next_item["official_date_start"]:
            print(f"OFFICIAL WINDOW END: {next_item['official_date_end']}")
        if next_item["official_time"]:
            print(f"OFFICIAL TIME: {next_item['official_time']}")
        print(f"CONSERVATIVE PLANNING TIME REMAINING: {(at - now).total_seconds() / 86400:.1f} days")
        if next_item["condition"]:
            print(f"CONDITION: {next_item['condition']}")
    else:
        print("NEXT OFFICIAL DEADLINE: none incomplete in registry")
    print(f"ACTIVE TASKS: {len(active)}; P0/P1: {len(p01)}")
    for item in sorted(p01, key=lambda row: (row["priority"], row["due_date"], row["task_id"])):
        print(f"- {item['task_id']} {item['priority']} {item['status']} due {item['due_date']} owner={item['owner']}: {item['title']}")
    print(f"OPEN RISKS: {len(open_risks)}; CRITICAL IMPACT: {len(critical_risks)}")
    for item in critical_risks:
        print(f"- {item['risk_id']} {item['probability']}/{item['impact']} owner={item['owner']}: {item['description']}")
    if p01:
        busiest_owner, count = owner_counts.most_common(1)[0]
        share = count / len(p01)
        print(f"P0/P1 WORKLOAD: {busiest_owner} owns {count}/{len(p01)} ({share:.0%})")
        if share > 0.40:
            print("WORKLOAD WARNING: exceeds the 40% concentration threshold")
    print("PROJECT HEALTH: RED" if critical_risks or any(item["priority"] == "P0" for item in active) else "PROJECT HEALTH: YELLOW")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

