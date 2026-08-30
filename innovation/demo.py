"""Offline synthetic demonstration of the Clinical Front Door.

Innovation release stage 1: "Contract and synthetic CLI fixture". Runs the whole flow
with the mock provider and a synthetic journey — no network, no external provider, no
patient data. Run it with:

    python3 -m innovation.demo

It shows the two things the prototype exists to demonstrate: that evidence which did not
exist at the decision time cannot reach the model, and that nothing takes effect without
a human confirming it.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

from innovation.frontdoor import FrontDoorService, HumanReviewRequired
from innovation.gateway import ModelGateway
from innovation.gateway.providers import MockProvider
from shared.contracts import PatientJourney
from shared.snapshot import take_snapshot

ROOT = Path(__file__).resolve().parents[1]
FIXTURE = ROOT / "tests/fixtures/patient_journey/valid.json"

BANNER = "RESEARCH PROTOTYPE - HUMAN REVIEW REQUIRED"
RULE = "─" * 78


def _heading(text: str) -> None:
    print(f"\n{RULE}\n{text}\n{RULE}")


def main() -> int:
    print(f"\n{BANNER}")
    print("Synthetic data, mock provider, no network. Not a clinical model prediction.")

    journey = PatientJourney.model_validate(json.loads(FIXTURE.read_text(encoding="utf-8")))
    service = FrontDoorService(ModelGateway(MockProvider()))

    # ---- Step 1: an early decision, before the labs have resulted -----------------
    early = datetime(2026, 1, 1, 9, 5, tzinfo=timezone.utc)
    _heading(f"1. Decision at {early:%H:%M} UTC — only the complaint has arrived")
    snapshot = take_snapshot(journey, early)
    print(f"   available : {', '.join(snapshot.evidence_ids)}")
    print(f"   withheld  : {', '.join(f'{r.event_id} ({r.reason})' for r in snapshot.rejected)}")

    first = service.assess(journey, early, missing_information=("VITAL", "ECG"))
    print(f"   urgency   : {first.response.urgency.level}   status: {first.response.status}")
    print(f"   red flags : {[(f.code, f.state) for f in first.response.red_flags]}")

    # ---- Step 2: later, with vitals available ------------------------------------
    later = datetime(2026, 1, 1, 9, 15, tzinfo=timezone.utc)
    _heading(f"2. Re-assessed at {later:%H:%M} UTC — vitals have now resulted")
    snapshot2 = take_snapshot(journey, later)
    print(f"   available : {', '.join(snapshot2.evidence_ids)}")
    print(f"   withheld  : {', '.join(f'{r.event_id} ({r.reason})' for r in snapshot2.rejected)}")
    print("   note      : ev-003 is the final diagnosis. It sits in the same file and is")
    print("               still withheld — a decision at 09:15 cannot use a 13:00 label.")

    second = service.assess(journey, later, missing_information=("ECG",))
    print(f"   urgency   : {second.response.urgency.level}   status: {second.response.status}")
    print(f"   next info : {[n.information_type for n in second.response.next_information]}")

    # ---- Step 3: nothing takes effect without a human ----------------------------
    _heading("3. Human confirmation gate")
    print(f"   effective before review : {second.effective}")
    try:
        service.act_on(second.recommendation_id)
        print("   act_on                  : UNEXPECTEDLY ALLOWED")
        return 1
    except HumanReviewRequired as exc:
        print(f"   act_on                  : refused — {exc}")

    service.review(
        second.recommendation_id,
        reviewer_id="clinician-01",
        action="MODIFY",
        note="Agrees with escalation; ordering ECG before disposition.",
    )
    reviewed = service.get(second.recommendation_id)
    print(f"   after clinician review  : effective={reviewed.effective}, "
          f"action={reviewed.latest_review.action}")
    print(f"   original urgency kept   : {reviewed.response.urgency.level} "
          "(the response is never edited by a review)")

    # ---- Step 4: history and audit ------------------------------------------------
    _heading("4. History and audit trail")
    for rec in service.history(journey.journey_id):
        print(f"   {rec.decision_time:%H:%M} UTC  {rec.response.urgency.level:<24} "
              f"reviews={len(rec.reviews)}  snapshot={rec.snapshot_checksum[:12]}")
    print("   Earlier recommendations are preserved, not overwritten.\n")

    for record in service.gateway.audit.records():
        print(f"   audit {record.request_id}  status={record.status:<10} "
              f"rules={list(record.applied_safety_rules)} reviewer={record.reviewer_id}")

    print(f"\n{BANNER}\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
