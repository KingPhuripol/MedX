"""Front Door workflow tests — `docs/innovation/CLINICAL_WORKFLOW.md`.

The properties under test are the ones the safety spec turns on: a decision may only see
evidence that existed at its decision time, and nothing takes effect without a human.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

import pytest

from innovation.frontdoor import FrontDoorService, HumanReviewRequired
from innovation.gateway import ModelGateway
from innovation.gateway.providers import MockProvider
from shared.contracts import PatientJourney

ROOT = Path(__file__).resolve().parents[1]

EARLY = datetime(2026, 1, 1, 9, 5, tzinfo=timezone.utc)
LATER = datetime(2026, 1, 1, 9, 15, tzinfo=timezone.utc)
AFTER_LABEL = datetime(2026, 1, 1, 14, 0, tzinfo=timezone.utc)


@pytest.fixture
def journey() -> PatientJourney:
    return PatientJourney.model_validate(
        json.loads((ROOT / "tests/fixtures/patient_journey/valid.json").read_text())
    )


@pytest.fixture
def service() -> FrontDoorService:
    return FrontDoorService(ModelGateway(MockProvider()))


# ----------------------------------------------------------------- temporal rule


def test_assessment_sees_only_evidence_available_at_its_decision_time(service, journey):
    early = service.assess(journey, EARLY)
    later = service.assess(journey, LATER)

    early_ids = set(early.response.urgency.evidence_ids)
    later_ids = set(later.response.urgency.evidence_ids)

    assert early_ids == {"ev-001"}
    assert later_ids == {"ev-001", "ev-002"}


def test_retrospective_label_never_reaches_a_live_decision(service, journey):
    """ev-003 is the final diagnosis, available at 13:00. A 09:15 decision must not use
    it, and the service must not hand it to the gateway in the first place."""
    recommendation = service.assess(journey, LATER)
    assert "ev-003" not in recommendation.response.urgency.evidence_ids

    audit = service.gateway.audit.find(recommendation.response.request_id)[0]
    assert "ev-003" not in audit.evidence_ids


def test_label_evidence_is_excluded_even_once_it_is_available(service, journey):
    """A label is an outcome, not an input. Being old enough does not make it a feature —
    this is the "do not use final diagnosis to predict earlier decisions" rule."""
    recommendation = service.assess(journey, AFTER_LABEL)
    audit = service.gateway.audit.find(recommendation.response.request_id)[0]
    assert "ev-003" not in audit.evidence_ids


# ------------------------------------------------------------- human confirmation


def test_recommendation_is_not_effective_until_a_human_acts(service, journey):
    recommendation = service.assess(journey, LATER)
    assert recommendation.effective is False
    with pytest.raises(HumanReviewRequired):
        service.act_on(recommendation.recommendation_id)


@pytest.mark.parametrize("action,expected", [("CONFIRM", True), ("MODIFY", True),
                                             ("REJECT", False), ("ESCALATE", False),
                                             ("REQUEST_INFORMATION", False)])
def test_only_confirm_and_modify_make_a_recommendation_effective(service, journey, action, expected):
    """Rejecting a recommendation is a decision not to act on it, not an approval."""
    recommendation = service.assess(journey, LATER)
    reason = "CLINICAL_JUDGEMENT_DIFFERS" if action in {"MODIFY", "REJECT"} else None
    service.review(
        recommendation.recommendation_id, reviewer_id="clinician-01", action=action,
        reason_code=reason,
    )
    assert service.get(recommendation.recommendation_id).effective is expected


def test_review_requires_a_named_reviewer(service, journey):
    recommendation = service.assess(journey, LATER)
    with pytest.raises(ValueError):
        service.review(recommendation.recommendation_id, reviewer_id="   ", action="CONFIRM")


def test_review_refuses_an_action_the_response_does_not_permit(service, journey):
    recommendation = service.assess(journey, LATER)
    with pytest.raises(ValueError):
        service.review(
            recommendation.recommendation_id, reviewer_id="clinician-01", action="APPROVE_AND_DISCHARGE"
        )


def test_override_preserves_the_original_output(service, journey):
    """`SAFETY_SPEC.md` requires the original output to stay immutable after an override."""
    recommendation = service.assess(journey, LATER)
    original_urgency = recommendation.response.urgency.level
    original_status = recommendation.response.status

    service.review(
        recommendation.recommendation_id,
        reviewer_id="clinician-01",
        action="MODIFY",
        reason_code="URGENCY_TOO_HIGH",
        note="Downgrading after bedside assessment.",
    )
    after = service.get(recommendation.recommendation_id)

    assert after.response.urgency.level == original_urgency
    assert after.response.status == original_status
    assert after.latest_review.note == "Downgrading after bedside assessment."


def test_review_is_mirrored_into_the_audit_trail(service, journey):
    """A review appends a record; it does not edit the call that preceded it.

    The mirror used to overwrite the gateway's own record in place. That defeated the
    frozen dataclass, was never written back to either durable sink — so a stored row
    said reviewer_id: null however many times it was reviewed — and was the wrong shape
    for an append-only log besides.
    """
    recommendation = service.assess(journey, LATER)
    service.review(
        recommendation.recommendation_id, reviewer_id="clinician-07", action="MODIFY",
        reason_code="ADDITIONAL_INFORMATION_AVAILABLE",
    )

    trail = service.gateway.audit.find(recommendation.response.request_id)
    assert len(trail) == 2

    call, review = trail
    # The gateway's own record still says what it said at the time: nobody had reviewed it.
    assert call.reviewer_id is None
    assert call.review_action is None

    assert review.reviewer_id == "clinician-07"
    assert review.review_action == "MODIFY"
    assert review.overridden_from == recommendation.response.urgency.level
    assert review.request_id == call.request_id


def test_a_second_review_appends_rather_than_replacing(service, journey):
    """Changing one's mind is a new record. The first decision stays visible."""
    recommendation = service.assess(journey, LATER)
    service.review(recommendation.recommendation_id, reviewer_id="nurse-01", action="CONFIRM")
    service.review(
        recommendation.recommendation_id, reviewer_id="clinician-07", action="REJECT",
        reason_code="CLINICAL_JUDGEMENT_DIFFERS",
    )

    trail = service.gateway.audit.find(recommendation.response.request_id)
    assert [r.reviewer_id for r in trail] == [None, "nurse-01", "clinician-07"]
    assert [r.review_action for r in trail] == [None, "CONFIRM", "REJECT"]


# ------------------------------------------------------------------------ history


def test_history_is_preserved_rather_than_overwritten(service, journey):
    first = service.assess(journey, EARLY)
    second = service.assess(journey, LATER)

    history = service.history(journey.journey_id)
    assert [r.recommendation_id for r in history] == [
        first.recommendation_id,
        second.recommendation_id,
    ]
    assert history[0].snapshot_checksum != history[1].snapshot_checksum


def test_same_journey_and_decision_time_is_the_same_question(service, journey):
    """Deterministic request IDs make gateway idempotency meaningful at this layer."""
    a = service.assess(journey, LATER)
    b = service.assess(journey, LATER)
    assert a.response.request_id == b.response.request_id
    assert len(service.gateway.audit.find(a.response.request_id)) == 1


def test_later_rejection_revokes_legacy_confirmation(service, journey):
    recommendation = service.assess(journey, LATER)
    service.review(recommendation.recommendation_id, reviewer_id='clinician-01', action='CONFIRM')
    assert recommendation.effective
    service.review(recommendation.recommendation_id, reviewer_id='clinician-01', action='REJECT',
                   reason_code='EVIDENCE_INCORRECT')
    assert not recommendation.effective
    with pytest.raises(HumanReviewRequired):
        service.act_on(recommendation.recommendation_id)
