"""Patient Journey models — `docs/shared/PATIENT_JOURNEY_SCHEMA.md` v1.0.0.

The journey is append-only. Nothing here mutates it; the snapshot operation in
`shared/snapshot.py` derives a new artifact instead.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

EventType = Literal[
    "CHIEF_COMPLAINT", "TRIAGE_NOTE", "DEMOGRAPHICS", "HISTORY", "MEDICATION",
    "ALLERGY", "VITAL", "EXAM", "LAB", "ECG", "IMAGE_2D", "IMAGE_3D",
    "REPORT", "CONSULT", "DIAGNOSIS", "DISPOSITION", "OUTCOME",
]

Modality = Literal["TEXT", "STRUCTURED", "IMAGE_2D", "IMAGE_3D", "SIGNAL", "LABEL", "REFERENCE"]

DataClassification = Literal[
    "SYNTHETIC", "PUBLIC_LICENSED", "DEIDENTIFIED_APPROVED",
    "IDENTIFIABLE_OR_LINKABLE", "RESTRICTED_DERIVATIVE",
]

Split = Literal["train", "validation", "test", "expert_test"]


class SourceRef(BaseModel):
    """Where an event came from, and at which version."""

    model_config = ConfigDict(extra="forbid")

    system: str = Field(min_length=1)
    version: str = Field(min_length=1)
    record_ref: str | None = None
    dataset: str | None = None


class JourneyEvent(BaseModel):
    """One evidence or label event on the timeline.

    `available_at_time` is the field the whole temporal rule rests on: it is when the
    item became usable for a decision, which is not when it was observed. For a lab
    result in MIMIC-IV that is `storetime`, not `charttime` — see
    `docs/research/DATASET_FEASIBILITY.md`.
    """

    model_config = ConfigDict(extra="allow")

    event_id: str = Field(min_length=1)
    event_type: str = Field(min_length=2)
    modality: Modality
    observed_at: datetime
    available_at_time: datetime
    status: str = Field(min_length=1)
    data_classification: DataClassification
    source_ref: SourceRef
    value: Any | None = None
    payload_ref: str | None = None

    @field_validator("available_at_time")
    @classmethod
    def _availability_not_before_observation(cls, v: datetime, info: Any) -> datetime:
        """Evidence cannot become available before it was observed.

        This catches a mis-derived availability time at ingestion rather than letting it
        widen the snapshot silently — the failure mode RISK-0003 exists to prevent.
        """
        observed = info.data.get("observed_at")
        if observed is not None and v < observed:
            raise ValueError(
                f"available_at_time {v.isoformat()} precedes observed_at {observed.isoformat()}"
            )
        return v


class PatientJourney(BaseModel):
    """An append-only timeline for one encounter.

    `patient_id` is the split key. Splitting happens at patient level before any
    example is generated, so a patient never appears in two splits
    (`CLAUDE.md` §Non-negotiable data rules 1).
    """

    model_config = ConfigDict(extra="allow")

    schema_version: str
    journey_id: str = Field(min_length=1)
    patient_id: str = Field(min_length=1)
    encounter_id: str = Field(min_length=1)
    split: Split
    data_classification: DataClassification
    source: SourceRef
    encounter_start: datetime
    events: list[JourneyEvent]
    outcomes: list[JourneyEvent] | None = None

    @field_validator("events")
    @classmethod
    def _event_ids_unique(cls, events: list[JourneyEvent]) -> list[JourneyEvent]:
        seen = [e.event_id for e in events]
        duplicates = {i for i in seen if seen.count(i) > 1}
        if duplicates:
            raise ValueError(f"duplicate event_id within journey: {sorted(duplicates)}")
        return events
