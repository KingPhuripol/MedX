"""Pharmacist-only API for medication reconciliation. GET/POST only; no order routes."""

from __future__ import annotations

import hashlib
import json

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from ..audit import utc_now_iso, write_audit
from ..deps import CurrentUser, get_engine, request_id, require_user
from ..gateway import GatewayRequest, invoke_gateway
from ..roles import Role
from .db import pharma_issue_decisions, pharma_issues, pharma_runs
from .fixtures import get_fixture, list_fixtures
from .models import DecisionBody, DismissBody, ReconcileBody
from .pipeline import reconcile

router = APIRouter(prefix="/api/pharma")


def require_pharmacist(request: Request, user: CurrentUser = Depends(require_user)) -> CurrentUser:
    if user.role is not Role.PHARMACIST:
        write_audit(
            get_engine(request),
            action="pharma.access",
            target=request.url.path[:128],
            outcome="denied",
            request_id=request_id(request),
            actor_id=user.id,
            actor_role=user.role.value,
        )
        raise HTTPException(status_code=403, detail="pharmacist role required")
    return user


@router.get("/fixtures")
def fixtures(user: CurrentUser = Depends(require_pharmacist)) -> dict:
    return {"data_class": "synthetic", "fixtures": list_fixtures()}


def _load_run(engine, run_id: str) -> dict | None:
    with engine.connect() as conn:
        row = conn.execute(select(pharma_runs.c.run_json).where(pharma_runs.c.run_id == run_id)).first()
        if row is None:
            return None
        decisions = conn.execute(
            select(pharma_issue_decisions).where(pharma_issue_decisions.c.run_id == run_id)
        ).mappings().all()
    run = json.loads(row.run_json)
    by_issue = {d["issue_id"]: d for d in decisions}
    for issue in run["issues"]:
        d = by_issue.get(issue["issue_id"])
        issue["status"] = {"confirm": "confirmed", "dismiss": "dismissed"}[d["decision"]] if d else "open"
        issue["decision"] = (
            {"decision": d["decision"], "reason": d["reason"], "reviewer_role": d["reviewer_role"], "ts_utc": d["ts_utc"]}
            if d
            else None
        )
    return run


@router.post("/reconcile")
def post_reconcile(body: ReconcileBody, request: Request, user: CurrentUser = Depends(require_pharmacist)) -> dict:
    engine = get_engine(request)
    snapshot = body.snapshot
    if snapshot is None:
        snapshot = get_fixture(body.fixture_ref or "")
        if snapshot is None:
            raise HTTPException(status_code=404, detail="unknown fixture_ref")
    provider = request.app.state.provider
    rid = request_id(request)

    def invoke(req: GatewayRequest):
        return invoke_gateway(engine, provider, req, request_id=rid, actor_id=user.id, actor_role=user.role.value)

    run = reconcile(snapshot, invoke, body.mode)
    ts = utc_now_iso()
    with engine.begin() as conn:
        conn.execute(
            pharma_runs.insert().values(
                run_id=run["run_id"], ts_utc=ts, actor_id=user.id, actor_role=user.role.value,
                patient_ref=run["patient_ref"], snapshot_sha256=run["snapshot_sha256"], mode=run["mode"],
                status=run["status"], formulary_version=run["formulary_version"],
                rules_version=run["rules_version"], run_json=json.dumps(run, sort_keys=True, ensure_ascii=False),
            )
        )
        for issue in run["issues"]:
            conn.execute(
                pharma_issues.insert().values(
                    issue_id=issue["issue_id"], run_id=run["run_id"], type=issue["type"],
                    rule_id=issue["rule_id"], severity_rank=issue["severity_rank"],
                    issue_json=json.dumps(issue, sort_keys=True, ensure_ascii=False),
                )
            )
    write_audit(
        engine,
        action="pharma.reconcile",
        target=f"pharma_run/{run['run_id']}",
        outcome=run["status"],
        request_id=rid,
        actor_id=user.id,
        actor_role=user.role.value,
        details={
            "run_id": run["run_id"],
            "snapshot_sha256": run["snapshot_sha256"],
            "formulary_version": run["formulary_version"],
            "rules_version": run["rules_version"],
            "mode": run["mode"],
            "issue_count": len(run["issues"]),
            "notice_count": len(run["notices"]),
            "unchecked_comparison_count": run["unchecked_comparisons"],
        },
    )
    return _load_run(engine, run["run_id"])  # type: ignore[return-value]


@router.get("/runs/{run_id}")
def get_run(run_id: str, request: Request, user: CurrentUser = Depends(require_pharmacist)) -> dict:
    run = _load_run(get_engine(request), run_id)
    if run is None:
        raise HTTPException(status_code=404, detail="unknown run")
    return run


def _decide(issue_id: str, decision: str, reason: str | None, request: Request, user: CurrentUser) -> dict:
    engine = get_engine(request)
    with engine.connect() as conn:
        issue = conn.execute(
            select(pharma_issues.c.run_id, pharma_issues.c.rule_id).where(pharma_issues.c.issue_id == issue_id)
        ).first()
    if issue is None:
        raise HTTPException(status_code=404, detail="unknown issue")
    reason_sha = hashlib.sha256(reason.encode("utf-8")).hexdigest() if reason is not None else None
    ts = utc_now_iso()
    try:
        with engine.begin() as conn:
            conn.execute(
                pharma_issue_decisions.insert().values(
                    issue_id=issue_id, run_id=issue.run_id, rule_id=issue.rule_id, decision=decision,
                    reason=reason, reason_sha256=reason_sha, reviewer_id=user.id,
                    reviewer_role=user.role.value, ts_utc=ts,
                )
            )
    except IntegrityError:
        raise HTTPException(status_code=409, detail="issue already decided") from None
    write_audit(
        engine,
        action=f"pharma.issue.{decision}",
        target=f"pharma_issue/{issue_id}",
        outcome="recorded",
        request_id=request_id(request),
        actor_id=user.id,
        actor_role=user.role.value,
        details={
            "reviewer_id": user.id,
            "reviewer_role": user.role.value,
            "ts_utc": ts,
            "run_id": issue.run_id,
            "issue_id": issue_id,
            "rule_id": issue.rule_id,
            "reason_sha256": reason_sha,
        },
    )
    status = {"confirm": "confirmed", "dismiss": "dismissed"}[decision]
    return {"issue_id": issue_id, "run_id": issue.run_id, "status": status, "ts_utc": ts}


@router.post("/issues/{issue_id}/confirm")
def confirm(
    issue_id: str, request: Request, body: DecisionBody | None = None, user: CurrentUser = Depends(require_pharmacist)
) -> dict:
    return _decide(issue_id, "confirm", None, request, user)


@router.post("/issues/{issue_id}/dismiss")
def dismiss(issue_id: str, body: DismissBody, request: Request, user: CurrentUser = Depends(require_pharmacist)) -> dict:
    return _decide(issue_id, "dismiss", body.reason, request, user)
