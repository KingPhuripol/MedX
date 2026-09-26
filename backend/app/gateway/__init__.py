"""Model Gateway: the single entry point to any model provider.

Code outside this package must not import ``app.gateway.adapters``; use ``build_provider``.
"""

from __future__ import annotations

import httpx

from ..config import Settings
from .adapters.mock import MockProvider
from .adapters.openai_compatible import OpenAICompatibleAdapter
from .contract import CONTRACT_VERSION, DataClass, GatewayRequest, GatewayResponse
from .provider import Provider, ProviderResult


def build_provider(name: str, settings: Settings, transport: httpx.BaseTransport | None = None) -> Provider:
    if name == "mock":
        return MockProvider()
    if name == "openai_compatible":
        return OpenAICompatibleAdapter(
            enabled=settings.external_enabled,
            base_url=settings.external_base_url,
            api_key=settings.external_api_key,
            model=settings.external_model,
            timeout_s=settings.gateway_timeout_s,
            transport=transport,
        )
    raise ValueError(f"unknown provider: {name}")


__all__ = [
    "CONTRACT_VERSION",
    "DataClass",
    "GatewayRequest",
    "GatewayResponse",
    "Provider",
    "ProviderResult",
    "build_provider",
]
