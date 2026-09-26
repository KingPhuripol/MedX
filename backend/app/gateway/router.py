"""POST /api/gateway/invoke — authenticated, always audited, fails safe."""

from __future__ import annotations

import time

from fastapi import APIRouter, Depends, Request

from ..audit import write_audit
from ..deps import CurrentUser, get_engine, request_id, require_user
from .contract import CONTRACT_VERSION, GatewayRequest, GatewayResponse, canonical_sha256
from .provider import Provider, ProviderResult

router = APIRouter(prefix="/api/gateway")


def get_provider(request: Request) -> Provider:
    return request.app.state.provider


@router.post("/invoke", response_model=GatewayResponse)
def invoke(
    body: GatewayRequest,
    request: Request,
    user: CurrentUser = Depends(require_user),
    provider: Provider = Depends(get_provider),
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
        get_engine(request),
        action="gateway.invoke",
        target=f"task/{body.task}",
        outcome=response.status,
        request_id=request_id(request),
        actor_id=user.id,
        actor_role=user.role.value,
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
