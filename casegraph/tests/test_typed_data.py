"""S2-A23: typed data contract; S2R-A05, S2R-A10."""

import math
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
    d.Vitals: {"hr": 80.0},
    d.LabSeries: {"results": (d.LabResult(test="wbc", value=5, unit="u"),)},
    d.MedicationList: {"list_source": "home_list", "entries": (d.MedicationEntry(generic_name="x"),)},
    # i2: the s1 dataset types joined casegraph.data (one evidence type system)
    d.IntakeTranscript: {"turns": (d.Turn(turn_index=0, speaker="patient", text="synthetic", spoken_at=DAY),)},
    d.VoiceIntakeFacts: {"facts": ()},
    d.Demographics: {"age_years": 40, "sex": "female"},
    d.AllergyList: {"status": "unknown", "entries": ()},
}
REQUIRED = ["event_time", "available_at_time", "source", "version", "data_class"]
HIDDEN = {"reasoning", "thought", "thoughts", "chain_of_thought", "rationale_hidden", "cot", "scratchpad"}


def test_seven_evidence_types_subclass_evidence_item():
    # i2: 7 s2 types + IntakeTranscript, VoiceIntakeFacts, Demographics, AllergyList (one type system)
    assert set(PAYLOAD) == set(d.EVIDENCE_TYPES) and len(d.EVIDENCE_TYPES) == 11
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
    # s2r: Alerts/MedicationIssues v1.1 fields; Reasoning outputs carry the required red_flag_screening.
    d.Alerts: {"status": "evaluated", "alerts": (), "missing_inputs": (), "rule_set_version": "v",
               "rule_results": (d.RuleResult(rule_id="R1", status="evaluated", missing_inputs=(),
                                             evaluated_on=("x-1",), fired=False),),
               "rules_evaluated": ("R1",), "rules_not_evaluated": ()},
    d.CaseSummary: {"text": "t", "red_flag_screening": "evaluated"},
    d.DepartmentSuggestion: {"department": None, "red_flag_screening": "evaluated"},
    d.CareSuggestion: {"items": (), "red_flag_screening": "evaluated"},
    d.MedicationIssues: {"status": "not_evaluated", "issues": (), "check_results": (), "checks_not_evaluated": (),
                         "missing_inputs": ()},
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


# ------------------------------------------------------------------------ S2R-A05 (s2r)


def _rr(rule_id="R1", evaluated=True):
    if evaluated:
        return d.RuleResult(rule_id=rule_id, status="evaluated", missing_inputs=(), evaluated_on=("x-1",), fired=False)
    return d.RuleResult(rule_id=rule_id, status="not_evaluated", missing_inputs=("Vitals.spo2",), evaluated_on=(),
                        fired=None)


ALERTS_BAD = {
    "empty": dict(rule_results=(), rules_evaluated=(), rules_not_evaluated=(), missing_inputs=()),
    "rule_not_evaluated": dict(rule_results=(_rr("R1"), _rr("R2", False)), rules_evaluated=("R1",),
                               rules_not_evaluated=("R2",), missing_inputs=("Vitals.spo2",)),
    "missing": dict(rule_results=(_rr("R1"),), rules_evaluated=("R1",), rules_not_evaluated=(),
                    missing_inputs=("Findings",)),
}


@pytest.mark.parametrize("case", list(ALERTS_BAD))
def test_alerts_cannot_claim_evaluated(case):
    with pytest.raises(ValidationError, match="status"):
        d.Alerts(**PROV, status="evaluated", alerts=(), rule_set_version="v", **ALERTS_BAD[case])
    # the aggregator gives the honest status for the same inputs, and that constructs fine
    honest = d.screening_status(ALERTS_BAD[case]["rule_results"], ALERTS_BAD[case]["missing_inputs"])
    assert honest != "evaluated"
    assert d.Alerts(**PROV, status=honest, alerts=(), rule_set_version="v", **ALERTS_BAD[case]).status == honest


def _mc(check="duplicate", evaluated=True):
    if evaluated:
        return d.MedicationCheck(medication="m", check=check, status="evaluated", missing_inputs=(),
                                 evaluated_on=("x-1",), fired=False)
    return d.MedicationCheck(medication="m", check=check, status="not_evaluated",
                             missing_inputs=("MedicationList.dose@x-1",), evaluated_on=(), fired=None)


MED_BAD = {
    "empty": dict(check_results=(), checks_not_evaluated=(), missing_inputs=()),
    "check_not_evaluated": dict(check_results=(_mc(), _mc("dose_mismatch", False)),
                                checks_not_evaluated=(_mc("dose_mismatch", False),),
                                missing_inputs=("MedicationList.dose@x-1",)),
    "missing": dict(check_results=(_mc(),), checks_not_evaluated=(), missing_inputs=("structured_rule_checks",)),
}


@pytest.mark.parametrize("case", list(MED_BAD))
def test_medication_issues_cannot_claim_evaluated(case):
    with pytest.raises(ValidationError, match="status"):
        d.MedicationIssues(**PROV, status="evaluated", issues=(), **MED_BAD[case])


def test_rule_result_invariants():
    with pytest.raises(ValidationError):  # not_evaluated cannot carry fired
        d.RuleResult(rule_id="R", status="not_evaluated", missing_inputs=("Vitals.hr",), evaluated_on=(), fired=False)
    with pytest.raises(ValidationError):  # evaluated with a missing input
        d.RuleResult(rule_id="R", status="evaluated", missing_inputs=("Vitals.hr",), evaluated_on=("x",), fired=False)
    with pytest.raises(ValidationError):  # evaluated on no evidence
        d.RuleResult(rule_id="R", status="evaluated", missing_inputs=(), evaluated_on=(), fired=False)
    with pytest.raises(ValidationError):  # alerts must come from a fired rule
        d.Alerts(**PROV, status="evaluated", rule_set_version="v", rule_results=(_rr("R1"),),
                 rules_evaluated=("R1",), rules_not_evaluated=(), missing_inputs=(),
                 alerts=(d.Alert(rule_id="R1", severity="urgent", message="m"),))


# ------------------------------------------------------------------------ S2R-A10 (s2r)


@pytest.mark.parametrize("bad", [math.nan, math.inf, -math.inf], ids=["nan", "inf", "-inf"])
def test_non_finite_values_rejected(bad):
    for key in ("hr", "sbp", "spo2", "temp_c", "rr"):
        with pytest.raises(ValidationError, match="finite"):
            d.Vitals(**COMMON, **{"hr": 80.0, key: bad})
    with pytest.raises(ValidationError, match="finite"):
        d.LabResult(test="wbc", value=bad, unit="u")
    with pytest.raises(ValidationError, match="finite"):
        d.load_evidence([{**COMMON, "data_type": "Vitals", "event_time": DAY.isoformat(),
                          "available_at_time": (DAY + H).isoformat(), "spo2": bad}])
