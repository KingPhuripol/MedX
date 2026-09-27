"""Deterministic offline mock provider (default). No network, no randomness.

Tasks may register a pure handler via ``app.gateway.register_mock_task``; unregistered tasks
keep the s0 hash-placeholder output.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from ..contract import GatewayRequest
from ..provider import ProviderResult

MOCK_LABEL = "MOCK — not clinical"

MockHandler = Callable[[dict[str, Any]], dict[str, Any]]
_TASK_HANDLERS: dict[str, MockHandler] = {}


def register_task(task: str, handler: MockHandler) -> None:
    """Register a pure, deterministic handler ``inputs -> output`` for one task name."""
    _TASK_HANDLERS[task] = handler


class MockProvider:
    name = "mock"
    model_version = "mock-0.1.0"

    def invoke(self, request: GatewayRequest, request_sha256: str) -> ProviderResult:
        handler = _TASK_HANDLERS.get(request.task)
        if handler is not None:
            output = dict(handler(request.inputs))
            output["label"] = MOCK_LABEL  # always labelled, whatever the handler returns
            return ProviderResult(status="ok", model_version=self.model_version, output=output)
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
