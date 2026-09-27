from datetime import datetime, timedelta, timezone

import pytest
from pydantic import ValidationError

import casegraph
from casegraph import (
    AllergyList,
    ClinicalText,
    Demographics,
    EvidenceItem,
    IntakeTranscript,
    LabSeries,
    MedicationList,
    TimedEvidence,
    Vitals,
    evidence_adapter,
)

TZ = timezone(timedelta(hours=7))
T0 = datetime(2030, 1, 1, 8, 0, tzinfo=TZ)
BASE = dict(patient_ref="SYNP-0001", encounter_ref="SYNE-0001", item_id="SYNE-0001-X", event_time=T0,
            observed_at=T0, available_at_time=T0 + timedelta(minutes=1), source="synthetic-test",
            provenance="synthetic", version="1")
VITALS = dict(sbp=120, dbp=80, hr=80, rr=16, temp_c=37.0, spo2=98, consciousness="A", on_oxygen=False)


def test_new_types_subclass_evidence_item():
    for cls in (IntakeTranscript, Demographics, Vitals, LabSeries, MedicationList, AllergyList):
        assert issubclass(cls, TimedEvidence) and issubclass(cls, EvidenceItem)
        assert cls.model_config["extra"] == "forbid"
    assert issubclass(IntakeTranscript, ClinicalText)


def test_abstract_bases_not_instantiable():
    with pytest.raises(TypeError):
        TimedEvidence(**BASE, data_type="x")
    with pytest.raises(TypeError):
        ClinicalText(**BASE, data_type="x", language="th")


def test_missing_observed_at_is_validation_error():
    data = {k: v for k, v in BASE.items() if k != "observed_at"}
    with pytest.raises(ValidationError):
        Demographics(**data, age_years=40, sex="female")


def test_time_order_enforced():
    with pytest.raises(ValidationError):
        Vitals(**{**BASE, "observed_at": T0 + timedelta(hours=1)}, **VITALS)
    with pytest.raises(ValidationError):
        Vitals(**{**BASE, "event_time": T0 + timedelta(seconds=30)}, **VITALS)


def test_extra_fields_forbidden_and_adults_only():
    with pytest.raises(ValidationError):
        Demographics(**BASE, age_years=40, sex="female", name="x")
    with pytest.raises(ValidationError):
        Demographics(**BASE, age_years=17, sex="female")


def test_vitals_null_not_zero():
    v = Vitals(**BASE, **{**VITALS, "temp_c": None})
    assert v.temp_c is None
    with pytest.raises(ValidationError):  # nullable but required: must be explicitly present
        Vitals(**BASE, **{k: x for k, x in VITALS.items() if k != "spo2"})


def test_medication_and_allergy_invariants():
    entry = dict(generic_name="amlodipine", atc_code="C08CA01", dose_value=5, dose_unit="mg", frequency="OD", route="PO")
    with pytest.raises(ValidationError):
        MedicationList(**BASE, list_source="patient_reported", entries=[entry])
    MedicationList(**BASE, list_source="patient_reported", entries=[entry], derived_from="SYNE-0001-TX")
    with pytest.raises(ValidationError):
        MedicationList(**BASE, list_source="home_list", entries=[{**entry, "atc_code": "bad"}])
    with pytest.raises(ValidationError):
        AllergyList(**BASE, status="known", entries=[])
    AllergyList(**BASE, status="unknown", entries=[])


def test_discriminated_adapter():
    obj = evidence_adapter.validate_python({**BASE, "data_type": "Vitals", **VITALS})
    assert isinstance(obj, Vitals)
    with pytest.raises(ValidationError):
        evidence_adapter.validate_python({**BASE, "data_type": "Unknown"})


def test_evidence_schema_does_not_depend_on_compiler_or_executor():
    # s1 asserted the whole package had no compiler/executor; superseded by slice s2, which adds them.
    # What must still hold: the s1 dataset schema stays independent of graph execution.
    import casegraph.evidence as e

    names = {n.lower() for n in dir(e)}
    assert not any("compile" in n or "execute" in n for n in names)
