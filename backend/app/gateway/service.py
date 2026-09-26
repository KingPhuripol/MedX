"""In-process gateway invocation shared by ``POST /api/gateway/invoke`` and server-side agents.

Always audited, fails safe: provider exceptions become ``status=error`` with no output.
"""

from __future__ import annotations

import time

from sqlalchemy import Engine

from ..audit import write_audit
from .contract import CONTRACT_VERSION, GatewayRequest, GatewayResponse, canonical_sha256
from .provider import Provider, ProviderResult


def invoke_gateway(
    engine: Engine,
    provider: Provider,
    body: GatewayRequest,
    *,
    request_id: str,
    actor_id: int | None,
    actor_role: str | None,
) -> GatewayResponse:
    sha = canonical_sha256(body)
    start = time.perf_counter()
    try:
        result = provider.invoke(body, sha)
    except Exception:  # fail safe: never surface provider internals or fabricate output
        result = ProviderResult(status="error", model_version="unknown", output=None, reason="provider_exception")
    latency_ms = round((time.perf_counter() - start) * 1000, 3)
    response = GatewayResponse(
        status=result.status,
        provider=provider.name,
        model_version=result.model_version,
        contract_version=CONTRACT_VERSION,
        output=result.output if result.status == "ok" else None,
        reason=result.reason,
        latency_ms=latency_ms,
        request_sha256=sha,
    )
    write_audit(
        engine,
        action="gateway.invoke",
        target=f"task/{body.task}",
        outcome=response.status,
        request_id=request_id,
        actor_id=actor_id,
        actor_role=actor_role,
        details={
            "provider": response.provider,
            "model_version": response.model_version,
            "contract_version": response.contract_version,
            "data_class": body.data_class.value,
            "request_sha256": sha,
            "status": response.status,
            "reason": response.reason,
            "latency_ms": response.latency_ms,
        },
    )
    return response
