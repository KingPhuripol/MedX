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
from dataclasses import dataclass, field
from datetime import datetime, timezone

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


class HumanReviewRequired(Exception):
    """Raised when something tries to act on a recommendation no human has confirmed."""


@dataclass(frozen=True)
class ReviewRecord:
    """One human action on a recommendation. Append-only."""

    reviewer_id: str
    action: ReviewAction
    reviewed_at: datetime
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
    reviews: tuple[ReviewRecord, ...] = field(default=())

    @property
    def effective(self) -> bool:
        """Whether this may inform care. False until a human confirms or modifies it.

        REJECT and ESCALATE are human actions but they do not make a recommendation
        effective — rejecting it is precisely a decision not to act on it.
        """
        return any(r.action in {"CONFIRM", "MODIFY"} for r in self.reviews)

    @property
    def latest_review(self) -> ReviewRecord | None:
        return self.reviews[-1] if self.reviews else None


class FrontDoorService:
    """Runs the end-to-end flow for one simulated encounter at a time."""

    def __init__(self, gateway: ModelGateway) -> None:
        self.gateway = gateway
        self._recommendations: dict[str, Recommendation] = {}
        #: journey_id -> recommendation ids, in the order they were produced. History is
        #: kept so a later assessment shows how new evidence changed the output rather
        #: than quietly replacing it (workflow step 5).
        self._history: dict[str, list[str]] = {}

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
        response = self.gateway.infer(request)

        recommendation = Recommendation(
            recommendation_id=f"rec-{uuid.uuid5(uuid.NAMESPACE_URL, request.request_id).hex[:12]}",
            journey_id=journey.journey_id,
            decision_time=decision_time,
            snapshot_checksum=snapshot.checksum(),
            response=response,
        )
        self._recommendations[recommendation.recommendation_id] = recommendation
        self._history.setdefault(journey.journey_id, []).append(recommendation.recommendation_id)
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
        # Deterministic request ID: the same journey at the same decision time is the
        # same question, which is what makes gateway idempotency meaningful here.
        request_id = "req-" + uuid.uuid5(
            uuid.NAMESPACE_URL, f"{journey.journey_id}|{decision_time.isoformat()}"
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
        note: str | None = None,
    ) -> Recommendation:
        """Record a human decision. The response itself is never edited."""
        if not reviewer_id.strip():
            raise ValueError("reviewer_id is required; an anonymous review is not a review")

        recommendation = self._recommendations[recommendation_id]
        allowed = recommendation.response.human_review.allowed_actions
        if action not in allowed:
            raise ValueError(f"action {action} is not permitted; allowed: {allowed}")

        record = ReviewRecord(
            reviewer_id=reviewer_id,
            action=action,
            reviewed_at=datetime.now(timezone.utc),
            note=note,
        )
        recommendation.reviews = recommendation.reviews + (record,)

        # Mirror the human decision into the audit trail beside the gateway call.
        for audit_record in self.gateway.audit.find(recommendation.response.request_id):
            object.__setattr__(audit_record, "reviewer_id", reviewer_id)
            object.__setattr__(audit_record, "review_action", action)
            if action == "MODIFY":
                object.__setattr__(
                    audit_record, "overridden_from", recommendation.response.urgency.level
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
