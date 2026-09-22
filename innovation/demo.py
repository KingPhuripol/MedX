"""Offline synthetic demonstration of the Clinical Front Door.

Innovation release stage 1: "Contract and synthetic CLI fixture". One evolving encounter,
mock provider, no network, no patient data. Run it with:

    python3 -m innovation.demo

It walks the workflow in `docs/innovation/CLINICAL_WORKFLOW.md` and shows the properties
the prototype exists to demonstrate:

  * the four intake states stay distinguishable — a refusal is not an absence;
  * evidence that did not exist at the decision time cannot reach the model;
  * a declined question is not put back in the queue;
  * nothing takes effect until a human confirms it.
"""

from __future__ import annotations

from datetime import datetime, timezone

from innovation.frontdoor import FrontDoorService, HumanReviewRequired, IntakeItem
from innovation.gateway import ModelGateway
from innovation.gateway.providers import MockProvider
from shared.snapshot import take_snapshot

BANNER = "RESEARCH PROTOTYPE - HUMAN REVIEW REQUIRED"
RULE = "─" * 78

T = lambda h, m: datetime(2026, 1, 1, h, m, tzinfo=timezone.utc)  # noqa: E731
JOURNEY_ID = "journey-demo-0001"


def _heading(text: str) -> None:
    print(f"\n{RULE}\n{text}\n{RULE}")


def main() -> int:
    print(f"\n{BANNER}")
    print("Synthetic data, mock provider, no network. Not a clinical model prediction.")

    service = FrontDoorService(ModelGateway(MockProvider()))

    # ---- 1. Intake ---------------------------------------------------------------
    _heading("1. Intake at 09:00 — four kinds of answer, four distinct records")
    journey = service.create_encounter(
        journey_id=JOURNEY_ID,
        patient_id="patient-demo-0001",
        encounter_id="encounter-demo-0001",
        encounter_start=T(9, 0),
        items=[
            IntakeItem("CHIEF_COMPLAINT", "KNOWN", value="Chest discomfort since this morning."),
            IntakeItem("VITAL", "NOT_AVAILABLE"),   # nurse has not taken them yet
            IntakeItem("ALLERGY", "UNKNOWN"),       # asked; patient does not know
            IntakeItem("MEDICATION", "REFUSED"),    # asked; patient declined to say
        ],
    )
    for event in journey.events:
        print(f"   {event.code:18} {event.status:20} ({event.event_type})")
    print("   None of these is 'blank'. A refusal, an unknown and a pending result are")
    print("   three different facts, and the record keeps them apart.")

    # ---- 2. Adaptive interview ----------------------------------------------------
    _heading("2. What to ask next at 09:00")
    plan = service.next_information(JOURNEY_ID, T(9, 0), provider_suggestions=("MEDICATION", "ECG"))
    for c in plan.candidates:
        blocking = "  [waiting is unsafe]" if c.urgency_prerequisite else ""
        print(f"   {c.rank}. {c.information_type:16} {c.reason_code}{blocking}")
    for d in plan.declined:
        print(f"   -- {d.information_type:16} DECLINED — not re-asked, even though the model suggested it")

    # ---- 3. First decision --------------------------------------------------------
    _heading("3. Decision at 09:05 — vitals still pending")
    first = service.assess(journey, T(9, 5), missing_information=("VITAL", "ECG"))
    print(f"   urgency   : {first.response.urgency.level}   status: {first.response.status}")
    print(f"   red flags : {[(f.code, f.state) for f in first.response.red_flags]}")
    print("   The deterministic screen ran before the model and escalated on its own.")

    # ---- 4. Evidence arrives ------------------------------------------------------
    _heading("4. Vitals result at 09:12; a diagnosis is recorded at 13:00")
    service.append_evidence(
        JOURNEY_ID,
        IntakeItem("VITAL", "KNOWN", value={"code": "heart_rate", "value": 104, "unit": "beats/min"},
                   observed_at=T(9, 10), available_at_time=T(9, 12)),
    )
    journey = service.append_evidence(
        JOURNEY_ID,
        IntakeItem("DIAGNOSIS", "KNOWN", value={"category": "synthetic-final-label"},
                   observed_at=T(12, 0), available_at_time=T(13, 0)),
    )
    snapshot = take_snapshot(journey, T(9, 15))
    print(f"   available at 09:15 : {', '.join(snapshot.evidence_ids)}")
    print(f"   withheld           : {', '.join(f'{r.event_id} ({r.reason})' for r in snapshot.rejected)}")
    print("   The 13:00 diagnosis is in the same file and is still withheld. A decision")
    print("   at 09:15 cannot see it, which is what stops the label leaking into the input.")

    second = service.assess(journey, T(9, 15), missing_information=("ECG",))
    print(f"   urgency   : {second.response.urgency.level}   status: {second.response.status}")

    # ---- 5. Human confirmation ----------------------------------------------------
    _heading("5. Human confirmation gate")
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
        reason_code="ADDITIONAL_INFORMATION_AVAILABLE",
        note="Agrees with escalation; ordering ECG before disposition.",
    )
    reviewed = service.get(second.recommendation_id)
    print(f"   after clinician review  : effective={reviewed.effective}, "
          f"action={reviewed.latest_review.action}, reason={reviewed.latest_review.reason_code}")
    print(f"   original urgency kept   : {reviewed.response.urgency.level} "
          "(the response is never edited by a review)")

    # ---- 6. History and audit -----------------------------------------------------
    _heading("6. History and audit trail")
    for rec in service.history(JOURNEY_ID):
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
