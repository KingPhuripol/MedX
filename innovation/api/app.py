"""Front Door HTTP API (FastAPI, DEC-0010).

`PRODUCT_SPEC.md` §Architecture puts this layer between any client and the safety and
gateway layers, and states the product is API-first: the UI is one caller of this API,
never a privileged path. So every capability is exposed here, and the UI gets no
endpoint of its own.

The API adds no clinical logic. It parses, delegates, and serialises — the temporal rule
lives in the snapshot, the safety rules in the policy layer, and the human-confirmation
gate in the service. Keeping this layer thin is what stops a second, divergent copy of
the safety behaviour appearing at the edge.
"""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from fastapi import Body, FastAPI, HTTPException, Path, status
from pydantic import BaseModel, ConfigDict, Field

from innovation.frontdoor import FrontDoorService, HumanReviewRequired
from innovation.frontdoor.service import Recommendation
from innovation.gateway import ModelGateway
from innovation.gateway.providers import MockProvider
from shared.contracts.journey import PatientJourney
from shared.contracts.model_api import GatewayResponse

BANNER = "RESEARCH PROTOTYPE - HUMAN REVIEW REQUIRED"


class AssessmentRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    decision_time: datetime
    missing_information: list[str] = Field(default_factory=list)


class ReviewRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    reviewer_id: str = Field(min_length=1)
    action: Literal["CONFIRM", "MODIFY", "REJECT", "REQUEST_INFORMATION", "ESCALATE"]
    note: str | None = None


class RecommendationView(BaseModel):
    """What a client receives.

    `banner` and `effective` are carried in the payload rather than left to the UI, so a
    client cannot render a recommendation without also receiving the fact that it is a
    research prototype and whether a human has confirmed it.
    """

    model_config = ConfigDict(extra="forbid")

    banner: str = BANNER
    recommendation_id: str
    journey_id: str
    decision_time: datetime
    snapshot_checksum: str
    effective: bool
    reviews: list[dict]
    response: GatewayResponse

    @classmethod
    def of(cls, recommendation: Recommendation) -> "RecommendationView":
        return cls(
            recommendation_id=recommendation.recommendation_id,
            journey_id=recommendation.journey_id,
            decision_time=recommendation.decision_time,
            snapshot_checksum=recommendation.snapshot_checksum,
            effective=recommendation.effective,
            reviews=[
                {
                    "reviewer_id": r.reviewer_id,
                    "action": r.action,
                    "reviewed_at": r.reviewed_at.isoformat(),
                    "note": r.note,
                }
                for r in recommendation.reviews
            ],
            response=recommendation.response,
        )


class JourneyStore:
    """Simple in-memory journey store for the prototype.

    Journeys are synthetic. Nothing here persists to disk, so a demo run leaves no
    patient-shaped data behind.
    """

    def __init__(self) -> None:
        self._journeys: dict[str, PatientJourney] = {}

    def put(self, journey: PatientJourney) -> PatientJourney:
        self._journeys[journey.journey_id] = journey
        return journey

    def get(self, journey_id: str) -> PatientJourney:
        if journey_id not in self._journeys:
            raise HTTPException(status.HTTP_404_NOT_FOUND, f"unknown journey {journey_id}")
        return self._journeys[journey_id]


def create_app(
    service: FrontDoorService | None = None, store: JourneyStore | None = None
) -> FastAPI:
    """Build the app. Both collaborators are injectable so tests need no network."""
    service = service or FrontDoorService(ModelGateway(MockProvider()))
    store = store or JourneyStore()

    app = FastAPI(
        title="AI Clinical Front Door",
        version="1.0.0",
        description=(
            f"{BANNER}. Research and clinical decision-support prototype. It does not "
            "diagnose, prescribe, order tests, refer, or discharge, and every output "
            "requires human confirmation before it may inform care."
        ),
    )
    app.state.service = service
    app.state.store = store

    @app.get("/health")
    def health() -> dict:
        return {
            "status": "ok",
            "banner": BANNER,
            "contract_version": "1.0.0",
            "provider": service.gateway.provider.name,
            "policy_version": service.gateway.safety.version,
        }

    @app.put("/journeys/{journey_id}", status_code=status.HTTP_201_CREATED)
    def put_journey(journey_id: str = Path(...), journey: PatientJourney = Body(...)) -> dict:
        """Register a synthetic journey. Real patient data is out of scope for this API."""
        if journey.journey_id != journey_id:
            raise HTTPException(
                status.HTTP_400_BAD_REQUEST, "journey_id in path and body must match"
            )
        if journey.data_classification != "SYNTHETIC":
            # DEC-0006 and the data rules: the prototype accepts synthetic journeys only.
            # Anything else needs an approval path that does not exist yet, and defaulting
            # to permissive here is exactly how real data ends up somewhere it should not.
            raise HTTPException(
                status.HTTP_403_FORBIDDEN,
                "this prototype accepts SYNTHETIC journeys only; other classifications "
                "require a recorded approval under the Human Approval Policy",
            )
        store.put(journey)
        return {"journey_id": journey.journey_id, "events": len(journey.events)}

    @app.post("/journeys/{journey_id}/assessments", status_code=status.HTTP_201_CREATED)
    def assess(journey_id: str, body: AssessmentRequest) -> RecommendationView:
        """Assess the journey as it stood at `decision_time`."""
        journey = store.get(journey_id)
        recommendation = service.assess(
            journey,
            body.decision_time,
            missing_information=tuple(body.missing_information),
        )
        return RecommendationView.of(recommendation)

    @app.get("/recommendations/{recommendation_id}")
    def get_recommendation(recommendation_id: str) -> RecommendationView:
        try:
            return RecommendationView.of(service.get(recommendation_id))
        except KeyError:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "unknown recommendation") from None

    @app.post("/recommendations/{recommendation_id}/review")
    def review(recommendation_id: str, body: ReviewRequest) -> RecommendationView:
        """Record a human decision. The recommendation itself is never edited."""
        try:
            recommendation = service.review(
                recommendation_id,
                reviewer_id=body.reviewer_id,
                action=body.action,
                note=body.note,
            )
        except KeyError:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "unknown recommendation") from None
        except ValueError as exc:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc)) from None
        return RecommendationView.of(recommendation)

    @app.get("/journeys/{journey_id}/history")
    def history(journey_id: str) -> list[RecommendationView]:
        """Every recommendation made for this journey, oldest first."""
        store.get(journey_id)
        return [RecommendationView.of(r) for r in service.history(journey_id)]

    @app.get("/recommendations/{recommendation_id}/effective")
    def effective(recommendation_id: str) -> dict:
        """Whether this recommendation may inform care. 409 until a human confirms it."""
        try:
            recommendation = service.act_on(recommendation_id)
        except KeyError:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "unknown recommendation") from None
        except HumanReviewRequired as exc:
            raise HTTPException(status.HTTP_409_CONFLICT, str(exc)) from None
        return {
            "recommendation_id": recommendation.recommendation_id,
            "effective": True,
            "confirmed_by": recommendation.latest_review.reviewer_id,
        }

    @app.get("/audit/{request_id}")
    def audit(request_id: str) -> list[dict]:
        """Audit records for a gateway call. References only, never payloads."""
        records = service.gateway.audit.find(request_id)
        if not records:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "no audit record")
        return [
            {
                "request_id": r.request_id,
                "status": r.status,
                "urgency_level": r.urgency_level,
                "evidence_ids": list(r.evidence_ids),
                "rejected_evidence": [list(x) for x in r.rejected_evidence],
                "applied_safety_rules": list(r.applied_safety_rules),
                "error_codes": list(r.error_codes),
                "policy_version": r.policy_version,
                "provider": r.provider,
                "model_version": r.model_version,
                "reviewer_id": r.reviewer_id,
                "review_action": r.review_action,
            }
            for r in records
        ]

    return app


app = create_app()
