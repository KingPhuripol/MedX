"""The executable contract must agree with the machine contract.

`schemas/` is the source of truth and `shared/contracts/` is the executable form. If
they disagree, one of them is wrong and the project has two definitions of the same
contract — the drift RISK-0006 describes. These tests validate the same fixtures through
both paths so the disagreement fails here rather than in production.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

import jsonschema
import pytest

from shared.contracts import GatewayRequest, GatewayResponse, PatientJourney
from shared.contracts.journey import JourneyEvent
from shared.snapshot import take_snapshot

ROOT = Path(__file__).resolve().parents[1]

FIXTURE_BINDINGS = [
    ("tests/fixtures/patient_journey/valid.json", "schemas/patient-journey.schema.json", PatientJourney),
    ("tests/fixtures/model_api/request.json", "schemas/model-api-request.schema.json", GatewayRequest),
    ("tests/fixtures/model_api/response.json", "schemas/model-api-response.schema.json", GatewayResponse),
]


def _load(path: str) -> dict:
    return json.loads((ROOT / path).read_text(encoding="utf-8"))


@pytest.mark.parametrize("fixture,schema,model", FIXTURE_BINDINGS)
def test_fixture_satisfies_both_schema_and_model(fixture, schema, model):
    payload = _load(fixture)
    jsonschema.validate(payload, _load(schema))  # machine contract
    model.model_validate(payload)  # executable contract


@pytest.mark.parametrize("fixture,schema,model", FIXTURE_BINDINGS)
def test_model_roundtrip_still_satisfies_the_schema(fixture, schema, model):
    """Serialising a parsed model must produce something the schema still accepts.

    This is the direction that catches drift: a model that quietly adds, drops or renames
    a field would round-trip to a document the machine contract rejects.

    `exclude_unset` keeps the round-trip honest — a field the fixture never set must not
    reappear as an explicit null, which is a different document from the one that went in.
    """
    parsed = model.model_validate(_load(fixture))
    dumped = json.loads(parsed.model_dump_json(exclude_unset=True))
    jsonschema.validate(dumped, _load(schema))
    assert dumped.keys() == _load(fixture).keys()


def test_unknown_field_is_refused():
    """`extra="forbid"` is what keeps provider-native fields out of client-facing types."""
    payload = _load("tests/fixtures/model_api/request.json")
    payload["provider_native_hint"] = "do not leak me"
    with pytest.raises(Exception):
        GatewayRequest.model_validate(payload)


def test_duplicate_evidence_ids_are_refused():
    payload = _load("tests/fixtures/model_api/request.json")
    payload["evidence"].append(dict(payload["evidence"][0]))
    with pytest.raises(Exception):
        GatewayRequest.model_validate(payload)


def test_availability_before_observation_is_refused():
    """A mis-derived availability time is caught at ingestion, not after it widens a snapshot."""
    with pytest.raises(Exception):
        JourneyEvent.model_validate(
            {
                "event_id": "ev-bad",
                "event_type": "LAB",
                "modality": "STRUCTURED",
                "observed_at": "2026-01-01T10:00:00Z",
                "available_at_time": "2026-01-01T09:00:00Z",
                "status": "AVAILABLE",
                "data_classification": "SYNTHETIC",
                "source_ref": {"system": "test", "version": "1.0.0"},
            }
        )


# --------------------------------------------------------------------- snapshot


def test_snapshot_matches_the_contract_worked_example():
    """`PATIENT_JOURNEY_SCHEMA.md` states: at 09:15Z ev-001 and ev-002 are available,
    and ev-003 is forbidden even though it sits in the same file."""
    journey = PatientJourney.model_validate(_load("tests/fixtures/patient_journey/valid.json"))
    snapshot = take_snapshot(journey, datetime(2026, 1, 1, 9, 15, tzinfo=timezone.utc))

    assert snapshot.evidence_ids == ("ev-001", "ev-002")
    assert [(r.event_id, r.reason) for r in snapshot.rejected] == [("ev-003", "FUTURE_EVIDENCE")]


def test_snapshot_is_deterministic_and_checksum_tracks_content():
    journey = PatientJourney.model_validate(_load("tests/fixtures/patient_journey/valid.json"))
    early = take_snapshot(journey, datetime(2026, 1, 1, 9, 5, tzinfo=timezone.utc))
    at_915 = take_snapshot(journey, datetime(2026, 1, 1, 9, 15, tzinfo=timezone.utc))
    again = take_snapshot(journey, datetime(2026, 1, 1, 9, 15, tzinfo=timezone.utc))

    assert at_915.checksum() == again.checksum()
    assert early.checksum() != at_915.checksum()
    assert early.evidence_ids == ("ev-001",)


def test_snapshot_does_not_mutate_the_journey():
    journey = PatientJourney.model_validate(_load("tests/fixtures/patient_journey/valid.json"))
    before = len(journey.events)
    take_snapshot(journey, datetime(2026, 1, 1, 9, 15, tzinfo=timezone.utc))
    assert len(journey.events) == before


def test_outcomes_are_subject_to_the_same_temporal_rule():
    """An outcome mis-stamped as early is a leak; honouring the stamp would hide it."""
    payload = _load("tests/fixtures/patient_journey/valid.json")
    payload["outcomes"] = [
        {
            "event_id": "out-001",
            "event_type": "OUTCOME",
            "modality": "LABEL",
            "observed_at": "2026-01-01T20:00:00Z",
            "available_at_time": "2026-01-01T20:00:00Z",
            "status": "AVAILABLE",
            "data_classification": "SYNTHETIC",
            "source_ref": {"system": "project-fixture", "version": "1.0.0"},
            "value": {"category": "synthetic-outcome"},
        }
    ]
    journey = PatientJourney.model_validate(payload)
    snapshot = take_snapshot(journey, datetime(2026, 1, 1, 9, 15, tzinfo=timezone.utc))

    assert "out-001" not in snapshot.evidence_ids
    assert ("out-001", "FUTURE_EVIDENCE") in [(r.event_id, r.reason) for r in snapshot.rejected]
