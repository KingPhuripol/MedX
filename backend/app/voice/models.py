"""Voice Agent local types (slice s3). All models forbid extra fields."""

from __future__ import annotations

import re
from typing import Any, Literal

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field

VOICE_VERSION = "s3-0.1.0"
EXTRACT_TASK = "voice.intake_extract"

# Fixed ask order (PROPOSAL 1.3.1: chief complaint, duration, drug allergy, ...).
ASK_ORDER: tuple[str, ...] = (
    "chief_complaint",
    "onset_duration",
    "severity",
    "allergy_status",
    "current_medications",
    "relevant_history",
)
LIST_FIELDS = frozenset({"allergens", "current_medications", "relevant_history"})
FACT_FIELDS: tuple[str, ...] = (*ASK_ORDER[:4], "allergens", *ASK_ORDER[4:])

# Closed symptom vocabulary. These are symptom categories, not diagnoses.
CHIEF_COMPLAINT_CODES: tuple[str, ...] = (
    "fever", "cough", "sore_throat", "runny_nose", "headache", "dizziness", "chest_pain", "dyspnea",
    "abdominal_pain", "diarrhea", "nausea_vomiting", "rash", "back_pain", "joint_pain", "dysuria", "fatigue",
)
SEVERITY_CATEGORIES = ("mild", "moderate", "severe")
ALLERGY_VALUES = ("none", "present")
ISO_DURATION = re.compile(r"^P(?:T\d{1,4}[HM]|\d{1,4}[DWMY])$")

Speaker = Literal["agent", "patient", "relative", "nurse"]
HumanSpeaker = Literal["patient", "relative", "nurse"]
FactState = Literal["KNOWN", "UNKNOWN", "REFUSED"]
Status = Literal["MISSING", "KNOWN", "UNKNOWN", "REFUSED"]
FactField = Literal[
    "chief_complaint", "onset_duration", "severity", "allergy_status", "allergens",
    "current_medications", "relevant_history",
]
HandoffReason = Literal["complete", "attempts_exhausted", "nurse_attention_phrase", "extraction_unavailable"]


class _Strict(BaseModel):
    model_config = ConfigDict(extra="forbid")


class Turn(_Strict):
    turn_id: str
    session_id: str
    seq: int
    speaker: Speaker
    text: str
    started_at: AwareDatetime
    ended_at: AwareDatetime


class IntakeFact(_Strict):
    fact_id: str
    session_id: str
    field: FactField
    state: FactState
    value: str | int | list[str] | None
    value_text: str
    span_turn_ids: list[str] = Field(min_length=1)
    event_time: AwareDatetime
    available_at_time: AwareDatetime
    extractor: str
    provider: str
    model_version: str
    request_sha256: str
    supersedes_fact_id: str | None


class FieldStatus(_Strict):
    field: str
    status: Status
    times_asked: int
    not_elicited: bool = False


class NextAction(_Strict):
    action: Literal["ask", "handoff"]
    field: str | None
    utterance_id: str
    utterance_th: str
    reason: HandoffReason | None
    missing_fields: list[str] = Field(default_factory=list)


# ---- extractor output (validated before anything is written) ----


class ExtractedFact(_Strict):
    field: FactField
    state: FactState
    value: str | int | list[str] | None
    value_text: str = Field(min_length=1, max_length=500)
    span_turn_ids: list[str] = Field(min_length=1, max_length=20)


class ExtractOutput(_Strict):
    label: str
    extractor: str = Field(min_length=1, max_length=64)
    facts: list[ExtractedFact] = Field(max_length=20)


# ---- API bodies ----


class StartSessionBody(_Strict):
    patient_ref: str = Field(pattern=r"^SYN-[A-Za-z0-9-]{1,60}$")
    data_class: Literal["synthetic"]


class AddTurnBody(_Strict):
    speaker: HumanSpeaker
    text: str = Field(min_length=1, max_length=2000)
    started_at: AwareDatetime
    ended_at: AwareDatetime
