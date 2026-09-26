"""Typed evidence and derived data for the Case Graph (PROPOSAL 3.2.1, 2.1.4, 1.3.4).

Evidence items carry time-validity (``event_time``/``available_at_time``), provenance, version and a
required ``data_class``. Derived values record who produced them and from which inputs. No model
here holds pixel arrays or a free-text reasoning/thought field.
"""

from __future__ import annotations

import hashlib
import json
from datetime import datetime
from typing import Annotated, Any, Literal, Union

from pydantic import AwareDatetime, Field, TypeAdapter, model_validator

from .types import EvidenceItem, TypedData

DataClassName = Literal["synthetic", "mimic", "hospital", "real", "unknown"]
# Least to most restrictive. ``unknown`` is treated as the most restrictive class.
DATA_CLASS_ORDER: tuple[str, ...] = ("synthetic", "mimic", "hospital", "real", "unknown")
PLACEHOLDER_LABEL = "PLACEHOLDER — not clinical"
SHA256_HEX = r"^[0-9a-f]{64}$"


def canonical_json(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def sha256_json(value: Any) -> str:
    return hashlib.sha256(canonical_json(value).encode("utf-8")).hexdigest()


def most_restrictive(classes: list[str] | tuple[str, ...] | set[str]) -> str:
    """Most restrictive data class; an empty input set is ``synthetic`` (nothing to protect)."""
    return max(classes, key=DATA_CLASS_ORDER.index, default="synthetic")


# --------------------------------------------------------------------------------------- evidence


class Evidence(EvidenceItem):
    """Base of all concrete evidence types. ``data_class`` has no default (1.3.4)."""

    item_id: str = Field(min_length=1)
    data_class: DataClassName

    @model_validator(mode="after")
    def _available_not_before_event(self) -> "Evidence":
        if self.available_at_time < self.event_time:
            raise ValueError("available_at_time must not be earlier than event_time")
        return self

    def content_sha256(self) -> str:
        return sha256_json(self.model_dump(mode="json"))


class ClinicalText(Evidence):
    data_type: Literal["ClinicalText"] = "ClinicalText"
    text: str = Field(min_length=1)


class _ImagingRef(Evidence):
    """Reference plus metadata only. Pixel data never enters the graph."""

    uri: str = Field(min_length=1)
    shape: tuple[int, ...] = Field(min_length=2, max_length=4)
    sha256: str = Field(pattern=SHA256_HEX)


class CTVolume(_ImagingRef):
    data_type: Literal["CTVolume"] = "CTVolume"


class MRIVolume(_ImagingRef):
    data_type: Literal["MRIVolume"] = "MRIVolume"


class CXRImage(_ImagingRef):
    data_type: Literal["CXRImage"] = "CXRImage"


class Vitals(Evidence):
    data_type: Literal["Vitals"] = "Vitals"
    values: dict[str, float] = Field(min_length=1)  # e.g. hr, sbp, spo2, rr, temp_c


class LabResult(TypedData):
    name: str = Field(min_length=1)
    value: float
    unit: str = Field(min_length=1)


class LabSeries(Evidence):
    data_type: Literal["LabSeries"] = "LabSeries"
    results: tuple[LabResult, ...] = Field(min_length=1)


class Medication(TypedData):
    name: str = Field(min_length=1)
    dose: str | None = None
    frequency: str | None = None
    list_source: str | None = None  # which medication list/source reported it


class MedicationList(Evidence):
    data_type: Literal["MedicationList"] = "MedicationList"
    medications: tuple[Medication, ...]


EVIDENCE_TYPES: tuple[type[Evidence], ...] = (
    ClinicalText, CTVolume, MRIVolume, CXRImage, Vitals, LabSeries, MedicationList,
)


# ---------------------------------------------------------------------------------------- derived


class Derived(TypedData):
    """Every derived value records the producing node and its inputs (evidence ids / output hashes)."""

    produced_by: str = Field(min_length=1)
    input_refs: tuple[str, ...]
    provider: str = Field(min_length=1)
    model_version: str = Field(min_length=1)


class Findings(Derived):
    source_data_types: tuple[str, ...] = Field(min_length=1)
    statements: tuple[str, ...]


class ImageTokens(Derived):
    modality: str = Field(min_length=1)
    encoder_provider: Literal["encoder_2d", "encoder_3d"]
    token_ref: str = Field(min_length=1)
    token_sha256: str = Field(pattern=SHA256_HEX)


class Alert(TypedData):
    rule_id: str = Field(min_length=1)
    severity: Literal["urgent", "warning"]
    message: str = Field(min_length=1)


class Alerts(Derived):
    status: Literal["evaluated", "not_evaluated"]
    alerts: tuple[Alert, ...]
    missing_inputs: tuple[str, ...]
    rule_set_version: str
    label: str = PLACEHOLDER_LABEL

    @property
    def has_urgent(self) -> bool:
        return any(a.severity == "urgent" for a in self.alerts)


class CaseSummary(Derived):
    text: str


class DepartmentSuggestion(Derived):
    department: str | None  # None: the provider proposed none; never filled in by the graph


class CareSuggestion(Derived):
    items: tuple[str, ...]


class MedicationIssue(TypedData):
    kind: str = Field(min_length=1)
    medication: str = Field(min_length=1)
    message: str = Field(min_length=1)


class MedicationIssues(Derived):
    issues: tuple[MedicationIssue, ...]
    summary: str | None = None
    rule_set_version: str | None = None
    label: str = PLACEHOLDER_LABEL


class ConfirmedResult(Derived):
    action: Literal["confirm", "edit", "reject"]
    graph_id: str = Field(min_length=1)
    reviewer_id: str = Field(min_length=1)
    reviewer_role: Literal["nurse", "physician", "pharmacist"]
    confirmed_at: AwareDatetime
    checkpoint_input_hash: str = Field(pattern=SHA256_HEX)
    payload: dict[str, Any] | None  # reviewed content (confirm), edited content (edit), None (reject)


DERIVED_TYPES: tuple[type[Derived], ...] = (
    Findings, ImageTokens, Alerts, CaseSummary, DepartmentSuggestion, CareSuggestion,
    MedicationIssues, ConfirmedResult,
)


class ConfirmedEvidence(Evidence):
    """A confirmed/edited Human Checkpoint result re-entering the record as new evidence."""

    data_type: Literal["ConfirmedResult"] = "ConfirmedResult"
    result: ConfirmedResult


AnyEvidence = Annotated[
    Union[ClinicalText, CTVolume, MRIVolume, CXRImage, Vitals, LabSeries, MedicationList, ConfirmedEvidence],
    Field(discriminator="data_type"),
]
EVIDENCE_LIST = TypeAdapter(list[AnyEvidence])


def dump_evidence(items: list[Evidence] | tuple[Evidence, ...]) -> list[dict[str, Any]]:
    return [i.model_dump(mode="json") for i in items]


def load_evidence(data: list[dict[str, Any]]) -> list[Evidence]:
    return list(EVIDENCE_LIST.validate_python(data))


def utc_iso(dt: datetime) -> str:
    return dt.isoformat(timespec="microseconds")
