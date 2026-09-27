"""Typed evidence and derived data for the Case Graph (PROPOSAL 3.2.1, 2.1.4, 1.3.4).

Evidence items carry time-validity (``event_time``/``available_at_time``), provenance, version and a
required ``data_class``. Derived values record who produced them and from which inputs. No model
here holds pixel arrays or a free-text reasoning/thought field.
"""

from __future__ import annotations

import hashlib
import json
from datetime import datetime
from collections.abc import Sequence
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


# NaN / +-inf are rejected at validation (s2r): every comparison against NaN is False, so a corrupted
# reading would otherwise pass every threshold rule as "normal".
FiniteFloat = Annotated[float, Field(allow_inf_nan=False)]


class Vitals(Evidence):
    data_type: Literal["Vitals"] = "Vitals"
    values: dict[str, FiniteFloat] = Field(min_length=1)  # e.g. hr, sbp, spo2, rr, temp_c


class LabResult(TypedData):
    name: str = Field(min_length=1)
    value: FiniteFloat
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


# ------------------------------------------------------------------ screening status (s2r, v1.1)

ScreeningStatus = Literal["evaluated", "partially_evaluated", "not_evaluated"]
CheckStatus = Literal["evaluated", "not_evaluated"]
RedFlagScreeningStatus = Literal["evaluated", "partially_evaluated", "not_evaluated", "unavailable"]
BANNER_NOT_PERFORMED = "RED-FLAG SCREENING NOT PERFORMED"
BANNER_INCOMPLETE = "RED-FLAG SCREENING INCOMPLETE"


def screening_status(
    parts: Sequence[Any], missing_inputs: Sequence[str] = (), *, allow_partial: bool = True
) -> ScreeningStatus:
    """The single status aggregator. The only place a status value of ``evaluated`` is produced.

    ``parts`` are per-rule/per-check results (objects with ``.status``) or, for one rule, one bool per
    declared input (True = present, finite, inside the snapshot). ``evaluated`` requires at least one
    part, every part evaluated and no missing input. An empty rule set is ``not_evaluated``. With
    ``allow_partial=False`` (a single rule) anything short of ``evaluated`` is ``not_evaluated``.
    """
    done = [p if isinstance(p, bool) else p.status == "evaluated" for p in parts]
    if done and all(done) and not missing_inputs:
        return "evaluated"
    if allow_partial and any(done):
        return "partially_evaluated"
    return "not_evaluated"


class _CheckResult(TypedData):
    """One rule/check outcome. ``fired`` is None exactly when the check was not evaluated."""

    status: CheckStatus
    missing_inputs: tuple[str, ...]
    evaluated_on: tuple[str, ...]  # evidence item_ids actually read
    fired: bool | None
    label: str = PLACEHOLDER_LABEL

    @model_validator(mode="after")
    def _consistent(self):
        if self.status != screening_status([not self.missing_inputs], self.missing_inputs, allow_partial=False):
            raise ValueError("status must be not_evaluated iff missing_inputs is non-empty")
        if self.status == "not_evaluated" and self.fired is not None:
            raise ValueError("a not_evaluated check cannot have fired=True/False")
        if self.status != "not_evaluated" and (self.fired is None or not self.evaluated_on):
            raise ValueError("an evaluated check needs fired and evaluated_on")
        return self


class RuleResult(_CheckResult):
    rule_id: str = Field(min_length=1)


def _check_aggregate(status: str, results: Sequence[_CheckResult], missing: tuple[str, ...]) -> None:
    if status != screening_status(results, missing):
        raise ValueError(f"status {status!r} != aggregate {screening_status(results, missing)!r} of the results")
    if list(missing) != sorted(set(missing)):
        raise ValueError("missing_inputs must be sorted and unique")
    if not {m for r in results for m in r.missing_inputs} <= set(missing):
        raise ValueError("missing_inputs must include every result's missing inputs")


class Alerts(Derived):
    """Red-flag output v1.1. Cannot be constructed as ``evaluated`` unless every rule was evaluated."""

    status: ScreeningStatus
    alerts: tuple[Alert, ...]
    rule_results: tuple[RuleResult, ...]
    rules_evaluated: tuple[str, ...]
    rules_not_evaluated: tuple[str, ...]
    missing_inputs: tuple[str, ...]
    rule_set_version: str
    label: str = PLACEHOLDER_LABEL

    @model_validator(mode="after")
    def _invariant(self) -> "Alerts":
        _check_aggregate(self.status, self.rule_results, self.missing_inputs)
        done = sorted(r.rule_id for r in self.rule_results if r.status == "evaluated")
        if list(self.rules_evaluated) != done:
            raise ValueError("rules_evaluated must list the evaluated rule ids, sorted")
        if list(self.rules_not_evaluated) != sorted(r.rule_id for r in self.rule_results if r.rule_id not in done):
            raise ValueError("rules_not_evaluated must list the not_evaluated rule ids, sorted")
        fired = {r.rule_id for r in self.rule_results if r.fired}
        if not {a.rule_id for a in self.alerts} <= fired:
            raise ValueError("every alert must come from an evaluated rule that fired")
        return self

    @property
    def has_urgent(self) -> bool:
        return any(a.severity == "urgent" for a in self.alerts)


def banner_for(status: str) -> str | None:
    if status == "evaluated":
        return None
    return BANNER_INCOMPLETE if status == "partially_evaluated" else BANNER_NOT_PERFORMED


class RedFlagScreening(TypedData):
    """Red-flag screening summary carried by the Human Checkpoint payload and the graph export."""

    status: RedFlagScreeningStatus
    performed: bool
    banner: str | None
    rules_evaluated: tuple[str, ...]
    rules_not_evaluated: tuple[str, ...]
    missing_inputs: tuple[str, ...]

    @model_validator(mode="after")
    def _consistent(self) -> "RedFlagScreening":
        if self.performed != (self.status == "evaluated") or self.banner != banner_for(self.status):
            raise ValueError("performed/banner inconsistent with status")
        return self

    @classmethod
    def from_alerts(cls, alerts: dict[str, Any] | None, declared_rules: Sequence[str]) -> "RedFlagScreening":
        """From an Alerts output dict; ``None`` (Red-flag absent or errored) is ``unavailable``."""
        if alerts is None:
            return cls(status="unavailable", performed=False, banner=banner_for("unavailable"), rules_evaluated=(),
                       rules_not_evaluated=tuple(sorted(declared_rules)), missing_inputs=("Alerts",))
        checked = Alerts.model_validate(alerts)  # re-validates the construction invariant
        return cls(status=checked.status, performed=checked.status == "evaluated", banner=banner_for(checked.status),
                   rules_evaluated=checked.rules_evaluated, rules_not_evaluated=checked.rules_not_evaluated,
                   missing_inputs=checked.missing_inputs)


class CaseSummary(Derived):
    text: str
    red_flag_screening: RedFlagScreeningStatus  # required (s2r): never shown as if screening passed


class DepartmentSuggestion(Derived):
    department: str | None  # None: the provider proposed none; never filled in by the graph
    red_flag_screening: RedFlagScreeningStatus


class CareSuggestion(Derived):
    items: tuple[str, ...]
    red_flag_screening: RedFlagScreeningStatus


class MedicationIssue(TypedData):
    kind: str = Field(min_length=1)
    medication: str = Field(min_length=1)
    message: str = Field(min_length=1)


class MedicationCheck(_CheckResult):
    medication: str = Field(min_length=1)
    check: str = Field(min_length=1)  # e.g. duplicate, dose_mismatch


class MedicationIssues(Derived):
    """Pharma output v1.1: same construction invariant as :class:`Alerts`."""

    status: ScreeningStatus
    issues: tuple[MedicationIssue, ...]
    check_results: tuple[MedicationCheck, ...]
    checks_not_evaluated: tuple[MedicationCheck, ...]
    missing_inputs: tuple[str, ...]
    summary: str | None = None
    rule_set_version: str | None = None
    label: str = PLACEHOLDER_LABEL

    @model_validator(mode="after")
    def _invariant(self) -> "MedicationIssues":
        _check_aggregate(self.status, self.check_results, self.missing_inputs)
        if self.checks_not_evaluated != tuple(r for r in self.check_results if r.status == "not_evaluated"):
            raise ValueError("checks_not_evaluated must be the not_evaluated check results")
        return self


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
