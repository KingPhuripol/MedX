"""Patient Journey models — `docs/shared/PATIENT_JOURNEY_SCHEMA.md` v1.0.0.

These models mirror `schemas/patient-journey.schema.json` exactly, including what it
*refuses*. The schema sets `additionalProperties: false` throughout, so these models set
`extra="forbid"`: a model looser than its schema will happily accept a document the
contract rejects, and that gap is the drift RISK-0006 describes.
`tests/test_contracts.py` pins the parity in both directions.

The journey is append-only. Nothing here mutates it; `shared/snapshot.py` derives a new
artifact instead.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

EventType = Literal[
    "CHIEF_COMPLAINT", "TRIAGE_NOTE", "DEMOGRAPHICS", "HISTORY", "MEDICATION",
    "ALLERGY", "VITAL", "EXAM", "LAB", "ECG", "IMAGE_2D", "IMAGE_3D",
    "REPORT", "CONSULT", "DIAGNOSIS", "DISPOSITION", "OUTCOME", "MISSINGNESS",
]

Modality = Literal["TEXT", "STRUCTURED", "IMAGE_2D", "IMAGE_3D", "SIGNAL", "LABEL", "REFERENCE"]

#: The four intake states the Front Door must distinguish (A1) map onto this enum:
#: known = AVAILABLE, asked-but-unknown = MEASURED_UNKNOWN, refused = WITHHELD,
#: not yet in existence = NOT_AVAILABLE_YET / NOT_MEASURED. Collapsing any of these into
#: "absent" is the missing-modality hallucination hazard in SAFETY_SPEC.md.
EventStatus = Literal[
    "AVAILABLE", "NOT_MEASURED", "MEASURED_UNKNOWN", "NOT_AVAILABLE_YET",
    "WITHHELD", "UNSUPPORTED", "CORRUPT", "NOT_APPLICABLE",
]

DataClassification = Literal[
    "SYNTHETIC", "PUBLIC_LICENSED", "DEIDENTIFIED_APPROVED",
    "IDENTIFIABLE_OR_LINKABLE", "RESTRICTED_DERIVATIVE",
]

Split = Literal[
    "train", "validation", "internal_test", "external_test", "expert_test",
    "architecture_intervention", "missing_modality_test", "unseen_combination_test",
]

#: Statuses that carry no usable evidence. They are recorded rather than omitted, so a
#: reader can tell "we asked and they did not know" from "we never asked".
NON_EVIDENTIAL_STATUSES: frozenset[str] = frozenset(
    {"NOT_MEASURED", "MEASURED_UNKNOWN", "NOT_AVAILABLE_YET", "WITHHELD",
     "UNSUPPORTED", "CORRUPT", "NOT_APPLICABLE"}
)


class JourneySource(BaseModel):
    """`journey.source` — system and version only, per the schema."""

    model_config = ConfigDict(extra="forbid")

    system: str = Field(min_length=2)
    version: str = Field(min_length=1)


class EventSourceRef(BaseModel):
    """`event.source_ref` — the schema requires `record_ref` here, unlike `journey.source`."""

    model_config = ConfigDict(extra="forbid")

    system: str = Field(min_length=2)
    version: str = Field(min_length=1)
    record_ref: str = Field(min_length=2)


class JourneyEvent(BaseModel):
    """One evidence or label event on the timeline.

    `available_at_time` is the field the whole temporal rule rests on: when the item
    became usable for a decision, which is not when it was observed. For a MIMIC-IV lab
    that is `storetime`, not `charttime` — see `docs/research/DATASET_FEASIBILITY.md`.
    """

    model_config = ConfigDict(extra="forbid")

    event_id: str = Field(min_length=1)
    event_type: EventType
    modality: Modality
    observed_at: datetime
    available_at_time: datetime
    recorded_at: datetime | None = None
    status: EventStatus
    data_classification: DataClassification
    source_ref: EventSourceRef
    payload_ref: str | None = None
    checksum: str | None = None
    value: Any | None = None
    code: str | None = None
    unit: str | None = None
    quality_flags: list[str] = Field(default_factory=list)
    authorization_tags: list[str] = Field(default_factory=list)

    @field_validator("available_at_time")
    @classmethod
    def _availability_not_before_observation(cls, v: datetime, info: Any) -> datetime:
        """Evidence cannot become available before it was observed.

        Catches a mis-derived availability time at ingestion rather than after it has
        widened a snapshot — the failure RISK-0003 exists to prevent.
        """
        observed = info.data.get("observed_at")
        if observed is not None and v < observed:
            raise ValueError(
                f"available_at_time {v.isoformat()} precedes observed_at {observed.isoformat()}"
            )
        return v

    @field_validator("quality_flags", "authorization_tags")
    @classmethod
    def _unique_items(cls, values: list[str]) -> list[str]:
        if len(values) != len(set(values)):
            raise ValueError("items must be unique")
        return values

    @property
    def carries_evidence(self) -> bool:
        """False for a recorded gap — a MISSINGNESS entry is information about absence."""
        return self.status == "AVAILABLE"


class PatientJourney(BaseModel):
    """An append-only timeline for one encounter.

    `patient_id` is the split key. Splitting happens at patient level before any example
    is generated, so a patient never appears in two splits
    (`CLAUDE.md` §Non-negotiable data rules 1).

    Note there is no `outcomes` field. `PATIENT_JOURNEY_SCHEMA.md` documents one, but
    `schemas/patient-journey.schema.json` sets `additionalProperties: false` and does not
    define it, so a journey carrying `outcomes` is invalid under the enforced contract.
    These models follow the machine schema, which `project_state/contract_versions.json`
    names as the machine record. The discrepancy is recorded for a human decision rather
    than resolved here by changing a contract unilaterally.

    Retrospective labels still live on the timeline as ordinary events — the fixture's
    `ev-003` is a `DIAGNOSIS`/`LABEL` event — and the snapshot rule applies to them the
    same way, so nothing about temporal protection depends on that field existing.
    """

    model_config = ConfigDict(extra="forbid")

    schema_version: Literal["1.0.0"]
    journey_id: str = Field(min_length=1)
    patient_id: str = Field(min_length=1)
    encounter_id: str = Field(min_length=1)
    split: Split
    data_classification: DataClassification
    source: JourneySource
    encounter_start: datetime
    events: list[JourneyEvent] = Field(min_length=1)

    @field_validator("events")
    @classmethod
    def _event_ids_unique(cls, events: list[JourneyEvent]) -> list[JourneyEvent]:
        seen = [e.event_id for e in events]
        duplicates = {i for i in seen if seen.count(i) > 1}
        if duplicates:
            raise ValueError(f"duplicate event_id within journey: {sorted(duplicates)}")
        return events


#: Kept as an alias so existing imports of `SourceRef` do not break; new code should name
#: the specific one, because the two shapes genuinely differ in the schema.
SourceRef = EventSourceRef
