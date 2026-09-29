"""Voice Agent cascade (text first): persist turn -> interrupt check -> gateway extraction ->
validate + ground -> append facts -> deterministic next action.

Fail-safe: any gateway/schema/grounding failure writes no facts from that call, marks the session
``extraction_error`` and hands off to the nurse. Model output is never spoken.
"""

from __future__ import annotations

import json
import time
import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any

from pydantic import ValidationError
from sqlalchemy import Connection, Engine, func, select

from ..audit import write_audit
from ..deps import CurrentUser
from casegraph.data import Evidence, IntakeTranscript, VoiceFact, VoiceIntakeFacts
from casegraph.data import Turn as CGTurn

from ..gateway import MOCK_LABEL, GatewayRequest, Provider, invoke_audited
from .db import voice_extractions, voice_facts, voice_sessions, voice_turns
from .models import (
    ALLERGY_VALUES,
    ASK_ORDER,
    CHIEF_COMPLAINT_CODES,
    EXTRACT_TASK,
    ISO_DURATION,
    LIST_FIELDS,
    SEVERITY_CATEGORIES,
    VOICE_VERSION,
    AddTurnBody,
    ExtractedFact,
    ExtractOutput,
    FieldStatus,
    IntakeFact,
    NextAction,
    StartSessionBody,
    Turn,
)
from .policy import MAX_ASKS, handoff, missing_fields, next_action, nurse_attention_hit
from .utterances_th import utterance

FUTURE_TOLERANCE = timedelta(seconds=5)
HELD_REASON = "allergy_downgrade_blocked"
EVIDENCE_SOURCE = "voice_agent.cascade"


class VoiceError(Exception):
    def __init__(self, status_code: int, detail: str) -> None:
        super().__init__(detail)
        self.status_code = status_code
        self.detail = detail


@dataclass(frozen=True)
class VoiceContext:
    engine: Engine
    provider: Provider
    actor: CurrentUser
    request_id: str = "in-process"


def _iso(dt: datetime) -> str:
    return dt.astimezone(timezone.utc).isoformat(timespec="microseconds")


def _dt(value: str) -> datetime:
    return datetime.fromisoformat(value)


def _new_id() -> str:
    return uuid.uuid4().hex


# ------------------------------------------------------------------ loading


def _session_row(conn: Connection, session_id: str) -> Any:
    row = conn.execute(select(voice_sessions).where(voice_sessions.c.session_id == session_id)).mappings().first()
    if row is None:
        raise VoiceError(404, "voice session not found")
    return row


def _turn_rows(conn: Connection, session_id: str) -> list[dict]:
    rows = conn.execute(
        select(voice_turns).where(voice_turns.c.session_id == session_id).order_by(voice_turns.c.seq)
    ).mappings().all()
    return [dict(r) for r in rows]


def _turn_model(row: dict) -> Turn:
    return Turn(
        turn_id=row["turn_id"], session_id=row["session_id"], seq=row["seq"], speaker=row["speaker"],
        text=row["text"], started_at=_dt(row["started_at"]), ended_at=_dt(row["ended_at"]),
    )


def _fact_rows(conn: Connection, session_id: str) -> list[IntakeFact]:
    rows = conn.execute(
        select(voice_facts).where(voice_facts.c.session_id == session_id).order_by(voice_facts.c.id)
    ).mappings().all()
    return [
        IntakeFact(
            fact_id=r["fact_id"], session_id=r["session_id"], field=r["field"], state=r["state"],
            value=json.loads(r["value_json"]), value_text=r["value_text"],
            span_turn_ids=json.loads(r["span_turn_ids_json"]), event_time=_dt(r["event_time"]),
            available_at_time=_dt(r["available_at_time"]), extractor=r["extractor"], provider=r["provider"],
            model_version=r["model_version"], request_sha256=r["request_sha256"],
            supersedes_fact_id=r["supersedes_fact_id"],
        )
        for r in rows
    ]


def latest_by_field(facts: list[IntakeFact]) -> dict[str, IntakeFact]:
    latest: dict[str, IntakeFact] = {}
    for f in facts:  # ordered by insertion; later versions win
        latest[f.field] = f
    return latest


def _allergy_conflict(conn: Connection, session_id: str) -> bool:
    n = conn.execute(
        select(func.count()).select_from(voice_extractions).where(
            voice_extractions.c.session_id == session_id, voice_extractions.c.reason == HELD_REASON
        )
    ).scalar_one()
    return n > 0


def _extraction_error(conn: Connection, session_id: str) -> bool:
    n = conn.execute(
        select(func.count()).select_from(voice_extractions).where(
            voice_extractions.c.session_id == session_id, voice_extractions.c.status == "error"
        )
    ).scalar_one()
    return n > 0


def field_statuses(facts: list[IntakeFact], turns: list[dict]) -> dict[str, FieldStatus]:
    latest = latest_by_field(facts)
    out: dict[str, FieldStatus] = {}
    for field in ASK_ORDER:
        times = sum(1 for t in turns if t["speaker"] == "agent" and t["field"] == field)
        status = latest[field].state if field in latest else "MISSING"
        out[field] = FieldStatus(
            field=field, status=status, times_asked=times, not_elicited=status == "MISSING" and times >= MAX_ASKS
        )
    return out


def _decide(statuses: dict[str, FieldStatus], attention: bool, extraction_error: bool) -> NextAction:
    if attention:
        return handoff("nurse_attention_phrase", missing_fields(statuses))
    if extraction_error:
        return handoff("extraction_unavailable", missing_fields(statuses))
    return next_action(statuses)


def _current_action(turns: list[dict], statuses: dict[str, FieldStatus]) -> NextAction | None:
    """The last action the agent actually emitted (recorded as an agent turn)."""
    for t in reversed(turns):
        if t["speaker"] != "agent":
            continue
        uid = t["utterance_id"]
        kind, _, rest = uid.partition(".")
        if kind in ("ask", "reask"):
            return NextAction(action="ask", field=rest, utterance_id=uid, utterance_th=utterance(uid), reason=None)
        return handoff(rest, missing_fields(statuses))
    return None


def _emit(conn: Connection, session_id: str, turns: list[dict], action: NextAction, at: datetime) -> str | None:
    """Record the agent's utterance as a turn. Handoffs are not repeated back-to-back."""
    last_agent = next((t for t in reversed(turns) if t["speaker"] == "agent"), None)
    if action.action == "handoff" and last_agent is not None and last_agent["utterance_id"] == action.utterance_id:
        return None
    turn_id = _new_id()
    row = {
        "turn_id": turn_id, "session_id": session_id, "seq": len(turns) + 1, "speaker": "agent",
        "text": action.utterance_th, "started_at": _iso(at), "ended_at": _iso(at), "field": action.field,
        "utterance_id": action.utterance_id, "nurse_attention": 0,
    }
    conn.execute(voice_turns.insert().values(**row))
    turns.append(row)
    return turn_id


# ------------------------------------------------------------------ extraction validation


def _value_ok(f: ExtractedFact) -> bool:
    v = f.value
    if f.state != "KNOWN":
        return v is None
    if f.field in LIST_FIELDS:
        if not isinstance(v, list) or len(v) > 20 or not all(isinstance(i, str) and i.strip() for i in v):
            return False
        return bool(v) if f.field == "allergens" else True
    if isinstance(v, bool):
        return False
    if f.field == "chief_complaint":
        return isinstance(v, str) and v in CHIEF_COMPLAINT_CODES
    if f.field == "onset_duration":
        return isinstance(v, str) and bool(ISO_DURATION.match(v))
    if f.field == "severity":
        return (isinstance(v, int) and 0 <= v <= 10) or (isinstance(v, str) and v in SEVERITY_CATEGORIES)
    if f.field == "allergy_status":
        return isinstance(v, str) and v in ALLERGY_VALUES
    return False


def validate_extraction(
    output: dict | None, visible: dict[str, dict], current_end: datetime
) -> tuple[list[ExtractedFact] | None, str | None]:
    """Schema + grounding checks. Returns (facts, None) or (None, reason)."""
    try:
        parsed = ExtractOutput.model_validate(output)
    except ValidationError:
        return None, "schema_invalid"
    for f in parsed.facts:
        for tid in f.span_turn_ids:
            turn = visible.get(tid)
            if turn is None or turn["speaker"] == "agent" or _dt(turn["ended_at"]) > current_end:
                return None, "bad_span"
        if not _value_ok(f):
            return None, "bad_value"
        cited = "\n".join(visible[t]["text"] for t in f.span_turn_ids).casefold()
        if f.value_text.casefold() not in cited:
            return None, "ungrounded_text"
        if isinstance(f.value, list) and any(i.casefold() not in cited for i in f.value):
            return None, "ungrounded_item"
    return parsed.facts, None


def _allergy_present(latest: dict[str, Any]) -> bool:
    status, allergens = latest.get("allergy_status"), latest.get("allergens")
    return (status is not None and status.state == "KNOWN" and status.value == "present") or (
        allergens is not None and allergens.state == "KNOWN" and bool(allergens.value)
    )


def reconcile_allergy(
    extracted: list[ExtractedFact], latest: dict[str, Any]
) -> tuple[list[ExtractedFact], list[dict]]:
    """Allergy safety guard, independent of the extractor.

    - A stated drug allergy is never replaced by ``none``/UNKNOWN/REFUSED automatically: the weaker
      fact is held (not written) and reported for nurse review.
    - Known allergens are never replaced by an UNKNOWN/REFUSED allergens fact.
    - Named allergens imply ``allergy_status`` KNOWN ``present`` (same span), so status and list agree.
    """
    batch_allergens = [f for f in extracted if f.field == "allergens" and f.state == "KNOWN" and f.value]
    batch_present = any(
        f.field == "allergy_status" and f.state == "KNOWN" and f.value == "present" for f in extracted
    )
    present = _allergy_present(latest) or bool(batch_allergens) or batch_present
    kept: list[ExtractedFact] = []
    held: list[dict] = []
    for f in extracted:
        weaker_status = f.field == "allergy_status" and not (f.state == "KNOWN" and f.value == "present")
        prev_allergens = latest.get("allergens")
        weaker_list = (
            f.field == "allergens" and f.state != "KNOWN" and prev_allergens is not None
            and prev_allergens.state == "KNOWN" and bool(prev_allergens.value)
        )
        if (weaker_status and present) or weaker_list:
            held.append({"field": f.field, "state": f.state, "value": f.value, "span_turn_ids": f.span_turn_ids,
                         "reason": "allergy_downgrade_blocked"})
            continue
        kept.append(f)
    if batch_allergens and not batch_present:
        src = batch_allergens[0]
        kept.insert(0, ExtractedFact(field="allergy_status", state="KNOWN", value="present",
                                     value_text=src.value_text, span_turn_ids=src.span_turn_ids))
    return kept, held


def _append_facts(
    conn: Connection, session_id: str, extracted: list[ExtractedFact], extractor: str, gw: Any,
    turns_by_id: dict[str, dict], existing: list[IntakeFact],
) -> list[IntakeFact]:
    latest = latest_by_field(existing)
    written: list[IntakeFact] = []
    for ef in extracted:
        prev = latest.get(ef.field)
        value: Any = ef.value
        span = list(dict.fromkeys(ef.span_turn_ids))
        if (
            ef.field in LIST_FIELDS and ef.state == "KNOWN" and prev is not None and prev.state == "KNOWN"
            and prev.value and value
        ):  # a list mentioned across turns accumulates; the span cites every contributing turn
            seen = {str(p).casefold() for p in prev.value}  # type: ignore[union-attr]
            value = list(prev.value) + [i for i in value if i.casefold() not in seen]  # type: ignore[arg-type]
            span = list(dict.fromkeys(prev.span_turn_ids + span))
        if prev is not None and prev.state == ef.state and prev.value == value:
            continue
        span_turns = [turns_by_id[t] for t in span]
        fact = IntakeFact(
            fact_id=_new_id(), session_id=session_id, field=ef.field, state=ef.state, value=value,
            value_text=ef.value_text, span_turn_ids=span,
            event_time=min(_dt(t["started_at"]) for t in span_turns),
            available_at_time=max(_dt(t["ended_at"]) for t in span_turns),
            extractor=extractor, provider=gw.provider, model_version=gw.model_version,
            request_sha256=gw.request_sha256, supersedes_fact_id=prev.fact_id if prev else None,
        )
        conn.execute(
            voice_facts.insert().values(
                fact_id=fact.fact_id, session_id=session_id, field=fact.field, state=fact.state,
                value_json=json.dumps(fact.value, ensure_ascii=False), value_text=fact.value_text,
                span_turn_ids_json=json.dumps(fact.span_turn_ids), event_time=_iso(fact.event_time),
                available_at_time=_iso(fact.available_at_time), extractor=fact.extractor, provider=fact.provider,
                model_version=fact.model_version, request_sha256=fact.request_sha256,
                supersedes_fact_id=fact.supersedes_fact_id,
            )
        )
        latest[ef.field] = fact
        written.append(fact)
    return written


# ------------------------------------------------------------------ public operations


def _session_payload(row: Any, turns: list[dict], extraction_error: bool, allergy_conflict: bool = False) -> dict:
    return {
        "session_id": row["session_id"],
        "patient_ref": row["patient_ref"],
        "data_class": row["data_class"],
        "status": row["status"],
        "created_at": row["created_at"],
        "extraction_error": extraction_error,
        "nurse_attention": any(t["nurse_attention"] for t in turns),
        # A later answer tried to weaken a recorded drug allergy; the allergy was kept for nurse review.
        "allergy_conflict": allergy_conflict,
    }


def _audit(ctx: VoiceContext, action: str, session_id: str, outcome: str, details: dict) -> None:
    write_audit(
        ctx.engine, action=action, target=f"voice_session/{session_id}", outcome=outcome,
        request_id=ctx.request_id, actor_id=ctx.actor.id, actor_role=ctx.actor.role.value, details=details,
    )


def start_session(ctx: VoiceContext, body: StartSessionBody, now: datetime) -> dict:
    session_id = _new_id()
    with ctx.engine.begin() as conn:
        conn.execute(
            voice_sessions.insert().values(
                session_id=session_id, patient_ref=body.patient_ref, data_class=body.data_class,
                created_at=_iso(now), created_by=ctx.actor.id, status="active",
            )
        )
        turns: list[dict] = []
        statuses = field_statuses([], turns)
        action = next_action(statuses)
        agent_turn_id = _emit(conn, session_id, turns, action, now)
        statuses = field_statuses([], turns)
        row = _session_row(conn, session_id)
    _audit(ctx, "voice.session.start", session_id, "success",
           {"session_id": session_id, "agent_turn_id": agent_turn_id, "next_action": action.utterance_id})
    return {
        "session": _session_payload(row, turns, False),
        "next_action": action.model_dump(),
        "field_statuses": [s.model_dump() for s in statuses.values()],
    }


def add_turn(ctx: VoiceContext, session_id: str, body: AddTurnBody, now: datetime) -> dict:
    # 1. Validate and persist the turn (append-only).
    with ctx.engine.begin() as conn:
        session = _session_row(conn, session_id)
        if session["status"] != "active":
            raise VoiceError(409, "voice session is finished")
        turns = _turn_rows(conn, session_id)
        if body.ended_at < body.started_at:
            raise VoiceError(422, "ended_at is earlier than started_at")
        if turns and body.started_at < _dt(turns[-1]["ended_at"]):
            raise VoiceError(422, "turn starts before the previous turn ended")
        if body.ended_at > now + FUTURE_TOLERANCE:
            raise VoiceError(422, "turn ends in the future")
        # Nurse-attention interrupt: deterministic, before extraction, independent of the gateway.
        prior = [t["text"] for t in turns if t["speaker"] != "agent"]
        attention = nurse_attention_hit(body.text, prior)
        turn = {
            "turn_id": _new_id(), "session_id": session_id, "seq": len(turns) + 1, "speaker": body.speaker,
            "text": body.text, "started_at": _iso(body.started_at), "ended_at": _iso(body.ended_at),
            "field": None, "utterance_id": None, "nurse_attention": int(attention),
        }
        conn.execute(voice_turns.insert().values(**turn))
        turns.append(turn)

    # 2. Extraction through the Model Gateway: only turns that had ended by this turn's end.
    current_end = body.ended_at
    visible = [t for t in turns if _dt(t["ended_at"]) <= current_end]
    last_asked = next((t["field"] for t in reversed(turns) if t["speaker"] == "agent" and t["field"]), None)
    request = GatewayRequest(
        task=EXTRACT_TASK,
        inputs={
            "turns": [
                {"turn_id": t["turn_id"], "speaker": t["speaker"], "text": t["text"], "ended_at": t["ended_at"]}
                for t in visible
            ],
            "last_asked_field": last_asked,
        },
        data_class="synthetic",  # type: ignore[arg-type]
    )
    gw = invoke_audited(ctx.engine, ctx.provider, request, ctx.actor, request_id=ctx.request_id)

    # 3-4. Validate schema and grounding; any failure -> no facts from this call.
    extracted: list[ExtractedFact] | None = None
    reason: str | None
    if gw.status != "ok":
        reason = f"gateway_{gw.status}"
    else:
        extracted, reason = validate_extraction(gw.output, {t["turn_id"]: t for t in visible}, current_end)

    with ctx.engine.begin() as conn:
        existing = _fact_rows(conn, session_id)
        new_facts: list[IntakeFact] = []
        held: list[dict] = []
        if extracted is not None:
            extracted, held = reconcile_allergy(extracted, latest_by_field(existing))
            extractor = str((gw.output or {}).get("extractor", "unknown"))[:64]
            new_facts = _append_facts(
                conn, session_id, extracted, extractor, gw, {t["turn_id"]: t for t in visible}, existing
            )
        if held:
            reason = HELD_REASON
        conn.execute(
            voice_extractions.insert().values(
                session_id=session_id, turn_id=turn["turn_id"], status="ok" if extracted is not None else "error",
                reason=reason, provider=gw.provider, model_version=gw.model_version,
                request_sha256=gw.request_sha256, latency_ms=str(gw.latency_ms),
            )
        )
        facts = existing + new_facts
        extraction_error = _extraction_error(conn, session_id)
        allergy_conflict = _allergy_conflict(conn, session_id)
        any_attention = any(t["nurse_attention"] for t in turns)
        # 5-6. Deterministic next action; the agent utterance is recorded as a turn.
        statuses = field_statuses(facts, turns)
        action = _decide(statuses, any_attention, extraction_error)
        agent_turn_id = _emit(conn, session_id, turns, action, current_end)
        statuses = field_statuses(facts, turns)
        session = _session_row(conn, session_id)

    _audit(ctx, "voice.turn.add", session_id, "success", {
        "session_id": session_id, "turn_id": turn["turn_id"], "speaker": body.speaker,
        "request_sha256": gw.request_sha256, "extraction": "ok" if extracted is not None else "error",
        "new_fact_ids": [f.fact_id for f in new_facts], "agent_turn_id": agent_turn_id,
        "held": [{k: h[k] for k in ("field", "state", "value", "span_turn_ids", "reason")} for h in held],
        "next_action": action.utterance_id,
    })
    return {
        "turn": _turn_model(turn).model_dump(mode="json"),
        "new_facts": [f.model_dump(mode="json") for f in new_facts],
        "field_statuses": [s.model_dump() for s in statuses.values()],
        "next_action": action.model_dump(),
        "extraction_error": extraction_error,
        "nurse_attention": any_attention,
        "held_facts": held,
        "allergy_conflict": allergy_conflict,
        "session": _session_payload(session, turns, extraction_error, allergy_conflict),
    }


def _state(
    conn: Connection, session_id: str
) -> tuple[Any, list[dict], list[IntakeFact], dict, NextAction, bool, bool]:
    session = _session_row(conn, session_id)
    turns = _turn_rows(conn, session_id)
    facts = _fact_rows(conn, session_id)
    statuses = field_statuses(facts, turns)
    extraction_error = _extraction_error(conn, session_id)
    action = _current_action(turns, statuses) or _decide(
        statuses, any(t["nurse_attention"] for t in turns), extraction_error
    )
    return session, turns, facts, statuses, action, extraction_error, _allergy_conflict(conn, session_id)


def get_session(ctx: VoiceContext, session_id: str) -> dict:
    with ctx.engine.connect() as conn:
        session, turns, facts, statuses, action, extraction_error, allergy_conflict = _state(conn, session_id)
    return {
        "session": _session_payload(session, turns, extraction_error, allergy_conflict),
        "turns": [_turn_model(t).model_dump(mode="json") | {"utterance_id": t["utterance_id"]} for t in turns],
        "facts": [f.model_dump(mode="json") for f in latest_by_field(facts).values()],
        "field_statuses": [s.model_dump() for s in statuses.values()],
        "next_action": action.model_dump(),
    }


def facts_as_of(ctx: VoiceContext, session_id: str, as_of: datetime | None) -> dict:
    with ctx.engine.connect() as conn:
        _session_row(conn, session_id)
        facts = _fact_rows(conn, session_id)
    if as_of is not None:
        facts = [f for f in facts if f.available_at_time <= as_of]
    return {
        "as_of": _iso(as_of) if as_of else None,
        "facts": [f.model_dump(mode="json") for f in latest_by_field(facts).values()],
    }


def build_evidence(session: Any, turns: list[dict], facts: list[IntakeFact], missing: list[str],
                   reason: str, allergy_conflict: bool = False) -> list[Evidence]:
    """Session evidence in the single Case Graph type system (slice i2).

    The latest fact per field becomes one ``VoiceIntakeFacts`` item and the turns become one
    ``IntakeTranscript`` item (both ClinicalText family, PROPOSAL 3.1). Every fact keeps its own
    ``available_at_time``, cited turn ids, gateway request hash and extractor version.
    """
    sid, ref, dc = session["session_id"], session["patient_ref"], session["data_class"]
    latest = list(latest_by_field(facts).values())
    items: list[Evidence] = []
    if latest or turns:
        times = [f.available_at_time for f in latest] or [max(_dt(t["ended_at"]) for t in turns)]
        events = [f.event_time for f in latest] or [_dt(turns[0]["started_at"])]
        items.append(VoiceIntakeFacts(
            item_id=f"voice:{sid}:facts", patient_ref=ref, data_class=dc, event_time=min(events),
            available_at_time=max(times), source=EVIDENCE_SOURCE,
            provenance=f"voice_session/{sid}/facts;extractor/{','.join(sorted({f.extractor for f in latest}))}",
            version=VOICE_VERSION,
            facts=tuple(VoiceFact(
                field=f.field, state=f.state, value=f.value, value_text=f.value_text,
                span_turn_ids=tuple(f.span_turn_ids), event_time=f.event_time,
                available_at_time=f.available_at_time, fact_id=f.fact_id, session_id=f.session_id,
                extractor=f.extractor, provider=f.provider, model_version=f.model_version,
                request_sha256=f.request_sha256, supersedes_fact_id=f.supersedes_fact_id,
                label=MOCK_LABEL if f.provider == "mock" else None,
            ) for f in latest),
            missing_fields=tuple(missing), handoff_reason=reason, allergy_conflict=allergy_conflict,
        ))
    if turns:
        items.append(IntakeTranscript(
            item_id=f"voice:{sid}:transcript", patient_ref=ref, data_class=dc,
            event_time=_dt(turns[0]["started_at"]), available_at_time=max(_dt(t["ended_at"]) for t in turns),
            source=EVIDENCE_SOURCE,
            provenance=f"voice_session/{sid}/turns/{turns[0]['turn_id']}..{turns[-1]['turn_id']};transcript",
            version=VOICE_VERSION,
            turns=tuple(CGTurn(turn_index=t["seq"], speaker=t["speaker"], text=t["text"],
                               spoken_at=_dt(t["started_at"]), ended_at=_dt(t["ended_at"]), turn_id=t["turn_id"])
                        for t in turns),
        ))
    return items


def finish(ctx: VoiceContext, session_id: str, now: datetime) -> dict:
    with ctx.engine.begin() as conn:
        session, turns, facts, statuses, action, extraction_error, allergy_conflict = _state(conn, session_id)
        if session["status"] != "active":
            raise VoiceError(409, "voice session is already finished")
        conn.execute(
            voice_sessions.update().where(voice_sessions.c.session_id == session_id).values(status="finished")
        )
        session = _session_row(conn, session_id)
    missing = missing_fields(statuses)
    reason = action.reason if action.action == "handoff" and action.reason else "finished_by_nurse"
    evidence = build_evidence(session, turns, facts, missing, reason, allergy_conflict)
    _audit(ctx, "voice.session.finish", session_id, "success", {
        "session_id": session_id, "status_change": "active->finished", "handoff_reason": reason,
        "missing_fields": missing, "n_turns": len(turns), "n_evidence": len(evidence),
        "allergy_conflict": allergy_conflict,
    })
    return {
        "session": _session_payload(session, turns, extraction_error, allergy_conflict),
        "handoff_reason": reason,
        "missing_fields": missing,
        "field_statuses": [s.model_dump() for s in statuses.values()],
        "facts": [f.model_dump(mode="json") for f in latest_by_field(facts).values()],
        "evidence": [e.model_dump(mode="json") for e in evidence],
    }


def timed_add_turn(ctx: VoiceContext, session_id: str, body: AddTurnBody, now: datetime) -> tuple[dict, float]:
    start = time.perf_counter()
    result = add_turn(ctx, session_id, body, now)
    return result, (time.perf_counter() - start) * 1000
