"""The snapshot operation from `docs/shared/PATIENT_JOURNEY_SCHEMA.md`.

Given a journey and a decision time T, produce the set of evidence a decision maker
could actually have had at T. This is the single place the temporal rule is applied,
so there is one implementation to audit rather than one per call site.

The base journey is never mutated; a snapshot is a new artifact.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from datetime import datetime

from shared.contracts.journey import JourneyEvent, PatientJourney


@dataclass(frozen=True)
class RejectedEvent:
    """An event excluded from the snapshot, with the reason recorded.

    Rejections are kept rather than dropped: the contract requires a snapshot to record
    what was excluded and why, so an auditor can tell "was not available yet" from
    "was never there".
    """

    event_id: str
    reason: str


@dataclass(frozen=True)
class JourneySnapshot:
    """Evidence available at `decision_time`, plus what was excluded and why."""

    journey_id: str
    patient_id: str
    decision_time: datetime
    included: tuple[JourneyEvent, ...]
    rejected: tuple[RejectedEvent, ...]
    missing_information: tuple[str, ...] = field(default=())

    @property
    def evidence_ids(self) -> tuple[str, ...]:
        return tuple(e.event_id for e in self.included)

    def checksum(self) -> str:
        """Stable digest of what the snapshot contains.

        Covers the identity and availability time of every included event, so the same
        decision time over the same journey reproduces the same checksum, and any change
        to the evidence set changes it.
        """
        payload = json.dumps(
            {
                "journey_id": self.journey_id,
                "decision_time": self.decision_time.isoformat(),
                "evidence": [
                    {"id": e.event_id, "available_at_time": e.available_at_time.isoformat()}
                    for e in self.included
                ],
            },
            sort_keys=True,
            separators=(",", ":"),
        )
        return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def take_snapshot(
    journey: PatientJourney,
    decision_time: datetime,
    *,
    allowed_classifications: frozenset[str] | None = None,
    missing_information: tuple[str, ...] = (),
) -> JourneySnapshot:
    """Select the events available at `decision_time`.

    An event is included when `available_at_time <= decision_time`. Everything later is
    rejected as `FUTURE_EVIDENCE` — including retrospective labels stored in the same
    file, which is exactly the case the rule exists for: a final diagnosis sitting in
    the journey must not reach a decision made hours earlier.

    Labels are ordinary events on the timeline, so they go through this rule like
    anything else. A label mis-stamped as early is a leak, and honouring the stamp
    without checking would hide it.
    """
    included: list[JourneyEvent] = []
    rejected: list[RejectedEvent] = []

    for event in journey.events:
        if event.available_at_time > decision_time:
            rejected.append(RejectedEvent(event.event_id, "FUTURE_EVIDENCE"))
            continue
        if (
            allowed_classifications is not None
            and event.data_classification not in allowed_classifications
        ):
            rejected.append(RejectedEvent(event.event_id, "CLASSIFICATION_NOT_AUTHORIZED"))
            continue
        included.append(event)

    # Deterministic order: availability time, then event ID for ties.
    included.sort(key=lambda e: (e.available_at_time, e.event_id))
    rejected.sort(key=lambda r: r.event_id)

    return JourneySnapshot(
        journey_id=journey.journey_id,
        patient_id=journey.patient_id,
        decision_time=decision_time,
        included=tuple(included),
        rejected=tuple(rejected),
        missing_information=missing_information,
    )
