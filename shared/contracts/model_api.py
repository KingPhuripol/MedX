"""Model Gateway request and response models — `docs/shared/MODEL_API_CONTRACT.md` v1.0.0.

Every provider speaks these types. A client never sees a provider-native field: the
gateway constructs the response, and `extra="forbid"` here is what makes that
structural rather than a convention (contract test 10).
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from shared.contracts.journey import Timestamp

CONTRACT_VERSION = "1.0.0"

Task = Literal["CLINICAL_FRONT_DOOR", "MEDICAL_CAPABILITY", "ARCHITECTURE_EVALUATION"]

RequestModality = Literal["TEXT", "STRUCTURED", "IMAGE_2D", "IMAGE_3D", "SIGNAL", "REFERENCE"]

DataClassification = Literal[
    "SYNTHETIC", "PUBLIC_LICENSED", "DEIDENTIFIED_APPROVED",
    "IDENTIFIABLE_OR_LINKABLE", "RESTRICTED_DERIVATIVE",
]

RequestedOutput = Literal[
    "URGENCY", "RED_FLAGS", "CARE_PATHWAYS", "NEXT_INFORMATION", "UNCERTAINTY", "GRAPH"
]

UrgencyLevel = Literal[
    "IMMEDIATE_REVIEW", "URGENT_REVIEW", "ROUTINE_REVIEW", "INSUFFICIENT_INFORMATION"
]

#: Ordering used only to answer "is this at least as urgent as that".
#: INSUFFICIENT_INFORMATION is not a low-acuity finding — it is an abstention, and the
#: deterministic safety layer may replace it with a higher level but never the reverse.
URGENCY_SEVERITY: dict[str, int] = {
    "INSUFFICIENT_INFORMATION": 0,
    "ROUTINE_REVIEW": 1,
    "URGENT_REVIEW": 2,
    "IMMEDIATE_REVIEW": 3,
}

ProviderName = Literal["mock", "external_prototype", "baseline", "team_model"]

ResponseStatus = Literal["COMPLETED", "ABSTAINED", "ESCALATED", "FAILED_SAFE"]

ReviewAction = Literal["CONFIRM", "MODIFY", "REJECT", "REQUEST_INFORMATION", "ESCALATE"]


# --------------------------------------------------------------------------- request


class EvidenceRef(BaseModel):
    """A reference to evidence. Never the payload itself.

    The gateway routes references, so raw patient content does not pass through it and
    cannot leak into a log or an external provider call (DEC-0006).
    """

    model_config = ConfigDict(extra="forbid")

    evidence_id: str = Field(min_length=3)
    event_type: str = Field(min_length=2)
    modality: RequestModality
    available_at_time: Timestamp
    data_classification: DataClassification
    payload_ref: str = Field(min_length=3)


class Authorization(BaseModel):
    model_config = ConfigDict(extra="forbid")

    data_classification: DataClassification
    external_provider_allowed: bool
    approval_id: str | None = Field(default=None, pattern=r"^APR-[0-9]{4}$")


class ProviderConstraints(BaseModel):
    model_config = ConfigDict(extra="forbid")

    timeout_ms: int = Field(ge=100, le=120_000)
    max_output_tokens: int = Field(ge=1, le=32_768)
    cost_class: Literal["FREE_LOCAL", "LOW", "APPROVED_PAID"]
    deterministic_preferred: bool


class GatewayRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    contract_version: Literal["1.0.0"]
    request_id: str = Field(min_length=6)
    journey_id: str = Field(min_length=4)
    decision_time: Timestamp
    task: Task
    evidence: list[EvidenceRef]
    missing_information: list[str]
    requested_outputs: list[RequestedOutput] = Field(min_length=1)
    authorization: Authorization
    provider_constraints: ProviderConstraints

    @field_validator("evidence")
    @classmethod
    def _evidence_ids_unique(cls, evidence: list[EvidenceRef]) -> list[EvidenceRef]:
        """The contract requires duplicate IDs to be rejected."""
        seen = [e.evidence_id for e in evidence]
        duplicates = {i for i in seen if seen.count(i) > 1}
        if duplicates:
            raise ValueError(f"duplicate evidence_id: {sorted(duplicates)}")
        return evidence

    @field_validator("missing_information", "requested_outputs")
    @classmethod
    def _unique_items(cls, values: list[str]) -> list[str]:
        if len(values) != len(set(values)):
            raise ValueError("items must be unique")
        return values


# -------------------------------------------------------------------------- response


class Urgency(BaseModel):
    model_config = ConfigDict(extra="forbid")

    level: UrgencyLevel
    confidence: float | None = Field(default=None, ge=0, le=1)
    evidence_ids: list[str] = Field(default_factory=list)


class RedFlag(BaseModel):
    model_config = ConfigDict(extra="forbid")

    code: str = Field(min_length=2)
    state: Literal["TRIGGERED", "NOT_TRIGGERED", "UNKNOWN"]
    evidence_ids: list[str] = Field(default_factory=list)


class CarePathway(BaseModel):
    model_config = ConfigDict(extra="forbid")

    code: str = Field(min_length=2)
    rank: int = Field(ge=1)
    confidence: float | None = Field(default=None, ge=0, le=1)
    evidence_ids: list[str] = Field(default_factory=list)


class NextInformation(BaseModel):
    model_config = ConfigDict(extra="forbid")

    information_type: str = Field(min_length=2)
    rank: int = Field(ge=1)
    reason_code: str = Field(min_length=2)


class Uncertainty(BaseModel):
    model_config = ConfigDict(extra="forbid")

    method: str = Field(min_length=2)
    limitations: list[str] = Field(min_length=1)
    out_of_distribution: bool | None = None
    abstention_reason: str | None = None


class HumanReview(BaseModel):
    """`required` is `Literal[True]`, so a response asserting autonomous action
    cannot be constructed at all (`SAFETY_SPEC.md` §Prohibited behavior)."""

    model_config = ConfigDict(extra="forbid")

    required: Literal[True] = True
    allowed_actions: list[ReviewAction] = Field(min_length=1)


class GraphRef(BaseModel):
    """A reference to the executed DAG, never inline reasoning text.

    The inspectable artifact is the executed graph; hidden chain-of-thought is not
    exposed (`CLAUDE.md` §Claim boundary).
    """

    model_config = ConfigDict(extra="forbid")

    graph_schema_version: str | None = None
    graph_id: str | None = None
    graph_ref: str | None = None


class Provenance(BaseModel):
    model_config = ConfigDict(extra="forbid")

    input_checksum: str = Field(min_length=8)
    provider_version: str = Field(min_length=1)
    config_version: str = Field(min_length=1)
    policy_version: str = Field(min_length=1)
    started_at: Timestamp
    completed_at: Timestamp


class ResponseError(BaseModel):
    model_config = ConfigDict(extra="forbid")

    code: Literal[
        "INVALID_REQUEST", "TEMPORAL_VIOLATION", "UNAUTHORIZED_DATA",
        "UNSUPPORTED_MODALITY", "PROVIDER_TIMEOUT", "INVALID_PROVIDER_OUTPUT",
        "BUDGET_EXCEEDED", "LOW_CONFIDENCE", "INTERNAL_SAFE_FAILURE",
    ]
    message: str = Field(min_length=3)
    retryable: bool


class GatewayResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    contract_version: Literal["1.0.0"]
    request_id: str = Field(min_length=6)
    response_id: str = Field(min_length=6)
    provider: ProviderName
    model_version: str = Field(min_length=2)
    status: ResponseStatus
    urgency: Urgency
    red_flags: list[RedFlag]
    care_pathways: list[CarePathway]
    next_information: list[NextInformation]
    uncertainty: Uncertainty
    human_review: HumanReview
    graph: GraphRef | None
    provenance: Provenance
    errors: list[ResponseError]
