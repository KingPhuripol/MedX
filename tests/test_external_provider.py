"""Unit tests for ExternalPrototypeProvider — validating DEC-0003 and DEC-0006."""

import json
from pathlib import Path
import httpx
import pytest

from innovation.gateway import ModelGateway
from innovation.gateway.providers.base import ProviderFailure, ProviderTimeout
from innovation.gateway.providers.external import ExternalPrototypeProvider
from innovation.gateway.registry import build_provider
from shared.contracts.model_api import GatewayRequest

ROOT = Path(__file__).resolve().parents[1]


def sample_request_dict() -> dict:
    return json.loads((ROOT / "tests/fixtures/model_api/request.json").read_text())


def test_external_prototype_default_initialization():
    provider = ExternalPrototypeProvider(api_key="test-key")
    assert provider.name == "external_prototype"
    assert "TEXT" in provider.supported_modalities()
    assert "STRUCTURED" in provider.supported_modalities()


def test_external_prototype_offline_fallback():
    provider = ExternalPrototypeProvider(api_key="")
    req = GatewayRequest.model_validate(sample_request_dict())
    output = provider.infer(req)
    assert output.urgency.level in {
        "IMMEDIATE_REVIEW",
        "URGENT_REVIEW",
        "ROUTINE_REVIEW",
        "INSUFFICIENT_INFORMATION",
    }
    assert output.model_version == provider.model_version
    assert output.provider_version == provider.provider_version


def test_external_prototype_non_synthetic_rejected_without_approval():
    provider = ExternalPrototypeProvider(api_key="test-key")
    data = sample_request_dict()
    data["authorization"]["data_classification"] = "IDENTIFIABLE_OR_LINKABLE"
    data["authorization"]["external_provider_allowed"] = False
    data["authorization"]["approval_id"] = None
    req = GatewayRequest.model_validate(data)

    with pytest.raises(ProviderFailure, match="DEC-0006"):
        provider.infer(req)


def test_external_prototype_successful_http_call():
    def mock_transport(request: httpx.Request) -> httpx.Response:
        content = {
            "choices": [
                {
                    "message": {
                        "content": json.dumps(
                            {
                                "urgency": {
                                    "level": "URGENT_REVIEW",
                                    "confidence": 0.88,
                                    "evidence_ids": ["ev-001"],
                                },
                                "red_flags": [
                                    {
                                        "code": "ABNORMAL_VITALS",
                                        "state": "TRIGGERED",
                                        "evidence_ids": ["ev-001"],
                                    }
                                ],
                                "care_pathways": [
                                    {
                                        "code": "ED_TRIAGE_PATHWAY",
                                        "rank": 1,
                                        "confidence": 0.9,
                                        "evidence_ids": ["ev-001"],
                                    }
                                ],
                                "next_information": [
                                    {
                                        "information_type": "LAB",
                                        "rank": 1,
                                        "reason_code": "CLINICAL_VERIFICATION",
                                    }
                                ],
                                "uncertainty": {
                                    "method": "external-llm-structured",
                                    "limitations": [
                                        "Synthetic evaluation prototype."
                                    ],
                                    "out_of_distribution": False,
                                    "abstention_reason": None,
                                },
                            }
                        )
                    }
                }
            ]
        }
        return httpx.Response(200, json=content)

    client = httpx.Client(transport=httpx.MockTransport(mock_transport))
    provider = ExternalPrototypeProvider(api_key="sk-test", client=client)
    req = GatewayRequest.model_validate(sample_request_dict())
    output = provider.infer(req)

    assert output.urgency.level == "URGENT_REVIEW"
    assert output.urgency.confidence == 0.88
    assert len(output.red_flags) == 1
    assert output.red_flags[0].code == "ABNORMAL_VITALS"
    assert output.red_flags[0].state == "TRIGGERED"


def test_external_prototype_timeout_handling():
    def mock_timeout(request: httpx.Request) -> httpx.Response:
        raise httpx.TimeoutException("Mocked timeout")

    client = httpx.Client(transport=httpx.MockTransport(mock_timeout))
    provider = ExternalPrototypeProvider(api_key="sk-test", client=client)
    req = GatewayRequest.model_validate(sample_request_dict())

    with pytest.raises(ProviderTimeout):
        provider.infer(req)


def test_external_prototype_http_error_handling():
    def mock_error(request: httpx.Request) -> httpx.Response:
        return httpx.Response(500, text="Internal Server Error")

    client = httpx.Client(transport=httpx.MockTransport(mock_error))
    provider = ExternalPrototypeProvider(api_key="sk-test", client=client)
    req = GatewayRequest.model_validate(sample_request_dict())

    with pytest.raises(ProviderFailure):
        provider.infer(req)


def test_gateway_with_external_prototype(monkeypatch):
    monkeypatch.setenv("FRONT_DOOR_PROVIDER", "external_prototype")
    monkeypatch.setenv("FRONT_DOOR_ALLOW_EXTERNAL", "1")

    provider = build_provider("external_prototype")
    gateway = ModelGateway(provider)
    try:
        response = gateway.infer(sample_request_dict())
        assert response.provider == "external_prototype"
        assert response.human_review.required is True
        assert response.contract_version == "1.0.0"
    finally:
        gateway.close()
