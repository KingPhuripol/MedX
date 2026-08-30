"""Persistence and append-only audit — acceptance criterion A3.

A3 requires the original model output and later human actions to remain immutable audit
events. That is a property of the store, not of the code that calls it, so it is enforced
by database triggers and tested by trying to violate it directly.
"""

from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

import pytest

from innovation.frontdoor import FrontDoorService, IntakeItem
from innovation.gateway import ModelGateway
from innovation.gateway.audit import AuditLog
from innovation.gateway.providers import MockProvider
from innovation.store import AppendOnlyViolation, SqliteStore

T0 = datetime(2026, 1, 1, 9, 0, tzinfo=timezone.utc)
T1 = datetime(2026, 1, 1, 9, 15, tzinfo=timezone.utc)


@pytest.fixture
def db_path(tmp_path: Path) -> Path:
    return tmp_path / "frontdoor.sqlite3"


def make_service(store: SqliteStore, audit_path: Path | None = None) -> FrontDoorService:
    return FrontDoorService(
        ModelGateway(MockProvider(), audit_log=AuditLog(path=audit_path, store=store)),
        store=store,
    )


def seed(service: FrontDoorService, journey_id: str = "journey-persist-0001"):
    return service.create_encounter(
        journey_id=journey_id,
        patient_id="patient-persist-0001",
        encounter_id="encounter-persist-0001",
        encounter_start=T0,
        items=[
            IntakeItem("CHIEF_COMPLAINT", "KNOWN", value="chest discomfort"),
            IntakeItem("VITAL", "KNOWN", value={"code": "heart_rate", "value": 104}),
            IntakeItem("MEDICATION", "REFUSED"),
        ],
    )


# ------------------------------------------------------------- survives a restart


def test_an_encounter_survives_a_restart(db_path):
    store = SqliteStore(db_path)
    seed(make_service(store))
    store.close()

    # A second process opening the same file.
    reopened = SqliteStore(db_path)
    service = make_service(reopened)
    journey = service.journey("journey-persist-0001")
    reopened.close()

    assert len(journey.events) == 3
    assert {e.code: e.status for e in journey.events} == {
        "CHIEF_COMPLAINT": "AVAILABLE",
        "VITAL": "AVAILABLE",
        "MEDICATION": "WITHHELD",
    }


def test_recommendations_and_reviews_survive_a_restart(db_path):
    store = SqliteStore(db_path)
    service = make_service(store)
    journey = seed(service)
    rec = service.assess(journey, T1)
    service.review(
        rec.recommendation_id, reviewer_id="clinician-01", action="MODIFY",
        reason_code="URGENCY_TOO_HIGH", note="bedside assessment",
    )
    original_urgency = rec.response.urgency.level
    store.close()

    reopened = SqliteStore(db_path)
    service = make_service(reopened)
    restored = service.get(rec.recommendation_id)
    reopened.close()

    assert restored.response.urgency.level == original_urgency
    assert restored.effective is True
    assert restored.latest_review.reviewer_id == "clinician-01"
    assert restored.latest_review.reason_code == "URGENCY_TOO_HIGH"


def test_history_survives_a_restart(db_path):
    """This is what caught the rehydrate bug: history was loaded and then reset."""
    store = SqliteStore(db_path)
    service = make_service(store)
    journey = seed(service)
    service.assess(journey, T0)
    service.assess(journey, T1)
    store.close()

    reopened = SqliteStore(db_path)
    service = make_service(reopened)
    history = service.history("journey-persist-0001")
    reopened.close()

    assert len(history) == 2
    assert history[0].decision_time < history[1].decision_time


def test_appended_evidence_survives_a_restart(db_path):
    store = SqliteStore(db_path)
    service = make_service(store)
    seed(service)
    service.append_evidence(
        "journey-persist-0001",
        IntakeItem("ECG", "KNOWN", value={"rhythm": "sinus"}),
        default_time=T1,
    )
    store.close()

    reopened = SqliteStore(db_path)
    service = make_service(reopened)
    journey = service.journey("journey-persist-0001")
    reopened.close()

    assert len(journey.events) == 4
    assert journey.events[-1].code == "ECG"


# ------------------------------------------------------------------- append-only


@pytest.mark.parametrize(
    "table", ["journeys", "journey_events", "recommendations", "reviews", "audit_events"]
)
@pytest.mark.parametrize("verb", ["UPDATE", "DELETE"])
def test_the_database_itself_refuses_rewrites(db_path, table, verb):
    """Enforced by triggers, so code written later cannot quietly rewrite history."""
    store = SqliteStore(db_path)
    service = make_service(store)
    journey = seed(service)
    rec = service.assess(journey, T1)
    service.review(rec.recommendation_id, reviewer_id="c1", action="CONFIRM")

    sql = (
        f"UPDATE {table} SET rowid = rowid" if verb == "UPDATE" else f"DELETE FROM {table}"
    )
    with pytest.raises(sqlite3.IntegrityError, match="append-only"):
        store._conn.execute(sql)
    store.close()


def test_a_second_review_appends_rather_than_replacing(db_path):
    """Changing one's mind is a new record. The first decision is still on the file."""
    store = SqliteStore(db_path)
    service = make_service(store)
    journey = seed(service)
    rec = service.assess(journey, T1)

    service.review(rec.recommendation_id, reviewer_id="c1", action="REQUEST_INFORMATION")
    service.review(
        rec.recommendation_id, reviewer_id="c2", action="MODIFY", reason_code="URGENCY_TOO_HIGH"
    )

    rows = store.reviews_for(rec.recommendation_id)
    store.close()

    assert [r["action"] for r in rows] == ["REQUEST_INFORMATION", "MODIFY"]
    assert [r["reviewer_id"] for r in rows] == ["c1", "c2"]


def test_audit_is_written_to_both_sinks(db_path, tmp_path):
    """Two durable sinks on purpose: the JSONL is readable during an incident without
    tooling, and the database makes tampering fail loudly."""
    audit_path = tmp_path / "audit.jsonl"
    store = SqliteStore(db_path)
    service = make_service(store, audit_path=audit_path)
    journey = seed(service)
    rec = service.assess(journey, T1)

    lines = audit_path.read_text().strip().splitlines()
    rows = store.audit_for(rec.response.request_id)
    store.close()

    assert len(lines) == 1
    assert len(rows) == 1
    assert json.loads(lines[0])["request_id"] == rec.response.request_id


def test_the_audit_trail_holds_no_payload_content(db_path, tmp_path):
    audit_path = tmp_path / "audit.jsonl"
    store = SqliteStore(db_path)
    service = make_service(store, audit_path=audit_path)
    journey = seed(service)
    service.assess(journey, T1)
    store.close()

    written = audit_path.read_text()
    assert "chest discomfort" not in written
    assert "ev-001" in written


def test_append_only_violation_surfaces_as_a_typed_error(db_path):
    store = SqliteStore(db_path)
    store.append_audit("req-x", "{}")
    with pytest.raises(AppendOnlyViolation):
        store._write("DELETE FROM audit_events", ())
    store.close()


# ------------------------------------------------ low-confidence / OOD abstention


def test_low_confidence_escalates_rather_than_reporting_a_weak_conclusion():
    from innovation.gateway.safety import SafetyPolicy
    from shared.contracts.model_api import GatewayRequest, Urgency

    request = GatewayRequest.model_validate(
        json.loads((Path(__file__).resolve().parents[1] / "tests/fixtures/model_api/request.json").read_text())
    )
    decision = SafetyPolicy().apply(
        request, Urgency(level="ROUTINE_REVIEW", confidence=0.2, evidence_ids=[]), ()
    )

    assert "SR-004-LOW_CONFIDENCE" in decision.applied_rules
    assert decision.urgency.level == "URGENT_REVIEW"
    assert any("not clinically validated" in limit for limit in decision.limitations)


def test_out_of_distribution_input_escalates():
    from innovation.gateway.safety import SafetyPolicy
    from shared.contracts.model_api import GatewayRequest, Urgency

    request = GatewayRequest.model_validate(
        json.loads((Path(__file__).resolve().parents[1] / "tests/fixtures/model_api/request.json").read_text())
    )
    decision = SafetyPolicy().apply(
        request,
        Urgency(level="ROUTINE_REVIEW", confidence=0.99, evidence_ids=[]),
        (),
        out_of_distribution=True,
    )

    assert "SR-005-OUT_OF_DISTRIBUTION" in decision.applied_rules
    assert decision.urgency.level == "URGENT_REVIEW"


def test_high_confidence_is_left_alone():
    from innovation.gateway.safety import SafetyPolicy
    from shared.contracts.model_api import GatewayRequest, Urgency

    request = GatewayRequest.model_validate(
        json.loads((Path(__file__).resolve().parents[1] / "tests/fixtures/model_api/request.json").read_text())
    )
    decision = SafetyPolicy().apply(
        request, Urgency(level="ROUTINE_REVIEW", confidence=0.95, evidence_ids=[]), ()
    )
    assert "SR-004-LOW_CONFIDENCE" not in decision.applied_rules
