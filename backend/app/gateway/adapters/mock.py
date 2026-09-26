"""Deterministic offline mock provider (default). No network, no randomness."""

from __future__ import annotations

from .. import mock_tasks
from ..contract import GatewayRequest
from ..provider import ProviderResult

MOCK_LABEL = "MOCK — not clinical"


class MockProvider:
    name = "mock"
    model_version = "mock-0.1.0"

    def invoke(self, request: GatewayRequest, request_sha256: str) -> ProviderResult:
        registered = mock_tasks.lookup(request.task)
        if registered is not None:
            fn, version = registered
            return ProviderResult(
                status="ok",
                model_version=f"{self.model_version}+{version}",
                output=fn(dict(request.inputs)),
            )
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
