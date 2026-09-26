import json
from dataclasses import replace

import httpx
import pytest

from app.gateway import CONTRACT_VERSION, build_provider

EXTERNAL_URL = "http://external.invalid/v1"
NON_SYNTHETIC = ["mimic", "hospital", "real", "unknown"]


def body(data_class="synthetic", **inputs):
    return {"task": "echo", "inputs": inputs or {"note": "synthetic fixture"}, "data_class": data_class}


class Recorder:
    """httpx.MockTransport that records every outbound request."""

    def __init__(self, handler):
        self.requests: list[httpx.Request] = []
        self._handler = handler
        self.transport = httpx.MockTransport(self._handle)

    def _handle(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        return self._handler(request)


def ok_handler(request: httpx.Request) -> httpx.Response:
    return httpx.Response(
        200,
        json={
            "id": "cmpl-1",
            "object": "chat.completion",
            "model": "ext-model-2026-01",
            "choices": [{"index": 0, "message": {"role": "assistant", "content": "synthetic reply"}}],
            "usage": {"prompt_tokens": 1},
        },
    )


@pytest.fixture
def use_external(app, settings):
    """Install the external adapter behind the gateway with a recording MockTransport."""

    def _install(handler=ok_handler, enabled=True):
        rec = Recorder(handler)
        s = replace(settings, external_enabled=enabled, external_base_url=EXTERNAL_URL, external_model="ext-cfg")
        app.state.provider = build_provider("openai_compatible", s, transport=rec.transport)
        return rec

    return _install


def test_default_provider_is_mock(client, login):
    assert client.get("/api/health").json()["default_provider"] == "mock"
    login("nurse1")
    resp = client.post("/api/gateway/invoke", json=body())
    data = resp.json()
    assert resp.status_code == 200
    assert data["status"] == "ok" and data["provider"] == "mock"
    assert data["contract_version"] == CONTRACT_VERSION == "0.1.0"
    assert data["output"]["label"] == "MOCK — not clinical"


def test_mock_deterministic(client, login):
    login("physician1")
    a = client.post("/api/gateway/invoke", json=body(x=1, y="z")).json()
    b = client.post("/api/gateway/invoke", json=body(y="z", x=1)).json()
    assert json.dumps(a["output"]).encode() == json.dumps(b["output"]).encode()
    assert a["request_sha256"] == b["request_sha256"]
    c = client.post("/api/gateway/invoke", json=body(x=2)).json()
    assert c["output"] != a["output"]


def test_gateway_requires_auth(client):
    resp = client.post("/api/gateway/invoke", json=body())
    assert resp.status_code == 401


def test_external_adapter_disabled_by_default(client, login, use_external):
    rec = use_external(enabled=False)
    login("nurse1")
    data = client.post("/api/gateway/invoke", json=body("synthetic")).json()
    assert (data["status"], data["reason"], data["output"]) == ("rejected", "adapter_disabled", None)
    assert rec.requests == []


def test_external_disabled_by_default_from_env(settings):
    from app.config import Settings

    assert Settings.from_env().external_enabled is False


@pytest.mark.parametrize("data_class", NON_SYNTHETIC)
def test_external_adapter_rejects_non_synthetic(client, login, use_external, data_class):
    login("nurse1")
    for enabled in (True, False):  # policy wins even when GATEWAY_EXTERNAL_ENABLED=true
        rec = use_external(enabled=enabled)
        resp = client.post("/api/gateway/invoke", json=body(data_class))
        data = resp.json()
        assert resp.status_code == 200
        assert (data["status"], data["reason"], data["output"]) == ("rejected", "policy_non_synthetic", None)
        assert rec.requests == []


def test_missing_data_class_is_422(client, login, use_external):
    rec = use_external(enabled=True)
    login("nurse1")
    payload = body()
    del payload["data_class"]
    assert client.post("/api/gateway/invoke", json=payload).status_code == 422
    assert client.post("/api/gateway/invoke", json=body("SYNTHETIC")).status_code == 422
    assert rec.requests == []


def _timeout(request):
    raise httpx.ReadTimeout("timed out", request=request)


FAILURES = {
    "timeout": (_timeout, "provider_timeout"),
    "http_5xx": (lambda r: httpx.Response(503, json={"error": {"message": "overloaded"}}), "provider_http_error"),
    "malformed": (lambda r: httpx.Response(200, content=b"{not json"), "provider_invalid_response"),
    "schema_invalid": (lambda r: httpx.Response(200, json={"model": "m", "choices": []}), "provider_invalid_response"),
}


@pytest.mark.parametrize("mode", list(FAILURES))
def test_external_adapter_fail_safe(client, login, use_external, mode):
    handler, reason = FAILURES[mode]
    rec = use_external(handler)
    login("nurse1")
    resp = client.post("/api/gateway/invoke", json=body())
    assert resp.status_code == 200
    data = resp.json()
    assert (data["status"], data["output"], data["reason"]) == ("error", None, reason)
    assert "Traceback" not in resp.text and "overloaded" not in resp.text
    assert len(rec.requests) == 1


def test_external_adapter_synthetic_happy_path(client, login, use_external):
    rec = use_external()
    login("nurse1")
    data = client.post("/api/gateway/invoke", json=body()).json()
    assert data["status"] == "ok"
    assert data["provider"] == "openai_compatible"
    assert data["model_version"] == "ext-model-2026-01"
    assert data["output"] == {"text": "synthetic reply"}  # no provider-native fields leak
    assert set(data) == {
        "status", "provider", "model_version", "contract_version", "output", "reason", "latency_ms", "request_sha256",
    }
    assert len(rec.requests) == 1
    assert str(rec.requests[0].url) == f"{EXTERNAL_URL}/chat/completions"


def test_provider_exception_fails_safe(client, login, app):
    class Boom:
        name = "boom"

        def invoke(self, request, sha):
            raise RuntimeError("secret internals")

    app.state.provider = Boom()
    login("nurse1")
    resp = client.post("/api/gateway/invoke", json=body())
    assert resp.status_code == 200
    assert resp.json()["status"] == "error" and resp.json()["output"] is None
    assert "secret internals" not in resp.text
