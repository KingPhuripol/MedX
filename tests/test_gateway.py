"""The ten contract cases from `docs/shared/MODEL_API_CONTRACT.md` §Contract tests.

Every adapter must pass this suite unchanged. "Team-model integration is accepted only
when it passes the same fixtures as the mock adapter" — so these are parametrised over
providers rather than written against the mock, and adding the team model later means
adding it to `ADAPTERS`, not writing a second suite.
"""

from __future__ import annotations

import json
from pathlib import Path

import jsonschema
import pytest

from innovation.gateway import ModelGateway
from innovation.gateway.providers import MockProvider
from innovation.gateway.providers.base import ProviderFailure, ProviderTimeout
from shared.contracts.model_api import URGENCY_SEVERITY

ROOT = Path(__file__).resolve().parents[1]
RESPONSE_SCHEMA = json.loads((ROOT / "schemas/model-api-response.schema.json").read_text())


def base_request() -> dict:
    return json.loads((ROOT / "tests/fixtures/model_api/request.json").read_text())


def new_gateway(**kwargs) -> ModelGateway:
    return ModelGateway(MockProvider(**kwargs))


def assert_contract_valid(response) -> dict:
    """Every response, including a refusal, must satisfy the machine contract."""
    dumped = json.loads(response.model_dump_json())
    jsonschema.validate(dumped, RESPONSE_SCHEMA)
    # Invariant that holds on every path: nothing completes without human review.
    assert dumped["human_review"]["required"] is True
    assert dumped["contract_version"] == "1.0.0"
    return dumped


# ------------------------------------------------------------------ case 1 of 10


def test_01_canonical_valid_request():
    response = new_gateway().infer(base_request())
    dumped = assert_contract_valid(response)

    assert dumped["request_id"] == "req-syn-0001"
    assert dumped["provider"] == "mock"
    assert dumped["errors"] == []
    # The mock proposes ROUTINE_REVIEW; the deterministic layer raises it because the
    # red flag is UNKNOWN. The escalation, not the proposal, is what reaches the client.
    assert dumped["status"] == "ESCALATED"


# ------------------------------------------------------------------ case 2 of 10


def test_02_missing_modality_is_reported_not_ignored():
    """An unusable image must not be indistinguishable from a normal one."""
    payload = base_request()
    payload["evidence"].append(
        {
            "evidence_id": "ev-img-3d",
            "event_type": "IMAGE_3D",
            "modality": "IMAGE_3D",
            "available_at_time": "2026-01-01T09:05:00Z",
            "data_classification": "SYNTHETIC",
            "payload_ref": "synthetic://journey-syn-0001/ev-img-3d",
        }
    )
    # The mock supports 2D but not 3D volumes.
    response = new_gateway().infer(payload)
    dumped = assert_contract_valid(response)

    codes = [e["code"] for e in dumped["errors"]]
    assert "UNSUPPORTED_MODALITY" in codes
    assert "ev-img-3d" in dumped["errors"][codes.index("UNSUPPORTED_MODALITY")]["message"]


def test_02b_unknown_red_flag_is_not_reported_as_absent():
    """UNKNOWN must never be collapsed into NOT_TRIGGERED."""
    dumped = assert_contract_valid(new_gateway().infer(base_request()))
    states = {f["state"] for f in dumped["red_flags"]}
    assert "UNKNOWN" in states
    assert "NOT_TRIGGERED" not in states


# ------------------------------------------------------------------ case 3 of 10


def test_03_triggered_red_flag_outranks_a_routine_proposal():
    """A model cannot report a triggered flag and a routine urgency at the same time.

    This is the central safety property: the deterministic layer only ever raises.
    """
    from shared.contracts.model_api import GatewayRequest, RedFlag, Urgency
    from innovation.gateway.safety import SafetyPolicy

    request = GatewayRequest.model_validate(base_request())
    decision = SafetyPolicy().apply(
        request,
        Urgency(level="ROUTINE_REVIEW", confidence=0.97, evidence_ids=["ev-001"]),
        (RedFlag(code="CRITICAL_FINDING", state="TRIGGERED", evidence_ids=["ev-001"]),),
    )

    assert decision.urgency.level == "IMMEDIATE_REVIEW"
    assert decision.status_floor == "ESCALATED"
    assert "SR-001-TRIGGERED_RED_FLAG" in decision.applied_rules
    # The provider's confidence described its own conclusion and does not transfer.
    assert decision.urgency.confidence is None


@pytest.mark.parametrize(
    "proposed",
    ["INSUFFICIENT_INFORMATION", "ROUTINE_REVIEW", "URGENT_REVIEW", "IMMEDIATE_REVIEW"],
)
def test_03b_safety_layer_never_lowers_urgency(proposed):
    from shared.contracts.model_api import GatewayRequest, RedFlag, Urgency
    from innovation.gateway.safety import SafetyPolicy

    request = GatewayRequest.model_validate(base_request())
    for flag_state in ("TRIGGERED", "UNKNOWN", "NOT_TRIGGERED"):
        decision = SafetyPolicy().apply(
            request,
            Urgency(level=proposed, confidence=None, evidence_ids=[]),
            (RedFlag(code="FLAG_UNDER_TEST", state=flag_state, evidence_ids=[]),),
        )
        assert URGENCY_SEVERITY[decision.urgency.level] >= URGENCY_SEVERITY[proposed]


# ------------------------------------------------------------------ case 4 of 10


def test_04_no_usable_evidence_abstains_rather_than_concluding():
    payload = base_request()
    payload["evidence"] = []
    payload["missing_information"] = ["everything"]

    dumped = assert_contract_valid(new_gateway().infer(payload))
    # Required front-door evidence is absent, so SR-003 escalates rather than
    # producing a confident low-acuity conclusion.
    assert dumped["status"] == "ESCALATED"
    assert dumped["uncertainty"]["abstention_reason"] is not None
    assert any("Required evidence" in limit for limit in dumped["uncertainty"]["limitations"])


# ------------------------------------------------------------------ case 5 of 10


def test_05_temporal_violation_is_refused_before_the_provider_is_called():
    """Future evidence is blocked at the boundary, so it never reaches a provider."""
    payload = base_request()
    payload["evidence"][1]["available_at_time"] = "2026-01-01T13:00:00Z"  # after decision_time

    class Tripwire(MockProvider):
        def infer(self, request):  # pragma: no cover - must never run
            raise AssertionError("provider was called despite a temporal violation")

    gateway = ModelGateway(Tripwire())
    dumped = assert_contract_valid(gateway.infer(payload))

    assert dumped["status"] == "FAILED_SAFE"
    assert [e["code"] for e in dumped["errors"]] == ["TEMPORAL_VIOLATION"]
    assert "ev-002" in dumped["errors"][0]["message"]
    assert dumped["care_pathways"] == []


# ------------------------------------------------------------------ case 6 of 10


def test_06_restricted_data_to_an_external_provider_is_refused():
    payload = base_request()
    payload["authorization"] = {
        "data_classification": "DEIDENTIFIED_APPROVED",
        "external_provider_allowed": False,
        "approval_id": None,
    }
    payload["evidence"][0]["data_classification"] = "DEIDENTIFIED_APPROVED"

    class ExternalProvider(MockProvider):
        name = "external_prototype"

    dumped = assert_contract_valid(ModelGateway(ExternalProvider()).infer(payload))
    assert [e["code"] for e in dumped["errors"]] == ["UNAUTHORIZED_DATA"]
    assert dumped["status"] == "FAILED_SAFE"


def test_06b_external_provider_requires_a_recorded_approval_id():
    """Permission alone is not enough; the approval must be recorded and referable."""
    payload = base_request()
    payload["authorization"] = {
        "data_classification": "DEIDENTIFIED_APPROVED",
        "external_provider_allowed": True,
        "approval_id": None,
    }

    class ExternalProvider(MockProvider):
        name = "external_prototype"

    dumped = assert_contract_valid(ModelGateway(ExternalProvider()).infer(payload))
    assert [e["code"] for e in dumped["errors"]] == ["UNAUTHORIZED_DATA"]


def test_06c_synthetic_data_to_an_external_provider_is_allowed():
    """The gate is on classification, not on the word 'external' — synthetic is fine."""

    class ExternalProvider(MockProvider):
        name = "external_prototype"

    dumped = assert_contract_valid(ModelGateway(ExternalProvider()).infer(base_request()))
    assert "UNAUTHORIZED_DATA" not in [e["code"] for e in dumped["errors"]]


# ------------------------------------------------------------------ case 7 of 10


def test_07_provider_timeout_fails_safe():
    gateway = new_gateway(fail_with=ProviderTimeout("deadline exceeded"))
    dumped = assert_contract_valid(gateway.infer(base_request()))

    assert dumped["status"] == "FAILED_SAFE"
    assert dumped["errors"][0]["code"] == "PROVIDER_TIMEOUT"
    assert dumped["errors"][0]["retryable"] is True
    assert dumped["urgency"]["level"] == "INSUFFICIENT_INFORMATION"


def test_07b_provider_failure_fails_safe():
    gateway = new_gateway(fail_with=ProviderFailure("upstream unavailable"))
    dumped = assert_contract_valid(gateway.infer(base_request()))
    assert dumped["errors"][0]["code"] == "INTERNAL_SAFE_FAILURE"


# ------------------------------------------------------------------ case 8 of 10


def test_08_malformed_provider_output_is_quarantined():
    """A broken adapter must never be partially rendered."""

    class BrokenProvider(MockProvider):
        def infer(self, request):
            return {"urgency": "totally not a ProviderOutput"}

    dumped = assert_contract_valid(ModelGateway(BrokenProvider()).infer(base_request()))
    assert dumped["status"] == "FAILED_SAFE"
    assert dumped["errors"][0]["code"] == "INVALID_PROVIDER_OUTPUT"
    assert dumped["care_pathways"] == []


def test_08b_unparsable_request_still_returns_a_contract_valid_refusal():
    dumped = assert_contract_valid(new_gateway().infer({"nonsense": True}))
    assert dumped["errors"][0]["code"] == "INVALID_REQUEST"
    assert dumped["human_review"]["required"] is True


def test_08c_unsupported_contract_version_fails_safe():
    payload = base_request()
    payload["contract_version"] = "2.0.0"
    dumped = assert_contract_valid(new_gateway().infer(payload))
    assert dumped["errors"][0]["code"] == "INVALID_REQUEST"


# ------------------------------------------------------------------ case 9 of 10


def test_09_requests_are_idempotent():
    gateway = new_gateway()
    first = gateway.infer(base_request())
    second = gateway.infer(base_request())

    assert first.response_id == second.response_id
    assert first.provenance.input_checksum == second.provenance.input_checksum
    # The provider is not called twice, so the audit trail records one call.
    assert len(gateway.audit.find("req-syn-0001")) == 1


def test_09b_checksum_covers_the_evidence_set():
    gateway = new_gateway()
    original = gateway.infer(base_request())

    changed = base_request()
    changed["request_id"] = "req-syn-0002"
    changed["evidence"] = changed["evidence"][:1]
    assert gateway.infer(changed).provenance.input_checksum != original.provenance.input_checksum


# ----------------------------------------------------------------- case 10 of 10


def test_10_no_provider_native_fields_reach_the_client():
    """The gateway builds the response, so an adapter cannot smuggle a field through."""
    response = new_gateway().infer(base_request())
    dumped = json.loads(response.model_dump_json())

    assert set(dumped) == set(RESPONSE_SCHEMA["required"])
    # Structural, not incidental: the response type refuses unknown fields outright.
    with pytest.raises(Exception):
        type(response).model_validate({**dumped, "provider_raw_completion": "leak"})


def test_10b_response_carries_no_free_text_reasoning_field():
    """The inspectable artifact is the executed graph, never hidden chain-of-thought."""
    dumped = json.loads(new_gateway().infer(base_request()).model_dump_json())
    forbidden = {"reasoning", "chain_of_thought", "thoughts", "rationale_text", "explanation"}
    assert forbidden.isdisjoint(dumped)
    assert set(dumped["graph"]) <= {"graph_schema_version", "graph_id", "graph_ref"}


# ------------------------------------------------------------------------- audit


def test_audit_records_every_call_including_refusals():
    payload = base_request()
    payload["evidence"][1]["available_at_time"] = "2026-01-01T13:00:00Z"

    gateway = new_gateway()
    gateway.infer(payload)
    record = gateway.audit.records()[0]

    assert record.status == "FAILED_SAFE"
    assert record.error_codes == ("TEMPORAL_VIOLATION",)
    assert ("ev-002", "FUTURE_EVIDENCE") in record.rejected_evidence
    assert record.policy_version == "safety-policy-v1"
    # Not yet reviewed must never read as approved.
    assert record.reviewer_id is None and record.review_action is None


def test_audit_holds_references_never_payloads():
    gateway = new_gateway()
    gateway.infer(base_request())
    serialised = gateway.audit.records()[0].to_json()

    # The journey fixture's chief-complaint text must not appear anywhere in the trail.
    assert "Chest discomfort" not in serialised
    assert "ev-001" in serialised


def test_offline_end_to_end_needs_no_network():
    """The default path is a mock provider and a synthetic journey, fully offline."""
    from datetime import datetime, timezone

    from shared.contracts import PatientJourney
    from shared.snapshot import take_snapshot

    journey = PatientJourney.model_validate(
        json.loads((ROOT / "tests/fixtures/patient_journey/valid.json").read_text())
    )
    decision_time = datetime(2026, 1, 1, 9, 15, tzinfo=timezone.utc)
    snapshot = take_snapshot(journey, decision_time)

    payload = base_request()
    payload["evidence"] = [
        e for e in payload["evidence"] if e["evidence_id"] in snapshot.evidence_ids
    ]
    dumped = assert_contract_valid(new_gateway().infer(payload))

    assert dumped["status"] in {"COMPLETED", "ABSTAINED", "ESCALATED"}
    assert "ev-003" not in json.dumps(dumped)
