"""Local care-suggestion models (slice s6). Not a shared contract.

``CareAssessment`` is richer than ``casegraph.data.CareSuggestion`` (unchanged, D3); each suggested
assessment carries a projection that validates as that shared type. Field order is the serialisation
order: alerts and red-flag screening always come before the status and any suggestion.
"""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from ..triage.models import Alert

TASK = "care.suggest.v1"
UNCERTAINTY_LABEL = "MOCK baseline — not calibrated"
OUTPUT_LABEL = "Suggestion for physician review — research prototype"
DecisionPoint = Literal["T1", "T2"]
MAX_NEXT_INFO = 5
MAX_PATHWAYS = 3


class _Strict(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class ScreeningView(_Strict):
    """Every ``casegraph.data.RedFlagScreening`` field (slice int2: the I2 block), serialised as lists, plus
    ``summary`` (``RedFlagScreening.summary()``). Built only from a validated ``RedFlagScreening``."""

    status: Literal["evaluated", "partially_evaluated", "not_evaluated", "unavailable"]
    performed: bool
    banner: str | None
    rules_evaluated: list[str]
    rules_not_evaluated: list[str]
    missing_inputs: list[str]
    rule_set_version: str
    label: str
    scope: str
    n_declared: int
    n_evaluated: int
    n_not_evaluated: int
    n_fired: int
    readings: list[dict[str, Any]]
    conflicts: list[dict[str, Any]]
    summary: str


class EvidenceRef(_Strict):
    item_id: str
    data_type: str
    available_at_time: str


class SummaryLine(_Strict):
    text: str
    evidence_refs: list[EvidenceRef] = Field(min_length=1)


class NextInfo(_Strict):
    code: str
    kind: str
    display: str
    display_th: str
    evidence_refs: list[EvidenceRef] = Field(min_length=1)
    source_refs: list[str]


class PathwayOption(_Strict):
    code: str
    display: str
    display_th: str
    evidence_refs: list[EvidenceRef] = Field(min_length=1)
    source_refs: list[str]


class CareResult(_Strict):
    """Deterministic engine output for one snapshot (no ids or wall-clock timestamps)."""

    alerts: list[Alert]
    red_flag_screening: ScreeningView
    escalation_required: bool
    status: Literal["suggested", "abstained", "error"]
    case_summary: list[SummaryLine]
    next_information: list[NextInfo] = Field(max_length=MAX_NEXT_INFO)
    pathway_options: list[PathwayOption] = Field(max_length=MAX_PATHWAYS)
    missing_information: list[str]
    uncertainty: str = UNCERTAINTY_LABEL
    reason: str | None
    provider: str | None
    model_version: str | None
    contract_version: str | None
    rules_version: str
    request_sha256: str | None
    as_of: str
    decision_point: DecisionPoint
    case_id: str
    casegraph_projection: dict[str, Any] | None
    output_label: str = OUTPUT_LABEL
    data_class: Literal["synthetic"] = "synthetic"

    def codes(self) -> dict[str, list[str]]:
        return {"next_information": [x.code for x in self.next_information],
                "pathway_options": [x.code for x in self.pathway_options]}


class CareAssessment(CareResult):
    """Stored, immutable assessment. Review state is derived from the separate review table."""

    assessment_id: str
    created_at: str
    created_by: int
    review_status: Literal["pending_review", "confirmed", "edited", "rejected"] = "pending_review"
