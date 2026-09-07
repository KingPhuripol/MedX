"""Front Door API tests.

The product is API-first, so the properties proven at the service layer must hold when
reached over HTTP. A client that only ever speaks to this API must not be able to reach a
state the safety spec forbids.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from innovation.api.app import create_app
from innovation.config import BANNER

ROOT = Path(__file__).resolve().parents[1]
JOURNEY = json.loads((ROOT / "tests/fixtures/patient_journey/valid.json").read_text())
JOURNEY_ID = JOURNEY["journey_id"]
LATER = "2026-01-01T09:15:00Z"


@pytest.fixture
def client() -> TestClient:
    c = TestClient(create_app())
    assert c.put(f"/journeys/{JOURNEY_ID}", json=JOURNEY).status_code == 201
    return c


def _assess(client: TestClient, missing=("ECG",)) -> dict:
    response = client.post(
        f"/journeys/{JOURNEY_ID}/assessments",
        json={"decision_time": LATER, "missing_information": list(missing)},
    )
    assert response.status_code == 201, response.text
    return response.json()


def test_health_declares_the_prototype_banner_and_versions(client):
    body = client.get("/health").json()
    assert body["banner"] == "RESEARCH PROTOTYPE - HUMAN REVIEW REQUIRED"
    assert body["contract_version"] == "1.0.0"
    assert body["policy_version"] == "safety-policy-v1"


def test_non_synthetic_journey_is_refused(client):
    """The prototype accepts synthetic journeys only; anything else needs an approval
    path that does not exist yet (DEC-0006)."""
    payload = dict(JOURNEY, journey_id="journey-real-0001",
                   data_classification="IDENTIFIABLE_OR_LINKABLE")
    response = client.put("/journeys/journey-real-0001", json=payload)
    assert response.status_code == 403
    assert "SYNTHETIC" in response.json()["error"]["message"]


def test_mismatched_journey_id_is_refused(client):
    assert client.put("/journeys/journey-other", json=JOURNEY).status_code == 400


def test_assessment_carries_the_banner_and_requires_review(client):
    body = _assess(client)
    assert body["banner"] == "RESEARCH PROTOTYPE - HUMAN REVIEW REQUIRED"
    assert body["effective"] is False
    assert body["response"]["human_review"]["required"] is True
    assert body["reviews"] == []


def test_future_evidence_never_appears_in_an_assessment(client):
    body = _assess(client)
    assert "ev-003" not in json.dumps(body["response"])


def test_effective_is_refused_until_a_human_confirms(client):
    body = _assess(client)
    rec_id = body["recommendation_id"]

    blocked = client.get(f"/recommendations/{rec_id}/effective")
    assert blocked.status_code == 409

    confirmed = client.post(
        f"/recommendations/{rec_id}/review",
        json={"reviewer_id": "clinician-01", "action": "CONFIRM"},
    )
    assert confirmed.status_code == 200
    assert confirmed.json()["effective"] is True

    allowed = client.get(f"/recommendations/{rec_id}/effective")
    assert allowed.status_code == 200
    assert allowed.json()["confirmed_by"] == "clinician-01"


def test_rejecting_does_not_make_a_recommendation_effective(client):
    rec_id = _assess(client)["recommendation_id"]
    client.post(
        f"/recommendations/{rec_id}/review",
        json={"reviewer_id": "clinician-01", "action": "REJECT",
              "reason_code": "CLINICAL_JUDGEMENT_DIFFERS"},
    )
    assert client.get(f"/recommendations/{rec_id}/effective").status_code == 409


def test_an_action_outside_the_contract_is_refused(client):
    rec_id = _assess(client)["recommendation_id"]
    response = client.post(
        f"/recommendations/{rec_id}/review",
        json={"reviewer_id": "clinician-01", "action": "DISCHARGE_PATIENT"},
    )
    assert response.status_code == 422  # rejected by the schema, before any handler runs


def test_anonymous_review_is_refused(client):
    rec_id = _assess(client)["recommendation_id"]
    response = client.post(
        f"/recommendations/{rec_id}/review",
        json={"reviewer_id": "", "action": "CONFIRM"},
    )
    assert response.status_code == 422


def test_override_preserves_the_original_response(client):
    body = _assess(client)
    rec_id = body["recommendation_id"]
    original = body["response"]["urgency"]["level"]

    after = client.post(
        f"/recommendations/{rec_id}/review",
        json={"reviewer_id": "clinician-02", "action": "MODIFY",
              "reason_code": "URGENCY_TOO_HIGH", "note": "bedside review"},
    ).json()

    assert after["response"]["urgency"]["level"] == original
    assert after["reviews"][0]["note"] == "bedside review"


def test_history_preserves_earlier_assessments(client):
    client.post(
        f"/journeys/{JOURNEY_ID}/assessments",
        json={"decision_time": "2026-01-01T09:05:00Z", "missing_information": []},
    )
    _assess(client)

    history = client.get(f"/journeys/{JOURNEY_ID}/history").json()
    assert len(history) == 2
    assert history[0]["decision_time"] < history[1]["decision_time"]
    assert history[0]["snapshot_checksum"] != history[1]["snapshot_checksum"]


def test_audit_is_reachable_and_holds_references_only(client):
    body = _assess(client)
    request_id = body["response"]["request_id"]

    records = client.get(f"/audit/{request_id}").json()
    assert records[0]["policy_version"] == "safety-policy-v1"
    assert "ev-001" in records[0]["evidence_ids"]
    assert "Chest discomfort" not in json.dumps(records)


def test_unknown_ids_return_404(client):
    assert client.get("/recommendations/rec-does-not-exist").status_code == 404
    assert client.get("/audit/req-does-not-exist").status_code == 404
    assert client.get("/journeys/journey-missing/history").status_code == 404


# ------------------------------------------------- A1 workflow over HTTP (Phase 1)


def test_encounter_creation_records_all_four_intake_states(client):
    body = {
        "journey_id": "journey-api-0001",
        "patient_id": "patient-api-0001",
        "encounter_id": "encounter-api-0001",
        "encounter_start": "2026-01-01T09:00:00Z",
        "items": [
            {"information_type": "CHIEF_COMPLAINT", "state": "KNOWN", "value": "chest discomfort"},
            {"information_type": "VITAL", "state": "NOT_AVAILABLE"},
            {"information_type": "ALLERGY", "state": "UNKNOWN"},
            {"information_type": "MEDICATION", "state": "REFUSED"},
        ],
    }
    response = client.post("/encounters", json=body)
    assert response.status_code == 201, response.text

    recorded = response.json()["recorded_states"]
    assert recorded == {
        "CHIEF_COMPLAINT": "AVAILABLE",
        "VITAL": "NOT_AVAILABLE_YET",
        "ALLERGY": "MEASURED_UNKNOWN",
        "MEDICATION": "WITHHELD",
    }


def test_encounter_rejects_a_known_item_with_no_value(client):
    body = {
        "journey_id": "journey-api-0002",
        "patient_id": "p", "encounter_id": "e",
        "encounter_start": "2026-01-01T09:00:00Z",
        "items": [{"information_type": "CHIEF_COMPLAINT", "state": "KNOWN"}],
    }
    assert client.post("/encounters", json=body).status_code == 400


def test_duplicate_encounter_is_refused(client):
    body = {
        "journey_id": "journey-api-0003",
        "patient_id": "p", "encounter_id": "e",
        "encounter_start": "2026-01-01T09:00:00Z",
        "items": [{"information_type": "CHIEF_COMPLAINT", "state": "KNOWN", "value": "x"}],
    }
    assert client.post("/encounters", json=body).status_code == 201
    assert client.post("/encounters", json=body).status_code == 409


def test_appending_evidence_is_append_only(client):
    before = len(JOURNEY["events"])
    response = client.post(
        f"/journeys/{JOURNEY_ID}/events",
        json={"information_type": "ECG", "state": "KNOWN", "value": {"rhythm": "sinus"},
              "observed_at": LATER, "available_at_time": LATER},
    )
    assert response.status_code == 201, response.text
    assert response.json()["total_events"] == before + 1

    # The earlier events are still there, unedited.
    again = client.post(
        f"/journeys/{JOURNEY_ID}/events",
        json={"information_type": "LAB", "state": "UNKNOWN"},
    )
    assert again.json()["total_events"] == before + 2
    assert again.json()["status"] == "MEASURED_UNKNOWN"


def test_next_information_ranks_required_first_and_never_re_asks_a_refusal(client):
    body = {
        "journey_id": "journey-api-0004",
        "patient_id": "p", "encounter_id": "e",
        "encounter_start": "2026-01-01T09:00:00Z",
        "items": [
            {"information_type": "CHIEF_COMPLAINT", "state": "KNOWN", "value": "chest discomfort"},
            {"information_type": "MEDICATION", "state": "REFUSED"},
        ],
    }
    client.post("/encounters", json=body)

    plan = client.get(
        "/journeys/journey-api-0004/next-information",
        params={"decision_time": "2026-01-01T09:00:00Z"},
    ).json()

    assert plan["candidates"][0]["information_type"] == "VITAL"
    assert plan["candidates"][0]["urgency_prerequisite"] is True
    assert "MEDICATION" not in [c["information_type"] for c in plan["candidates"]]
    assert [d["information_type"] for d in plan["declined"]] == ["MEDICATION"]
    assert plan["banner"] == "RESEARCH PROTOTYPE - HUMAN REVIEW REQUIRED"


def test_next_information_for_an_unknown_journey_is_404(client):
    assert client.get(
        "/journeys/journey-missing/next-information",
        params={"decision_time": LATER},
    ).status_code == 404


# ------------------------------------------------------- structured override reason


@pytest.mark.parametrize("action", ["MODIFY", "REJECT"])
def test_override_without_a_structured_reason_is_refused(client, action):
    rec_id = _assess(client)["recommendation_id"]
    response = client.post(
        f"/recommendations/{rec_id}/review",
        json={"reviewer_id": "clinician-01", "action": action},
    )
    assert response.status_code == 400
    assert "reason_code" in response.json()["error"]["message"]


@pytest.mark.parametrize("action", ["CONFIRM", "REQUEST_INFORMATION", "ESCALATE"])
def test_non_override_actions_need_no_reason(client, action):
    rec_id = _assess(client)["recommendation_id"]
    response = client.post(
        f"/recommendations/{rec_id}/review",
        json={"reviewer_id": "clinician-01", "action": action},
    )
    assert response.status_code == 200


def test_reason_other_requires_a_note(client):
    rec_id = _assess(client)["recommendation_id"]
    response = client.post(
        f"/recommendations/{rec_id}/review",
        json={"reviewer_id": "clinician-01", "action": "MODIFY", "reason_code": "OTHER"},
    )
    assert response.status_code == 400


def test_a_reason_outside_the_vocabulary_is_refused(client):
    rec_id = _assess(client)["recommendation_id"]
    response = client.post(
        f"/recommendations/{rec_id}/review",
        json={"reviewer_id": "clinician-01", "action": "MODIFY", "reason_code": "BECAUSE_I_SAID_SO"},
    )
    assert response.status_code == 422  # refused by the schema, before any handler runs


def test_the_reason_is_recorded_on_the_recommendation(client):
    rec_id = _assess(client)["recommendation_id"]
    body = client.post(
        f"/recommendations/{rec_id}/review",
        json={"reviewer_id": "clinician-01", "action": "MODIFY",
              "reason_code": "URGENCY_TOO_HIGH", "note": "bedside assessment"},
    ).json()

    assert body["reviews"][0]["reason_code"] == "URGENCY_TOO_HIGH"
    assert body["effective"] is True


# ------------------------------------------------------------------ error envelope


def test_every_error_uses_one_envelope(client):
    """Errors used to be FastAPI's default `{"detail": ...}`, and the shape differed
    between an HTTPException and a validation failure. A client had to handle two shapes
    and could rely on neither carrying a correlation id."""
    not_found = client.get("/recommendations/rec-does-not-exist")
    assert not_found.status_code == 404
    body = not_found.json()
    assert body["error"]["code"] == "NOT_FOUND"
    assert body["banner"] == BANNER
    assert "request_id" in body["error"]

    invalid = client.post("/encounters", json={"nonsense": True})
    assert invalid.status_code == 422
    body = invalid.json()
    assert body["error"]["code"] == "SCHEMA_INVALID"
    assert body["error"]["details"], "a schema failure should say which field failed"


def test_a_validation_error_does_not_echo_the_submitted_value(client):
    """Field locations are safe to return. The submitted value is not, because for this
    API the submitted value can be clinical content."""
    canary = "CANARY-crushing-central-chest-pain"
    response = client.post(
        "/journeys/journey-syn-0001/events",
        json={"information_type": canary, "state": "NOT_A_STATE", "value": canary},
    )
    assert response.status_code in {400, 404, 422}
    assert canary not in response.text


def test_the_same_routes_answer_under_v1_and_unprefixed(client):
    """The version prefix was added by mounting one router twice, so the existing
    unprefixed surface keeps working rather than breaking every caller at once."""
    assert client.get("/v1/journeys/journey-syn-0001/history").status_code == 200
    assert client.get("/journeys/journey-syn-0001/history").status_code == 200


def test_health_and_ready_are_distinct(client):
    health = client.get("/health").json()
    assert health["status"] == "ok"
    assert health["banner"] == BANNER

    ready = client.get("/ready")
    assert ready.status_code == 200
    body = ready.json()
    assert body["ready"] is True
    assert set(body["checks"]) == {"provider", "storage"}
    assert "Not authorised for clinical use" in body["boundary"]


def test_the_correlation_id_is_echoed(client):
    response = client.get("/health", headers={"X-Request-Id": "trace-abc-123"})
    assert response.headers["X-Request-Id"] == "trace-abc-123"
