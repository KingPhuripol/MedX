"""The ten contract cases from `docs/shared/MODEL_API_CONTRACT.md` §Contract tests.

"Every adapter passes" and "team-model integration is accepted only when it passes the
same fixtures as the mock adapter" — so the suite is parametrised over `ADAPTERS` and
asserts *contract-level* properties, never one provider's particular answers. Adding the
team model later means appending to `ADAPTERS`, not writing a second suite.

Provider-specific behaviour is tested separately and labelled as such, so it can never be
mistaken for a contract requirement.
"""

from __future__ import annotations

import json
from pathlib import Path

import jsonschema
import pytest

from innovation.gateway import ModelGateway
from innovation.gateway.providers import BaselineProvider, MockProvider
from dataclasses import replace

from innovation.gateway.providers.base import ProviderFailure, ProviderTimeout
from shared.contracts.model_api import URGENCY_SEVERITY, RedFlag, Urgency

ROOT = Path(__file__).resolve().parents[1]
RESPONSE_SCHEMA = json.loads((ROOT / "schemas/model-api-response.schema.json").read_text())

#: Every enabled adapter. A new provider is certified by being added here.
ADAPTERS = [MockProvider, BaselineProvider]


@pytest.fixture(params=ADAPTERS, ids=[a.name for a in ADAPTERS])
def adapter(request):
    """Each contract test runs once per adapter."""
    return request.param


def base_request() -> dict:
    return json.loads((ROOT / "tests/fixtures/model_api/request.json").read_text())


def assert_contract_valid(response) -> dict:
    """Every response, including a refusal, must satisfy the machine contract."""
    dumped = json.loads(response.model_dump_json())
    jsonschema.validate(dumped, RESPONSE_SCHEMA)
    # Invariants that hold on every path, for every provider.
    assert dumped["human_review"]["required"] is True
    assert dumped["contract_version"] == "1.0.0"
    assert dumped["urgency"]["level"] in URGENCY_SEVERITY
    return dumped


def as_external(adapter_cls, **kwargs):
    """The same adapter, presented as an external provider."""

    class External(adapter_cls):
        name = "external_prototype"

    return External(**kwargs)


# ------------------------------------------------------------------ case 1 of 10


def test_01_canonical_valid_request(adapter):
    dumped = assert_contract_valid(ModelGateway(adapter()).infer(base_request()))

    assert dumped["request_id"] == "req-syn-0001"
    assert dumped["provider"] == adapter.name
    assert dumped["errors"] == []
    assert dumped["status"] in {"COMPLETED", "ABSTAINED", "ESCALATED"}


# ------------------------------------------------------------------ case 2 of 10


def test_02_missing_modality_is_reported_not_ignored(adapter):
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
    dumped = assert_contract_valid(ModelGateway(adapter()).infer(payload))

    codes = [e["code"] for e in dumped["errors"]]
    assert "UNSUPPORTED_MODALITY" in codes
    assert "ev-img-3d" in dumped["errors"][codes.index("UNSUPPORTED_MODALITY")]["message"]


def test_02b_a_red_flag_is_never_silently_omitted(adapter):
    """Whatever a provider concludes, a flag it reports carries an explicit state.
    There is no "absent means fine" encoding available to it."""
    dumped = assert_contract_valid(ModelGateway(adapter()).infer(base_request()))
    for flag in dumped["red_flags"]:
        assert flag["state"] in {"TRIGGERED", "NOT_TRIGGERED", "UNKNOWN"}


# ------------------------------------------------------------------ case 3 of 10


def test_03_triggered_red_flag_outranks_a_routine_proposal():
    """A model cannot report a triggered flag and a routine urgency at the same time.

    Tested against the policy directly because it must hold regardless of whether any
    current provider happens to emit a TRIGGERED flag.
    """
    from innovation.gateway.safety import SafetyPolicy
    from shared.contracts.model_api import GatewayRequest, RedFlag, Urgency

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
@pytest.mark.parametrize("flag_state", ["TRIGGERED", "UNKNOWN", "NOT_TRIGGERED"])
def test_03b_safety_layer_never_lowers_urgency(proposed, flag_state):
    from innovation.gateway.safety import SafetyPolicy
    from shared.contracts.model_api import GatewayRequest, RedFlag, Urgency

    request = GatewayRequest.model_validate(base_request())
    decision = SafetyPolicy().apply(
        request,
        Urgency(level=proposed, confidence=None, evidence_ids=[]),
        (RedFlag(code="FLAG_UNDER_TEST", state=flag_state, evidence_ids=[]),),
    )
    assert URGENCY_SEVERITY[decision.urgency.level] >= URGENCY_SEVERITY[proposed]


# ------------------------------------------------------------------ case 4 of 10


def test_04_no_usable_evidence_abstains_rather_than_concluding(adapter):
    payload = base_request()
    payload["evidence"] = []
    payload["missing_information"] = ["everything"]

    dumped = assert_contract_valid(ModelGateway(adapter()).infer(payload))
    # Required front-door evidence is absent, so SR-003 escalates rather than
    # producing a confident low-acuity conclusion.
    assert dumped["status"] == "ESCALATED"
    assert dumped["uncertainty"]["abstention_reason"] is not None
    assert any("Required evidence" in limit for limit in dumped["uncertainty"]["limitations"])


# ------------------------------------------------------------------ case 5 of 10


def test_05_temporal_violation_is_refused_before_the_provider_is_called(adapter):
    """Future evidence is blocked at the boundary, so it never reaches a provider."""
    payload = base_request()
    payload["evidence"][1]["available_at_time"] = "2026-01-01T13:00:00Z"  # after decision_time

    class Tripwire(adapter):
        def infer(self, request):  # pragma: no cover - must never run
            raise AssertionError("provider was called despite a temporal violation")

    dumped = assert_contract_valid(ModelGateway(Tripwire()).infer(payload))

    assert dumped["status"] == "FAILED_SAFE"
    assert [e["code"] for e in dumped["errors"]] == ["TEMPORAL_VIOLATION"]
    assert "ev-002" in dumped["errors"][0]["message"]
    assert dumped["care_pathways"] == []


# ------------------------------------------------------------------ case 6 of 10


def test_06_restricted_data_to_an_external_provider_is_refused(adapter):
    payload = base_request()
    payload["authorization"] = {
        "data_classification": "DEIDENTIFIED_APPROVED",
        "external_provider_allowed": False,
        "approval_id": None,
    }
    payload["evidence"][0]["data_classification"] = "DEIDENTIFIED_APPROVED"

    dumped = assert_contract_valid(ModelGateway(as_external(adapter)).infer(payload))
    assert [e["code"] for e in dumped["errors"]] == ["UNAUTHORIZED_DATA"]
    assert dumped["status"] == "FAILED_SAFE"


def test_06b_external_provider_requires_a_recorded_approval_id(adapter):
    """Permission alone is not enough; the approval must be recorded and referable."""
    payload = base_request()
    payload["authorization"] = {
        "data_classification": "DEIDENTIFIED_APPROVED",
        "external_provider_allowed": True,
        "approval_id": None,
    }

    dumped = assert_contract_valid(ModelGateway(as_external(adapter)).infer(payload))
    assert [e["code"] for e in dumped["errors"]] == ["UNAUTHORIZED_DATA"]


def test_06c_synthetic_data_to_an_external_provider_is_allowed(adapter):
    """The gate is on classification, not on the word 'external' — synthetic is fine."""
    dumped = assert_contract_valid(ModelGateway(as_external(adapter)).infer(base_request()))
    assert "UNAUTHORIZED_DATA" not in [e["code"] for e in dumped["errors"]]


# ------------------------------------------------------------------ case 7 of 10


def test_07_provider_timeout_fails_safe(adapter):
    gateway = ModelGateway(adapter(fail_with=ProviderTimeout("deadline exceeded")))
    dumped = assert_contract_valid(gateway.infer(base_request()))

    assert dumped["status"] == "FAILED_SAFE"
    assert dumped["errors"][0]["code"] == "PROVIDER_TIMEOUT"
    assert dumped["errors"][0]["retryable"] is True
    assert dumped["urgency"]["level"] == "INSUFFICIENT_INFORMATION"


def test_07b_provider_failure_fails_safe(adapter):
    gateway = ModelGateway(adapter(fail_with=ProviderFailure("upstream unavailable")))
    dumped = assert_contract_valid(gateway.infer(base_request()))
    assert dumped["errors"][0]["code"] == "INTERNAL_SAFE_FAILURE"


# ------------------------------------------------------------------ case 8 of 10


def test_08_malformed_provider_output_is_quarantined(adapter):
    """A broken adapter must never be partially rendered."""

    class Broken(adapter):
        def infer(self, request):
            return {"urgency": "totally not a ProviderOutput"}

    dumped = assert_contract_valid(ModelGateway(Broken()).infer(base_request()))
    assert dumped["status"] == "FAILED_SAFE"
    assert dumped["errors"][0]["code"] == "INVALID_PROVIDER_OUTPUT"
    assert dumped["care_pathways"] == []


def test_08b_unparsable_request_still_returns_a_contract_valid_refusal(adapter):
    dumped = assert_contract_valid(ModelGateway(adapter()).infer({"nonsense": True}))
    assert dumped["errors"][0]["code"] == "INVALID_REQUEST"
    assert dumped["human_review"]["required"] is True


def test_08c_unsupported_contract_version_fails_safe(adapter):
    payload = base_request()
    payload["contract_version"] = "2.0.0"
    dumped = assert_contract_valid(ModelGateway(adapter()).infer(payload))
    assert dumped["errors"][0]["code"] == "INVALID_REQUEST"


# ------------------------------------------------------------------ case 9 of 10


def test_09_requests_are_idempotent(adapter):
    gateway = ModelGateway(adapter())
    first = gateway.infer(base_request())
    second = gateway.infer(base_request())

    assert first.response_id == second.response_id
    assert first.provenance.input_checksum == second.provenance.input_checksum
    # The provider is not called twice, so the audit trail records one call.
    assert len(gateway.audit.find("req-syn-0001")) == 1


def test_09b_checksum_covers_the_evidence_set(adapter):
    gateway = ModelGateway(adapter())
    original = gateway.infer(base_request())

    changed = base_request()
    changed["request_id"] = "req-syn-0002"
    changed["evidence"] = changed["evidence"][:1]
    assert gateway.infer(changed).provenance.input_checksum != original.provenance.input_checksum


def test_09c_the_same_input_gives_the_same_output(adapter):
    """Reproducibility: a fresh gateway, same request, same substantive answer."""
    first = ModelGateway(adapter()).infer(base_request())
    second = ModelGateway(adapter()).infer(base_request())

    assert first.urgency == second.urgency
    assert first.red_flags == second.red_flags
    assert first.care_pathways == second.care_pathways
    assert first.provenance.input_checksum == second.provenance.input_checksum


# ----------------------------------------------------------------- case 10 of 10


def test_10_no_provider_native_fields_reach_the_client(adapter):
    """The gateway builds the response, so an adapter cannot smuggle a field through."""
    response = ModelGateway(adapter()).infer(base_request())
    dumped = json.loads(response.model_dump_json())

    assert set(dumped) == set(RESPONSE_SCHEMA["required"])
    with pytest.raises(Exception):
        type(response).model_validate({**dumped, "provider_raw_completion": "leak"})


def test_10b_response_carries_no_free_text_reasoning_field(adapter):
    """The inspectable artifact is the executed graph, never hidden chain-of-thought."""
    dumped = json.loads(ModelGateway(adapter()).infer(base_request()).model_dump_json())
    forbidden = {"reasoning", "chain_of_thought", "thoughts", "rationale_text", "explanation"}
    assert forbidden.isdisjoint(dumped)
    assert set(dumped["graph"]) <= {"graph_schema_version", "graph_id", "graph_ref"}


# ------------------------------------------------------------------------- audit


def test_audit_records_every_call_including_refusals(adapter):
    payload = base_request()
    payload["evidence"][1]["available_at_time"] = "2026-01-01T13:00:00Z"

    gateway = ModelGateway(adapter())
    gateway.infer(payload)
    record = gateway.audit.records()[0]

    assert record.status == "FAILED_SAFE"
    assert record.error_codes == ("TEMPORAL_VIOLATION",)
    assert ("ev-002", "FUTURE_EVIDENCE") in record.rejected_evidence
    assert record.policy_version == "safety-policy-v1"
    # Not yet reviewed must never read as approved.
    assert record.reviewer_id is None and record.review_action is None


def test_audit_holds_references_never_payloads(adapter):
    gateway = ModelGateway(adapter())
    gateway.infer(base_request())
    serialised = gateway.audit.records()[0].to_json()

    # The journey fixture's chief-complaint text must not appear anywhere in the trail.
    assert "Chest discomfort" not in serialised
    assert "ev-001" in serialised


def test_offline_end_to_end_needs_no_network(adapter):
    """The default path is a mock provider and a synthetic journey, fully offline."""
    from datetime import datetime, timezone

    from shared.contracts import PatientJourney
    from shared.snapshot import take_snapshot

    journey = PatientJourney.model_validate(
        json.loads((ROOT / "tests/fixtures/patient_journey/valid.json").read_text())
    )
    snapshot = take_snapshot(journey, datetime(2026, 1, 1, 9, 15, tzinfo=timezone.utc))

    payload = base_request()
    payload["evidence"] = [
        e for e in payload["evidence"] if e["evidence_id"] in snapshot.evidence_ids
    ]
    dumped = assert_contract_valid(ModelGateway(adapter()).infer(payload))

    assert dumped["status"] in {"COMPLETED", "ABSTAINED", "ESCALATED"}
    assert "ev-003" not in json.dumps(dumped)


# --------------------------------------------------- provider-specific behaviour
# Not contract requirements. Kept apart so they cannot be read as such.


def test_mock_reports_unknown_rather_than_claiming_a_flag_is_absent():
    """The mock cannot read payloads, so UNKNOWN is the truthful state, and SR-002 then
    escalates rather than reassuring."""
    dumped = json.loads(ModelGateway(MockProvider()).infer(base_request()).model_dump_json())
    assert "UNKNOWN" in {f["state"] for f in dumped["red_flags"]}
    assert dumped["status"] == "ESCALATED"


def test_baseline_reports_not_triggered_only_where_it_has_the_evidence():
    """The baseline may clear a flag it can actually evaluate, and must report UNKNOWN
    for one it cannot — "we could not check" is not "we checked and it was clear"."""
    payload = base_request()
    payload["evidence"] = [e for e in payload["evidence"] if e["event_type"] != "VITAL"]

    dumped = json.loads(ModelGateway(BaselineProvider()).infer(payload).model_dump_json())
    states = {f["code"]: f["state"] for f in dumped["red_flags"]}
    assert states["ABNORMAL_VITALS_REQUIRE_REVIEW"] == "UNKNOWN"
    assert states["COMPLAINT_REQUIRES_CLINICIAN_REVIEW"] == "NOT_TRIGGERED"


# ------------------------------------- pre-inference screen (CLINICAL_WORKFLOW step 3)


def test_screen_runs_before_the_provider_is_called(adapter):
    """A1: the red-flag and required-information rules run before learned inference.

    Proven by ordering, not by inspection: the provider records when it was called, and
    the screen's findings must already exist by then.
    """
    calls: list[str] = []

    class Recording(adapter):
        def infer(self, request):
            calls.append("provider")
            return super().infer(request)

    provider = Recording()
    gateway = ModelGateway(provider)

    from shared.contracts.model_api import GatewayRequest

    request = GatewayRequest.model_validate(base_request())
    screen = gateway.safety.screen(request)  # what the gateway does first
    assert calls == []  # screening the request calls no provider

    gateway.infer(base_request())
    assert calls == ["provider"]
    assert "SCR-002-COMPLAINT_NOT_RULE_EVALUATED" in screen.applied_rules


def test_provider_cannot_clear_a_flag_the_screen_raised(adapter):
    """The central reason the screen runs first: a model may add or raise a flag, but it
    cannot talk one down."""

    class OverconfidentProvider(adapter):
        def infer(self, request):
            output = super().infer(request)
            cleared = tuple(
                f.model_copy(update={"state": "NOT_TRIGGERED"}) for f in output.red_flags
            ) + (
                RedFlag(code="COMPLAINT_NOT_EVALUATED_BY_RULE", state="NOT_TRIGGERED", evidence_ids=[]),
                RedFlag(code="REQUIRED_INFORMATION_INCOMPLETE", state="NOT_TRIGGERED", evidence_ids=[]),
            )
            return replace(output, red_flags=cleared, urgency=Urgency(
                level="ROUTINE_REVIEW", confidence=0.99, evidence_ids=[]))

    payload = base_request()
    payload["evidence"] = [e for e in payload["evidence"] if e["event_type"] != "VITAL"]

    dumped = assert_contract_valid(ModelGateway(OverconfidentProvider()).infer(payload))
    states = {f["code"]: f["state"] for f in dumped["red_flags"]}

    # VITAL is missing, so the screen raised REQUIRED_INFORMATION_INCOMPLETE as TRIGGERED.
    assert states["REQUIRED_INFORMATION_INCOMPLETE"] == "TRIGGERED"
    assert states["COMPLAINT_NOT_EVALUATED_BY_RULE"] == "UNKNOWN"
    # And the confident routine proposal did not survive.
    assert dumped["urgency"]["level"] in {"IMMEDIATE_REVIEW", "URGENT_REVIEW"}
    assert dumped["status"] == "ESCALATED"


def test_merge_keeps_the_more_severe_state():
    from innovation.gateway.safety import SafetyPolicy

    merged = SafetyPolicy.merge_flags(
        (RedFlag(code="SHARED", state="TRIGGERED", evidence_ids=["a"]),),
        (RedFlag(code="SHARED", state="NOT_TRIGGERED", evidence_ids=["b"]),),
    )
    assert [(f.code, f.state) for f in merged] == [("SHARED", "TRIGGERED")]


def test_merge_unions_evidence_when_severity_is_equal():
    from innovation.gateway.safety import SafetyPolicy

    merged = SafetyPolicy.merge_flags(
        (RedFlag(code="SHARED", state="UNKNOWN", evidence_ids=["a"]),),
        (RedFlag(code="SHARED", state="UNKNOWN", evidence_ids=["b"]),),
    )
    assert merged[0].evidence_ids == ["a", "b"]
