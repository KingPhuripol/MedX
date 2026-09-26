"""Shared fail-safe gateway invocation used by the HTTP router and in-process clients.

Keeps one definition of: canonical request hash, provider-exception containment, output only on
``ok``, and the audit ``details`` fields (hashes/references only, never raw inputs).
"""

from __future__ import annotations

import time
from typing import Any

from .contract import CONTRACT_VERSION, GatewayRequest, GatewayResponse, canonical_sha256
from .provider import Provider, ProviderResult


def invoke_provider(provider: Provider, request: GatewayRequest) -> GatewayResponse:
    sha = canonical_sha256(request)
    start = time.perf_counter()
    try:
        result = provider.invoke(request, sha)
    except Exception:  # fail safe: never surface provider internals or fabricate output
        result = ProviderResult(status="error", model_version="unknown", output=None, reason="provider_exception")
    latency_ms = round((time.perf_counter() - start) * 1000, 3)
    return GatewayResponse(
        status=result.status,
        provider=provider.name,
        model_version=result.model_version,
        contract_version=CONTRACT_VERSION,
        output=result.output if result.status == "ok" else None,
        reason=result.reason,
        latency_ms=latency_ms,
        request_sha256=sha,
    )


def audit_details(request: GatewayRequest, response: GatewayResponse) -> dict[str, Any]:
    return {
        "provider": response.provider,
        "model_version": response.model_version,
        "contract_version": response.contract_version,
        "data_class": request.data_class.value,
        "request_sha256": response.request_sha256,
        "status": response.status,
        "reason": response.reason,
        "latency_ms": response.latency_ms,
    }
