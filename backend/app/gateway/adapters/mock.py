"""Deterministic offline mock provider (default). No network, no randomness.

Registered tasks (``app.gateway.mock_tasks.register``) dispatch to their pure handler; unregistered
tasks keep the s0 hash-placeholder output. MOCK label rule (slice i2): every output carries
``label: "MOCK — not clinical"`` and a registered task reports ``mock-0.1.0+<handler version>``.
"""

from __future__ import annotations

from .. import mock_tasks
from ..contract import GatewayRequest
from ..provider import ProviderResult

MOCK_LABEL = "MOCK — not clinical"
MOCK_BASE_VERSION = "mock-0.1.0"


class MockProvider:
    name = "mock"
    model_version = MOCK_BASE_VERSION

    def invoke(self, request: GatewayRequest, request_sha256: str) -> ProviderResult:
        registered = mock_tasks.lookup(request.task)
        if registered is not None:
            fn, version = registered
            output = dict(fn(dict(request.inputs)))
            output["label"] = MOCK_LABEL  # always labelled, whatever the handler returns
            return ProviderResult(status="ok", model_version=f"{MOCK_BASE_VERSION}+{version}", output=output)
        # Output is a pure function of the canonical request hash.
        return ProviderResult(
            status="ok",
            model_version=self.model_version,
            output={
                "label": MOCK_LABEL,
                "mock_id": request_sha256[:16],
                "text": f"{MOCK_LABEL}. Placeholder output; no model was run.",
            },
        )
