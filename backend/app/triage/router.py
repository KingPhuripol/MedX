"""/api/triage — assessment (nurse), human review (nurse), and care-facing confirmed read.

Nothing is care-facing until a nurse confirms or edits. Red-flag alerts must be acknowledged
before any review. Every 403/409 is audited as ``triage.review.denied``.

Slice i2: ``assess`` also compiles and executes the Case Graph over the same evidence at ``as_of`` and
returns its ``graph_id`` and red-flag ``screening`` block; the graph's Human Checkpoint (``human:nurse``) is
resumed only by the confirm / edit / reject endpoints below (``casegraph_run.resume``).
"""

from __future__ import annotations

import hashlib
from datetime import timedelta
from typing import Any, NoReturn

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import JSONResponse
from pydantic import AwareDatetime, BaseModel, Field
from sqlalchemy.exc import IntegrityError

from ..audit import utc_now_iso, write_audit
from ..deps import CurrentUser, get_engine, request_id, require_user
from ..gateway import service as gateway_service
from ..gateway.contract import GatewayRequest, GatewayResponse
from ..roles import Role
from . import casegraph_run, store
from . import engine as triage_engine
from .departments import BY_CODE, DEPARTMENT_LIST_VERSION, DEPARTMENTS
from .fixtures import engine_cases
from .models import TriageAssessment

router = APIRouter(prefix="/api/triage")

READ_ROLES = {Role.NURSE, Role.PHYSICIAN}
WRITE_ROLES = {Role.NURSE}
REVIEW_STATUS = {"confirm": "confirmed", "edit": "edited", "reject": "rejected"}
MAX_REASON = 1000


class AssessBody(BaseModel):
    as_of: AwareDatetime


class ReviewBody(BaseModel):
    # Lenient types so the handler decides the order of checks (auth, role, ack, fields).
    department_code: str = Field(default="", max_length=16)
    reason: str = Field(default="", max_length=MAX_REASON)
    acknowledged_alert_ids: list[str] = Field(default_factory=list, max_length=32)


def _audit(request: Request, user: CurrentUser, action: str, target: str, outcome: str, details: dict) -> None:
    write_audit(
        get_engine(request),
        action=action,
        target=target,
        outcome=outcome,
        request_id=request_id(request),
        actor_id=user.id,
        actor_role=user.role.value,
        details=details,
    )


def _deny(request: Request, user: CurrentUser, target: str, status: int, reason: str) -> NoReturn:
    _audit(request, user, "triage.review.denied", target, "denied", {"status": status, "reason": reason})
    raise HTTPException(status_code=status, detail=reason)


def _require(request: Request, user: CurrentUser, roles: set[Role], target: str) -> None:
    if user.role not in roles:
        _deny(request, user, target, 403, "role_not_permitted")


def _view(request: Request, a: TriageAssessment) -> dict[str, Any]:
    review = store.get_review(get_engine(request), a.assessment_id)
    data = a.model_dump(mode="json")
    data["graph_checkpoint_status"] = (
        casegraph_run.checkpoint_status(request.app.state.casegraph, a.graph_id) if a.graph_id else None
    )
    if review:
        data["review_status"] = REVIEW_STATUS[review["action"]]
        data["confirmed_department"] = review["final_department"]
        data["review"] = {k: review[k] for k in ("action", "final_department", "reviewer_id", "reviewer_role",
                                                 "ts_utc", "acknowledged_alert_ids", "reason_sha256")}
    else:
        data["review"] = None
    return data


def _load(request: Request, assessment_id: str) -> TriageAssessment:
    a = store.get_assessment(get_engine(request), assessment_id)
    if a is None:
        raise HTTPException(status_code=404, detail="unknown_assessment")
    return a


@router.get("/cases")
def list_cases(request: Request, user: CurrentUser = Depends(require_user)) -> dict:
    _require(request, user, READ_ROLES, "triage/cases")
    items = []
    for ref, case in engine_cases().items():
        cc = next((f.value for f in case.facts if f.kind == "chief_complaint"), None)
        latest = max(f.available_at_time for f in case.facts)
        items.append({"case_ref": ref, "chief_complaint": cc, "suggested_as_of": latest.isoformat()})
    return {"data_class": "synthetic", "cases": items}


@router.get("/departments")
def list_departments(request: Request, user: CurrentUser = Depends(require_user)) -> dict:
    _require(request, user, READ_ROLES, "triage/departments")
    return {
        "version": DEPARTMENT_LIST_VERSION,
        "departments": [{"code": d.code, "label_th": d.label_th, "label_en": d.label_en} for d in DEPARTMENTS],
    }


def _check_as_of(request: Request, user: CurrentUser, case_ref: str, case: Any, as_of: Any) -> None:
    """C3 (S4 HIGH, D-I2-2): ``as_of`` must lie within [earliest evidence, latest evidence + skew].

    A later ``as_of`` would let an assessment claim a decision time no evidence supports (stale vitals read as
    current); an earlier one would assess a case with no evidence yet. Every rejection is audited.
    """
    times = [f.available_at_time for f in case.facts]
    earliest, latest = min(times), max(times)
    skew = timedelta(seconds=float(request.app.state.settings.triage_as_of_skew_s))
    reason = None
    if as_of > latest + skew:
        reason = "as_of_beyond_evidence"
    elif as_of < earliest:
        reason = "as_of_before_evidence"
    if reason is None:
        return
    _audit(request, user, "triage.assess.rejected", f"triage/cases/{case_ref}/assess", "denied", {
        "status": 422, "reason": reason, "as_of": as_of.isoformat(), "earliest_evidence": earliest.isoformat(),
        "latest_evidence": latest.isoformat(), "skew_s": skew.total_seconds(),
    })
    raise HTTPException(status_code=422, detail=reason)


@router.post("/cases/{case_ref}/assess", status_code=201)
def assess(case_ref: str, body: AssessBody, request: Request, user: CurrentUser = Depends(require_user)) -> dict:
    _require(request, user, WRITE_ROLES, f"triage/cases/{case_ref}/assess")
    case = engine_cases().get(case_ref)
    if case is None:
        raise HTTPException(status_code=404, detail="unknown_case")
    _check_as_of(request, user, case_ref, case, body.as_of)
    engine = get_engine(request)
    provider = request.app.state.provider

    def invoke(req: GatewayRequest) -> GatewayResponse:
        return gateway_service.invoke(engine, provider, req, user, request_id=request_id(request))

    a = triage_engine.assess(case, body.as_of, invoke, actor_id=user.id)
    graph_error = None
    try:  # i2 scope 7: the Case Graph over the same evidence at the same as_of
        graph = casegraph_run.run_graph(request.app.state.casegraph, case, body.as_of, engine, provider, user,
                                        request_id(request))
        screening = casegraph_run.screening_block(graph)
        graph_alerts = sorted({x["rule_id"] for x in (casegraph_run.graph_alerts(graph) or [])})
        a = a.model_copy(update={
            "graph_id": graph.graph_id, "screening": screening,
            # an alert the graph raised always escalates, even if the engine did not raise it
            "escalation_required": a.escalation_required or bool(graph_alerts),
        })
    except Exception as exc:  # fail safe: screening shows NOT PERFORMED (unavailable) and the case escalates
        graph_error, graph_alerts = type(exc).__name__, []
        a = a.model_copy(update={"screening": casegraph_run.unavailable_screening(), "escalation_required": True})
    store.insert_assessment(engine, a)
    dept = a.department
    _audit(request, user, "triage.assess", f"assessment/{a.assessment_id}", "success", {
        "assessment_id": a.assessment_id,
        "case_ref": a.case_ref,
        "as_of": a.as_of.isoformat(),
        "ruleset_version": a.ruleset_version,
        "alert_rule_ids": [x.rule_id for x in a.alerts],
        "not_evaluable_rule_ids": [x.rule_id for x in a.not_evaluable],
        "escalation_required": a.escalation_required,
        "department_status": dept.status,
        "department_top3": [{"code": e.code, "score": e.score} for e in dept.top3],
        "missing_information": dept.missing_information,
        "provider": dept.provider,
        "model_version": dept.model_version,
        "request_sha256": dept.request_sha256,
        "graph_id": a.graph_id,
        "graph_error": graph_error,
        "graph_alert_rule_ids": graph_alerts,
        "screening_status": (a.screening or {}).get("status"),
    })
    return a.model_dump(mode="json")


@router.get("/assessments/{assessment_id}")
def get_assessment(assessment_id: str, request: Request, user: CurrentUser = Depends(require_user)) -> dict:
    _require(request, user, READ_ROLES, f"triage/assessments/{assessment_id}")
    return _view(request, _load(request, assessment_id))


@router.get("/cases/{case_ref}/confirmed")
def confirmed(case_ref: str, request: Request, user: CurrentUser = Depends(require_user)) -> Any:
    """The only care-facing read.

    Resolves against the newest assessment for the case (``as_of``, then ``created_at``), never against
    review order. A department is returned only if that newest assessment was confirmed or edited. Otherwise
    the answer is 404 ``pending_review`` and, if an assessment exists, its alerts and escalation flag are
    included so urgency from an unreviewed or rejected newer assessment is never hidden behind an older one.
    """
    _require(request, user, READ_ROLES, f"triage/cases/{case_ref}/confirmed")
    if case_ref not in engine_cases():
        raise HTTPException(status_code=404, detail="unknown_case")
    engine = get_engine(request)
    a = store.newest_assessment_for_case(engine, case_ref)
    review = store.get_review(engine, a.assessment_id) if a else None
    if a is None or review is None or review["action"] not in ("confirm", "edit"):
        pending = None
        if a is not None:
            pending = {
                "assessment_id": a.assessment_id,
                "as_of": a.as_of.isoformat(),
                "review_status": REVIEW_STATUS[review["action"]] if review else "pending_review",
                "alert_rule_ids": [x.rule_id for x in a.alerts],
                "escalation_required": a.escalation_required,
            }
        return JSONResponse(status_code=404, content={"detail": "pending_review", "newest_assessment": pending})
    dept = BY_CODE[review["final_department"]]
    return {
        "case_ref": case_ref,
        "assessment_id": a.assessment_id,
        "as_of": a.as_of.isoformat(),
        "ruleset_version": a.ruleset_version,
        "alert_rule_ids": [x.rule_id for x in a.alerts],
        "escalation_required": a.escalation_required,
        "department": {"code": dept.code, "label_th": dept.label_th, "label_en": dept.label_en},
        "review": {k: review[k] for k in ("action", "reviewer_id", "reviewer_role", "ts_utc",
                                          "acknowledged_alert_ids")},
    }


def _review(action: str, assessment_id: str, body: ReviewBody, request: Request, user: CurrentUser) -> dict:
    target = f"assessment/{assessment_id}"
    _require(request, user, WRITE_ROLES, target)
    a = _load(request, assessment_id)
    engine = get_engine(request)
    if store.get_review(engine, assessment_id) is not None:
        _deny(request, user, target, 409, "already_reviewed")

    alert_ids = [x.rule_id for x in a.alerts]
    acked = list(dict.fromkeys(body.acknowledged_alert_ids))
    if not set(acked) <= set(alert_ids):
        raise HTTPException(status_code=422, detail="unknown_alert_id")
    if a.escalation_required and set(acked) != set(alert_ids):
        _deny(request, user, target, 409, "alerts_not_acknowledged")

    stores = request.app.state.casegraph
    if a.graph_id is not None:  # i2: the graph checkpoint must be resumable before any review is written
        refusal = casegraph_run.resume_refusal(stores, a.graph_id, user.role.value)
        if refusal is not None:
            _deny(request, user, target, 409, refusal)

    reason = body.reason.strip()
    code = body.department_code.strip()
    final: str | None
    if action == "confirm":
        if a.department.status != "suggested" or code not in {e.code for e in a.department.top3}:
            raise HTTPException(status_code=422, detail="department_not_in_top3")
        final = code
    elif action == "edit":
        if code not in BY_CODE:
            raise HTTPException(status_code=422, detail="unknown_department")
        if not reason:
            raise HTTPException(status_code=422, detail="reason_required")
        final = code
    else:
        if not reason:
            raise HTTPException(status_code=422, detail="reason_required")
        final = None

    ts = utc_now_iso()
    reason_sha = hashlib.sha256(reason.encode("utf-8")).hexdigest() if reason else None
    try:
        store.insert_review(
            engine,
            assessment_id=assessment_id,
            action=action,
            final_department=final,
            reviewer_id=user.id,
            reviewer_role=user.role.value,
            ts_utc=ts,
            acknowledged_alert_ids=sorted(acked),
            reason=reason or None,
            reason_sha256=reason_sha,
        )
    except IntegrityError:
        _deny(request, user, target, 409, "already_reviewed")

    confirmation = None
    if a.graph_id is not None:  # the only production path that resumes the Case Graph checkpoint
        result = casegraph_run.resume(
            stores, a.graph_id, action, str(user.id), user.role.value,
            edited_payload={"final_department": final, "reason_sha256": reason_sha,
                            "acknowledged_alert_ids": sorted(acked)} if action == "edit" else None,
        )
        confirmation = {"graph_id": a.graph_id, "confirmed_at": result.confirmed_at.isoformat(),
                        "checkpoint_input_hash": result.checkpoint_input_hash}

    dept = a.department
    _audit(request, user, f"triage.review.{action}", target, "success", {
        "assessment_id": assessment_id,
        "reviewer_id": user.id,
        "reviewer_role": user.role.value,
        "ts_utc": ts,
        "original_suggestion": {
            "status": dept.status,
            "top3": [{"code": e.code, "score": e.score} for e in dept.top3],
            "missing_information": dept.missing_information,
            "alert_rule_ids": alert_ids,
        },
        "final_department": final,
        "acknowledged_alert_ids": sorted(acked),
        "reason_sha256": reason_sha,
        "graph_checkpoint": confirmation,
    })
    return _view(request, a)


@router.post("/assessments/{assessment_id}/confirm")
def confirm(assessment_id: str, body: ReviewBody, request: Request, user: CurrentUser = Depends(require_user)) -> dict:
    return _review("confirm", assessment_id, body, request, user)


@router.post("/assessments/{assessment_id}/edit")
def edit(assessment_id: str, body: ReviewBody, request: Request, user: CurrentUser = Depends(require_user)) -> dict:
    return _review("edit", assessment_id, body, request, user)


@router.post("/assessments/{assessment_id}/reject")
def reject(assessment_id: str, body: ReviewBody, request: Request, user: CurrentUser = Depends(require_user)) -> dict:
    return _review("reject", assessment_id, body, request, user)
