"""Intake — `docs/innovation/CLINICAL_WORKFLOW.md` steps 1, 2 and 5.

Acceptance criterion A1 requires intake to capture **known, unknown, refused and
unavailable distinctly**. Those four are not decoration: collapsing any of them into
"absent" is the missing-modality hallucination hazard in `SAFETY_SPEC.md`, where an
absent image gets treated as a normal one.

No schema change was needed — `schemas/patient-journey.schema.json` already carries the
statuses and a `MISSINGNESS` event type. A recorded gap is an event on the timeline like
any other, with its own `available_at_time`, so "we asked at 09:05 and they did not know"
is itself evidence available from 09:05.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any, Literal

from shared.contracts.journey import (
    EventSourceRef,
    JourneyEvent,
    JourneySource,
    PatientJourney,
)

#: What the clinician-facing intake form can say about one item.
IntakeState = Literal["KNOWN", "UNKNOWN", "REFUSED", "NOT_AVAILABLE"]

#: Intake state -> the schema status that records it. The four map one-to-one, so the
#: distinction survives into the machine record rather than living only in the UI.
STATE_TO_STATUS: dict[str, str] = {
    "KNOWN": "AVAILABLE",
    "UNKNOWN": "MEASURED_UNKNOWN",      # asked, and the answer is not known
    "REFUSED": "WITHHELD",              # asked, and the person declined to answer
    "NOT_AVAILABLE": "NOT_AVAILABLE_YET",  # not yet in existence, e.g. a pending result
}

#: Default modality per information type, used when an item is KNOWN.
TYPE_MODALITY: dict[str, str] = {
    "CHIEF_COMPLAINT": "TEXT",
    "TRIAGE_NOTE": "TEXT",
    "HISTORY": "TEXT",
    "DEMOGRAPHICS": "STRUCTURED",
    "MEDICATION": "STRUCTURED",
    "ALLERGY": "STRUCTURED",
    "VITAL": "STRUCTURED",
    "EXAM": "STRUCTURED",
    "LAB": "STRUCTURED",
    "ECG": "SIGNAL",
    "IMAGE_2D": "IMAGE_2D",
    "IMAGE_3D": "IMAGE_3D",
    "REPORT": "TEXT",
    "CONSULT": "TEXT",
    # Retrospective labels. They may be appended once known, and the snapshot rule keeps
    # them out of any decision made before they existed. The Front Door additionally
    # excludes LABEL modality from live requests: an outcome is never an input.
    "DIAGNOSIS": "LABEL",
    "DISPOSITION": "LABEL",
    "OUTCOME": "LABEL",
}


@dataclass(frozen=True)
class IntakeItem:
    """One answer on the intake form, including the answers that are not values."""

    information_type: str
    state: IntakeState
    value: Any | None = None
    observed_at: datetime | None = None
    #: When this became usable for a decision. Defaults to `observed_at`; a pending lab
    #: that will only result later carries a later time and is therefore withheld from
    #: earlier snapshots automatically.
    available_at_time: datetime | None = None
    note: str | None = None


class IntakeError(ValueError):
    """An intake submission that cannot be recorded truthfully."""


def build_event(
    item: IntakeItem,
    *,
    event_id: str,
    default_time: datetime,
    source: EventSourceRef,
    data_classification: str = "SYNTHETIC",
) -> JourneyEvent:
    """Turn one intake answer into a timeline event."""
    if item.state == "KNOWN" and item.value is None:
        raise IntakeError(
            f"{item.information_type} is marked KNOWN but carries no value; "
            "use UNKNOWN, REFUSED or NOT_AVAILABLE instead of recording an empty value"
        )
    if item.state != "KNOWN" and item.value is not None:
        raise IntakeError(
            f"{item.information_type} is marked {item.state} but carries a value; "
            "a recorded gap must not smuggle one in"
        )
    if item.information_type not in TYPE_MODALITY:
        raise IntakeError(f"unknown information_type {item.information_type!r}")

    observed = item.observed_at or default_time
    available = item.available_at_time or observed

    if item.state == "KNOWN":
        return JourneyEvent(
            event_id=event_id,
            event_type=item.information_type,
            modality=TYPE_MODALITY[item.information_type],
            observed_at=observed,
            available_at_time=available,
            status="AVAILABLE",
            data_classification=data_classification,
            source_ref=source,
            value=item.value,
            code=item.information_type,
        )

    # A recorded gap. It is an event, not an omission: the fact that the question was
    # asked and left open is itself information available from this moment.
    return JourneyEvent(
        event_id=event_id,
        event_type="MISSINGNESS",
        modality="REFERENCE",
        observed_at=observed,
        available_at_time=available,
        status=STATE_TO_STATUS[item.state],
        data_classification=data_classification,
        source_ref=source,
        code=item.information_type,
        value=None,
        quality_flags=[f"INTAKE_{item.state}"],
    )


def build_journey(
    *,
    journey_id: str,
    patient_id: str,
    encounter_id: str,
    encounter_start: datetime,
    items: list[IntakeItem],
    split: str = "expert_test",
    data_classification: str = "SYNTHETIC",
    system: str = "front-door-intake",
    version: str = "1.0.0",
) -> PatientJourney:
    """Create an encounter from an intake submission (workflow step 1 and 2)."""
    if not items:
        raise IntakeError("intake requires at least one item, even if every one is a gap")

    events = [
        build_event(
            item,
            event_id=f"ev-{i:03d}",
            default_time=encounter_start,
            source=EventSourceRef(system=system, version=version, record_ref=f"{journey_id}-{i:03d}"),
            data_classification=data_classification,
        )
        for i, item in enumerate(items, start=1)
    ]

    return PatientJourney(
        schema_version="1.0.0",
        journey_id=journey_id,
        patient_id=patient_id,
        encounter_id=encounter_id,
        split=split,
        data_classification=data_classification,
        source=JourneySource(system=system, version=version),
        encounter_start=encounter_start,
        events=events,
    )


def append_event(journey: PatientJourney, item: IntakeItem, *, default_time: datetime) -> PatientJourney:
    """Append one item to a journey, returning a new journey (workflow step 5).

    The journey is append-only, so this never edits an existing event and never returns
    the same object. Correcting an earlier entry means appending a new event, not
    rewriting history.
    """
    next_index = len(journey.events) + 1
    event = build_event(
        item,
        event_id=f"ev-{next_index:03d}",
        default_time=default_time,
        source=EventSourceRef(
            system=journey.source.system,
            version=journey.source.version,
            record_ref=f"{journey.journey_id}-{next_index:03d}",
        ),
        data_classification=journey.data_classification,
    )
    if any(e.event_id == event.event_id for e in journey.events):
        raise IntakeError(f"event_id {event.event_id} already exists in {journey.journey_id}")

    return journey.model_copy(update={"events": [*journey.events, event]})
