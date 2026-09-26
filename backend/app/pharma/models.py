"""Local Pydantic models for the Pharma Agent. Field names follow ``casegraph.EvidenceItem``
(``available_at_time``, ``provenance``, ``version``) without importing or extending it.

There is deliberately no field anywhere for a replacement, edited, or new order.
"""

from __future__ import annotations

from typing import Any, Literal

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, field_validator, model_validator

from ..gateway import DataClass

SourceType = Literal["home_list", "patient_reported", "new_order"]
FrequencyCode = Literal["q24h", "q12h", "q8h", "q6h", "prn"]
Mode = Literal["rules_only", "rules_plus_model"]
IssueType = Literal[
    "allergy_direct",
    "allergy_class",
    "allergy_cross_reactivity",
    "duplication_ingredient",
    "duplication_class",
    "dose_mismatch",
    "frequency_mismatch",
    "missing_field",
    "omission",
]
NoticeType = Literal["unrecognised_drug", "allergy_unmapped", "source_unreadable", "source_missing"]
MissingField = Literal["dose", "frequency"]
ISSUE_TYPES: tuple[str, ...] = IssueType.__args__  # type: ignore[attr-defined]
NOTICE_TYPES: tuple[str, ...] = NoticeType.__args__  # type: ignore[attr-defined]


class _Frozen(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")


# ---------------------------------------------------------------- input snapshot


class MedEntry(_Frozen):
    text: str = Field(min_length=1, max_length=500)
    discontinue_intent: bool = False
    reason: str | None = Field(default=None, max_length=500)

    @model_validator(mode="after")
    def _reason_needs_intent(self) -> "MedEntry":
        if self.reason is not None and not self.discontinue_intent:
            raise ValueError("reason is only allowed together with discontinue_intent")
        return self


class MedSource(_Frozen):
    source_type: SourceType
    evidence_ref: str = Field(min_length=1, max_length=128)
    available_at_time: AwareDatetime
    provenance: str = Field(min_length=1, max_length=256)
    version: str = Field(min_length=1, max_length=64)
    entries: tuple[MedEntry, ...]

    @field_validator("entries", mode="before")
    @classmethod
    def _coerce_text(cls, value: Any) -> Any:
        if isinstance(value, (list, tuple)):
            return [{"text": v} if isinstance(v, str) else v for v in value]
        return value

    @model_validator(mode="after")
    def _intent_only_on_orders(self) -> "MedSource":
        if self.source_type != "new_order" and any(e.discontinue_intent for e in self.entries):
            raise ValueError("discontinue_intent is only allowed on new_order entries")
        return self


class AllergyRecord(_Frozen):
    text: str = Field(min_length=1, max_length=300)
    evidence_ref: str = Field(min_length=1, max_length=128)
    available_at_time: AwareDatetime
    provenance: str = Field(min_length=1, max_length=256)
    version: str = Field(min_length=1, max_length=64)


class MedSnapshot(_Frozen):
    patient_ref: str = Field(min_length=1, max_length=128)
    as_of: AwareDatetime
    data_class: DataClass  # required, no default
    sources: tuple[MedSource, ...]
    allergies: tuple[AllergyRecord, ...] = ()


# ---------------------------------------------------------------- step 1 (extract) schema


class ExtractedEntry(_Frozen):
    drug_name_raw: str = Field(min_length=1, max_length=200)
    dose_value: float | None = Field(default=..., ge=0)
    dose_unit: str | None = Field(default=..., max_length=16)
    route: str | None = Field(default=..., max_length=32)
    frequency_code: FrequencyCode | None = Field(default=...)
    raw_span: str = Field(min_length=1, max_length=500)


class ExtractOutput(_Frozen):
    entries: tuple[ExtractedEntry, ...]


# ---------------------------------------------------------------- step 3 (phrase) schema


class PhraseItem(_Frozen):
    issue_id: str = Field(min_length=1, max_length=128)
    text: str = Field(min_length=1, max_length=1000)


class PhraseOutput(_Frozen):
    phrasings: tuple[PhraseItem, ...]


# ---------------------------------------------------------------- outputs


class ConflictingSource(_Frozen):
    source_type: Literal["home_list", "patient_reported", "new_order", "allergy_record"]
    evidence_ref: str
    available_at_time: str
    raw_span: str
    presence: Literal["present", "absent"] = "present"
    drug_name_raw: str | None = None
    dose_value: float | None = None
    dose_unit: str | None = None
    route: str | None = None
    frequency_code: str | None = None


class Phrasing(_Frozen):
    text: str
    source: Literal["model", "template", "template_fallback"]
    provider: str
    model_version: str
    fallback_reason: str | None = None


class IssueNote(_Frozen):
    kind: Literal["missing_field"]
    field: MissingField
    source_type: str
    evidence_ref: str


class Issue(_Frozen):
    issue_id: str
    run_id: str
    type: IssueType
    severity: str
    severity_rank: int
    rule_id: str  # "<rule_id>@<rule_version>"
    ingredients: tuple[str, ...]
    ingredient_rxcuis: tuple[str, ...]
    conflicting_sources: tuple[ConflictingSource, ...] = Field(min_length=1)
    field: MissingField | None = None  # missing_field only: which field the incomplete entry does not state
    unverifiable: bool = False
    possible_substitution: bool = False
    notes: tuple[IssueNote, ...] = ()
    detail: dict[str, Any] = Field(default_factory=dict)
    phrasing: Phrasing
    status: Literal["open", "confirmed", "dismissed"] = "open"


class Notice(_Frozen):
    notice_id: str
    type: NoticeType
    severity_rank: int = 5
    source_type: str | None = None
    evidence_ref: str | None = None
    raw_span: str | None = None
    detail: str


class DecisionBody(BaseModel):
    model_config = ConfigDict(extra="forbid")


class DismissBody(BaseModel):
    model_config = ConfigDict(extra="forbid")

    reason: str = Field(min_length=1, max_length=1000)

    @field_validator("reason")
    @classmethod
    def _not_blank(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("reason must not be blank")
        return value


class ReconcileBody(BaseModel):
    model_config = ConfigDict(extra="forbid")

    snapshot: MedSnapshot | None = None
    fixture_ref: str | None = Field(default=None, max_length=128)
    mode: Mode = "rules_plus_model"

    @model_validator(mode="after")
    def _exactly_one(self) -> "ReconcileBody":
        if (self.snapshot is None) == (self.fixture_ref is None):
            raise ValueError("provide exactly one of snapshot or fixture_ref")
        return self
