from __future__ import annotations

from sqlalchemy import select

from app.db import demo_events, demo_runs


def create_run(client, login, username="nurse1"):
    login(username)
    response = client.post("/api/demo/v1/journeys/medx-front-door-v1/runs")
    assert response.status_code == 201, response.text
    return response.json()["run_id"]


def test_journey_requires_authentication(client):
    assert client.get("/api/demo/v1/journeys").status_code == 401


def test_runs_are_synthetic_deterministic_and_isolated(client, login, app):
    run_a = create_run(client, login)
    run_b = client.post("/api/demo/v1/journeys/medx-front-door-v1/runs").json()["run_id"]
    assert run_a != run_b
    case_a = client.get(f"/api/demo/v1/runs/{run_a}/cases/SYN-2026-0017").json()
    case_b = client.get(f"/api/demo/v1/runs/{run_b}/cases/SYN-2026-0017").json()
    assert case_a["summary"] == case_b["summary"]
    assert case_a["data_class"] == "synthetic"
    client.post(f"/api/demo/v1/tasks/task-triage-017/claim", json={"run_id": run_a, "version": 1})
    queue_a = client.get(f"/api/demo/v1/runs/{run_a}/queue").json()["items"]
    queue_b = client.get(f"/api/demo/v1/runs/{run_b}/queue").json()["items"]
    assert next(x for x in queue_a if x["task_id"] == "task-triage-017")["status"] == "claimed"
    assert next(x for x in queue_b if x["task_id"] == "task-triage-017")["status"] == "ready"
    with app.state.engine.connect() as conn:
        assert len(conn.execute(select(demo_runs)).all()) == 2
        assert len(conn.execute(select(demo_events)).all()) == 1


def test_role_matrix_red_flag_gate_and_append_only_review(client, login):
    run_id = create_run(client, login)
    denied = client.post("/api/demo/v1/tasks/task-care-017/claim", json={"run_id": run_id, "version": 1})
    assert denied.status_code == 403
    gated = client.post(
        "/api/demo/v1/tasks/task-triage-017/reviews/confirm",
        json={"run_id": run_id, "version": 1, "acknowledged_alerts": []},
    )
    assert gated.status_code == 422
    reviewed = client.post(
        "/api/demo/v1/tasks/task-triage-017/reviews/confirm",
        json={"run_id": run_id, "version": 1, "acknowledged_alerts": ["red-flag-017"]},
    )
    assert reviewed.status_code == 201
    duplicate = client.post(
        "/api/demo/v1/tasks/task-triage-017/reviews/reject",
        json={"run_id": run_id, "version": 2, "reason": "duplicate", "acknowledged_alerts": ["red-flag-017"]},
    )
    assert duplicate.status_code == 409


def test_pharmacist_review_is_role_gated_and_immutable(client, login):
    run_id = create_run(client, login)
    denied = client.post(
        "/api/demo/v1/medication-reviews/med-review-017/confirm",
        json={"run_id": run_id, "version": 1},
    )
    assert denied.status_code == 403
    client.post("/api/auth/logout")
    login("pharmacist1")
    response = client.post(
        "/api/demo/v1/medication-reviews/med-review-017/confirm",
        json={"run_id": run_id, "version": 1},
    )
    assert response.status_code == 201
    medication = client.get(f"/api/demo/v1/runs/{run_id}/cases/SYN-2026-0017/medications").json()
    assert medication["discrepancies"][0]["status"] == "confirm"


def _summary_case(client, login):
    run_id = create_run(client, login)
    return client.get(f"/api/demo/v1/runs/{run_id}/cases/SYN-2026-0017").json()


def test_case_summary_fields_present_and_ordered(client, login):
    case = _summary_case(client, login)
    vitals = case["vitals"]
    assert len(vitals) >= 2
    assert [v["observed_at"] for v in vitals] == sorted(v["observed_at"] for v in vitals)
    for key in ("observed_at", "available_at_time", "hr", "rr", "sbp", "dbp", "spo2", "temp_c", "consciousness", "on_oxygen"):
        assert all(key in v for v in vitals)
    assert vitals[-1]["evidence_id"] in case["triage"]["evidence_ids"]
    assert isinstance(case["allergies"], list) and {"substance", "reaction"} <= set(case["allergies"][0])
    for lab in case["labs"]:
        assert {"test", "value", "unit", "ref_low", "ref_high", "resulted_at"} <= set(lab)
    # a lab outside its range exists, consistent with the critical red-flag story
    assert any(lab["value"] > lab["ref_high"] for lab in case["labs"])


def test_case_summary_preserves_null_as_missing(client, login):
    latest = _summary_case(client, login)["vitals"][-1]
    assert latest["temp_c"] is None  # missing stays null, never 0


def test_case_summary_respects_decision_time(client, login):
    case = _summary_case(client, login)
    cutoff = case["decision_time"]  # same UTC ISO format, so string order is time order
    stamps = [v["observed_at"] for v in case["vitals"]] + [v["available_at_time"] for v in case["vitals"]]
    stamps += [lab[k] for lab in case["labs"] for k in ("resulted_at", "available_at_time")]
    assert all(t <= cutoff for t in stamps)
