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

from contextlib import asynccontextmanager

from fastapi import APIRouter, Body, FastAPI, HTTPException, Path, Request, Response, status
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, ConfigDict, Field

from innovation.api.errors import install_error_handlers
from innovation.config import BANNER, Settings
from innovation.logging import configure as configure_logging
from innovation.logging import set_request_id

from innovation.frontdoor import (
    FrontDoorService,
    HumanReviewRequired,
    IntakeError,
    IntakeItem,
    UnknownJourney,
)
from innovation.frontdoor.service import ACTIONS_REQUIRING_REASON, Recommendation
from innovation.gateway import ModelGateway
from innovation.gateway.audit import AuditLog
from innovation.gateway.registry import build_provider
from innovation.store import SqliteStore
from shared.contracts.journey import PatientJourney
from shared.contracts.model_api import GatewayResponse

class AssessmentRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    decision_time: datetime
    missing_information: list[str] = Field(default_factory=list)


class ReviewRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    reviewer_id: str = Field(min_length=1)
    action: Literal["CONFIRM", "MODIFY", "REJECT", "REQUEST_INFORMATION", "ESCALATE"]
    #: Required for MODIFY and REJECT — an override changes what the output means, and a
    #: structured reason is what makes an override-rate metric possible later.
    reason_code: Literal[
        "CLINICAL_JUDGEMENT_DIFFERS",
        "ADDITIONAL_INFORMATION_AVAILABLE",
        "EVIDENCE_INCORRECT",
        "URGENCY_TOO_HIGH",
        "URGENCY_TOO_LOW",
        "PATHWAY_INAPPROPRIATE",
        "INFORMATION_REQUEST_UNNECESSARY",
        "OTHER",
    ] | None = None
    note: str | None = None


class IntakeItemRequest(BaseModel):
    """One answer on the intake form — including the answers that are not values."""

    model_config = ConfigDict(extra="forbid")

    information_type: str
    #: KNOWN / UNKNOWN / REFUSED / NOT_AVAILABLE are recorded distinctly (A1). A gap is an
    #: event on the timeline, never an omission.
    state: Literal["KNOWN", "UNKNOWN", "REFUSED", "NOT_AVAILABLE"]
    value: object | None = None
    observed_at: datetime | None = None
    available_at_time: datetime | None = None
    note: str | None = None

    def to_item(self) -> IntakeItem:
        return IntakeItem(
            information_type=self.information_type,
            state=self.state,
            value=self.value,
            observed_at=self.observed_at,
            available_at_time=self.available_at_time,
            note=self.note,
        )


class EncounterRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    journey_id: str = Field(min_length=1)
    patient_id: str = Field(min_length=1)
    encounter_id: str = Field(min_length=1)
    encounter_start: datetime
    items: list[IntakeItemRequest] = Field(min_length=1)
    split: str = "expert_test"


class InterviewView(BaseModel):
    """The adaptive interview screen's data.

    Declined items are listed separately and are never queued as questions — the system
    does not nag on a clinician's behalf (`PRODUCT_SPEC.md` §Adaptive interview:
    "It must not coerce answers").
    """

    model_config = ConfigDict(extra="forbid")

    banner: str = BANNER
    journey_id: str
    decision_time: datetime
    candidates: list[dict]
    declined: list[dict]
    already_known: list[str]


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
    #: Evidence excluded from this decision, with the reason. Exposed so a client can show
    #: what the decision could not see, not only what it used.
    withheld: list[dict]
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
            withheld=[
                {"event_id": event_id, "reason": reason}
                for event_id, reason in recommendation.withheld
            ],
            reviews=[
                {
                    "reviewer_id": r.reviewer_id,
                    "action": r.action,
                    "reviewed_at": r.reviewed_at.isoformat(),
                    "reason_code": r.reason_code,
                    "note": r.note,
                }
                for r in recommendation.reviews
            ],
            response=recommendation.response,
        )


def _require_synthetic(classification: str) -> None:
    """The prototype accepts synthetic journeys only.

    Anything else needs an approval path that does not exist yet, and defaulting to
    permissive here is exactly how real data ends up somewhere it should not (DEC-0006).
    """
    if classification != "SYNTHETIC":
        raise HTTPException(
            status.HTTP_403_FORBIDDEN,
            "this prototype accepts SYNTHETIC journeys only; other classifications "
            "require a recorded approval under the Human Approval Policy",
        )


def build_default_service(settings: Settings | None = None) -> FrontDoorService:
    """Assemble the service from deployment configuration.

    Storage is opt-in. Without FRONT_DOOR_DB the prototype runs entirely in memory, which
    is what the offline demo wants and what leaves nothing patient-shaped on disk. With
    it, encounters survive a restart and the audit trail lands in a database whose
    triggers refuse UPDATE and DELETE.

    The provider likewise comes from deployment configuration, never from a request
    payload — a client cannot ask the API to use a different model.
    """
    settings = settings or Settings()
    store = SqliteStore(settings.db) if settings.db else None
    audit = AuditLog(path=settings.audit_log, store=store)
    return FrontDoorService(
        ModelGateway(
            build_provider(settings.provider),
            audit_log=audit,
            max_workers=settings.provider_concurrency,
        ),
        store=store,
    )


def build_router(service: FrontDoorService) -> APIRouter:
    """Every resource route, in one router that can be mounted more than once.

    The routes used to be closures on the app itself, which meant that adding a version
    prefix later would have to touch each one. As a router they are registered twice —
    under `/v1` and unprefixed for compatibility — and the UI needs one line changed
    rather than eleven. That is the payoff of `PRODUCT_SPEC.md`'s rule that the UI is one
    caller of this API and never a privileged path.
    """
    router = APIRouter()

    def get_journey(journey_id: str) -> PatientJourney:
        try:
            return service.journey(journey_id)
        except UnknownJourney:
            raise HTTPException(
                status.HTTP_404_NOT_FOUND, f"unknown journey {journey_id}"
            ) from None

    @router.put("/journeys/{journey_id}", status_code=status.HTTP_201_CREATED)
    def put_journey(journey_id: str = Path(...), journey: PatientJourney = Body(...)) -> dict:
        """Register a synthetic journey built elsewhere, e.g. a fixture."""
        if journey.journey_id != journey_id:
            raise HTTPException(
                status.HTTP_400_BAD_REQUEST, "journey_id in path and body must match"
            )
        _require_synthetic(journey.data_classification)
        service.register(journey)
        return {"journey_id": journey.journey_id, "events": len(journey.events)}

    @router.post("/encounters", status_code=status.HTTP_201_CREATED)
    def create_encounter(body: EncounterRequest) -> dict:
        """Workflow steps 1-2: create an encounter and capture intake.

        Every intake item is recorded, including the ones with no value: a gap that was
        asked about is different from a question never asked, and both are different from
        a refusal.
        """
        try:
            journey = service.create_encounter(
                journey_id=body.journey_id,
                patient_id=body.patient_id,
                encounter_id=body.encounter_id,
                encounter_start=body.encounter_start,
                items=[i.to_item() for i in body.items],
                split=body.split,
            )
        except IntakeError as exc:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc)) from None
        except ValueError as exc:
            raise HTTPException(status.HTTP_409_CONFLICT, str(exc)) from None

        return {
            "journey_id": journey.journey_id,
            "events": len(journey.events),
            "recorded_states": {
                e.code or e.event_type: e.status for e in journey.events
            },
        }

    @router.post("/journeys/{journey_id}/events", status_code=status.HTTP_201_CREATED)
    def append_event(journey_id: str, body: IntakeItemRequest) -> dict:
        """Workflow step 5: append evidence. Append-only — nothing is ever edited."""
        get_journey(journey_id)
        try:
            journey = service.append_evidence(journey_id, body.to_item())
        except IntakeError as exc:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc)) from None
        appended = journey.events[-1]
        return {
            "journey_id": journey.journey_id,
            "event_id": appended.event_id,
            "status": appended.status,
            "available_at_time": appended.available_at_time.isoformat(),
            "total_events": len(journey.events),
        }

    @router.get("/journeys/{journey_id}/next-information")
    def next_information(journey_id: str, decision_time: datetime) -> InterviewView:
        """Workflow step 4: ranked information to seek, as of `decision_time`."""
        get_journey(journey_id)
        plan = service.next_information(journey_id, decision_time)
        return InterviewView(
            journey_id=journey_id,
            decision_time=decision_time,
            candidates=[
                {
                    "information_type": c.information_type,
                    "rank": c.rank,
                    "reason_code": c.reason_code,
                    "reason": c.reason,
                    "urgency_prerequisite": c.urgency_prerequisite,
                    "availability_note": c.availability_note,
                }
                for c in plan.candidates
            ],
            declined=[{"information_type": d.information_type, "note": d.note} for d in plan.declined],
            already_known=list(plan.already_known),
        )

    @router.post("/journeys/{journey_id}/assessments", status_code=status.HTTP_201_CREATED)
    def assess(journey_id: str, body: AssessmentRequest) -> RecommendationView:
        """Assess the journey as it stood at `decision_time`."""
        journey = get_journey(journey_id)
        recommendation = service.assess(
            journey,
            body.decision_time,
            missing_information=tuple(body.missing_information),
        )
        return RecommendationView.of(recommendation)

    @router.get("/recommendations/{recommendation_id}")
    def get_recommendation(recommendation_id: str) -> RecommendationView:
        try:
            return RecommendationView.of(service.get(recommendation_id))
        except KeyError:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "unknown recommendation") from None

    @router.post("/recommendations/{recommendation_id}/review")
    def review(recommendation_id: str, body: ReviewRequest) -> RecommendationView:
        """Record a human decision. The recommendation itself is never edited."""
        try:
            recommendation = service.review(
                recommendation_id,
                reviewer_id=body.reviewer_id,
                action=body.action,
                reason_code=body.reason_code,
                note=body.note,
            )
        except KeyError:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "unknown recommendation") from None
        except ValueError as exc:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc)) from None
        return RecommendationView.of(recommendation)

    @router.get("/journeys/{journey_id}/history")
    def history(journey_id: str) -> list[RecommendationView]:
        """Every recommendation made for this journey, oldest first."""
        get_journey(journey_id)
        return [RecommendationView.of(r) for r in service.history(journey_id)]

    @router.get("/recommendations/{recommendation_id}/effective")
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

    @router.get("/audit/{request_id}")
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

    return router


def create_app(
    service: FrontDoorService | None = None, settings: Settings | None = None
) -> FastAPI:
    """Build the app. The service and settings are injectable so tests need no network."""
    settings = settings or Settings()
    service = service or build_default_service(settings)
    configure_logging(settings.log_level, settings.log_format)

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        yield
        # Both of these existed and neither was ever called: the provider threadpool and
        # the database connection outlived the process's willingness to use them.
        service.gateway.close()
        if service.store is not None:
            service.store.close()

    app = FastAPI(
        title="AI Clinical Front Door",
        version="1.1.0",
        lifespan=lifespan,
        description=(
            f"{BANNER}. Research and clinical decision-support prototype. It does not "
            "diagnose, prescribe, order tests, refer, or discharge, and every output "
            "requires human confirmation before it may inform care."
        ),
    )
    app.state.service = service
    app.state.settings = settings

    @app.middleware("http")
    async def correlate(request: Request, call_next):
        request_id = set_request_id(request.headers.get("X-Request-Id"))
        response = await call_next(request)
        response.headers["X-Request-Id"] = request_id
        return response

    if settings.cors_origins:
        app.add_middleware(
            CORSMiddleware,
            allow_origins=list(settings.cors_origins),
            allow_credentials=False,
            allow_methods=["*"],
            allow_headers=["*"],
        )

    install_error_handlers(app)

    # Probes are infrastructure, not API: they stay unversioned so a deployment does not
    # have to learn the contract version to know whether the process is alive.
    @app.get("/health")
    def health() -> dict:
        """Liveness. Touches nothing, so it answers even when a dependency is down."""
        return {
            "status": "ok",
            "banner": BANNER,
            "contract_version": "1.0.0",
            "policy_version": service.gateway.safety.version,
            "provider_circuit": service.gateway.breaker.state,
            **settings.public_view(),
        }

    @app.get("/ready")
    def ready(response: Response) -> dict:
        """Readiness. Whether this process should be given traffic.

        Distinct from /health on purpose. A Front Door whose storage is unreachable can
        still answer "the process is up" — but it must not be sent a patient encounter it
        cannot record.
        """
        checks: dict[str, str] = {"provider": "ok", "storage": "ok"}
        if service.store is not None:
            try:
                service.store.audit_count()
            except Exception:
                checks["storage"] = "unreachable"
        if service.gateway.breaker.state == "OPEN":
            checks["provider"] = "circuit_open"

        ready_now = all(value == "ok" for value in checks.values())
        if not ready_now:
            response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
        return {
            "ready": ready_now,
            "checks": checks,
            "banner": BANNER,
            "boundary": (
                "Research prototype. Not authorised for clinical use, and every output "
                "requires human confirmation before it may inform care."
            ),
        }

    router = build_router(service)
    app.include_router(router, prefix="/v1")
    # The unprefixed routes stay so nothing that already calls this API breaks. They are
    # hidden from the schema, so /docs shows one surface rather than each path twice.
    app.include_router(router, include_in_schema=False)

    from innovation.ui import mount_ui

    return mount_ui(app)


app = create_app()
