"""Shared fail-safe gateway invocation used by the HTTP router and in-process clients.

Keeps one definition of: canonical request hash, provider-exception containment, output only on
``ok``, and the audit ``details`` fields (hashes/references only, never raw inputs).
``invoke_audited`` writes exactly one ``gateway.invoke`` audit row per call (Voice Agent, router);
``invoke_provider`` + ``audit_details`` serve callers that write their own audit row (Case Graph).
"""

from __future__ import annotations

import time
from typing import Any

from sqlalchemy import Engine

from ..audit import write_audit
from ..deps import CurrentUser
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


def invoke_audited(
    engine: Engine,
    provider: Provider,
    request: GatewayRequest,
    actor: CurrentUser | None,
    *,
    request_id: str = "in-process",
) -> GatewayResponse:
    response = invoke_provider(provider, request)
    write_audit(
        engine,
        action="gateway.invoke",
        target=f"task/{request.task}",
        outcome=response.status,
        request_id=request_id,
        actor_id=actor.id if actor else None,
        actor_role=actor.role.value if actor else None,
        details=audit_details(request, response),
    )
    return response


# slice s4 callers use service.invoke; same audited path.
invoke = invoke_audited
