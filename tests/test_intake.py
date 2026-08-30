"""Intake, append and adaptive interview — acceptance criterion A1.

A1 requires intake to capture known, unknown, refused and unavailable **distinctly**.
The point is not tidiness: collapsing any of them into "absent" is the missing-modality
hallucination hazard, where a question nobody asked reads the same as one answered "no".
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import jsonschema
import json
import pytest
from pathlib import Path

from innovation.frontdoor import (
    IntakeError,
    IntakeItem,
    append_event,
    build_journey,
    plan_next_information,
)
from shared.snapshot import take_snapshot

ROOT = Path(__file__).resolve().parents[1]
JOURNEY_SCHEMA = json.loads((ROOT / "schemas/patient-journey.schema.json").read_text())
T0 = datetime(2026, 1, 1, 9, 0, tzinfo=timezone.utc)


def make_journey(items: list[IntakeItem]):
    return build_journey(
        journey_id="journey-test-0001",
        patient_id="patient-test-0001",
        encounter_id="encounter-test-0001",
        encounter_start=T0,
        items=items,
    )


# ------------------------------------------------------------- four distinct states


def test_the_four_intake_states_are_recorded_distinctly():
    journey = make_journey([
        IntakeItem("CHIEF_COMPLAINT", "KNOWN", value="chest discomfort"),
        IntakeItem("VITAL", "NOT_AVAILABLE"),
        IntakeItem("ALLERGY", "UNKNOWN"),
        IntakeItem("MEDICATION", "REFUSED"),
    ])
    by_code = {e.code: e.status for e in journey.events}

    assert by_code == {
        "CHIEF_COMPLAINT": "AVAILABLE",
        "VITAL": "NOT_AVAILABLE_YET",
        "ALLERGY": "MEASURED_UNKNOWN",
        "MEDICATION": "WITHHELD",
    }
    # Four inputs, four distinguishable outputs — none collapsed into a shared "absent".
    assert len(set(by_code.values())) == 4


def test_an_intake_journey_validates_against_the_machine_schema():
    journey = make_journey([
        IntakeItem("CHIEF_COMPLAINT", "KNOWN", value="chest discomfort"),
        IntakeItem("VITAL", "UNKNOWN"),
    ])
    jsonschema.validate(json.loads(journey.model_dump_json(exclude_unset=True)), JOURNEY_SCHEMA)


def test_a_recorded_gap_is_evidence_with_its_own_availability_time():
    """"We asked at 09:00 and they did not know" is information available from 09:00."""
    journey = make_journey([IntakeItem("ALLERGY", "UNKNOWN")])
    gap = journey.events[0]

    assert gap.event_type == "MISSINGNESS"
    assert gap.available_at_time == T0
    assert take_snapshot(journey, T0).evidence_ids == ("ev-001",)
    # And before it was asked, it is not there.
    assert take_snapshot(journey, T0 - timedelta(minutes=1)).evidence_ids == ()


def test_known_without_a_value_is_refused():
    with pytest.raises(IntakeError, match="marked KNOWN but carries no value"):
        make_journey([IntakeItem("CHIEF_COMPLAINT", "KNOWN", value=None)])


def test_a_gap_carrying_a_value_is_refused():
    """A gap must not smuggle a value in under a missing status."""
    with pytest.raises(IntakeError, match="must not smuggle"):
        make_journey([IntakeItem("VITAL", "REFUSED", value={"heart_rate": 104})])


def test_unknown_information_type_is_refused():
    with pytest.raises(IntakeError, match="unknown information_type"):
        make_journey([IntakeItem("ASTROLOGY", "KNOWN", value="scorpio")])


def test_a_pending_result_is_withheld_from_earlier_snapshots():
    """A lab that will only result at 10:00 is not evidence at 09:00, even once recorded."""
    later = T0 + timedelta(hours=1)
    journey = make_journey([
        IntakeItem("CHIEF_COMPLAINT", "KNOWN", value="chest discomfort"),
        IntakeItem("LAB", "KNOWN", value={"code": "troponin"}, observed_at=T0, available_at_time=later),
    ])
    assert take_snapshot(journey, T0).evidence_ids == ("ev-001",)
    assert take_snapshot(journey, later).evidence_ids == ("ev-001", "ev-002")


# ------------------------------------------------------------------------- append


def test_append_is_immutable_and_returns_a_new_journey():
    journey = make_journey([IntakeItem("CHIEF_COMPLAINT", "KNOWN", value="chest discomfort")])
    updated = append_event(journey, IntakeItem("VITAL", "KNOWN", value={"hr": 104}), default_time=T0)

    assert len(journey.events) == 1  # original untouched
    assert len(updated.events) == 2
    assert updated is not journey
    assert updated.events[0] == journey.events[0]


def test_appending_never_rewrites_an_earlier_event():
    """Correcting an earlier entry means adding a new event, not editing the old one."""
    journey = make_journey([IntakeItem("VITAL", "UNKNOWN")])
    updated = append_event(journey, IntakeItem("VITAL", "KNOWN", value={"hr": 104}), default_time=T0)

    assert updated.events[0].status == "MEASURED_UNKNOWN"  # the original answer survives
    assert updated.events[1].status == "AVAILABLE"


# -------------------------------------------------------------- adaptive interview


def test_required_evidence_ranks_first_and_is_marked_as_blocking():
    journey = make_journey([IntakeItem("CHIEF_COMPLAINT", "KNOWN", value="chest discomfort")])
    plan = plan_next_information(take_snapshot(journey, T0))

    assert plan.candidates[0].information_type == "VITAL"
    assert plan.candidates[0].reason_code == "REQUIRED_FOR_CONCLUSION"
    assert plan.candidates[0].urgency_prerequisite is True


def test_a_declined_item_is_never_re_queued_as_a_question():
    """`PRODUCT_SPEC.md` §Adaptive interview: "It must not coerce answers"."""
    journey = make_journey([
        IntakeItem("CHIEF_COMPLAINT", "KNOWN", value="chest discomfort"),
        IntakeItem("VITAL", "KNOWN", value={"hr": 104}),
        IntakeItem("MEDICATION", "REFUSED"),
    ])
    plan = plan_next_information(
        take_snapshot(journey, T0), provider_suggestions=("MEDICATION", "ECG")
    )

    asked = [c.information_type for c in plan.candidates]
    assert "MEDICATION" not in asked  # even though the provider suggested it
    assert [d.information_type for d in plan.declined] == ["MEDICATION"]
    assert "ECG" in asked


def test_known_information_is_not_asked_for_again():
    journey = make_journey([
        IntakeItem("CHIEF_COMPLAINT", "KNOWN", value="chest discomfort"),
        IntakeItem("VITAL", "KNOWN", value={"hr": 104}),
    ])
    plan = plan_next_information(
        take_snapshot(journey, T0), provider_suggestions=("VITAL", "ECG")
    )

    assert [c.information_type for c in plan.candidates] == ["ECG"]
    assert set(plan.already_known) == {"CHIEF_COMPLAINT", "VITAL"}


def test_a_provider_suggestion_cannot_displace_a_required_item():
    journey = make_journey([IntakeItem("CHIEF_COMPLAINT", "KNOWN", value="chest discomfort")])
    plan = plan_next_information(take_snapshot(journey, T0), provider_suggestions=("ECG",))

    assert plan.candidates[0].information_type == "VITAL"
    assert plan.candidates[0].rank == 1
    assert plan.candidates[-1].information_type == "ECG"


def test_every_candidate_carries_a_reason_tied_to_a_decision():
    journey = make_journey([IntakeItem("CHIEF_COMPLAINT", "KNOWN", value="chest discomfort")])
    plan = plan_next_information(take_snapshot(journey, T0), provider_suggestions=("ECG",))

    for candidate in plan.candidates:
        assert candidate.reason_code and candidate.reason
        assert candidate.rank >= 1
