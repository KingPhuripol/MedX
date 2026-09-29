"""S3 Voice Agent adapter: replay the T1 IntakeTranscript through the S3 session service (slice e1).

In-process, in-memory SQLite, offline mock provider through the Model Gateway. The product code is used
through its public service functions only and is never changed here. Research prototype - not for
clinical use.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from app.db import create_schema, make_engine
from app.gateway import build_provider
from app.voice import create_voice_schema
from app.voice import eval as s3_harness  # S3's own in-process wiring: Settings, CurrentUser, Role
from app.voice.models import AddTurnBody, StartSessionBody
from app.voice.service import VoiceContext, add_turn, finish, start_session

from .inputs import CaseInputs, InputIntegrityError, t, transcript
from .mapping import nfc

FIELDS = ("chief_complaint", "onset_duration", "severity", "allergy_status", "allergens",
          "current_medications", "relevant_history")


def make_context() -> tuple[VoiceContext, Any]:
    engine = make_engine("sqlite://")
    create_schema(engine)
    create_voice_schema(engine)
    provider = build_provider("mock", s3_harness.Settings())
    actor = s3_harness.CurrentUser(id=0, username="e1-eval", role=s3_harness.Role.NURSE)
    return VoiceContext(engine=engine, provider=provider, actor=actor, request_id="e1-voice"), engine


def turn_windows(tx: dict[str, Any]) -> list[tuple[str, str, datetime, datetime]]:
    """(speaker, NFC text, started_at, ended_at) per recorded turn."""
    turns = sorted(tx["turns"], key=lambda x: x["turn_index"])
    out = []
    for i, x in enumerate(turns):
        start = t(x["spoken_at"])
        end = t(turns[i + 1]["spoken_at"]) if i + 1 < len(turns) else t(tx["observed_at"])
        out.append((x["speaker"], nfc(x["text"]), start, end))
    return out


def replay(ctx: VoiceContext, case: CaseInputs, dp: str = "T1") -> dict[str, Any]:
    """Replay one case's transcript; return the final S3 facts per field (JSON-safe, no generated IDs)."""
    snap = case.snapshots[dp]
    tx = transcript(snap)
    T = t(snap["as_of"])
    if tx is None:
        return {"status": "no_transcript", "facts": {}, "handoff_reason": None, "n_turns": 0}
    windows = turn_windows(tx)
    for _, _, _, end in windows:
        if end > T:
            raise InputIntegrityError(f"{case.case_id}: a turn ends after T")
    started = start_session(ctx, StartSessionBody(patient_ref=f"SYN-{case.patient_ref}", data_class="synthetic"),
                            windows[0][2])
    sid = started["session"]["session_id"]
    text_by_turn: dict[str, tuple[int, str, str]] = {}
    for idx, (speaker, text, start, end) in enumerate(windows):
        resp = add_turn(ctx, sid, AddTurnBody(speaker=speaker, text=text, started_at=start, ended_at=end), end)
        text_by_turn[resp["turn"]["turn_id"]] = (idx, speaker, text)
    done = finish(ctx, sid, t(tx["observed_at"]))
    facts: dict[str, Any] = {}
    for f in done["facts"]:
        span = [text_by_turn[x] for x in f["span_turn_ids"]]
        facts[f["field"]] = {
            "state": f["state"],
            "value": f["value"],
            "value_text": f["value_text"],
            "available_at_time": f["available_at_time"],
            "event_time": f["event_time"],
            "span_turn_indexes": [s[0] for s in span],
            "span_text": " ".join(s[2] for s in span),
        }
        if t(f["available_at_time"]) > T:
            raise InputIntegrityError(f"{case.case_id}: S3 fact {f['field']} available after T")
    return {
        "status": "replayed",
        "transcript_item_id": tx["item_id"],
        "n_turns": len(windows),
        "handoff_reason": done["handoff_reason"],
        "missing_fields": done["missing_fields"],
        "facts": {k: facts[k] for k in FIELDS if k in facts},
    }


def run_split(cases: list[CaseInputs]) -> dict[str, dict[str, Any]]:
    ctx, engine = make_context()
    try:
        return {c.case_id: replay(ctx, c) for c in cases}
    finally:
        engine.dispose()
