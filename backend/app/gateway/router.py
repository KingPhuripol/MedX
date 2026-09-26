"""POST /api/gateway/invoke — authenticated, always audited, fails safe."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Request

from ..audit import write_audit
from ..deps import CurrentUser, get_engine, request_id, require_user
from .contract import GatewayRequest, GatewayResponse
from .provider import Provider
from .service import audit_details, invoke_provider

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
    response = invoke_provider(provider, body)
    write_audit(
        get_engine(request),
        action="gateway.invoke",
        target=f"task/{body.task}",
        outcome=response.status,
        request_id=request_id(request),
        actor_id=user.id,
        actor_role=user.role.value,
        details=audit_details(body, response),
    )
    return response
