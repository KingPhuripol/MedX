"""V2D-D2 happy path and V2D-A12 contract shape. Synthetic dev fixtures, mock provider, offline."""

from __future__ import annotations

from app.voice.models import ReviewDecision, ReviewPayload
from casegraph.data import CLINICAL_TEXT_TYPES

from .review_helpers import (
    RESPONSE_KEYS, SUGGESTION_KEYS, Intake, dt, stored_case_facts, stored_evidence, voice_facts_of,
)

EDIT = "เป็นมา 4 วัน (พยาบาลแก้)"
REQUIRED_MISSING = {"age", "sex", "vitals.hr", "vitals.rr", "vitals.sbp", "vitals.spo2", "vitals.temp_c", "vitals.avpu"}


def test_happy_path_confirm_edit_reject(client, app, login):
    login("nurse1")
    it = Intake(client, app, 1)
    out = it.submit({"onset_duration": ("edit", EDIT), "relevant_history": ("reject", None)})
    assert set(out) == RESPONSE_KEYS
    rid, sid = out["review_id"], it.sid
    assert out["case_ref"] == "V-SYN-V2A-01" and out["red_flag"] is False
    assert out["confirmed_fields"] == ["chief_complaint", "onset_duration", "severity", "allergy_status",
                                       "current_medications"]
    assert out["missing_fields"] == ["relevant_history"]
    assert out["evidence_item_ids"] == [f"voice:{sid}:review:{rid}:facts", f"voice:{sid}:review:{rid}:transcript"]

    facts = voice_facts_of(app, rid)
    assert set(facts) == set(out["confirmed_fields"])
    assert facts["allergy_status"]["value"] == "none"
    assert facts["onset_duration"]["value"] == EDIT and facts["onset_duration"]["value_text"] == EDIT
    assert facts["onset_duration"]["provider"] == "human" and facts["onset_duration"]["extractor"] == "nurse_review"
    assert facts["chief_complaint"]["value_text"] == "มีไข้"
    submitted = dt(out["submitted_at"])
    for e in stored_evidence(app, rid):
        assert e["data_type"] in CLINICAL_TEXT_TYPES
        assert dt(e["available_at_time"]) == submitted
        assert e["provenance"] == f"voice_session/{sid}/review/{rid}"
    assert all(dt(f["available_at_time"]) == submitted for f in facts.values())
    assert {f["kind"]: f["value"] for f in stored_case_facts(app, rid)} == {
        "chief_complaint": "มีไข้", "onset_duration": EDIT}

    cases = client.get("/api/triage/cases").json()["cases"]
    assert cases[0]["case_ref"] == "V-SYN-V2A-01" and cases[0]["source"] == "voice_review"
    assert cases[0]["chief_complaint"] == "มีไข้" and cases[0]["red_flag"] is False

    ds = out["department_suggestion"]
    assert set(ds) == SUGGESTION_KEYS
    assert ds["status"] == "abstained" and ds["top3"] == [] and ds["label"] == "Suggestion for nurse review"
    assert REQUIRED_MISSING <= set(ds["missing_information"])
    assert out["triage_path"] == f"/nurse/triage/{ds['assessment_id']}"
    got = client.get(f"/api/triage/assessments/{ds['assessment_id']}")
    assert got.status_code == 200 and got.json()["case_ref"] == "V-SYN-V2A-01"


def test_response_shape(client, app, login):
    assert set(ReviewPayload.model_fields) == {
        "session_id", "patient_ref", "decisions", "consent_acknowledged_at", "red_flag_acknowledged_at"}
    assert set(ReviewDecision.model_fields) == {"field", "action", "value", "original", "reason"}
    assert ReviewPayload.model_config["extra"] == "forbid" and ReviewDecision.model_config["extra"] == "forbid"
    login("nurse1")
    for n in (1, 3, 6):
        out = Intake(client, app, n).submit()
        assert set(out) == RESPONSE_KEYS
        assert set(out["department_suggestion"]) == SUGGESTION_KEYS
        assert out["department_suggestion"]["status"] in {"suggested", "abstained", "pending"}
        # no fact values and no transcript text in the response
        assert "มีไข้" not in str(out) and "เจ็บหน้าอก" not in str(out)
