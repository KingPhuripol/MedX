"""/api/voice — nurse role only. No PUT/PATCH/DELETE routes."""

from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import AwareDatetime, TypeAdapter, ValidationError

from ..deps import CurrentUser, get_engine, request_id, require_user
from ..roles import Role
from . import service
from .models import AddTurnBody, StartSessionBody

router = APIRouter(prefix="/api/voice")
_AWARE = TypeAdapter(AwareDatetime)


def require_nurse(user: CurrentUser = Depends(require_user)) -> CurrentUser:
    if user.role is not Role.NURSE:
        raise HTTPException(status_code=403, detail="voice intake is for the nurse role")
    return user


def _ctx(request: Request, user: CurrentUser) -> service.VoiceContext:
    return service.VoiceContext(
        engine=get_engine(request), provider=request.app.state.provider, actor=user, request_id=request_id(request)
    )


def _now(request: Request) -> datetime:
    clock = getattr(request.app.state, "voice_clock", None)
    return clock() if clock else datetime.now(timezone.utc)


def _run(fn, *args):
    try:
        return fn(*args)
    except service.VoiceError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.detail) from None


@router.post("/sessions", status_code=201)
def start(body: StartSessionBody, request: Request, user: CurrentUser = Depends(require_nurse)) -> dict:
    return _run(service.start_session, _ctx(request, user), body, _now(request))


@router.post("/sessions/{session_id}/turns")
def add_turn(session_id: str, body: AddTurnBody, request: Request, user: CurrentUser = Depends(require_nurse)) -> dict:
    return _run(service.add_turn, _ctx(request, user), session_id, body, _now(request))


@router.get("/sessions/{session_id}")
def get_session(session_id: str, request: Request, user: CurrentUser = Depends(require_nurse)) -> dict:
    return _run(service.get_session, _ctx(request, user), session_id)


@router.get("/sessions/{session_id}/facts")
def get_facts(
    session_id: str,
    request: Request,
    as_of: str | None = Query(default=None, max_length=64),
    user: CurrentUser = Depends(require_nurse),
) -> dict:
    parsed = None
    if as_of is not None:
        try:
            parsed = _AWARE.validate_python(as_of)
        except ValidationError:
            raise HTTPException(status_code=422, detail="as_of must be a timezone-aware ISO-8601 time") from None
    return _run(service.facts_as_of, _ctx(request, user), session_id, parsed)


@router.post("/sessions/{session_id}/finish")
def finish(session_id: str, request: Request, user: CurrentUser = Depends(require_nurse)) -> dict:
    return _run(service.finish, _ctx(request, user), session_id, _now(request))
