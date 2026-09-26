"""POST /api/gateway/invoke — authenticated, always audited, fails safe."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Request

from ..deps import CurrentUser, get_engine, request_id, require_user
from .contract import GatewayRequest, GatewayResponse
from .provider import Provider
from .service import invoke_gateway

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
    return invoke_gateway(
        get_engine(request),
        provider,
        body,
        request_id=request_id(request),
        actor_id=user.id,
        actor_role=user.role.value,
    )
