"""Slice i2 (C6): one evidence type system. Replaces the s1 ``casegraph.evidence`` tests.

The s1 dataset types (IntakeTranscript, Demographics, Vitals, LabSeries, MedicationList, AllergyList) now live
in ``casegraph.data`` and derive from ``data.Evidence`` (``data_class`` required).
"""

import ast
import importlib.util
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
from pydantic import ValidationError

import casegraph
from casegraph import data as d
from casegraph.types import EvidenceItem

REPO = Path(__file__).resolve().parents[2]
TZ = timezone(timedelta(hours=7))
T0 = datetime(2030, 1, 1, 8, 0, tzinfo=TZ)
BASE = dict(patient_ref="SYNP-0001", encounter_ref="SYNE-0001", item_id="SYNE-0001-X", event_time=T0,
            observed_at=T0, available_at_time=T0 + timedelta(minutes=1), source="synthetic-test",
            provenance="synthetic", version="1", data_class="synthetic")
VITALS = dict(sbp=120, dbp=80, hr=80, rr=16, temp_c=37.0, spo2=98, consciousness="A", on_oxygen=False)


def test_one_evidence_type_system():
    assert importlib.util.find_spec("casegraph.evidence") is None
    assert not (REPO / "casegraph" / "evidence.py").exists()
    for cls in (d.IntakeTranscript, d.Demographics, d.Vitals, d.LabSeries, d.MedicationList, d.AllergyList,
                d.VoiceIntakeFacts):
        assert issubclass(cls, d.Evidence) and issubclass(cls, EvidenceItem)
        assert cls.model_config["extra"] == "forbid"
        assert cls.model_fields["data_class"].is_required()
    assert issubclass(d.IntakeTranscript, d._ClinicalTextFamily) and issubclass(d.VoiceIntakeFacts, d._ClinicalTextFamily)
    assert casegraph.Vitals is d.Vitals and casegraph.EVIDENCE_ADAPTER is d.EVIDENCE_ADAPTER
    # 0 EvidenceItem subclasses outside casegraph.data (scan backend/ and casegraph/)
    outside = []
    for root in ("backend/app", "casegraph", "data_factory", "eval"):
        for path in sorted((REPO / root).rglob("*.py")):
            if path.name == "data.py" and path.parent.name == "casegraph" or "tests" in path.parts:
                continue
            for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
                if isinstance(node, ast.ClassDef) and any(
                    getattr(b, "id", getattr(b, "attr", "")) in {"EvidenceItem", "Evidence", "TimedEvidence"}
                    for b in node.bases
                ):
                    outside.append(f"{path.relative_to(REPO)}:{node.name}")
    assert outside == []


def test_data_class_required():
    data = {k: v for k, v in BASE.items() if k != "data_class"}
    with pytest.raises(ValidationError):
        d.Demographics(**data, age_years=40, sex="female")


def test_time_order_enforced():
    with pytest.raises(ValidationError):
        d.Vitals(**{**BASE, "observed_at": T0 + timedelta(hours=1)}, **VITALS)
    with pytest.raises(ValidationError):
        d.Vitals(**{**BASE, "event_time": T0 + timedelta(seconds=30), "observed_at": T0}, **VITALS)


def test_vitals_null_not_zero_and_named():
    v = d.Vitals(**BASE, **{**VITALS, "temp_c": None})
    assert v.temp_c is None and "temp_c" not in v.readings()
    with pytest.raises(ValidationError):
        d.Vitals(**BASE, values={"hr": 80})  # the s2 dict-valued Vitals is retired
    with pytest.raises(ValidationError):
        d.Vitals(**BASE, consciousness="C", new_confusion=False)


def test_medication_and_allergy_invariants():
    entry = dict(generic_name="amlodipine", atc_code="C08CA01", dose_value=5, dose_unit="mg", frequency="OD", route="PO")
    d.MedicationList(**BASE, list_source="patient_reported", entries=[entry], derived_from="SYNE-0001-TX")
    with pytest.raises(ValidationError):
        d.MedicationList(**BASE, list_source="home_list", entries=[{**entry, "atc_code": "bad"}])
    with pytest.raises(ValidationError):
        d.AllergyList(**BASE, status="known", entries=[])
    d.AllergyList(**BASE, status="unknown", entries=[])


def test_transcript_turns_inside_item_window():
    turn = dict(turn_index=0, speaker="patient", text="x", spoken_at=T0)
    d.IntakeTranscript(**BASE, turns=[turn])
    with pytest.raises(ValidationError):  # a turn after the item became available cannot be planted
        d.IntakeTranscript(**BASE, turns=[{**turn, "spoken_at": T0 + timedelta(minutes=5)}])


def test_discriminated_adapter():
    obj = d.EVIDENCE_ADAPTER.validate_python({**BASE, "data_type": "Vitals", **VITALS})
    assert isinstance(obj, d.Vitals)
    with pytest.raises(ValidationError):
        d.EVIDENCE_ADAPTER.validate_python({**BASE, "data_type": "Unknown"})
