"""/api/voice — nurse role only. No PUT/PATCH/DELETE routes."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.exceptions import RequestValidationError
from pydantic import AwareDatetime, TypeAdapter, ValidationError

from ..deps import CurrentUser, get_engine, request_id, require_user
from ..roles import Role
from . import review, service
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


async def _review_body(request: Request, user: CurrentUser = Depends(require_nurse)) -> tuple[CurrentUser, Any]:
    """Read the body only after require_nurse (SPEC 3.2 order). Unparseable JSON becomes None, a row-2 schema failure."""
    try:
        return user, json.loads(await request.body())
    except ValueError:  # JSONDecodeError and UnicodeDecodeError
        return user, None


@router.post("/sessions/{session_id}/review", status_code=201)
def submit_review(session_id: str, request: Request, auth_body: tuple = Depends(_review_body)) -> dict:
    """v2d: the nurse's six decisions become case evidence, then the shared triage assess runs at submitted_at."""
    from ..triage import router as triage_router  # local: casegraph imports app.voice, triage.router imports casegraph

    user, payload = auth_body
    ctx, now = _ctx(request, user), _now(request)
    try:
        result = review.submit(ctx, session_id, payload, now)
    except review.ReviewDenied as exc:
        if exc.errors is not None:
            raise RequestValidationError(exc.errors) from None
        raise HTTPException(status_code=exc.status, detail=exc.reason) from None
    try:
        a = triage_router.run_assessment(request, user, result.case_ref, now)
    except Exception as exc:  # fail safe: the review stays committed; the nurse assesses from /nurse/triage
        review.audit_handoff(ctx, result, None, "pending", type(exc).__name__)
        a, suggestion = None, {
            "status": "pending", "assessment_id": None, "as_of": None, "reason": "assessment_unavailable",
            "top3": [], "missing_information": [], "alert_rule_ids": [], "escalation_required": None,
        }
    if a is not None:
        dept = a.department
        status = "suggested" if dept.status == "suggested" else "abstained"
        suggestion = {
            "status": status, "assessment_id": a.assessment_id, "as_of": a.as_of.isoformat(),
            "reason": None if status == "suggested" else dept.reason,
            "top3": [{"code": e.code, "label_th": e.label_th, "label_en": e.label_en, "score": e.score}
                     for e in dept.top3] if status == "suggested" else [],
            "missing_information": list(dept.missing_information),
            "alert_rule_ids": [x.rule_id for x in a.alerts], "escalation_required": a.escalation_required,
        }
        review.audit_handoff(ctx, result, a.assessment_id, dept.status, None)
    return {
        "review_id": result.review_id, "session_id": result.session_id, "patient_ref": result.patient_ref,
        "case_ref": result.case_ref, "submitted_at": result.submitted_at.isoformat(), "red_flag": result.red_flag,
        "triage_path": f"/nurse/triage/{a.assessment_id}" if a is not None else "/nurse/triage",
        "evidence_item_ids": result.evidence_item_ids, "confirmed_fields": result.confirmed_fields,
        "missing_fields": result.missing_fields,
        "department_suggestion": suggestion | {"label": "Suggestion for nurse review"},
    }
