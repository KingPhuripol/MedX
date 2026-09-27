"""Reader:Text provider = S3 voice extraction + the i2 symptom extractor (slice i2, PROPOSAL 3.1).

The Voice Agent is outside the graph; its transcript (``IntakeTranscript``) and extracted facts
(``VoiceIntakeFacts``) enter the graph as ClinicalText and Reader:Text turns them into typed ``Findings``.

* Transcript present (always the source when present): one ``voice.intake_extract`` call per patient turn
  (turns visible up to that turn, as the S3 cascade does; ``last_asked_field`` is not known from a recorded
  transcript and is ``None``) and one ``voice.symptom_extract.v1`` call over all patient turns. Only turns
  with ``spoken_at <= T`` (and ended by T) are read. S3 schema/grounding validation and the S3 allergy
  guard are reused unchanged. The first KNOWN chief complaint is kept; other fields: latest wins.
* Only ``VoiceIntakeFacts`` (S4 author fixtures, live S3 sessions without a transcript): pass-through, 0 calls.

``invoke(task, inputs)`` returns ``(output, model_version)`` or raises :class:`ReaderError`.
"""

from __future__ import annotations

import unicodedata
from collections.abc import Callable, Sequence
from datetime import datetime
from typing import Any

from app.voice import symptoms as symptom_extractor
from app.voice.models import EXTRACT_TASK, ExtractedFact
from app.voice.service import reconcile_allergy, validate_extraction

from .data import IntakeTranscript, IntakeValue, SymptomFact, Turn, TurnRef, VoiceIntakeFacts

SYMPTOM_TASK = symptom_extractor.TASK
Invoke = Callable[[str, dict[str, Any]], tuple[dict[str, Any], str]]


class ReaderError(Exception):
    """A gateway failure or an invalid/ungrounded extractor output: the node fails safe (no Findings)."""


def _nfc(s: str) -> str:
    return unicodedata.normalize("NFC", s)


def _end(t: Turn) -> datetime:
    return t.ended_at or t.spoken_at


def visible_turns(item: IntakeTranscript, T: datetime) -> list[Turn]:
    """Turns spoken and ended by T (defence in depth: the snapshot already excludes later items)."""
    return sorted((t for t in item.turns if t.spoken_at <= T and _end(t) <= T), key=lambda t: t.turn_index)


def _turn_id(item: IntakeTranscript, t: Turn) -> str:
    return t.turn_id or f"{item.item_id}#{t.turn_index}"


def read_transcript(
    item: IntakeTranscript, T: datetime, invoke: Invoke
) -> tuple[list[IntakeValue], list[SymptomFact], list[str]]:
    """(intake values, symptom facts, "task=model_version" list) for one transcript at T."""
    turns = visible_turns(item, T)
    by_id = {_turn_id(item, t): t for t in turns}
    view = {tid: {"speaker": t.speaker, "text": _nfc(t.text), "ended_at": _end(t).isoformat()}
            for tid, t in by_id.items()}
    versions: set[str] = set()
    latest: dict[str, ExtractedFact] = {}
    first_cc: ExtractedFact | None = None
    for i, t in enumerate(turns):
        if t.speaker != "patient":
            continue
        upto = [(_turn_id(item, x), x) for x in turns[: i + 1]]
        inputs = {"turns": [{"turn_id": tid, "speaker": x.speaker, "text": _nfc(x.text),
                             "ended_at": _end(x).isoformat()} for tid, x in upto],
                  "last_asked_field": None}
        output, version = invoke(EXTRACT_TASK, inputs)
        versions.add(f"{EXTRACT_TASK}={version}")
        facts, reason = validate_extraction(output, {tid: view[tid] for tid, _ in upto}, _end(t))
        if facts is None:
            raise ReaderError(f"{EXTRACT_TASK}: {reason}")
        facts, _held = reconcile_allergy(facts, latest)
        for f in facts:
            if f.field == "chief_complaint" and f.state == "KNOWN" and first_cc is None:
                first_cc = f
            latest[f.field] = f
    if first_cc is not None:
        latest["chief_complaint"] = first_cc
    intake = [_intake_value(item, f, by_id) for _, f in sorted(latest.items())]

    patient = [t for t in turns if t.speaker == "patient"]
    output, version = invoke(SYMPTOM_TASK, {"turns": [
        {"turn_index": t.turn_index, "speaker": t.speaker, "text": _nfc(t.text), "spoken_at": t.spoken_at.isoformat()}
        for t in patient]})
    versions.add(f"{SYMPTOM_TASK}={version}")
    return intake, _symptom_facts(item, output, {t.turn_index: t for t in patient}), sorted(versions)


def _intake_value(item: IntakeTranscript, f: ExtractedFact, by_id: dict[str, Turn]) -> IntakeValue:
    span = [by_id[tid] for tid in dict.fromkeys(f.span_turn_ids)]
    if not span:
        raise ReaderError(f"{f.field}: fact cites no turn")
    return IntakeValue(
        kind=f.field, state=f.state, value=f.value, value_text=f.value_text,
        evidence_turns=tuple(TurnRef(item_id=item.item_id, turn_index=t.turn_index, spoken_at=t.spoken_at) for t in span),
        span_text=" ".join(_nfc(t.text) for t in span)[:2000], available_at_time=max(_end(t) for t in span),
    )


def _symptom_facts(item: IntakeTranscript, output: Any, patient: dict[int, Turn]) -> list[SymptomFact]:
    if not isinstance(output, dict) or not isinstance(output.get("facts"), list):
        raise ReaderError(f"{SYMPTOM_TASK}: schema_invalid")
    out: list[SymptomFact] = []
    try:
        for f in output["facts"]:
            cited = [patient[int(i)] for i in f["evidence_turns"]]  # KeyError: a cited turn that is not a patient turn
            if not cited:
                raise ReaderError(f"{SYMPTOM_TASK}: {f.get('name')} cites no turn")
            out.append(SymptomFact(
                name=f["name"], state=f["state"], onset=f.get("onset", "unknown"),
                evidence_turns=tuple(TurnRef(item_id=item.item_id, turn_index=t.turn_index, spoken_at=t.spoken_at)
                                     for t in cited),
                source_refs=tuple(f["source_refs"]), available_at_time=max(_end(t) for t in cited),
            ))
    except (KeyError, TypeError, ValueError) as exc:
        raise ReaderError(f"{SYMPTOM_TASK}: invalid output ({type(exc).__name__})") from None
    return out


# ------------------------------------------------------------------------------- pass-through


_S4_SYMPTOM_VALUE = {"present": "present", "absent": "absent", "unknown": "unknown"}


def pass_through(items: Sequence[VoiceIntakeFacts]) -> tuple[list[IntakeValue], list[SymptomFact]]:
    """VoiceIntakeFacts -> Findings parts with 0 calls. ``symptom.*`` facts (S4 fixtures) become SymptomFacts.

    Every fact is kept with its own ``available_at_time``: the S4 snapshot applies latest-wins across times
    and worst-value/flag rules within one time, exactly as for the source facts (no merging here).
    """
    intake: list[IntakeValue] = []
    facts: list[SymptomFact] = []
    for item in sorted(items, key=lambda i: (i.available_at_time, i.item_id)):
        for f in item.facts:
            if f.field.startswith("symptom."):
                state = _S4_SYMPTOM_VALUE.get(f.value) if f.state == "KNOWN" else "unknown"
                if state is None:
                    raise ReaderError(f"{item.item_id}: invalid symptom value for {f.field}")
                facts.append(SymptomFact(name=f.field.removeprefix("symptom."), state=state,  # type: ignore[arg-type]
                                         source_item=item.item_id, available_at_time=f.available_at_time))
            else:
                intake.append(IntakeValue(kind=f.field, state=f.state, value=f.value, value_text=f.value_text,
                                          source_item=item.item_id, available_at_time=f.available_at_time))
    return intake, facts
