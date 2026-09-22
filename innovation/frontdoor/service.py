"""Front Door service — the workflow in `docs/innovation/CLINICAL_WORKFLOW.md`.

Sits above the Model Gateway and below any client:

    Client -> Front Door API -> Front Door service -> Model Gateway -> provider

Its job is the part the gateway deliberately does not do: hold a recommendation in a
pending state until a human acts on it, and keep the history of what was recommended at
each decision time rather than overwriting it.

`CLAUDE.md` §Product and safety invariants: "Human confirmation is required before a
recommendation affects care." Here that is enforced by `Recommendation.effective`, which
is false until a reviewer confirms — and by there being no method that marks a
recommendation effective without a reviewer identity.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field, replace
from datetime import datetime, timezone
from typing import TYPE_CHECKING, Literal, get_args

if TYPE_CHECKING:  # pragma: no cover - import cycle guard
    from innovation.store import SqliteStore

from innovation.frontdoor.intake import IntakeItem, append_event, build_journey
from innovation.frontdoor.planner import InterviewPlan, plan_next_information
from innovation.gateway.gateway import ModelGateway
from shared.contracts.journey import PatientJourney
from shared.contracts.model_api import (
    Authorization,
    EvidenceRef,
    GatewayRequest,
    GatewayResponse,
    ProviderConstraints,
    ReviewAction,
)
from shared.snapshot import JourneySnapshot, take_snapshot

DEFAULT_REQUESTED_OUTPUTS = [
    "URGENCY", "RED_FLAGS", "CARE_PATHWAYS", "NEXT_INFORMATION", "UNCERTAINTY", "GRAPH",
]


#: Structured reasons a reviewer may give for overriding or rejecting an output.
#: `PRODUCT_SPEC.md` §Human confirmation requires a *structured* reason, not free text:
#: free text cannot be counted, so an override-rate metric built on it would be unusable,
#: and the reason would not survive into evaluation.
OverrideReason = Literal[
    "CLINICAL_JUDGEMENT_DIFFERS",
    "ADDITIONAL_INFORMATION_AVAILABLE",
    "EVIDENCE_INCORRECT",
    "URGENCY_TOO_HIGH",
    "URGENCY_TOO_LOW",
    "PATHWAY_INAPPROPRIATE",
    "INFORMATION_REQUEST_UNNECESSARY",
    "OTHER",
]

#: Actions that change what the recommendation means, and therefore need a reason.
ACTIONS_REQUIRING_REASON = frozenset({"MODIFY", "REJECT"})


class HumanReviewRequired(Exception):
    """Raised when something tries to act on a recommendation no human has confirmed."""


class UnknownJourney(KeyError):
    """No such journey."""


@dataclass(frozen=True)
class ReviewRecord:
    """One human action on a recommendation. Append-only."""

    reviewer_id: str
    action: ReviewAction
    reviewed_at: datetime
    reason_code: OverrideReason | None = None
    note: str | None = None


@dataclass
class Recommendation:
    """A gateway response plus its review state.

    The response is never edited. An override is recorded alongside it, so the original
    output survives the correction — `SAFETY_SPEC.md` §Interface controls requires the
    original to remain immutable after an override.
    """

    recommendation_id: str
    journey_id: str
    decision_time: datetime
    snapshot_checksum: str
    response: GatewayResponse
    #: What the snapshot excluded at this decision time, and why. Held on the
    #: recommendation because it describes what *this decision* could not see — the
    #: gateway never learns of it, since the Front Door filters before the request is
    #: built. Without it the graph explorer could not answer "what did it not know?".
    withheld: tuple[tuple[str, str], ...] = field(default=())
    reviews: tuple[ReviewRecord, ...] = field(default=())

    @property
    def effective(self) -> bool:
        """Whether this may inform care. False until a human confirms or modifies it.

        REJECT and ESCALATE are human actions but they do not make a recommendation
        effective — rejecting it is precisely a decision not to act on it.
        """
        return bool(self.reviews and self.reviews[-1].action in {"CONFIRM", "MODIFY"})

    @property
    def latest_review(self) -> ReviewRecord | None:
        return self.reviews[-1] if self.reviews else None


class FrontDoorService:
    """Runs the end-to-end flow for one simulated encounter at a time."""

    def __init__(self, gateway: ModelGateway, store: "SqliteStore | None" = None) -> None:
        self.gateway = gateway
        #: Optional durable store. Without it the service is fully in-memory, which is
        #: what the offline demo and most tests want.
        self.store = store
        self._journeys: dict[str, PatientJourney] = {}
        self._recommendations: dict[str, Recommendation] = {}
        #: journey_id -> recommendation ids, in the order they were produced. History is
        #: kept so a later assessment shows how new evidence changed the output rather
        #: than quietly replacing it (workflow step 5).
        self._history: dict[str, list[str]] = {}
        if store is not None:
            self._rehydrate()

    def _rehydrate(self) -> None:
        """Load what a previous process wrote, so a restart does not lose an encounter."""
        assert self.store is not None
        for journey_id in self.store.journey_ids():
            journey = self.store.get_journey(journey_id)
            if journey is not None:
                self._journeys[journey_id] = journey
            for row in self.store.recommendations_for(journey_id):
                response = GatewayResponse.model_validate_json(row["response_json"])
                reviews = tuple(
                    ReviewRecord(
                        reviewer_id=r["reviewer_id"],
                        action=r["action"],
                        reviewed_at=datetime.fromisoformat(r["reviewed_at"]),
                        reason_code=r["reason_code"],
                        note=r["note"],
                    )
                    for r in self.store.reviews_for(row["recommendation_id"])
                )
                recommendation = Recommendation(
                    recommendation_id=row["recommendation_id"],
                    journey_id=row["journey_id"],
                    decision_time=datetime.fromisoformat(row["decision_time"]),
                    snapshot_checksum=row["snapshot_checksum"],
                    response=response,
                    reviews=reviews,
                )
                self._recommendations[recommendation.recommendation_id] = recommendation
                self._history.setdefault(journey_id, []).append(recommendation.recommendation_id)

    # -------------------------------------------------------------------- encounter

    def create_encounter(
        self,
        *,
        journey_id: str,
        patient_id: str,
        encounter_id: str,
        encounter_start: datetime,
        items: list[IntakeItem],
        split: str = "expert_test",
        data_classification: str = "SYNTHETIC",
    ) -> PatientJourney:
        """Workflow steps 1 and 2: create the encounter and capture intake."""
        if journey_id in self._journeys:
            raise ValueError(f"journey {journey_id} already exists; append events instead")
        journey = build_journey(
            journey_id=journey_id,
            patient_id=patient_id,
            encounter_id=encounter_id,
            encounter_start=encounter_start,
            items=items,
            split=split,
            data_classification=data_classification,
        )
        self._journeys[journey_id] = journey
        self._persist_journey(journey)
        return journey

    def register(self, journey: PatientJourney) -> PatientJourney:
        """Store a journey built elsewhere, e.g. a fixture."""
        self._journeys[journey.journey_id] = journey
        self._persist_journey(journey)
        return journey

    def _persist_journey(self, journey: PatientJourney) -> None:
        if self.store is not None:
            self.store.put_journey(journey)

    def journey_ids(self) -> tuple[str, ...]:
        return tuple(self._journeys)

    def journey(self, journey_id: str) -> PatientJourney:
        if journey_id not in self._journeys:
            raise UnknownJourney(journey_id)
        return self._journeys[journey_id]

    def append_evidence(
        self, journey_id: str, item: IntakeItem, *, default_time: datetime | None = None
    ) -> PatientJourney:
        """Workflow step 5: append new evidence as an immutable event.

        Returns a new journey; earlier recommendations keep pointing at the evidence they
        actually saw, because a snapshot is taken per assessment and never re-derived.
        """
        current = self.journey(journey_id)
        updated = append_event(
            current, item, default_time=default_time or datetime.now(timezone.utc)
        )
        self._journeys[journey_id] = updated
        self._persist_journey(updated)
        return updated

    def next_information(
        self,
        journey_id: str,
        decision_time: datetime,
        *,
        provider_suggestions: tuple[str, ...] = (),
    ) -> InterviewPlan:
        """Workflow step 4: what to ask or collect next, as of `decision_time`."""
        snapshot = take_snapshot(self.journey(journey_id), decision_time)
        return plan_next_information(snapshot, provider_suggestions=provider_suggestions)

    # ------------------------------------------------------------------ assessment

    def assess(
        self,
        journey: PatientJourney,
        decision_time: datetime,
        *,
        task: str = "CLINICAL_FRONT_DOOR",
        missing_information: tuple[str, ...] = (),
        external_provider_allowed: bool = False,
        approval_id: str | None = None,
        timeout_ms: int = 10_000,
    ) -> Recommendation:
        """Snapshot the journey at `decision_time`, ask the gateway, hold for review.

        The snapshot happens here rather than in the caller so that no client can hand
        the gateway an evidence set it assembled by its own rules.
        """
        snapshot = take_snapshot(journey, decision_time)
        request = self._build_request(
            journey=journey,
            snapshot=snapshot,
            decision_time=decision_time,
            task=task,
            missing_information=missing_information,
            external_provider_allowed=external_provider_allowed,
            approval_id=approval_id,
            timeout_ms=timeout_ms,
        )
        # An identical question already answered returns the answer already given, with
        # its review history intact. Re-running it would build a fresh Recommendation with
        # reviews=() and drop a human confirmation on the floor.
        existing_id = f"rec-{uuid.uuid5(uuid.NAMESPACE_URL, request.request_id).hex[:12]}"
        already = self._recommendations.get(existing_id)
        if already is not None:
            return already

        response = self.gateway.infer(request)

        recommendation = Recommendation(
            recommendation_id=existing_id,
            journey_id=journey.journey_id,
            decision_time=decision_time,
            snapshot_checksum=snapshot.checksum(),
            response=response,
            withheld=tuple((r.event_id, r.reason) for r in snapshot.rejected),
        )
        self._recommendations[recommendation.recommendation_id] = recommendation
        self._history.setdefault(journey.journey_id, []).append(recommendation.recommendation_id)
        if self.store is not None:
            self.store.put_recommendation(
                recommendation_id=recommendation.recommendation_id,
                journey_id=journey.journey_id,
                request_id=response.request_id,
                decision_time=decision_time,
                snapshot_checksum=recommendation.snapshot_checksum,
                response_json=response.model_dump_json(),
            )
        return recommendation

    def _build_request(
        self,
        *,
        journey: PatientJourney,
        snapshot: JourneySnapshot,
        decision_time: datetime,
        task: str,
        missing_information: tuple[str, ...],
        external_provider_allowed: bool,
        approval_id: str | None,
        timeout_ms: int,
    ) -> GatewayRequest:
        evidence = [
            EvidenceRef(
                evidence_id=event.event_id,
                event_type=event.event_type,
                modality=event.modality,
                available_at_time=event.available_at_time,
                data_classification=event.data_classification,
                payload_ref=event.payload_ref
                or f"synthetic://{journey.journey_id}/{event.event_id}",
            )
            for event in snapshot.included
            # LABEL evidence is an outcome, not an input to a live decision.
            if event.modality != "LABEL"
        ]
        # Deterministic request ID: the same journey, at the same decision time, over the
        # same evidence is the same question — which is what makes gateway idempotency
        # meaningful here. The snapshot checksum is part of the identity (DEC-0015): it
        # used to be journey and decision time alone, so appending evidence and
        # re-assessing at the same instant produced a *different* answer under the *same*
        # id, silently replacing a recommendation a human had already confirmed.
        request_id = "req-" + uuid.uuid5(
            uuid.NAMESPACE_URL,
            f"{journey.journey_id}|{decision_time.isoformat()}|{snapshot.checksum()}",
        ).hex[:12]

        return GatewayRequest(
            contract_version="1.0.0",
            request_id=request_id,
            journey_id=journey.journey_id,
            decision_time=decision_time,
            task=task,
            evidence=evidence,
            missing_information=list(missing_information),
            requested_outputs=DEFAULT_REQUESTED_OUTPUTS,
            authorization=Authorization(
                data_classification=journey.data_classification,
                external_provider_allowed=external_provider_allowed,
                approval_id=approval_id,
            ),
            provider_constraints=ProviderConstraints(
                timeout_ms=timeout_ms,
                max_output_tokens=1024,
                cost_class="FREE_LOCAL",
                deterministic_preferred=True,
            ),
        )

    # ---------------------------------------------------------------- human review

    def review(
        self,
        recommendation_id: str,
        *,
        reviewer_id: str,
        action: ReviewAction,
        reason_code: OverrideReason | None = None,
        note: str | None = None,
    ) -> Recommendation:
        """Record a human decision. The response itself is never edited."""
        if not reviewer_id.strip():
            raise ValueError("reviewer_id is required; an anonymous review is not a review")

        recommendation = self._recommendations[recommendation_id]
        allowed = recommendation.response.human_review.allowed_actions
        if action not in allowed:
            raise ValueError(f"action {action} is not permitted; allowed: {allowed}")

        # An override changes what the system's output means, so it carries a structured
        # reason. Free text alone cannot be aggregated into an override-rate metric.
        if action in ACTIONS_REQUIRING_REASON and reason_code is None:
            raise ValueError(
                f"action {action} requires a structured reason_code; "
                f"one of {sorted(get_args(OverrideReason))}"
            )
        if reason_code == "OTHER" and not (note or "").strip():
            raise ValueError("reason_code OTHER requires a note explaining it")

        record = ReviewRecord(
            reviewer_id=reviewer_id,
            action=action,
            reviewed_at=datetime.now(timezone.utc),
            reason_code=reason_code,
            note=note,
        )
        recommendation.reviews = recommendation.reviews + (record,)
        if self.store is not None:
            # A new row every time. Changing one's mind appends; it never overwrites.
            self.store.append_review(
                recommendation_id=recommendation_id,
                reviewer_id=reviewer_id,
                action=action,
                reason_code=reason_code,
                note=note,
                reviewed_at=record.reviewed_at,
            )

        # Mirror the human decision into the audit trail beside the gateway call, as a
        # new record. It used to overwrite the gateway's record in place via
        # object.__setattr__, which defeated the frozen dataclass, was never written back
        # to either durable sink — so the stored row said reviewer_id: null forever — and
        # was the wrong shape besides: an append-only log records that a review happened,
        # it does not edit the call that preceded it.
        gateway_records = self.gateway.audit.find(recommendation.response.request_id)
        if gateway_records:
            self.gateway.audit.append(
                replace(
                    gateway_records[0],
                    reviewer_id=reviewer_id,
                    review_action=action,
                    overridden_from=(
                        recommendation.response.urgency.level if action == "MODIFY" else None
                    ),
                    notes=tuple(gateway_records[0].notes)
                    + (f"human review recorded at {record.reviewed_at.isoformat()}",),
                )
            )
        return recommendation

    def act_on(self, recommendation_id: str) -> Recommendation:
        """Gate for anything that would let a recommendation inform care.

        Deliberately not a boolean check the caller may skip: the only way to obtain the
        recommendation for downstream use raises unless a human has confirmed it.
        """
        recommendation = self._recommendations[recommendation_id]
        if not recommendation.effective:
            raise HumanReviewRequired(
                f"{recommendation_id} has not been confirmed by a human reviewer"
            )
        return recommendation

    # ----------------------------------------------------------------------- reads

    def get(self, recommendation_id: str) -> Recommendation:
        return self._recommendations[recommendation_id]

    def history(self, journey_id: str) -> tuple[Recommendation, ...]:
        """Every recommendation made for a journey, oldest first."""
        return tuple(self._recommendations[i] for i in self._history.get(journey_id, []))
