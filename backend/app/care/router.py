"""/api/care — care suggestion for physician review (slice s6). Physician only, read and write.

Only dev-split cases are served. Nothing is care-facing until a physician confirms or edits. Every alert
and (when screening is not ``evaluated``) the screening banner must be acknowledged before any review.
Every 401/403/409 is audited as ``care.review.denied``. Reason and transcript text never enter the audit log.
"""

from __future__ import annotations

import hashlib
import uuid
from typing import Any, NoReturn

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field
from sqlalchemy.exc import IntegrityError

from ..audit import utc_now_iso, write_audit
from ..deps import CurrentUser, get_engine, optional_user, request_id
from ..gateway import service as gateway_service
from ..gateway.contract import GatewayRequest, GatewayResponse
from ..roles import Role
from . import dataset, engine, store
from .models import MAX_NEXT_INFO, MAX_PATHWAYS, CareAssessment
from .ruleset import rules

router = APIRouter(prefix="/api/care")

SPLIT = "dev"  # the test and train splits are never served
ROLES = {Role.PHYSICIAN}
REVIEW_STATUS = {"confirm": "confirmed", "edit": "edited", "reject": "rejected"}
MAX_REASON = 1000


class AssessBody(BaseModel):
    decision_point: str = Field(pattern=r"^T[12]$")


class ReviewBody(BaseModel):
    # Lenient types so the handler decides the order of checks (auth, role, ack, fields).
    acknowledged_alert_ids: list[str] = Field(default_factory=list, max_length=32)
    screening_acknowledged: bool = False
    reason: str = Field(default="", max_length=MAX_REASON)
    next_information: list[str] = Field(default_factory=list, max_length=16)
    pathway_options: list[str] = Field(default_factory=list, max_length=16)


def _audit(request: Request, user: CurrentUser | None, action: str, target: str, outcome: str, details: dict) -> None:
    write_audit(get_engine(request), action=action, target=target, outcome=outcome, request_id=request_id(request),
                actor_id=user.id if user else None, actor_role=user.role.value if user else None, details=details)


def _deny(request: Request, user: CurrentUser | None, target: str, status: int, reason: str) -> NoReturn:
    _audit(request, user, "care.review.denied", target, "denied", {"status": status, "reason": reason})
    raise HTTPException(status_code=status, detail=reason)


def physician(request: Request) -> CurrentUser:
    target = f"care{request.url.path.removeprefix('/api/care')}"
    user = optional_user(request)
    if user is None:
        _deny(request, None, target, 401, "authentication required")
    if user.role not in ROLES:
        _deny(request, user, target, 403, "role_not_permitted")
    return user


def _unavailable() -> JSONResponse:
    return JSONResponse(status_code=503, content={"detail": "dataset_missing: run make data"})


def _codes(a: CareAssessment) -> dict[str, list[str]]:
    return a.codes()


def _view(request: Request, a: CareAssessment) -> dict[str, Any]:
    review = store.get_review(get_engine(request), a.assessment_id)
    data = a.model_dump(mode="json")
    if review:
        data["review_status"] = REVIEW_STATUS[review["action"]]
        data["review"] = {k: review[k] for k in ("action", "final_codes", "reviewer_id", "reviewer_role", "ts_utc",
                                                 "acknowledged_alert_ids", "screening_acknowledged", "reason_sha256")}
    else:
        data["review"] = None
    return data


def _load(request: Request, assessment_id: str) -> CareAssessment:
    a = store.get_assessment(get_engine(request), assessment_id)
    if a is None:
        raise HTTPException(status_code=404, detail="unknown_assessment")
    return a


@router.get("/cases")
def list_cases(user: CurrentUser = Depends(physician)) -> Any:
    try:
        ids = dataset.case_ids(SPLIT)
    except dataset.DatasetMissing:
        return _unavailable()
    cases = []
    for cid in ids:
        dps = []
        for dp in dataset.DECISION_POINTS:
            snap = dataset.load_snapshot(SPLIT, cid, dp)
            if snap is not None:
                dps.append({"decision_point": dp, "as_of": snap.get("as_of")})
        cases.append({"case_id": cid, "decision_points": dps})
    return {"data_class": "synthetic", "split": SPLIT, "cases": cases}


@router.get("/vocabulary")
def vocabulary(user: CurrentUser = Depends(physician)) -> dict:
    v = rules()["vocabulary"]
    return {
        "rules_version": rules()["version"],
        "next_information": [{"code": c, "display": x["display_en"], "display_th": x["display_th"]}
                             for c, x in v["next_info"].items()],
        "pathway_options": [{"code": c, "display": x["display_en"], "display_th": x["display_th"]}
                            for c, x in v["pathways"].items()],
    }


@router.post("/cases/{case_id}/assess", status_code=201)
def assess(case_id: str, body: AssessBody, request: Request, user: CurrentUser = Depends(physician)) -> Any:
    try:
        snap = dataset.load_snapshot(SPLIT, case_id, body.decision_point)
    except dataset.DatasetMissing:
        return _unavailable()
    if snap is None:
        raise HTTPException(status_code=404, detail="unknown_case")
    db = get_engine(request)
    provider = request.app.state.provider

    def invoke(req: GatewayRequest) -> GatewayResponse:
        return gateway_service.invoke_audited(db, provider, req, user, request_id=request_id(request))

    result = engine.assess(snap, invoke, decision_point=body.decision_point)
    a = CareAssessment(**result.model_dump(), assessment_id=uuid.uuid4().hex, created_at=utc_now_iso(),
                       created_by=user.id)
    store.insert_assessment(db, a)
    _audit(request, user, "care.assess", f"care_assessment/{a.assessment_id}", "success", {
        "assessment_id": a.assessment_id,
        "case_id": a.case_id,
        "decision_point": a.decision_point,
        "as_of": a.as_of,
        "status": a.status,
        "reason": a.reason,
        "codes": _codes(a),
        "missing_information": a.missing_information,
        "screening_status": a.red_flag_screening.status,
        "alert_rule_ids": [x.rule_id for x in a.alerts],
        "escalation_required": a.escalation_required,
        "provider": a.provider,
        "model_version": a.model_version,
        "rules_version": a.rules_version,
        "request_sha256": a.request_sha256,
    })
    return JSONResponse(status_code=201, content=_view(request, a))


@router.get("/assessments/{assessment_id}")
def get_assessment(assessment_id: str, request: Request, user: CurrentUser = Depends(physician)) -> dict:
    return _view(request, _load(request, assessment_id))


@router.get("/cases/{case_id}/confirmed")
def confirmed(case_id: str, request: Request, user: CurrentUser = Depends(physician)) -> Any:
    """The only care-facing read: the newest assessment for the case, and only if it was confirmed or edited.

    Otherwise 404 ``pending_review`` with the newest assessment's alerts, so urgency is never hidden.
    """
    db = get_engine(request)
    a = store.newest_assessment_for_case(db, case_id)
    review = store.get_review(db, a.assessment_id) if a else None
    if a is None or review is None or review["action"] not in ("confirm", "edit"):
        pending = None if a is None else {
            "assessment_id": a.assessment_id,
            "decision_point": a.decision_point,
            "as_of": a.as_of,
            "review_status": REVIEW_STATUS[review["action"]] if review else "pending_review",
            "alert_rule_ids": [x.rule_id for x in a.alerts],
            "escalation_required": a.escalation_required,
            "screening_status": a.red_flag_screening.status,
        }
        return JSONResponse(status_code=404, content={"detail": "pending_review", "newest_assessment": pending})
    return {
        "case_id": case_id,
        "assessment_id": a.assessment_id,
        "decision_point": a.decision_point,
        "as_of": a.as_of,
        "alert_rule_ids": [x.rule_id for x in a.alerts],
        "escalation_required": a.escalation_required,
        "screening_status": a.red_flag_screening.status,
        "final_codes": review["final_codes"],
        "output_label": a.output_label,
        "review": {k: review[k] for k in ("action", "reviewer_id", "reviewer_role", "ts_utc",
                                          "acknowledged_alert_ids", "screening_acknowledged")},
    }


def _edited_codes(body: ReviewBody) -> dict[str, list[str]]:
    v = rules()["vocabulary"]
    ni, cp = list(dict.fromkeys(body.next_information)), list(dict.fromkeys(body.pathway_options))
    if not set(ni) <= set(v["next_info"]) or not set(cp) <= set(v["pathways"]):
        raise HTTPException(status_code=422, detail="code_outside_vocabulary")
    if len(ni) > MAX_NEXT_INFO or len(cp) > MAX_PATHWAYS:
        raise HTTPException(status_code=422, detail="too_many_codes")
    if not ni and not cp:
        raise HTTPException(status_code=422, detail="codes_required")
    return {"next_information": ni, "pathway_options": cp}


def _review(action: str, assessment_id: str, body: ReviewBody, request: Request, user: CurrentUser) -> dict:
    target = f"care_assessment/{assessment_id}"
    a = _load(request, assessment_id)
    db = get_engine(request)
    if store.get_review(db, assessment_id) is not None:
        _deny(request, user, target, 409, "already_reviewed")

    alert_ids = [x.rule_id for x in a.alerts]
    acked = list(dict.fromkeys(body.acknowledged_alert_ids))
    if not set(acked) <= set(alert_ids):
        raise HTTPException(status_code=422, detail="unknown_alert_id")
    if set(acked) != set(alert_ids):
        _deny(request, user, target, 409, "alerts_not_acknowledged")
    if a.red_flag_screening.status != "evaluated" and not body.screening_acknowledged:
        _deny(request, user, target, 409, "screening_not_acknowledged")

    reason = body.reason.strip()
    final: dict[str, list[str]] | None
    if action == "confirm":
        if a.status != "suggested":
            raise HTTPException(status_code=422, detail="nothing_to_confirm")
        final = _codes(a)
    elif action == "edit":
        if not reason:
            raise HTTPException(status_code=422, detail="reason_required")
        final = _edited_codes(body)
    else:
        if not reason:
            raise HTTPException(status_code=422, detail="reason_required")
        final = None

    ts = utc_now_iso()
    reason_sha = hashlib.sha256(reason.encode("utf-8")).hexdigest() if reason else None
    try:
        store.insert_review(db, assessment_id=assessment_id, action=action, final_codes=final, reviewer_id=user.id,
                            reviewer_role=user.role.value, ts_utc=ts, acknowledged_alert_ids=sorted(acked),
                            screening_acknowledged=body.screening_acknowledged, reason=reason or None,
                            reason_sha256=reason_sha)
    except IntegrityError:
        _deny(request, user, target, 409, "already_reviewed")

    _audit(request, user, f"care.review.{action}", target, "success", {
        "assessment_id": assessment_id,
        "reviewer_id": user.id,
        "reviewer_role": user.role.value,
        "ts_utc": ts,
        "original_suggestion": {
            "status": a.status,
            "codes": _codes(a),
            "missing_information": a.missing_information,
            "alert_rule_ids": alert_ids,
            "screening_status": a.red_flag_screening.status,
        },
        "final_codes": final,
        "acknowledged_alert_ids": sorted(acked),
        "screening_acknowledged": body.screening_acknowledged,
        "reason_sha256": reason_sha,
    })
    return _view(request, a)


@router.post("/assessments/{assessment_id}/confirm")
def confirm(assessment_id: str, body: ReviewBody, request: Request, user: CurrentUser = Depends(physician)) -> dict:
    return _review("confirm", assessment_id, body, request, user)


@router.post("/assessments/{assessment_id}/edit")
def edit(assessment_id: str, body: ReviewBody, request: Request, user: CurrentUser = Depends(physician)) -> dict:
    return _review("edit", assessment_id, body, request, user)


@router.post("/assessments/{assessment_id}/reject")
def reject(assessment_id: str, body: ReviewBody, request: Request, user: CurrentUser = Depends(physician)) -> dict:
    return _review("reject", assessment_id, body, request, user)
