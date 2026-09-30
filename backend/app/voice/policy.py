"""Deterministic next-question policy and nurse-attention interrupt. No model involved."""

from __future__ import annotations

import re
from collections.abc import Iterable, Mapping

from .models import ASK_ORDER, AmbientAction, FieldStatus, NextAction
from .utterances_th import utterance

MAX_ASKS = 2

# Nurse-attention phrase list — SIMULATION-ONLY PLACEHOLDER pending clinical sign-off (Decision D1).
# It only ever routes toward the nurse. It assigns no urgency level, triage category or department.
ATTENTION_SINGLE: tuple[str, ...] = (
    "หมดสติ", "ไม่รู้สึกตัว", "ชัก", "เลือดออกมาก", "เลือดออกไม่หยุด", "อาเจียนเป็นเลือด",
    "ถ่ายเป็นเลือด", "อยากตาย", "ฆ่าตัวตาย", "ทำร้ายตัวเอง", "ปากเบี้ยว", "แขนขาอ่อนแรง",
)
# Every group in a combination must appear somewhere in the session's non-agent turns so far.
ATTENTION_COMBOS: tuple[tuple[tuple[str, ...], ...], ...] = (
    (("เจ็บหน้าอก", "แน่นหน้าอก"), ("หายใจไม่ออก", "หายใจลำบาก", "เหงื่อแตก", "เหงื่อออกมาก")),
)
_WS = re.compile(r"\s+")


def _norm(text: str) -> str:
    return _WS.sub("", text)


def nurse_attention_hit(current_text: str, prior_texts: Iterable[str] = ()) -> bool:
    """True if the current non-agent turn completes a listed phrase or combination."""
    current = _norm(current_text)
    if any(p in current for p in ATTENTION_SINGLE):
        return True
    context = "".join(_norm(t) for t in prior_texts) + current
    for combo in ATTENTION_COMBOS:
        if all(any(p in context for p in group) for group in combo) and any(
            p in current for group in combo for p in group
        ):
            return True
    return False


def handoff(reason: str, missing: list[str] | None = None) -> NextAction:
    uid = f"handoff.{reason}"
    return NextAction(
        action="handoff", field=None, utterance_id=uid, utterance_th=utterance(uid), reason=reason,  # type: ignore[arg-type]
        missing_fields=list(missing or []),
    )


def ask(field: str, times_asked: int) -> NextAction:
    uid = f"{'ask' if times_asked == 0 else 'reask'}.{field}"
    return NextAction(action="ask", field=field, utterance_id=uid, utterance_th=utterance(uid), reason=None)


def missing_fields(statuses: Mapping[str, FieldStatus]) -> list[str]:
    return [f for f in ASK_ORDER if statuses[f].status == "MISSING"]


def next_action(statuses: Mapping[str, FieldStatus]) -> NextAction:
    """Ask the first MISSING field (fixed order) asked fewer than MAX_ASKS times; else hand off.

    KNOWN / UNKNOWN / REFUSED fields are never asked. MISSING is never turned into a negative.
    """
    for field in ASK_ORDER:
        st = statuses[field]
        if st.status == "MISSING" and st.times_asked < MAX_ASKS:
            return ask(field, st.times_asked)
    missing = missing_fields(statuses)
    if missing:
        return handoff("attempts_exhausted", missing)
    return handoff("complete")


def ambient_action(statuses: Mapping[str, FieldStatus], attention: bool, extraction_error: bool) -> AmbientAction:
    """Ambient mode (v2a): suggest the allowlisted question for the first MISSING field to the nurse.

    Nurse attention, then extraction failure, preempt everything and are sticky. There is no ask limit.
    """
    missing = missing_fields(statuses)
    if attention or extraction_error:
        reason = "nurse_attention_phrase" if attention else "extraction_unavailable"
        return AmbientAction(kind="handoff", field=None, suggested_question_id=None, suggested_question_th=None,
                             reason=reason, missing_fields=missing)
    if not missing:
        return AmbientAction(kind="complete", field=None, suggested_question_id=None, suggested_question_th=None,
                             reason="complete", missing_fields=[])
    field = missing[0]
    uid = f"{'ask' if statuses[field].times_asked == 0 else 'reask'}.{field}"
    return AmbientAction(kind="prompt_nurse", field=field, suggested_question_id=uid,
                         suggested_question_th=utterance(uid), reason=None, missing_fields=missing)
