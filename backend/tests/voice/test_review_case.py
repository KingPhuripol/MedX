"""V2D-D3, D4, D8 (case list), A10, A11: what the nurse's decisions put into the triage case."""

from __future__ import annotations

from datetime import timedelta

import pytest

from app.triage import engine as triage_engine
from app.triage.fixtures import engine_cases

from .review_helpers import (
    ALLERGY_CONFLICT_TURNS, Intake, counts, dt, hand_turns, stored_case_facts, stored_evidence, voice_facts_of,
)

ASK = ("chief_complaint", "onset_duration", "severity", "allergy_status", "current_medications", "relevant_history")

# (fixture, field, action): every field rejected; every MISSING row marked unknown; confirm of UNKNOWN / REFUSED.
NEVER_POSITIVE = (
    [(1, f, "reject") for f in ASK]
    + [(6, f, "unknown") for f in ("severity", "allergy_status", "current_medications", "relevant_history")]
    + [(3, "allergy_status", "confirm"), (4, "allergy_status", "confirm")]
)


@pytest.mark.parametrize(("n", "field", "action"), NEVER_POSITIVE)
def test_rejected_and_unknown_never_positive(client, app, login, n, field, action):
    login("nurse1")
    it = Intake(client, app, n)
    overrides = {field: (action, None)} if action != "confirm" else None
    out = it.submit(overrides)
    rid = out["review_id"]
    facts = voice_facts_of(app, rid)
    assert field not in facts and field in out["missing_fields"] and field not in out["confirmed_fields"]
    if field == "allergy_status":
        assert "allergens" not in facts
    kinds = [f["kind"] for f in stored_case_facts(app, rid)]
    assert field not in kinds
    assert not any(k.startswith("symptom.") for k in kinds)
    if field == "chief_complaint":  # the words stay in the transcript only; nothing re-extracts them
        transcript = next(e for e in stored_evidence(app, rid) if e["data_type"] == "IntakeTranscript")
        assert any("มีไข้" in t["text"] for t in transcript["turns"])
        case = next(c for c in client.get("/api/triage/cases").json()["cases"] if c["case_ref"] == out["case_ref"])
        assert case["chief_complaint"] is None


ALLERGY_CASES = {
    "a_confirm_negative_allowed": (1, ("confirm", None)),
    "b_missing_unknown": (6, ("unknown", None)),
    "c_missing_add_text": (6, ("add", "ไม่แพ้ยา")),
    "d_known_none_reject": (1, ("reject", None)),
    "e_known_none_edit_text": (1, ("edit", "ไม่แพ้")),
    "f_conflict_confirm_unclear": ("conflict", ("confirm", None)),
    "g_unknown_confirm": (3, ("confirm", None)),
}


def test_allergy_none_only_by_nurse_confirm(client, app, login):
    login("nurse1")
    results = {}
    for name, (n, (action, value)) in ALLERGY_CASES.items():
        src = hand_turns("SYN-V2D-AC", ALLERGY_CONFLICT_TURNS) if n == "conflict" else n
        it = Intake(client, app, src, patient_ref=f"SYN-V2D-{name[0].upper()}")
        overrides = None if action == "confirm" else {"allergy_status": (action, value)}
        if n == "conflict":
            assert it.get()["session"]["allergy_conflict"] is True
        out = it.submit(overrides)
        results[name] = voice_facts_of(app, out["review_id"]).get("allergy_status")
    assert results["a_confirm_negative_allowed"]["value"] == "none"
    for name in ("b_missing_unknown", "d_known_none_reject", "f_conflict_confirm_unclear", "g_unknown_confirm"):
        assert results[name] is None, name
    for name, text in (("c_missing_add_text", "ไม่แพ้ยา"), ("e_known_none_edit_text", "ไม่แพ้")):
        assert results[name]["value"] is None and results[name]["value_text"] == text, name
    assert [n for n, f in results.items() if f and f["value"] == "none"] == ["a_confirm_negative_allowed"]


def test_allergy_present_confirm_carries_allergens(client, app, login):
    login("nurse1")
    out = Intake(client, app, 7).submit()
    facts = voice_facts_of(app, out["review_id"])
    assert facts["allergy_status"]["value"] == "present" and facts["allergens"]["value"] == ["ซัลฟา"]
    assert out["confirmed_fields"].index("allergens") == out["confirmed_fields"].index("allergy_status") + 1


def _pre_slice_list() -> list[dict]:
    items = []
    for ref, case in engine_cases().items():
        cc = next((f.value for f in case.facts if f.kind == "chief_complaint"), None)
        latest = max(f.available_at_time for f in case.facts)
        items.append({"case_ref": ref, "chief_complaint": cc, "suggested_as_of": latest.isoformat()})
    return items


def test_fixture_case_list_unchanged(client, app, login):
    login("nurse1")
    before = client.get("/api/triage/cases").json()["cases"]
    assert before == _pre_slice_list() and len(before) == 40
    Intake(client, app, 1).submit()
    after = client.get("/api/triage/cases").json()["cases"]
    assert after[1:] == before and set(after[0]) == {"case_ref", "chief_complaint", "suggested_as_of", "source",
                                                     "red_flag"}


def test_time_validity(client, app, login):
    login("nurse1")
    ref = "SYN-V2D-TIME"
    first = Intake(client, app, 1, patient_ref=ref).submit({"onset_duration": ("reject", None)})
    t1 = dt(first["submitted_at"])
    fx6_start = dt("2026-01-10T02:00:00+00:00")
    second_intake = Intake(client, app, 6, patient_ref=ref, shift=(t1 + timedelta(hours=1)) - fx6_start)
    second = second_intake.submit()
    t2 = dt(second["submitted_at"])
    case_ref = first["case_ref"]

    early = client.post(f"/api/triage/cases/{case_ref}/assess", json={"as_of": (t1 - timedelta(seconds=1)).isoformat()})
    assert early.status_code == 422 and early.json()["detail"] == "as_of_before_evidence"

    mid = client.post(f"/api/triage/cases/{case_ref}/assess", json={"as_of": (t1 + timedelta(minutes=5)).isoformat()})
    assert mid.status_code == 201, mid.text
    mid = mid.json()
    assert "voice.nurse_attention" not in [a["rule_id"] for a in mid["alerts"]]
    assert "onset_duration" in mid["department"]["missing_information"]  # only the first review's S4 facts

    late = client.get(f"/api/triage/assessments/{second['department_suggestion']['assessment_id']}").json()
    assert late["alerts"][0]["rule_id"] == "voice.nurse_attention"
    assert all(ref.startswith(("voice_review/", "voice_turn/")) for ref in late["alerts"][0]["evidence_refs"])
    assert f"voice_review/{second['review_id']}" in late["alerts"][0]["evidence_refs"]
    assert "onset_duration" not in late["department"]["missing_information"]

    for out, t in ((first, t1), (second, t2)):
        for e in stored_evidence(app, out["review_id"]):
            assert dt(e["available_at_time"]) <= t
            assert all(dt(f["available_at_time"]) <= t for f in e.get("facts", []))
        assert all(dt(f["available_at_time"]) <= t for f in stored_case_facts(app, out["review_id"]))


def test_pending_on_assess_failure(client, app, login, monkeypatch, audit_rows):
    def boom(*a, **k):
        raise RuntimeError("engine down")

    monkeypatch.setattr(triage_engine, "assess", boom)
    login("nurse1")
    out = Intake(client, app, 1).submit()
    ds = out["department_suggestion"]
    assert ds["status"] == "pending" and ds["assessment_id"] is None and ds["reason"] == "assessment_unavailable"
    assert out["triage_path"] == "/nurse/triage"
    assert counts(app) == (1, 6, 0)
    handoff = [r for r in audit_rows() if r["action"] == "voice.review.handoff"]
    assert len(handoff) == 1 and handoff[0]["details"]["error_type"] == "RuntimeError"
    assert handoff[0]["details"]["assessment_id"] is None


def test_zero_s4_facts(client, app, login):
    login("nurse1")
    out = Intake(client, app, 1).submit({"chief_complaint": ("reject", None), "onset_duration": ("reject", None)})
    assert stored_case_facts(app, out["review_id"]) == []
    assert out["department_suggestion"]["status"] == "abstained"
    listed = client.get("/api/triage/cases").json()["cases"][0]
    assert listed["case_ref"] == out["case_ref"] and listed["chief_complaint"] is None
    again = client.post(f"/api/triage/cases/{out['case_ref']}/assess", json={"as_of": out["submitted_at"]})
    assert again.status_code == 201 and again.json()["department"]["status"] == "abstained"
