"""Provider independence, timeout and circuit breaker — acceptance criterion A2.

A2 asks that adapters share one gateway interface, that provider-specific fields never
escape, that the shared fixtures pass for each enabled adapter, and that timeout, invalid
schema, cost limit and an unavailable provider all fail safely.
"""

from __future__ import annotations

import json
import os
import time
from pathlib import Path

import pytest

from innovation.gateway import ModelGateway
from innovation.gateway.breaker import CircuitBreaker
from innovation.gateway.providers import BaselineProvider, MockProvider
from innovation.gateway.providers.base import ProviderFailure
from innovation.gateway.registry import (
    ENV_ALLOW_EXTERNAL,
    ENV_VAR,
    ProviderNotAvailable,
    available_providers,
    build_provider,
)

ROOT = Path(__file__).resolve().parents[1]


def base_request() -> dict:
    return json.loads((ROOT / "tests/fixtures/model_api/request.json").read_text())


# ------------------------------------------------------- configuration-only swap


def test_default_provider_is_local(monkeypatch):
    """The default must be the one that cannot leave the machine."""
    monkeypatch.delenv(ENV_VAR, raising=False)
    assert build_provider().name == "mock"


def test_provider_is_selected_by_environment_alone(monkeypatch):
    """A5: "Provider swap requires configuration only, not client/UI logic changes"."""
    monkeypatch.setenv(ENV_VAR, "baseline")
    assert build_provider().name == "baseline"
    monkeypatch.setenv(ENV_VAR, "mock")
    assert build_provider().name == "mock"


def test_swapping_the_provider_changes_no_client_code(monkeypatch):
    """The same request, unchanged, through two providers — only the answer differs."""
    responses = {}
    for name in ("mock", "baseline"):
        monkeypatch.setenv(ENV_VAR, name)
        gateway = ModelGateway(build_provider())
        responses[name] = json.loads(gateway.infer(base_request()).model_dump_json())

    assert responses["mock"]["provider"] == "mock"
    assert responses["baseline"]["provider"] == "baseline"
    # Same shape, same required keys, same guarantees — a client cannot tell them apart
    # structurally, which is the whole point of the gateway contract.
    assert responses["mock"].keys() == responses["baseline"].keys()
    for body in responses.values():
        assert body["human_review"]["required"] is True
        assert body["contract_version"] == "1.0.0"


def test_unknown_provider_is_refused():
    with pytest.raises(ProviderNotAvailable, match="unknown provider"):
        build_provider("gpt-whatever")


def test_external_providers_are_disabled_by_default(monkeypatch):
    """A prototype that reaches an external service because nobody configured it is the
    failure DEC-0006 exists to prevent, so the registry refuses by default."""
    from innovation.gateway import registry

    monkeypatch.setitem(registry.EXTERNAL_PROVIDERS, "some_external", MockProvider)
    monkeypatch.delenv(ENV_ALLOW_EXTERNAL, raising=False)

    with pytest.raises(ProviderNotAvailable, match="external and is disabled"):
        build_provider("some_external")

    monkeypatch.setenv(ENV_ALLOW_EXTERNAL, "1")
    assert build_provider("some_external") is not None


def test_available_providers_excludes_external_unless_asked():
    assert available_providers() == ("baseline", "mock")


# ---------------------------------------------------------------------- timeout


def test_the_declared_timeout_is_actually_enforced():
    """`timeout_ms` used to be passed to providers and enforced by nobody."""

    class SlowProvider(MockProvider):
        def infer(self, request):
            time.sleep(0.5)
            return super().infer(request)

    payload = base_request()
    payload["provider_constraints"]["timeout_ms"] = 100

    gateway = ModelGateway(SlowProvider())
    started = time.monotonic()
    response = gateway.infer(payload)
    elapsed = time.monotonic() - started
    gateway.close()

    assert response.status == "FAILED_SAFE"
    assert response.errors[0].code == "PROVIDER_TIMEOUT"
    assert response.errors[0].retryable is True
    # Released on time rather than waiting out the slow provider.
    assert elapsed < 0.4, f"caller was held for {elapsed:.2f}s despite a 100 ms deadline"


def test_a_provider_within_its_deadline_is_unaffected():
    payload = base_request()
    payload["provider_constraints"]["timeout_ms"] = 5000
    gateway = ModelGateway(MockProvider())
    assert gateway.infer(payload).errors == []
    gateway.close()


# --------------------------------------------------------------- circuit breaker


def test_breaker_opens_after_repeated_failures_and_stops_calling_the_provider():
    """No hidden retry storm: a dead provider is not called on every request."""
    calls = []

    class AlwaysFails(MockProvider):
        def infer(self, request):
            calls.append(1)
            raise ProviderFailure("upstream down")

    clock = [0.0]
    gateway = ModelGateway(
        AlwaysFails(),
        breaker=CircuitBreaker(failure_threshold=2, reset_after_seconds=30, clock=lambda: clock[0]),
    )

    for i in range(5):
        payload = base_request()
        payload["request_id"] = f"req-breaker-{i:04d}"
        response = gateway.infer(payload)
        assert response.status == "FAILED_SAFE"

    gateway.close()
    # Two real attempts opened the circuit; the remaining three were refused without a call.
    assert len(calls) == 2


def test_an_open_circuit_still_returns_a_usable_contract_valid_response():
    """"Provider timeout/error → safe unavailable response; human workflow remains usable"."""

    class AlwaysFails(MockProvider):
        def infer(self, request):
            raise ProviderFailure("upstream down")

    gateway = ModelGateway(AlwaysFails(), breaker=CircuitBreaker(failure_threshold=1))
    gateway.infer(base_request())

    payload = base_request()
    payload["request_id"] = "req-breaker-open"
    response = gateway.infer(payload)
    gateway.close()

    assert response.status == "FAILED_SAFE"
    assert response.errors[0].code == "INTERNAL_SAFE_FAILURE"
    assert "circuit is OPEN" in response.errors[0].message
    assert response.human_review.required is True
    assert response.errors[0].retryable is True


def test_breaker_recovers_after_the_cooldown():
    calls = []
    failing = [True]

    class Flaky(MockProvider):
        def infer(self, request):
            calls.append(1)
            if failing[0]:
                raise ProviderFailure("upstream down")
            return super().infer(request)

    clock = [0.0]
    gateway = ModelGateway(
        Flaky(),
        breaker=CircuitBreaker(failure_threshold=1, reset_after_seconds=30, clock=lambda: clock[0]),
    )
    gateway.infer(base_request())  # opens the circuit
    assert gateway.breaker.state == "OPEN"

    clock[0] = 31  # cooldown elapses
    failing[0] = False
    payload = base_request()
    payload["request_id"] = "req-breaker-recover"
    response = gateway.infer(payload)
    gateway.close()

    assert response.status != "FAILED_SAFE"
    assert gateway.breaker.state == "CLOSED"


def test_a_malformed_return_counts_towards_the_breaker():
    """A consistently broken adapter must not be retried forever."""

    class Broken(MockProvider):
        def infer(self, request):
            return {"not": "a ProviderOutput"}

    gateway = ModelGateway(Broken(), breaker=CircuitBreaker(failure_threshold=1))
    gateway.infer(base_request())
    gateway.close()
    assert gateway.breaker.state == "OPEN"


# -------------------------------------------------------------------- cost limit


def test_paid_work_without_a_recorded_approval_is_refused():
    payload = base_request()
    payload["provider_constraints"]["cost_class"] = "APPROVED_PAID"
    payload["authorization"]["approval_id"] = None

    response = ModelGateway(MockProvider()).infer(payload)
    assert response.status == "FAILED_SAFE"
    assert response.errors[0].code == "BUDGET_EXCEEDED"


def test_paid_work_with_a_recorded_approval_proceeds():
    payload = base_request()
    payload["provider_constraints"]["cost_class"] = "APPROVED_PAID"
    payload["authorization"]["approval_id"] = "APR-0001"

    response = ModelGateway(MockProvider()).infer(payload)
    assert "BUDGET_EXCEEDED" not in [e.code for e in response.errors]


# ------------------------------------------------------- no provider fields escape


@pytest.mark.parametrize("provider_cls", [MockProvider, BaselineProvider])
def test_no_provider_specific_field_reaches_a_client(provider_cls):
    response = ModelGateway(provider_cls()).infer(base_request())
    body = json.loads(response.model_dump_json())
    schema = json.loads((ROOT / "schemas/model-api-response.schema.json").read_text())

    assert set(body) == set(schema["required"])
    # The provider name is an enum member, not free text a provider could set to anything.
    assert body["provider"] in {"mock", "external_prototype", "baseline", "team_model"}
