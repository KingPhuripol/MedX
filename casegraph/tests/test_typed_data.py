"""S2-A23: typed data contract."""

from datetime import timedelta

import pytest
from pydantic import BaseModel, ValidationError

from casegraph import data as d
from casegraph.types import EvidenceItem, TypedData

from .fixtures import DAY, H, SHA_A

COMMON = dict(
    item_id="x-1", patient_ref="SYN-T", event_time=DAY, available_at_time=DAY + H,
    source="synthetic-fixture", provenance="casegraph/tests", version="1", data_class="synthetic",
)
PAYLOAD = {
    d.ClinicalText: {"text": "synthetic"},
    d.CTVolume: {"uri": "synthetic://ct", "shape": (8, 8, 8), "sha256": SHA_A},
    d.MRIVolume: {"uri": "synthetic://mri", "shape": (8, 8, 8), "sha256": SHA_A},
    d.CXRImage: {"uri": "synthetic://cxr", "shape": (8, 8), "sha256": SHA_A},
    d.Vitals: {"values": {"hr": 80.0}},
    d.LabSeries: {"results": (d.LabResult(name="wbc", value=5, unit="u"),)},
    d.MedicationList: {"medications": (d.Medication(name="x"),)},
}
REQUIRED = ["event_time", "available_at_time", "source", "version", "data_class"]
HIDDEN = {"reasoning", "thought", "thoughts", "chain_of_thought", "rationale_hidden", "cot", "scratchpad"}


def test_seven_evidence_types_subclass_evidence_item():
    assert set(PAYLOAD) == set(d.EVIDENCE_TYPES) and len(d.EVIDENCE_TYPES) == 7
    assert all(issubclass(cls, EvidenceItem) for cls in d.EVIDENCE_TYPES)
    assert all(issubclass(cls, TypedData) for cls in d.DERIVED_TYPES)


@pytest.mark.parametrize("cls", d.EVIDENCE_TYPES, ids=lambda c: c.__name__)
def test_typed_data_contract(cls):
    item = cls(**COMMON, **PAYLOAD[cls])
    assert item.data_type == cls.__name__
    for missing in [*REQUIRED, "item_id"]:
        with pytest.raises(ValidationError):
            cls(**{k: v for k, v in COMMON.items() if k != missing}, **PAYLOAD[cls])
    with pytest.raises(ValidationError, match="available_at_time"):
        cls(**{**COMMON, "available_at_time": DAY - timedelta(seconds=1)}, **PAYLOAD[cls])
    with pytest.raises(ValidationError):  # data_class has no default and a closed vocabulary
        cls(**{**COMMON, "data_class": "public"}, **PAYLOAD[cls])
    with pytest.raises(ValidationError):  # extra fields forbidden
        cls(**COMMON, **PAYLOAD[cls], pixels=[[0]])
    with pytest.raises(ValidationError):  # frozen
        item.source = "other"  # type: ignore[misc]


def test_imaging_holds_reference_not_pixels():
    for cls in (d.CTVolume, d.MRIVolume, d.CXRImage):
        assert set(cls.model_fields) - set(d.Evidence.model_fields) == {"uri", "shape", "sha256"}
        with pytest.raises(ValidationError):
            cls(**COMMON, uri="u", shape=(8, 8), sha256="not-a-hash")


DERIVED_SAMPLES = {
    d.Findings: {"source_data_types": ("ClinicalText",), "statements": ("s",)},
    d.ImageTokens: {"modality": "CXRImage", "encoder_provider": "encoder_2d", "token_ref": "r", "token_sha256": SHA_A},
    d.Alerts: {"status": "evaluated", "alerts": (), "missing_inputs": (), "rule_set_version": "v"},
    d.CaseSummary: {"text": "t"},
    d.DepartmentSuggestion: {"department": None},
    d.CareSuggestion: {"items": ()},
    d.MedicationIssues: {"issues": ()},
    d.ConfirmedResult: {"action": "confirm", "graph_id": "g", "reviewer_id": "r", "reviewer_role": "nurse",
                        "confirmed_at": DAY, "checkpoint_input_hash": SHA_A, "payload": None},
}
PROV = {"produced_by": "n", "input_refs": ("x-1",), "provider": "rules", "model_version": "v"}


@pytest.mark.parametrize("cls", d.DERIVED_TYPES, ids=lambda c: c.__name__)
def test_derived_records_provenance_and_forbids_extra(cls):
    obj = cls(**PROV, **DERIVED_SAMPLES[cls])
    assert obj.produced_by == "n" and obj.input_refs == ("x-1",)
    with pytest.raises(ValidationError):
        cls(**PROV, **DERIVED_SAMPLES[cls], reasoning="hidden")
    with pytest.raises(ValidationError):
        cls(**{k: v for k, v in PROV.items() if k != "produced_by"}, **DERIVED_SAMPLES[cls])


def test_imagetokens_only_from_encoders():
    with pytest.raises(ValidationError):
        d.ImageTokens(**PROV, **{**DERIVED_SAMPLES[d.ImageTokens], "encoder_provider": "external_model"})


def _all_models(cls, seen):
    if cls in seen:
        return
    seen.add(cls)
    for f in cls.model_fields.values():
        for arg in [f.annotation, *getattr(f.annotation, "__args__", ())]:
            for inner in [arg, *getattr(arg, "__args__", ())]:
                if isinstance(inner, type) and issubclass(inner, BaseModel):
                    _all_models(inner, seen)


def test_no_hidden_reasoning_fields():
    seen: set = set()
    for cls in (*d.DERIVED_TYPES, *d.EVIDENCE_TYPES, d.ConfirmedEvidence):
        _all_models(cls, seen)
    assert len(seen) >= 15
    offenders = [f"{c.__name__}.{n}" for c in seen for n in c.model_fields if n.lower() in HIDDEN]
    assert offenders == []
