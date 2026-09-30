"""V2D-D5: a red flag heard during ambient intake is required, carried into the case, shown first, and cannot be
removed by a department output, a graph failure or a later review without a red flag."""

from __future__ import annotations

import json
from datetime import timedelta

import pytest

from app.triage import casegraph_run, department
from app.triage.departments import DEPARTMENTS
from app.triage.models import DepartmentEntry, DepartmentSuggestion

from .review_helpers import Intake, counts, dt

RULE = "voice.nurse_attention"


def _red(client, app, n=6, **kw) -> dict:
    return Intake(client, app, n, **kw).submit()


def _assessment(client, out: dict) -> dict:
    return client.get(f"/api/triage/assessments/{out['department_suggestion']['assessment_id']}").json()


def _suggested(snap, invoke):
    d = DEPARTMENTS[0]
    return DepartmentSuggestion(
        status="suggested", top3=[DepartmentEntry(code=d.code, label_th=d.label_th, label_en=d.label_en, score=0.9,
                                                  evidence_refs=[])],
        uncertainty="low", uncertainty_label="stub", missing_information=[], reason=None, provider="stub",
        model_version="stub-1", contract_version=None, request_sha256=None)


@pytest.mark.parametrize("n", [6, 9])
def test_red_flag_ack_required(client, app, login, n):
    login("nurse1")
    it = Intake(client, app, n)
    it.finish()
    r = it.review(it.payload(red_flag_acknowledged_at=None), expect=422)
    assert r.json()["detail"] == "red_flag_ack_required"
    assert counts(app) == (0, 0, 0)
    assert all(c.get("source") != "voice_review" for c in client.get("/api/triage/cases").json()["cases"])


def test_red_flag_carried_and_first(client, app, login):
    login("nurse1")
    red = _red(client, app)
    assert red["red_flag"] is True
    # a newer non-red-flag voice case still lists after the red-flag one
    Intake(client, app, 1, shift=timedelta(days=30)).submit()
    cases = client.get("/api/triage/cases").json()["cases"]
    assert cases[0]["case_ref"] == red["case_ref"] and cases[0]["red_flag"] is True
    assert cases[1]["case_ref"] == "V-SYN-V2A-01" and cases[1]["red_flag"] is False
    a = _assessment(client, red)
    assert a["alerts"][0]["rule_id"] == RULE and a["escalation_required"] is True
    assert a["alerts"][0]["severity"] == "escalate"
    keys = list(a)
    assert keys.index("alerts") < keys.index("department")
    assert red["department_suggestion"]["alert_rule_ids"][0] == RULE
    assert red["department_suggestion"]["escalation_required"] is True
    # no transcript text in the alert
    blob = json.dumps(a["alerts"][0], ensure_ascii=False)
    assert "เจ็บหน้าอก" not in blob and "หายใจไม่ออก" not in blob


def test_confirm_requires_ack(client, app, login, monkeypatch):
    monkeypatch.setattr(department, "suggest", _suggested)
    login("nurse1")
    red = _red(client, app)
    a = _assessment(client, red)
    assert a["department"]["status"] == "suggested"
    code = a["department"]["top3"][0]["code"]
    url = f"/api/triage/assessments/{a['assessment_id']}"
    r = client.post(f"{url}/confirm", json={"department_code": code})
    assert r.status_code == 409 and r.json()["detail"] == "alerts_not_acknowledged"
    ids = [x["rule_id"] for x in a["alerts"]]
    r = client.post(f"{url}/confirm", json={"department_code": code, "acknowledged_alert_ids": ids})
    assert r.status_code == 200, r.text


def test_edit_on_abstained_voice_case_requires_ack(client, app, login):
    login("nurse1")
    red = _red(client, app)
    a = _assessment(client, red)
    url = f"/api/triage/assessments/{a['assessment_id']}"
    body = {"department_code": DEPARTMENTS[0].code, "reason": "nurse assessed at bedside"}
    assert client.post(f"{url}/edit", json=body).status_code == 409
    r = client.post(f"{url}/edit", json=body | {"acknowledged_alert_ids": [x["rule_id"] for x in a["alerts"]]})
    assert r.status_code == 200, r.text


def test_alert_survives_later_review_without_red_flag(client, app, login):
    login("nurse1")
    red = _red(client, app, patient_ref="SYN-V2D-RF")
    t1 = dt(red["submitted_at"])
    later = Intake(client, app, 1, patient_ref="SYN-V2D-RF",
                   shift=(t1 + timedelta(hours=1)) - dt("2026-01-05T02:00:00+00:00")).submit()
    assert later["red_flag"] is False and later["case_ref"] == red["case_ref"]
    a = _assessment(client, later)
    assert a["alerts"][0]["rule_id"] == RULE and a["escalation_required"] is True
    assert client.get("/api/triage/cases").json()["cases"][0]["red_flag"] is True


def test_alert_survives_graph_failure(client, app, login, monkeypatch):
    def boom(*a, **k):
        raise RuntimeError("graph down")

    monkeypatch.setattr(casegraph_run, "run_graph", boom)
    login("nurse1")
    a = _assessment(client, _red(client, app))
    assert a["alerts"][0]["rule_id"] == RULE and a["escalation_required"] is True
    assert a["graph_id"] is None


def test_alert_survives_department_error(client, app, login, monkeypatch):
    monkeypatch.setattr(department, "suggest",
                        lambda snap, invoke: department._empty("error", "gateway_error:stub", [], None))
    login("nurse1")
    red = _red(client, app)
    assert red["department_suggestion"]["status"] == "abstained"
    assert red["department_suggestion"]["reason"] == "gateway_error:stub"
    a = _assessment(client, red)
    assert a["department"]["status"] == "error"
    assert a["alerts"][0]["rule_id"] == RULE and a["escalation_required"] is True
