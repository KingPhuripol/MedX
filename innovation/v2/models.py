from __future__ import annotations

from datetime import datetime, timezone
from typing import Literal
from pydantic import BaseModel, ConfigDict, Field, AwareDatetime, model_validator

from shared.contracts.model_api import RedFlag


def now() -> datetime:
    return datetime.now(timezone.utc)


class Model(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)


class Measurement(Model):
    name: str = Field(min_length=1, max_length=128)
    value: float
    unit: str = Field(min_length=1, max_length=32)


class ClinicalFact(Model):
    event_id: str = Field(min_length=1, max_length=128)
    kind: Literal["CHIEF_COMPLAINT", "HISTORY", "MEDICATION", "ALLERGY", "VITAL", "LAB", "REPORT", "LABEL"]
    state: Literal["KNOWN", "UNKNOWN", "REFUSED", "NOT_AVAILABLE"] = "KNOWN"
    value: str | float | int | dict | None = None
    observed_at: AwareDatetime
    available_at_time: AwareDatetime
    supersedes_event_id: str | None = None
    source: Literal["PATIENT_REPORTED", "STAFF_CONFIRMED"] = "STAFF_CONFIRMED"
    conflicts_with_event_ids: list[str] = Field(default_factory=list, max_length=20)

    @model_validator(mode="after")
    def valid_value(self):
        if self.state == "KNOWN" and (self.value is None or self.value == ""):
            raise ValueError("KNOWN requires a value")
        if self.state != "KNOWN" and self.value is not None:
            raise ValueError("unknown/refused/unavailable must not carry a value")
        if self.observed_at > self.available_at_time:
            raise ValueError("observation cannot follow availability")
        if self.kind in {'VITAL', 'LAB'} and isinstance(self.value, dict) and {'name', 'value', 'unit'} <= self.value.keys():
            Measurement.model_validate(self.value)
        return self


class EncounterCreate(Model):
    encounter_id: str = Field(min_length=1, max_length=128, pattern=r"^[A-Za-z0-9_-]+$")
    age: int = Field(ge=18, le=120)
    profile: Literal["synthetic_intake_v1"] = "synthetic_intake_v1"
    classification: Literal["SYNTHETIC"] = "SYNTHETIC"
    care_context: Literal[
        "ED_FIRST_CONTACT_ADULT_NON_TRAUMA_NON_OBSTETRIC",
        "PAEDIATRIC", "TRAUMA", "OBSTETRIC", "PREHOSPITAL",
    ] = "ED_FIRST_CONTACT_ADULT_NON_TRAUMA_NON_OBSTETRIC"


class Mutation(Model):
    expected_revision: int = Field(ge=0)
    idempotency_key: str = Field(min_length=1, max_length=128)


class EventRequest(Mutation):
    fact: ClinicalFact


class CaseRevision(Model):
    encounter_id: str
    case_revision: int
    decision_time: AwareDatetime
    timepoint: Literal["T0", "T1"] = "T0"
    care_context: str = "ED_FIRST_CONTACT_ADULT_NON_TRAUMA_NON_OBSTETRIC"
    evidence: list[ClinicalFact]
    checksum: str


class Differential(Model):
    possibility: str
    rationale: str
    evidence_ids: list[str] = Field(min_length=1)
    contradictions: list[str]
    missing_information: list[str]


class UrgencyRecommendation(Model):
    level: Literal[
        "IMMEDIATE_REVIEW", "URGENT_REVIEW", "ROUTINE_REVIEW", "INSUFFICIENT_INFORMATION"
    ] = "INSUFFICIENT_INFORMATION"
    confidence: float | None = Field(default=None, ge=0, le=1)
    evidence_ids: list[str] = Field(default_factory=list)


class CarePathwayCandidate(Model):
    code: str = Field(min_length=1, max_length=128)
    rank: int = Field(ge=1)
    confidence: float | None = Field(default=None, ge=0, le=1)
    evidence_ids: list[str] = Field(default_factory=list)
    rationale: str | None = Field(default=None, max_length=2000)


class NextInformationCandidate(Model):
    information_type: str = Field(min_length=1, max_length=128)
    rank: int = Field(ge=1)
    reason_code: str = Field(min_length=1, max_length=128)
    waiting_is_unsafe: bool = False


class UncertaintyState(Model):
    confidence: float | None = Field(default=None, ge=0, le=1)
    calibrated: bool = False
    abstained: bool = True
    escalation_required: bool = False
    reasons: list[str] = Field(default_factory=list)


class DraftContent(Model):
    summary: str = Field(min_length=1, max_length=20000)
    evidence_ids: list[str]
    outstanding: list[str] = Field(default_factory=list)
    differentials: list[Differential] = Field(default_factory=list)
    urgency: UrgencyRecommendation = Field(default_factory=UrgencyRecommendation)
    care_pathways: list[CarePathwayCandidate] = Field(default_factory=list)
    next_information: list[NextInformationCandidate] = Field(default_factory=list)
    uncertainty: UncertaintyState = Field(default_factory=UncertaintyState)
    limitations: list[str] = Field(default_factory=lambda: ["Synthetic research prototype; clinical validation pending"])


class SafetyScreen(Model):
    """Result of the deterministic pre-inference screen, attached to a draft.

    It sits beside `content` rather than inside it because `content` is what a provider
    produces and what a physician MODIFY replaces. A screen finding that a reviewer or a
    provider could overwrite would not be a safety control. The service computes this
    from the snapshot; no request body can set it.
    """

    policy_version: str
    urgency_floor: Literal[
        "IMMEDIATE_REVIEW", "URGENT_REVIEW", "ROUTINE_REVIEW", "INSUFFICIENT_INFORMATION"
    ]
    red_flags: list[RedFlag] = Field(default_factory=list)
    applied_rules: list[str] = Field(default_factory=list)
    missing_required: list[str] = Field(default_factory=list)
    limitations: list[str] = Field(default_factory=list)


class ClinicalDraft(Model):
    draft_id: str
    encounter_id: str
    case_revision: int
    draft_revision: int = 1
    snapshot: CaseRevision
    content: DraftContent
    screen: SafetyScreen | None = None
    provenance: dict = Field(default_factory=dict)
    created_by: str
    created_at: AwareDatetime = Field(default_factory=now)


class ReviewDecision(Mutation):
    draft_revision: int = Field(ge=1)
    expected_review_sequence: int = Field(ge=0)
    action: Literal["CONFIRM", "MODIFY", "REJECT", "REQUEST_INFORMATION", "ESCALATE"]
    reason_code: Literal[
        "CLINICAL_CORRECTION", "MISSING_INFORMATION", "UNSAFE_TO_CONFIRM", "OUT_OF_SCOPE", "OTHER"
    ] | None = None
    reason: str | None = Field(default=None, max_length=2000)
    content: DraftContent | None = None

    @model_validator(mode="after")
    def modification(self):
        if self.action == "MODIFY" and (self.content is None or not self.reason):
            raise ValueError("MODIFY requires revised content and reason")
        if self.action != "MODIFY" and self.content is not None:
            raise ValueError("content is only accepted for MODIFY")
        if self.action in {"MODIFY", "REJECT", "REQUEST_INFORMATION", "ESCALATE"} and not self.reason:
            raise ValueError(f"{self.action} requires reason")
        if self.action == "CONFIRM" and (self.reason_code is not None or self.reason is not None):
            raise ValueError("CONFIRM does not accept a reason")
        # Older clients supplied a required note before reason codes existed. Preserve
        # them as an explicit OTHER category instead of dropping their audit meaning.
        if self.action != "CONFIRM" and self.reason_code is None:
            self.reason_code = "OTHER"
        return self


class DesignSpec(Model):
    design_id: str = Field(pattern=r"^[a-z0-9_-]{1,64}$")
    nodes: list[Literal["intake", "check", "draft", "verify"]] = Field(min_length=1, max_length=4)
    prompt_version: Literal["grounded-v1", "concise-v1"] = "grounded-v1"
    routing: Literal["static", "adaptive", "random"] = "static"
    routing_seed: int = 0

    @model_validator(mode="after")
    def structure(self):
        if len(set(self.nodes)) != len(self.nodes) or "draft" not in self.nodes:
            raise ValueError("unique nodes and one draft node are required")
        if "verify" in self.nodes and self.nodes.index("verify") < self.nodes.index("draft"):
            raise ValueError("verify must follow draft")
        if any(self.nodes.index(n) > self.nodes.index("draft") for n in ("intake", "check") if n in self.nodes):
            raise ValueError("intake/check must precede draft")
        return self


class TurnRequest(Mutation):
    text: str = Field(min_length=1, max_length=10000)
    decision_time: AwareDatetime
    design_id: Literal["form", "single", "fixed", "adaptive", "random", "static_dag"] = "single"
    intent: Literal["conversation", "draft"] = "draft"  # Preserve existing v2 clients.


class DraftRequest(Mutation):
    decision_time: AwareDatetime


class ToolEvent(Model):
    sequence: int
    tool: str
    evidence_ids: list[str]
    status: Literal["COMPLETED", "FAILED", "BLOCKED"]
    elapsed_ms: float = 0
    error_code: str | None = None


class AgentRun(Model):
    run_id: str
    encounter_id: str
    case_revision: int
    status: Literal["COMPLETED", "FAILED_SAFE", "BUDGET_EXCEEDED", "NEEDS_REVIEW"]
    response: str
    proposals: list[dict] = Field(default_factory=list)
    draft_id: str | None = None
    trace: list[ToolEvent] = Field(default_factory=list)
    provenance: dict
    error_code: str | None = None


class ScenarioSpec(Model):
    family_id: str
    scenario_group: str = "legacy"
    patient_age: int = Field(default=40, ge=18, le=120)
    split: Literal["development", "validation", "test", "regression"]
    behaviour: str
    clinical_reviewed: bool = False
    seed: int = 0
    simulator_version: str = "scripted-v1"
    world: list[ClinicalFact] = Field(default_factory=list)
    expected_evidence_ids: list[str] = Field(default_factory=list)
    review_task: Literal["draft", "modify", "reject"] = "draft"
    decision_time: AwareDatetime | None = None


class EvaluationRun(Model):
    design: DesignSpec
    family_id: str
    split: str
    seed: int
    passed: bool
    valid_simulation: bool = True
    checks: dict[str, bool]
    clinical_verdict: Literal["NOT_REVIEWED"] = "NOT_REVIEWED"
    elapsed_ms: float
    tool_calls: int
    provenance: dict


class FactProposal(Model):
    proposal_id: str
    fact: ClinicalFact
    requires_confirmation: Literal[True] = True


class ConversationResult(Model):
    response: str = Field(min_length=1, max_length=10000)
    facts: list[ClinicalFact] = Field(default_factory=list, max_length=20)
    evidence_ids: list[str] = Field(default_factory=list)


class ProposalAcceptance(Mutation):
    fact: ClinicalFact  # Staff may correct proposed fields before confirmation.


class ReviewedProposal(Model):
    proposal_id: str = Field(min_length=1, max_length=128)
    fact: ClinicalFact


class ProposalBatchAcceptance(Mutation):
    proposals: list[ReviewedProposal] = Field(min_length=1, max_length=20)
