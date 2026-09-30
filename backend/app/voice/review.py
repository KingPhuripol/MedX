"""Slice v2d: nurse review and confirmed handoff of an ambient voice intake into a triage case.

The nurse makes one decision per intake row on the phone. Only nurse-approved facts reach the case, as
ClinicalText-family evidence available at the confirmation time ``submitted_at``. A red flag heard during the
session is carried into every later assessment of the case as a non-suppressible Alert (``attention_alert``).
Research prototype on synthetic data only.
"""

from __future__ import annotations

import hashlib
import json
import re
import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any

from pydantic import ValidationError
from sqlalchemy import Engine, select
from sqlalchemy.exc import IntegrityError

from casegraph.data import Evidence, IntakeTranscript, VoiceFact, VoiceIntakeFacts
from casegraph.data import Turn as CGTurn

from ..audit import insert_audit, write_audit
from ..gateway import MOCK_LABEL
from ..triage.models import Alert, Case
from ..triage.models import IntakeFact as S4Fact
from . import service
from .db import voice_review_decisions, voice_reviews
from .models import ASK_ORDER, ReviewDecision, ReviewPayload

# Display strings of the v2c review rows (mobile/lib/voice.ts rows()/knownValue(), factory/v2c f6bcf6d; D-V2D-3).
UNKNOWN_TH = "ผู้ป่วยไม่ทราบ"
REFUSED_TH = "ผู้ป่วยไม่ตอบ"
EMPTY_TH = "ยังไม่มี"
ALLERGY_NONE_TH = "ไม่มีประวัติแพ้ยา"
ALLERGY_UNCLEAR_TH = "ข้อมูลแพ้ยายังไม่ชัด ตรวจในหน้าตรวจทาน"
NEGATIVE = re.compile(r"ไม่แพ้|ไม่มีประวัติแพ้")

SOURCE = "voice.review"
VERSION = "v2d-1"
S4_FIELDS = ("chief_complaint", "onset_duration")
CLOCK_SKEW = timedelta(seconds=60)
ALLOWED = {"MISSING": {"add", "unknown"}}  # every other status: confirm / edit / reject
DEFAULT_ALLOWED = {"confirm", "edit", "reject"}

ATTENTION_RULE_ID = "voice.nurse_attention"
ATTENTION_RULESET = "voice-attention-placeholder-1"


class ReviewDenied(Exception):
    def __init__(self, status: int, reason: str, errors: list | None = None) -> None:
        super().__init__(reason)
        self.status, self.reason, self.errors = status, reason, errors


def _iso(dt: datetime) -> str:
    return service._iso(dt)


def case_ref_for(patient_ref: str) -> str:
    return "V-" + patient_ref


def fact_text(f: Any) -> str:
    if f is None:
        return ""
    if isinstance(f.value_text, str) and f.value_text.strip():
        return f.value_text.strip()
    if isinstance(f.value, list):
        return ", ".join(str(v) for v in f.value)
    return "" if f.value is None else str(f.value)


def display_values(st: service._State) -> dict[str, str | None]:
    """What the v2c phone showed on each row (SPEC 3.3). None: MISSING, the row had no system value."""
    latest = service.latest_by_field(st.facts)
    out: dict[str, str | None] = {}
    for field in ASK_ORDER:
        status = st.statuses[field].status
        if status == "MISSING":
            out[field] = None
        elif status == "UNKNOWN":
            out[field] = UNKNOWN_TH
        elif status == "REFUSED":
            out[field] = REFUSED_TH
        elif field != "allergy_status":
            out[field] = fact_text(latest.get(field)) or EMPTY_TH
        else:
            out[field] = _allergy_display(st, latest)
    return out


def _allergy_display(st: service._State, latest: dict[str, Any]) -> str:
    status, allergens = latest.get("allergy_status"), latest.get("allergens")
    if (status is not None and status.state == "KNOWN" and status.value == "none"
            and not st.allergy_conflict and not st.extraction_error):
        return ALLERGY_NONE_TH
    if st.allergy_conflict or status is None or status.value != "present":
        return ALLERGY_UNCLEAR_TH
    text = (fact_text(allergens) if allergens is not None and allergens.state == "KNOWN" else "") or fact_text(status)
    return ALLERGY_UNCLEAR_TH if not text or NEGATIVE.search(text) else text


# ------------------------------------------------------------------ validation (SPEC 3.2, order normative)


def _validate(st: service._State, body: ReviewPayload, session_id: str, now: datetime,
              display: dict[str, str | None], review_exists: bool) -> dict[str, ReviewDecision]:
    session = st.session
    if body.session_id != session_id:
        raise ReviewDenied(422, "session_id_mismatch")
    if service._mode(session) != "ambient":
        raise ReviewDenied(422, "session_not_ambient")
    if session["status"] != "finished":
        raise ReviewDenied(409, "session_not_finished")
    if session["data_class"] != "synthetic" or not session["patient_ref"].startswith("SYN-"):
        raise ReviewDenied(422, "not_synthetic")
    if body.patient_ref != session["patient_ref"]:
        raise ReviewDenied(422, "patient_ref_mismatch")
    if len(case_ref_for(session["patient_ref"])) > 64:
        raise ReviewDenied(422, "case_ref_too_long")
    if review_exists:
        raise ReviewDenied(409, "review_exists")
    turns = st.turns
    if body.consent_acknowledged_at > now + CLOCK_SKEW or (
            turns and body.consent_acknowledged_at > service._dt(turns[0]["started_at"])):
        raise ReviewDenied(422, "consent_time_invalid")
    attention = [t for t in turns if t["nurse_attention"]]
    ack = body.red_flag_acknowledged_at
    if attention and ack is None:
        raise ReviewDenied(422, "red_flag_ack_required")
    if not attention and ack is not None:
        raise ReviewDenied(422, "red_flag_ack_unexpected")
    if ack is not None and (ack < service._dt(attention[0]["started_at"]) or ack > now + CLOCK_SKEW):
        raise ReviewDenied(422, "red_flag_ack_time_invalid")
    fields = [d.field for d in body.decisions]
    if len(fields) != len(ASK_ORDER) or set(fields) != set(ASK_ORDER):
        raise ReviewDenied(422, "decision_fields_mismatch")
    decisions = {d.field: d for d in body.decisions}
    if any(d.action not in ALLOWED.get(st.statuses[f].status, DEFAULT_ALLOWED) for f, d in decisions.items()):
        raise ReviewDenied(422, "action_not_allowed")
    if any(d.original != display[f] for f, d in decisions.items()):  # add/unknown rows: display is None
        raise ReviewDenied(422, "original_mismatch")
    if any(d.action == "confirm" and d.value != display[f] for f, d in decisions.items()):
        raise ReviewDenied(422, "confirm_value_mismatch")
    for d in decisions.values():
        ok = {
            "edit": isinstance(d.value, str) and 1 <= len(d.value.strip()) <= 500,
            "add": isinstance(d.value, str) and 1 <= len(d.value.strip()) <= 500,
            "reject": d.value is None,
            "unknown": d.value in (None, UNKNOWN_TH),
        }.get(d.action, True)
        if not ok:
            raise ReviewDenied(422, "value_invalid")
    return decisions


# ------------------------------------------------------------------ decision -> case outcome (SPEC 3.4)


def _confirmed(sys: Any, fact_id: str, session_id: str, now: datetime) -> VoiceFact:
    return VoiceFact(
        field=sys.field, state="KNOWN", value=sys.value, value_text=sys.value_text,
        span_turn_ids=tuple(sys.span_turn_ids), event_time=sys.event_time, available_at_time=now, fact_id=fact_id,
        session_id=session_id, extractor=sys.extractor, provider=sys.provider, model_version=sys.model_version,
        request_sha256=sys.request_sha256, supersedes_fact_id=sys.fact_id,
        label=MOCK_LABEL if sys.provider == "mock" else None,
    )


def _nurse_text(field: str, text: str, fact_id: str, session_id: str, now: datetime, supersedes: str | None) -> VoiceFact:
    # Allergy free text is never parsed into "none"/"present" (D-V2D-2): value null, words in value_text only.
    return VoiceFact(
        field=field, state="KNOWN", value=None if field == "allergy_status" else text, value_text=text,
        span_turn_ids=(), event_time=now, available_at_time=now, fact_id=fact_id, session_id=session_id,
        extractor="nurse_review", provider="human", supersedes_fact_id=supersedes,
    )


def _finals(st: service._State, decisions: dict[str, ReviewDecision], display: dict[str, str | None],
            rid: str, sid: str, now: datetime) -> tuple[dict[str, VoiceFact], list[dict]]:
    latest = service.latest_by_field(st.facts)
    finals: dict[str, VoiceFact] = {}
    rows: list[dict] = []
    for field in ASK_ORDER:
        d, sys = decisions[field], latest.get(field)
        fid = f"vr:{rid}:{field}"
        fact = None
        if d.action == "confirm" and st.statuses[field].status == "KNOWN" and display[field] != ALLERGY_UNCLEAR_TH:
            fact = _confirmed(sys, fid, sid, now)
        elif d.action in ("edit", "add"):
            supersedes = sys.fact_id if d.action == "edit" and sys is not None else None
            fact = _nurse_text(field, d.value.strip(), fid, sid, now, supersedes)  # type: ignore[union-attr]
        if fact is not None:
            finals[field] = fact
            allergens = latest.get("allergens")
            if (field == "allergy_status" and d.action == "confirm" and fact.value == "present"
                    and allergens is not None and allergens.state == "KNOWN"):
                finals["allergens"] = _confirmed(allergens, f"vr:{rid}:allergens", sid, now)
        rows.append({
            "review_id": rid, "session_id": sid, "field": field, "action": d.action, "original": d.original,
            "final_value": json.dumps(fact.value, ensure_ascii=False) if fact else None,
            "final_state": "KNOWN" if fact else "none", "system_fact_id": sys.fact_id if sys else None,
            "reason": d.reason,
        })
    return finals, rows


def _evidence(st: service._State, finals: dict[str, VoiceFact], missing: list[str], rid: str,
              now: datetime) -> list[Evidence]:
    sid, ref = st.session["session_id"], st.session["patient_ref"]
    first = service._dt(st.turns[0]["started_at"]) if st.turns else now
    base = {"patient_ref": ref, "data_class": "synthetic", "event_time": first, "available_at_time": now,
            "source": SOURCE, "provenance": f"voice_session/{sid}/review/{rid}", "version": VERSION}
    items: list[Evidence] = [VoiceIntakeFacts(
        item_id=f"voice:{sid}:review:{rid}:facts", facts=tuple(finals.values()), missing_fields=tuple(missing),
        handoff_reason="nurse_review", allergy_conflict=st.allergy_conflict, **base,
    )]
    if st.turns:
        items.append(IntakeTranscript(
            item_id=f"voice:{sid}:review:{rid}:transcript", **base,
            turns=tuple(CGTurn(turn_index=t["seq"], speaker=t["speaker"], text=t["text"],
                               spoken_at=service._dt(t["started_at"]), ended_at=service._dt(t["ended_at"]),
                               turn_id=t["turn_id"]) for t in st.turns),
        ))
    return items


# ------------------------------------------------------------------ submit


@dataclass
class ReviewResult:
    review_id: str
    session_id: str
    patient_ref: str
    case_ref: str
    submitted_at: datetime
    red_flag: bool
    evidence_item_ids: list[str]
    confirmed_fields: list[str]
    missing_fields: list[str]


def _deny(ctx: service.VoiceContext, session_id: str, exc: ReviewDenied) -> None:
    service._audit(ctx, "voice.review.denied", session_id, "denied", {"status": exc.status, "reason": exc.reason})


def submit(ctx: service.VoiceContext, session_id: str, raw: Any, now: datetime) -> ReviewResult:
    """Validate (SPEC 3.2) then write the review, its decisions and audit rows in one transaction (B1).

    Any failure writes no case rows and one ``voice.review.denied`` audit row, then raises ``ReviewDenied``.
    """
    try:
        return _submit(ctx, session_id, raw, now)
    except ReviewDenied as exc:
        _deny(ctx, session_id, exc)
        raise


def _submit(ctx: service.VoiceContext, session_id: str, raw: Any, now: datetime) -> ReviewResult:
    try:
        body = ReviewPayload.model_validate(raw)
    except ValidationError as exc:
        raise ReviewDenied(422, "schema_invalid", exc.errors(include_url=False)) from None
    with ctx.engine.connect() as conn:
        try:
            st = service._state(conn, session_id)
        except service.VoiceError as exc:
            raise ReviewDenied(exc.status_code, exc.detail) from None
        exists = conn.execute(
            select(voice_reviews.c.review_id).where(voice_reviews.c.session_id == session_id)
        ).first() is not None
    display = display_values(st)
    decisions = _validate(st, body, session_id, now, display, exists)

    rid = uuid.uuid4().hex
    ref = st.session["patient_ref"]
    case_ref = case_ref_for(ref)
    finals, rows = _finals(st, decisions, display, rid, session_id, now)
    order = [*ASK_ORDER[:4], "allergens", *ASK_ORDER[4:]]
    confirmed = [f for f in order if f in finals]
    missing = [f for f in ASK_ORDER if f not in finals]
    evidence = _evidence(st, finals, missing, rid, now)
    provenance = f"voice_session/{session_id}/review/{rid}"
    s4 = [S4Fact(fact_id=f"vr:{rid}.{f}", kind=f, value=finals[f].value_text[:500], available_at_time=now,
                 source=SOURCE, provenance=provenance, version=VERSION) for f in S4_FIELDS if f in finals]
    attention_ids = [t["turn_id"] for t in st.turns if t["nurse_attention"]]
    red_flag = bool(attention_ids)
    ids = [e.item_id for e in evidence]
    actor = ctx.actor
    audit = {"target": f"voice_session/{session_id}", "outcome": "success", "request_id": ctx.request_id,
             "actor_id": actor.id, "actor_role": actor.role.value}
    try:
        with ctx.engine.begin() as conn:
            conn.execute(voice_reviews.insert().values(
                review_id=rid, session_id=session_id, patient_ref=ref, case_ref=case_ref, reviewer_id=actor.id,
                reviewer_role=actor.role.value, submitted_at=_iso(now),
                consent_acknowledged_at=_iso(body.consent_acknowledged_at), red_flag=int(red_flag),
                red_flag_acknowledged_at=_iso(body.red_flag_acknowledged_at) if body.red_flag_acknowledged_at else None,
                attention_turn_ids_json=json.dumps(attention_ids),
                evidence_json=json.dumps([e.model_dump(mode="json") for e in evidence], ensure_ascii=False),
                case_facts_json=json.dumps([f.model_dump(mode="json") for f in s4], ensure_ascii=False),
            ))
            conn.execute(voice_review_decisions.insert(), [
                r | {"actor_id": actor.id, "decided_at": _iso(now)} for r in rows
            ])
            insert_audit(conn, action="voice.review.submit", **audit, details={
                "review_id": rid, "session_id": session_id, "case_ref": case_ref, "mode": "ambient",
                "decisions": [{"field": r["field"], "action": r["action"],
                               "changed": r["action"] not in ("confirm", "unknown"),
                               "system_fact_id": r["system_fact_id"]} for r in rows],
                "reason_sha256": {f: hashlib.sha256(d.reason.encode("utf-8")).hexdigest()
                                  for f, d in decisions.items() if d.reason},
                "confirmed_fields": confirmed, "missing_fields": missing, "evidence_item_ids": ids,
                "red_flag": red_flag,
            })
            insert_audit(conn, action="voice.review.consent_ack", **audit, details={
                "review_id": rid, "session_id": session_id,
                "consent_acknowledged_at": _iso(body.consent_acknowledged_at),
            })
            if red_flag:
                insert_audit(conn, action="voice.review.red_flag_ack", **audit, details={
                    "review_id": rid, "session_id": session_id,
                    "red_flag_acknowledged_at": _iso(body.red_flag_acknowledged_at),  # type: ignore[arg-type]
                    "attention_turn_ids": attention_ids,
                })
    except IntegrityError:  # a concurrent review of the same session won the UNIQUE(session_id) race
        raise ReviewDenied(409, "review_exists") from None
    return ReviewResult(rid, session_id, ref, case_ref, now, red_flag, ids, confirmed, missing)


def audit_handoff(ctx: service.VoiceContext, result: ReviewResult, assessment_id: str | None,
                  department_status: str, error_type: str | None) -> None:
    write_audit(ctx.engine, action="voice.review.handoff", target=f"voice_session/{result.session_id}",
                outcome="success" if error_type is None else "failure", request_id=ctx.request_id,
                actor_id=ctx.actor.id, actor_role=ctx.actor.role.value, details={
                    "review_id": result.review_id, "case_ref": result.case_ref, "assessment_id": assessment_id,
                    "department_status": department_status, "error_type": error_type,
                })


# ------------------------------------------------------------------ triage case lookup (SPEC B3, B4)


@dataclass
class VoiceCase:
    case: Case
    submitted: list[datetime]  # submitted_at of every review, oldest first
    red_flags: list[tuple[datetime, str, list[str]]]  # (submitted_at, review_id, attention turn ids)

    @property
    def latest(self) -> datetime:
        return self.submitted[-1]

    @property
    def chief_complaint(self) -> str | None:
        cc = [f for f in self.case.facts if f.kind == "chief_complaint"]
        return max(cc, key=lambda f: f.available_at_time).value if cc else None


def voice_cases(engine: Engine) -> dict[str, VoiceCase]:
    """Every reviewed voice case by ``case_ref`` (``V-<patient_ref>``). All reviews of a patient add up."""
    # ponytail: reads every review per call; index by case_ref if the review table grows past a demo.
    with engine.connect() as conn:
        rows = conn.execute(select(voice_reviews)).mappings().all()
    grouped: dict[str, list[Any]] = {}
    for r in sorted(rows, key=lambda r: service._dt(r["submitted_at"])):
        grouped.setdefault(r["case_ref"], []).append(r)
    out: dict[str, VoiceCase] = {}
    for ref, rs in grouped.items():
        facts = [S4Fact.model_validate(f) for r in rs for f in json.loads(r["case_facts_json"])]
        out[ref] = VoiceCase(
            case=Case(case_ref=ref, data_class="synthetic", facts=facts),
            submitted=[service._dt(r["submitted_at"]) for r in rs],
            red_flags=[(service._dt(r["submitted_at"]), r["review_id"], json.loads(r["attention_turn_ids_json"]))
                       for r in rs if r["red_flag"]],
        )
    return out


def attention_alert(vc: VoiceCase, as_of: datetime) -> Alert | None:
    """The carried red flag: one Alert if any red-flag review was submitted by ``as_of``. No transcript text."""
    hits = [(rid, tids) for t, rid, tids in vc.red_flags if t <= as_of]
    if not hits:
        return None
    refs = [ref for rid, tids in hits for ref in (f"voice_review/{rid}", *(f"voice_turn/{t}" for t in tids))]
    return Alert(
        rule_id=ATTENTION_RULE_ID, ruleset_version=ATTENTION_RULESET, severity="escalate", evidence_refs=refs,
        name_en="Red-flag phrase heard during voice intake",
        name_th="พบสัญญาณที่ต้องประเมินเร่งด่วนระหว่างซักประวัติ",
        message_en=("A nurse-attention phrase was heard during the ambient voice intake and acknowledged by the "
                    "nurse. Assess the patient now per unit protocol. Placeholder phrase list, not clinically "
                    "validated."),
        message_th=("ระบบได้ยินคำที่ต้องให้พยาบาลประเมินระหว่างการบันทึกเสียง และพยาบาลรับทราบแล้ว "
                    "ให้ประเมินผู้ป่วยทันทีตามแนวปฏิบัติของหน่วยงาน (รายการคำเป็นตัวอย่าง ยังไม่ผ่านการรับรองทางคลินิก)"),
    )
