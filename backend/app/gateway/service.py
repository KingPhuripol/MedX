"""Audited gateway invocation shared by the HTTP route and in-process callers (e.g. the Voice Agent).

Every model call goes through ``invoke_audited`` so it writes exactly one ``gateway.invoke`` audit row.
"""

from __future__ import annotations

import time

from sqlalchemy import Engine

from ..audit import write_audit
from ..deps import CurrentUser
from .contract import CONTRACT_VERSION, GatewayRequest, GatewayResponse, canonical_sha256
from .provider import Provider, ProviderResult


def invoke_audited(
    engine: Engine,
    provider: Provider,
    request: GatewayRequest,
    actor: CurrentUser | None,
    *,
    request_id: str = "in-process",
) -> GatewayResponse:
    sha = canonical_sha256(request)
    start = time.perf_counter()
    try:
        result = provider.invoke(request, sha)
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
        target=f"task/{request.task}",
        outcome=response.status,
        request_id=request_id,
        actor_id=actor.id if actor else None,
        actor_role=actor.role.value if actor else None,
        details={
            "provider": response.provider,
            "model_version": response.model_version,
            "contract_version": response.contract_version,
            "data_class": request.data_class.value,
            "request_sha256": sha,
            "status": response.status,
            "reason": response.reason,
            "latency_ms": response.latency_ms,
        },
    )
    return response
