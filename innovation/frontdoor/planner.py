"""Adaptive information gathering — `CLINICAL_WORKFLOW.md` step 4.

Ranks what to ask or collect next, using only information available at the decision time.

Two constraints from the spec shape this more than the ranking does:

- **It recommends information, it does not order tests.** Every candidate is a suggestion
  for a human, carrying the reason it would change something.
- **It must not coerce answers.** An item the person declined is *not* put back at the top
  of the queue. Declined items are surfaced separately, marked as declined, so a clinician
  can see the gap without the system nagging on their behalf.
"""

from __future__ import annotations

from dataclasses import dataclass

from innovation.gateway.safety import REQUIRED_FRONT_DOOR_EVIDENCE
from shared.snapshot import JourneySnapshot

#: Why an information type is being suggested. Each is tied to a decision it would change,
#: not to "we have a blank field" — a form with a gap is not a clinical reason.
REASON_CODES = {
    "REQUIRED_FOR_CONCLUSION": "Required before any conclusion other than escalation can be reached",
    "PREVIOUSLY_UNAVAILABLE": "Recorded earlier as not yet available; it may have resulted since",
    "PREVIOUSLY_UNKNOWN": "Asked earlier and not known; may be answerable now from another source",
    "PROVIDER_SUGGESTED": "Suggested by the model as the gap most likely to change the assessment",
}


@dataclass(frozen=True)
class InformationCandidate:
    """One suggestion for the adaptive interview."""

    information_type: str
    rank: int
    reason_code: str
    reason: str
    #: True when waiting for this item is itself unsafe, so it must not simply be queued.
    urgency_prerequisite: bool = False
    #: Recorded so the interview can show why an item cannot simply be collected.
    availability_note: str | None = None


@dataclass(frozen=True)
class DeclinedItem:
    """Information the person declined to give. Shown, never re-queued."""

    information_type: str
    note: str = "Declined at intake. Not re-asked; a clinician may revisit it in person."


@dataclass(frozen=True)
class InterviewPlan:
    candidates: tuple[InformationCandidate, ...]
    declined: tuple[DeclinedItem, ...]
    already_known: tuple[str, ...]


def plan_next_information(
    snapshot: JourneySnapshot,
    *,
    provider_suggestions: tuple[str, ...] = (),
    task: str = "CLINICAL_FRONT_DOOR",
) -> InterviewPlan:
    """Rank the next information to seek, given only what is known at the decision time."""
    known: set[str] = set()
    unavailable: dict[str, str] = {}
    unknown: set[str] = set()
    declined: set[str] = set()

    for event in snapshot.included:
        if event.status == "AVAILABLE":
            known.add(event.event_type)
        elif event.event_type == "MISSINGNESS" and event.code:
            if event.status == "WITHHELD":
                declined.add(event.code)
            elif event.status == "MEASURED_UNKNOWN":
                unknown.add(event.code)
            else:  # NOT_AVAILABLE_YET, NOT_MEASURED
                unavailable[event.code] = event.status

    candidates: list[InformationCandidate] = []
    seen: set[str] = set()

    def add(info_type: str, reason_code: str, *, prerequisite: bool = False, note: str | None = None) -> None:
        # Never suggest something already answered, and never re-queue a refusal.
        if info_type in seen or info_type in known or info_type in declined:
            return
        seen.add(info_type)
        candidates.append(
            InformationCandidate(
                information_type=info_type,
                rank=len(candidates) + 1,
                reason_code=reason_code,
                reason=REASON_CODES[reason_code],
                urgency_prerequisite=prerequisite,
                availability_note=note,
            )
        )

    # 1. Required evidence comes first, and waiting for it is itself unsafe: without it the
    #    system can only escalate, so queueing it silently would stall the encounter.
    if task == "CLINICAL_FRONT_DOOR":
        for info_type in sorted(REQUIRED_FRONT_DOOR_EVIDENCE - known):
            add(
                info_type,
                "REQUIRED_FOR_CONCLUSION",
                prerequisite=True,
                note=(
                    f"recorded as {unavailable[info_type]}" if info_type in unavailable else None
                ),
            )

    # 2. Items previously pending — cheap to re-check and often already resulted.
    for info_type in sorted(unavailable):
        add(info_type, "PREVIOUSLY_UNAVAILABLE", note=f"recorded as {unavailable[info_type]}")

    # 3. Items asked and not known. Re-asking the patient rarely helps, but another source
    #    may have it, so it is suggested without being pushed.
    for info_type in sorted(unknown):
        add(info_type, "PREVIOUSLY_UNKNOWN")

    # 4. Whatever the model thinks would move the assessment, last — a suggestion, not a
    #    requirement, and it cannot displace a required item.
    for info_type in provider_suggestions:
        add(info_type, "PROVIDER_SUGGESTED")

    return InterviewPlan(
        candidates=tuple(candidates),
        declined=tuple(DeclinedItem(i) for i in sorted(declined)),
        already_known=tuple(sorted(known)),
    )
