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
    assert "SYNTHETIC" in response.json()["detail"]


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
        json={"reviewer_id": "clinician-01", "action": "REJECT"},
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
        json={"reviewer_id": "clinician-02", "action": "MODIFY", "note": "bedside review"},
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
