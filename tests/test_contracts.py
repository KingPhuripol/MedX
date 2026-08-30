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


def test_retrospective_label_on_the_timeline_is_withheld():
    """The real protection: a final diagnosis is an ordinary event and goes through the
    same rule. The fixture's ev-003 is a DIAGNOSIS/LABEL available at 13:00."""
    journey = PatientJourney.model_validate(_load("tests/fixtures/patient_journey/valid.json"))
    label = journey.events[2]
    assert (label.event_type, label.modality) == ("DIAGNOSIS", "LABEL")

    snapshot = take_snapshot(journey, datetime(2026, 1, 1, 9, 15, tzinfo=timezone.utc))
    assert label.event_id not in snapshot.evidence_ids
    assert (label.event_id, "FUTURE_EVIDENCE") in [(r.event_id, r.reason) for r in snapshot.rejected]


# ------------------------------------------------------- schema/model constraint parity


def _reject_both(payload: dict, schema_path: str, model) -> None:
    """Assert the machine schema and the executable model both refuse a document.

    Testing that valid fixtures pass is not enough — it leaves the models free to be
    *looser* than the schema, which is how a document the contract rejects gets accepted
    in code. These cases pin the refusal surface, not just the acceptance surface.
    """
    schema = _load(schema_path)
    with pytest.raises(jsonschema.ValidationError):
        jsonschema.validate(payload, schema)
    with pytest.raises(Exception):
        model.model_validate(payload)


JOURNEY_SCHEMA = "schemas/patient-journey.schema.json"


def _journey() -> dict:
    return _load("tests/fixtures/patient_journey/valid.json")


def test_parity_journey_rejects_an_undeclared_top_level_field():
    """`outcomes` is documented in PATIENT_JOURNEY_SCHEMA.md but absent from the machine
    schema, which sets additionalProperties:false. The models follow the machine schema.
    This discrepancy between the two contract artifacts is recorded for a human decision.
    """
    payload = _journey()
    payload["outcomes"] = []
    _reject_both(payload, JOURNEY_SCHEMA, PatientJourney)


def test_parity_journey_rejects_a_split_outside_the_enum():
    payload = _journey()
    payload["split"] = "test"  # plausible, and not a member of the schema's enum
    _reject_both(payload, JOURNEY_SCHEMA, PatientJourney)


@pytest.mark.parametrize("split", [
    "train", "validation", "internal_test", "external_test", "expert_test",
    "architecture_intervention", "missing_modality_test", "unseen_combination_test",
])
def test_parity_every_schema_split_is_accepted_by_the_model(split):
    """The mirror of the case above: the model must not be *narrower* than the schema
    either, or a valid journey would be refused in code."""
    payload = dict(_journey(), split=split)
    jsonschema.validate(payload, _load(JOURNEY_SCHEMA))
    assert PatientJourney.model_validate(payload).split == split


def test_parity_event_rejects_an_undeclared_field():
    payload = _journey()
    payload["events"][0]["provider_hint"] = "leak"
    _reject_both(payload, JOURNEY_SCHEMA, PatientJourney)


def test_parity_event_rejects_a_status_outside_the_enum():
    payload = _journey()
    payload["events"][0]["status"] = "PROBABLY_FINE"
    _reject_both(payload, JOURNEY_SCHEMA, PatientJourney)


def test_parity_event_rejects_an_event_type_outside_the_enum():
    payload = _journey()
    payload["events"][0]["event_type"] = "VIBES"
    _reject_both(payload, JOURNEY_SCHEMA, PatientJourney)


def test_parity_event_source_ref_requires_record_ref():
    """journey.source and event.source_ref are different shapes in the schema: only the
    event one requires record_ref, and neither permits extra keys."""
    payload = _journey()
    payload["events"][0]["source_ref"].pop("record_ref")
    _reject_both(payload, JOURNEY_SCHEMA, PatientJourney)


def test_parity_journey_source_rejects_record_ref():
    payload = _journey()
    payload["source"]["record_ref"] = "not-allowed-here"
    _reject_both(payload, JOURNEY_SCHEMA, PatientJourney)


def test_parity_journey_rejects_an_empty_event_list():
    payload = _journey()
    payload["events"] = []
    _reject_both(payload, JOURNEY_SCHEMA, PatientJourney)


def test_parity_request_rejects_an_undeclared_field():
    payload = _load("tests/fixtures/model_api/request.json")
    payload["provider_native_hint"] = "leak"
    _reject_both(payload, "schemas/model-api-request.schema.json", GatewayRequest)


def test_parity_response_rejects_an_undeclared_field():
    payload = _load("tests/fixtures/model_api/response.json")
    payload["provider_raw_completion"] = "leak"
    _reject_both(payload, "schemas/model-api-response.schema.json", GatewayResponse)


def test_parity_response_rejects_human_review_not_required():
    """The schema pins human_review.required to const true, and so must the model."""
    payload = _load("tests/fixtures/model_api/response.json")
    payload["human_review"]["required"] = False
    _reject_both(payload, "schemas/model-api-response.schema.json", GatewayResponse)
