"""Deterministic, synthetic-only clinical operations demo.

This namespace intentionally contains no clinical inference. It exposes authored
fixtures and append-only operational review events for presentation use.
"""

from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy import func, select

from ..audit import write_audit
from ..db import demo_events, demo_runs
from ..deps import CurrentUser, get_engine, request_id, require_user
from ..roles import Role
from .models import ClaimBody, HandoffBody, MedicationReviewBody, TaskReviewBody

router = APIRouter(prefix="/api/demo/v1", tags=["synthetic-demo"])

JOURNEY_ID = "medx-front-door-v1"
CASE_ID = "SYN-2026-0017"

CASE = {
    "case_id": CASE_ID,
    "display_name": "ผู้รับบริการสังเคราะห์ 017",
    "data_class": "synthetic",
    "stage": "triage_review",
    "owner": {"role": "nurse", "display": "ทีมพยาบาลคัดกรอง"},
    "safety": {
        "level": "critical",
        "label": "พบสัญญาณที่ต้องประเมินเร่งด่วน",
        "detail": "หายใจลำบากร่วมกับแน่นหน้าอก — ข้อมูลสังเคราะห์สำหรับทดสอบ red-flag precedence",
        "acknowledged": False,
    },
    "next_action": "ตรวจ red flag และทบทวนผลคัดกรอง",
    "demographics": {"age": 58, "sex": "หญิง", "hn": "SYN-HN-0017"},
    "summary": "มีอาการแน่นหน้าอก หายใจลำบาก และเวียนศีรษะ เริ่มประมาณ 40 นาทีก่อนมาถึง",
    "intake": {
        "chief_complaint": "แน่นหน้าอกและหายใจลำบาก",
        "onset": "40 นาทีก่อนมาถึง",
        "source": "บทสนทนาจำลองภาษาไทย",
        "status": "reviewed",
    },
    "triage": {
        "suggestion": "ประเมินโดยบุคลากรทันทีและส่งต่อแพทย์",
        "department": "อายุรกรรมฉุกเฉิน",
        "confidence": "ข้อเสนอจากกฎสังเคราะห์ — ต้องยืนยันโดยบุคลากร",
        "evidence_ids": ["EVD-RED-01", "EVD-VITAL-02"],
    },
    "care": {
        "status": "pending",
        "suggestion": "ตรวจทานข้อมูลประกอบและบันทึกการตัดสินใจของแพทย์",
        "evidence_ids": ["EVD-TRIAGE-03"],
    },
    "version": 1,
}

BASE_TASKS = (
    {"task_id": "task-intake-017", "case_id": CASE_ID, "role": "nurse", "kind": "intake", "label": "ตรวจข้อมูลรับเข้า", "priority": "critical"},
    {"task_id": "task-triage-017", "case_id": CASE_ID, "role": "nurse", "kind": "triage", "label": "ทบทวนการคัดกรอง", "priority": "critical"},
    {"task_id": "task-care-017", "case_id": CASE_ID, "role": "physician", "kind": "care", "label": "ตรวจ care suggestion", "priority": "warning"},
    {"task_id": "task-med-017", "case_id": CASE_ID, "role": "pharmacist", "kind": "medications", "label": "ทบทวนความคลาดเคลื่อนของยา", "priority": "warning"},
)

MEDICATIONS = {
    "case_id": CASE_ID,
    "data_class": "synthetic",
    "sources": [
        {"source_id": "med-src-interview", "label": "สัมภาษณ์ผู้รับบริการ", "recorded_value": "Aspirin 81 mg วันละครั้ง", "captured_at": "2026-09-28T02:10:00+00:00"},
        {"source_id": "med-src-referral", "label": "ใบส่งตัวสังเคราะห์", "recorded_value": "Aspirin 81 mg — ไม่ระบุความถี่", "captured_at": "2026-09-28T02:04:00+00:00"},
    ],
    "discrepancies": [
        {"review_id": "med-review-017", "type": "frequency_mismatch", "label": "ความถี่ไม่ตรงกัน", "detail": "แหล่งข้อมูลหนึ่งไม่ระบุความถี่ โปรดตรวจสอบกับข้อมูลต้นทาง", "status": "pending", "provenance": ["med-src-interview", "med-src-referral"], "version": 1}
    ],
    "actor": {"role": "system", "display": "MedX synthetic fixture"},
    "timestamp": "2026-09-28T02:10:00+00:00",
    "version": 1,
}


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds")


def _run(engine, run_id: str):
    with engine.connect() as conn:
        row = conn.execute(select(demo_runs).where(demo_runs.c.run_id == run_id)).mappings().first()
    if row is None:
        raise HTTPException(status_code=404, detail="demo run not found")
    return row


def _events(engine, run_id: str) -> list[dict]:
    with engine.connect() as conn:
        rows = conn.execute(select(demo_events).where(demo_events.c.run_id == run_id).order_by(demo_events.c.id)).mappings().all()
    return [dict(row) | {"payload": json.loads(row["payload_json"])} for row in rows]


def _append(request: Request, run_id: str, case_id: str, event_type: str, user: CurrentUser, payload: dict, task_id: str | None = None) -> dict:
    engine = get_engine(request)
    _run(engine, run_id)
    with engine.connect() as conn:
        version = int(conn.execute(select(func.count()).select_from(demo_events).where(demo_events.c.run_id == run_id)).scalar_one()) + 2
    event = {"event_id": str(uuid.uuid4()), "run_id": run_id, "case_id": case_id, "task_id": task_id, "event_type": event_type, "actor_id": user.id, "actor_role": user.role.value, "ts_utc": now_iso(), "version": version, "payload_json": json.dumps(payload, ensure_ascii=False, sort_keys=True)}
    with engine.begin() as conn:
        conn.execute(demo_events.insert().values(**event))
    write_audit(engine, action=f"demo.{event_type}", target=f"run/{run_id}/case/{case_id}", outcome="success", request_id=request_id(request), actor_id=user.id, actor_role=user.role.value, details={"task_id": task_id, "version": version})
    return {k: v for k, v in event.items() if k != "payload_json"} | {"payload": payload, "data_class": "synthetic"}


@router.get("/journeys")
def journeys(user: CurrentUser = Depends(require_user)) -> dict:
    return {"items": [{"journey_id": JOURNEY_ID, "title": "เส้นทาง Clinical Front Door", "description": "เดโมข้อมูลสังเคราะห์ครบ Nurse → Physician → Pharmacist", "roles": ["nurse", "physician", "pharmacist"], "case_count": 1, "data_class": "synthetic", "actor": {"id": user.id, "role": user.role.value}, "timestamp": "2026-09-28T00:00:00+00:00", "version": 1}]}


@router.post("/journeys/{journey_id}/runs", status_code=201)
def create_run(journey_id: str, request: Request, user: CurrentUser = Depends(require_user)) -> dict:
    if journey_id != JOURNEY_ID:
        raise HTTPException(status_code=404, detail="journey not found")
    run_id, created_at = str(uuid.uuid4()), now_iso()
    with get_engine(request).begin() as conn:
        conn.execute(demo_runs.insert().values(run_id=run_id, journey_id=journey_id, created_at=created_at, created_by=user.id, created_by_role=user.role.value, version=1))
    write_audit(get_engine(request), action="demo.run.create", target=f"run/{run_id}", outcome="success", request_id=request_id(request), actor_id=user.id, actor_role=user.role.value, details={"journey_id": journey_id, "data_class": "synthetic"})
    return {"run_id": run_id, "journey_id": journey_id, "data_class": "synthetic", "actor": {"id": user.id, "role": user.role.value}, "timestamp": created_at, "version": 1}


@router.get("/runs/{run_id}/queue")
def queue(run_id: str, request: Request, user: CurrentUser = Depends(require_user)) -> dict:
    run = _run(get_engine(request), run_id)
    events = _events(get_engine(request), run_id)
    items = []
    for base in BASE_TASKS:
        if base["role"] != user.role.value:
            continue
        task_events = [e for e in events if e["task_id"] == base["task_id"]]
        latest = task_events[-1] if task_events else None
        status = "ready"
        owner = None
        if latest and latest["event_type"] == "task.claimed":
            status, owner = "claimed", {"id": latest["actor_id"], "role": latest["actor_role"]}
        items.append(base | {"status": status, "owner": owner, "stage": base["kind"], "safety_state": "critical" if base["role"] == "nurse" else "review", "next_action": base["label"], "data_class": "synthetic", "actor": {"role": "system"}, "timestamp": run["created_at"], "version": latest["version"] if latest else 1})
    return {"run_id": run_id, "items": items, "data_class": "synthetic", "actor": {"id": user.id, "role": user.role.value}, "timestamp": now_iso(), "version": max([i["version"] for i in items], default=1)}


@router.get("/runs/{run_id}/cases/{case_id}")
def case(run_id: str, case_id: str, request: Request, user: CurrentUser = Depends(require_user)) -> dict:
    run = _run(get_engine(request), run_id)
    if case_id != CASE_ID:
        raise HTTPException(status_code=404, detail="case not found")
    events = _events(get_engine(request), run_id)
    owner = CASE["owner"]
    stage = CASE["stage"]
    for event in events:
        if event["event_type"] == "task.handoff":
            owner = {"role": event["payload"]["to_role"], "display": f"ทีม {event['payload']['to_role']}"}
            stage = {"physician": "care_review", "pharmacist": "medication_review", "nurse": "triage_review"}[event["payload"]["to_role"]]
    return CASE | {"run_id": run_id, "owner": owner, "stage": stage, "actor": {"id": user.id, "role": user.role.value}, "timestamp": run["created_at"], "version": len(events) + 1}


@router.get("/runs/{run_id}/cases/{case_id}/timeline")
def timeline(run_id: str, case_id: str, request: Request, user: CurrentUser = Depends(require_user)) -> dict:
    _run(get_engine(request), run_id)
    if case_id != CASE_ID:
        raise HTTPException(status_code=404, detail="case not found")
    base = [
        {"event_id": "evt-arrival", "kind": "intake", "title": "บันทึกข้อมูลรับเข้า", "detail": "นำเข้าบทสนทนาจำลองภาษาไทย", "actor": {"role": "nurse", "display": "พยาบาลสังเคราะห์"}, "timestamp": "2026-09-28T02:00:00+00:00", "version": 1, "data_class": "synthetic"},
        {"event_id": "evt-redflag", "kind": "safety", "title": "ตรวจพบ red flag", "detail": "หายใจลำบากร่วมกับแน่นหน้าอก", "actor": {"role": "system", "display": "ruleset v1"}, "timestamp": "2026-09-28T02:01:00+00:00", "version": 1, "data_class": "synthetic"},
    ]
    appended = [{"event_id": e["event_id"], "kind": e["event_type"], "title": {"task.claimed": "รับเคสแล้ว", "task.reviewed": "บันทึกการตรวจทานแล้ว", "task.handoff": "ส่งต่อเคสแล้ว", "medication.reviewed": "บันทึก medication review แล้ว"}.get(e["event_type"], e["event_type"]), "detail": e["payload"].get("note") or e["payload"].get("reason") or e["payload"].get("action", ""), "actor": {"id": e["actor_id"], "role": e["actor_role"]}, "timestamp": e["ts_utc"], "version": e["version"], "data_class": "synthetic"} for e in _events(get_engine(request), run_id)]
    return {"run_id": run_id, "case_id": case_id, "items": base + appended, "data_class": "synthetic", "actor": {"id": user.id, "role": user.role.value}, "timestamp": now_iso(), "version": len(appended) + 1}


@router.post("/tasks/{task_id}/claim", status_code=201)
def claim(task_id: str, body: ClaimBody, request: Request, user: CurrentUser = Depends(require_user)) -> dict:
    task = next((t for t in BASE_TASKS if t["task_id"] == task_id), None)
    if not task:
        raise HTTPException(status_code=404, detail="task not found")
    if task["role"] != user.role.value:
        raise HTTPException(status_code=403, detail="task belongs to another role")
    if any(e["task_id"] == task_id and e["event_type"] == "task.claimed" for e in _events(get_engine(request), body.run_id)):
        raise HTTPException(status_code=409, detail="task already claimed")
    return _append(request, body.run_id, task["case_id"], "task.claimed", user, {"expected_version": body.version}, task_id)


@router.post("/tasks/{task_id}/handoffs", status_code=201)
def handoff(task_id: str, body: HandoffBody, request: Request, user: CurrentUser = Depends(require_user)) -> dict:
    allowed = {Role.NURSE: Role.PHYSICIAN, Role.PHYSICIAN: Role.PHARMACIST}
    if allowed.get(user.role) is None or allowed[user.role].value != body.to_role:
        raise HTTPException(status_code=403, detail="handoff not allowed for this role transition")
    task = next((t for t in BASE_TASKS if t["task_id"] == task_id), None)
    if not task:
        raise HTTPException(status_code=404, detail="task not found")
    if user.role is Role.NURSE and "red-flag-017" not in body.acknowledged_alerts:
        raise HTTPException(status_code=422, detail="red flag acknowledgement is required")
    return _append(request, body.run_id, task["case_id"], "task.handoff", user, {"to_role": body.to_role, "note": body.note, "acknowledged_alerts": body.acknowledged_alerts, "expected_version": body.version}, task_id)


@router.post("/tasks/{task_id}/reviews/{action}", status_code=201)
def task_review(task_id: str, action: str, body: TaskReviewBody, request: Request, user: CurrentUser = Depends(require_user)) -> dict:
    task = next((t for t in BASE_TASKS if t["task_id"] == task_id), None)
    if not task or action not in {"confirm", "edit", "reject"}:
        raise HTTPException(status_code=404, detail="task review action not found")
    if task["role"] != user.role.value:
        raise HTTPException(status_code=403, detail="task belongs to another role")
    if action in {"edit", "reject"} and not body.reason.strip():
        raise HTTPException(status_code=422, detail="reason is required")
    if user.role is Role.NURSE and "red-flag-017" not in body.acknowledged_alerts:
        raise HTTPException(status_code=422, detail="red flag acknowledgement is required")
    if any(e["task_id"] == task_id and e["event_type"] == "task.reviewed" for e in _events(get_engine(request), body.run_id)):
        raise HTTPException(status_code=409, detail="task review already recorded")
    return _append(request, body.run_id, task["case_id"], "task.reviewed", user, {"action": action, "reason": body.reason, "acknowledged_alerts": body.acknowledged_alerts, "expected_version": body.version}, task_id)


@router.get("/runs/{run_id}/cases/{case_id}/medications")
def medications(run_id: str, case_id: str, request: Request, user: CurrentUser = Depends(require_user)) -> dict:
    _run(get_engine(request), run_id)
    if case_id != CASE_ID:
        raise HTTPException(status_code=404, detail="case not found")
    reviewed = [e for e in _events(get_engine(request), run_id) if e["event_type"] == "medication.reviewed"]
    data = json.loads(json.dumps(MEDICATIONS))
    if reviewed:
        data["discrepancies"][0]["status"] = reviewed[-1]["payload"]["action"]
        data["discrepancies"][0]["version"] = reviewed[-1]["version"]
    data["run_id"] = run_id
    data["actor"] = {"id": user.id, "role": user.role.value}
    return data


@router.post("/medication-reviews/{review_id}/{action}", status_code=201)
def review_medication(review_id: str, action: str, body: MedicationReviewBody, request: Request, user: CurrentUser = Depends(require_user)) -> dict:
    if user.role is not Role.PHARMACIST:
        raise HTTPException(status_code=403, detail="pharmacist role required")
    if review_id != "med-review-017" or action not in {"confirm", "edit", "reject"}:
        raise HTTPException(status_code=404, detail="medication review action not found")
    if action in {"edit", "reject"} and not body.reason.strip():
        raise HTTPException(status_code=422, detail="reason is required")
    if any(e["event_type"] == "medication.reviewed" for e in _events(get_engine(request), body.run_id)):
        raise HTTPException(status_code=409, detail="medication review already recorded")
    return _append(request, body.run_id, CASE_ID, "medication.reviewed", user, {"review_id": review_id, "action": action, "reason": body.reason, "final_value": body.final_value, "expected_version": body.version}, "task-med-017")
