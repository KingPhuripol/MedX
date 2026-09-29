"""Provider protocol. Adapters return a ProviderResult built only from contract types."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal, Protocol

from .contract import GatewayRequest


@dataclass(frozen=True)
class ProviderResult:
    status: Literal["ok", "rejected", "error"]
    model_version: str
    output: dict[str, Any] | None = None
    reason: str | None = None


class Provider(Protocol):
    name: str

    def invoke(self, request: GatewayRequest, request_sha256: str) -> ProviderResult: ...
