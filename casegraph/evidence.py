"""Typed evidence items (PROPOSAL 3.2.1 Table 3.1). Additive extension of ``EvidenceItem`` for slice s1."""

from __future__ import annotations

from typing import Annotated, Any, Literal, Union

from pydantic import AwareDatetime, Field, TypeAdapter, model_validator

from .types import EvidenceItem, TypedData

_ABSTRACT: set[type] = set()


class TimedEvidence(EvidenceItem):
    """Abstract: an evidence item with identity and an observation time.

    Invariant: ``event_time <= observed_at <= available_at_time``.
    """

    item_id: str = Field(min_length=1)
    encounter_ref: str = Field(min_length=1)
    observed_at: AwareDatetime

    def __init__(self, /, **data: Any) -> None:
        if type(self) in _ABSTRACT:
            raise TypeError(f"{type(self).__name__} is abstract")
        super().__init__(**data)

    @model_validator(mode="after")
    def _time_order(self) -> "TimedEvidence":
        if not (self.event_time <= self.observed_at <= self.available_at_time):
            raise ValueError("require event_time <= observed_at <= available_at_time")
        return self


class ClinicalText(TimedEvidence):
    """Abstract free-text evidence."""

    language: str = Field(min_length=2)


_ABSTRACT |= {TimedEvidence, ClinicalText}


class Turn(TypedData):
    turn_index: int = Field(ge=0)
    speaker: Literal["nurse", "patient"]
    text: str = Field(min_length=1)
    spoken_at: AwareDatetime


class IntakeTranscript(ClinicalText):
    data_type: Literal["IntakeTranscript"] = "IntakeTranscript"
    language: Literal["th"] = "th"
    turns: tuple[Turn, ...] = Field(min_length=1)


class Demographics(TimedEvidence):
    data_type: Literal["Demographics"] = "Demographics"
    age_years: int = Field(ge=18, le=95)
    sex: Literal["female", "male"]


class Vitals(TimedEvidence):
    """Every value is required but nullable: a missing measurement is ``None``, never 0."""

    data_type: Literal["Vitals"] = "Vitals"
    sbp: int | None
    dbp: int | None
    hr: int | None
    rr: int | None
    temp_c: float | None
    spo2: int | None
    consciousness: Literal["A", "C", "V", "P", "U"] | None
    on_oxygen: bool | None


class LabResult(TypedData):
    test: str = Field(min_length=1)
    value: float
    unit: str = Field(min_length=1)
    ref_low: float | None
    ref_high: float | None
    collected_at: AwareDatetime
    resulted_at: AwareDatetime


class LabSeries(TimedEvidence):
    data_type: Literal["LabSeries"] = "LabSeries"
    results: tuple[LabResult, ...] = Field(min_length=1)


class MedicationEntry(TypedData):
    generic_name: str = Field(min_length=1)
    atc_code: str = Field(pattern=r"^[A-Z]\d{2}[A-Z]{2}\d{2}$")
    dose_value: float = Field(gt=0)
    dose_unit: str = Field(min_length=1)
    frequency: str = Field(min_length=1)
    route: str = Field(min_length=1)


class MedicationList(TimedEvidence):
    data_type: Literal["MedicationList"] = "MedicationList"
    list_source: Literal["home_list", "patient_reported", "new_order"]
    entries: tuple[MedicationEntry, ...]
    derived_from: str | None = None

    @model_validator(mode="after")
    def _derived(self) -> "MedicationList":
        if (self.list_source == "patient_reported") != (self.derived_from is not None):
            raise ValueError("derived_from is required for patient_reported lists and only for them")
        return self


class AllergyEntry(TypedData):
    substance: str = Field(min_length=1)
    atc_class: str = Field(min_length=1)
    reaction: str = Field(min_length=1)


class AllergyList(TimedEvidence):
    data_type: Literal["AllergyList"] = "AllergyList"
    status: Literal["known", "no_known_allergy", "unknown"]
    entries: tuple[AllergyEntry, ...]

    @model_validator(mode="after")
    def _entries(self) -> "AllergyList":
        if (self.status == "known") != bool(self.entries):
            raise ValueError("entries must be non-empty iff status == 'known'")
        return self


CONCRETE_TYPES = (IntakeTranscript, Demographics, Vitals, LabSeries, MedicationList, AllergyList)
AnyEvidence = Annotated[Union[CONCRETE_TYPES], Field(discriminator="data_type")]  # noqa: UP007
evidence_adapter: TypeAdapter = TypeAdapter(AnyEvidence)
