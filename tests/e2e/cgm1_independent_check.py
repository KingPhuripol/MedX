"""cg-m1 independent checker: own timelines (shifted minutes vs the builder's), HTTP assess, oracle = union of
stored graphs loaded by graph_id and re-derived from raw stores (not versions()). Synthetic, mock provider.
Run: PYTHONPATH=backend:. .venv/bin/python -m pytest -q -p no:cacheprovider tests/e2e/cgm1_independent_check.py
make test: tests/e2e/cgm1_independent_check.py (4 tests, listed in pyproject testpaths)
"""
from datetime import datetime

import pytest
from backend.tests.conftest import app, client, login, audit_rows, settings  # noqa: F401  (fixtures)
from backend.tests.triage.helpers import T0, make_case
from app.triage import casegraph_run, router
from casegraph.tests.fixtures import H, M, labs, s4_intake, vitals
from casegraph.tests.staged_fixtures import FRESH, URGENT, allergy, home, order

# (urgent_at, extra_vitals, events, as_of, expected sequence, expected alert idx->rules)
CASES = {
    "X1": (8, [], [("lab", 35), ("order", 65)], 75, ["T2", "T3"], {0: ["RF-SPO2"]}),
    "X2": (3, [], [("order", 25), ("lab", 35)], 85, ["T3", "T2"], {0: ["RF-SPO2"]}),
    "X3": (45, [], [("lab", 15), ("order", 55), ("lab", 80)], 140, ["T2", "T3", "T2"], {1: ["RF-SPO2"]}),
    "X4": (None, [], [("lab", 30), ("order", 60)], 90, ["T2", "T3"], {}),
}


def run(app, client, login, monkeypatch, name, case):
    urgent, extra, events, as_of_m, seq, exp = case
    p = f"SYN-X-{name}"
    t = lambda m: T0 + m * M  # noqa: E731
    items = [*s4_intake(p, p, T0 - 20 * M), vitals(p, f"{p}-vs1", T0 - 10 * M, T0 - 9 * M, **FRESH),
             home(p, f"{p}-home", T0 - 24 * H), allergy(p, f"{p}-allergy", T0 - 48 * H)]
    if urgent is not None:
        items.append(vitals(p, f"{p}-u", t(urgent), t(urgent + 1), **URGENT))
    for i, (k, m) in enumerate(events):
        items.append(labs(p, f"{p}-e{i}", t(m), t(m)) if k == "lab" else order(p, f"{p}-e{i}", t(m)))
    monkeypatch.setattr(router, "engine_cases", lambda: {p: make_case(case_ref=p, late=[("vital.hr", 80, as_of_m)])})
    monkeypatch.setattr(casegraph_run, "evidence_from_case", lambda c: items)
    login("nurse1")
    r1 = client.post(f"/api/triage/cases/{p}/assess", json={"as_of": T0.isoformat()})
    assert r1.status_code == 201 and [g["stage"] for g in r1.json()["built_graphs"]] == ["T1"]
    r2 = client.post(f"/api/triage/cases/{p}/assess", json={"as_of": t(as_of_m).isoformat()})
    assert r2.status_code == 201, r2.text
    return p, r2.json()


@pytest.mark.parametrize("name", list(CASES))
def test_variant(app, client, login, audit_rows, monkeypatch, name):
    case = CASES[name]
    p, body = run(app, client, login, monkeypatch, name, case)
    assert [g["stage"] for g in body["built_graphs"]] == case[4]
    st = app.state.casegraph.state
    union = set()
    for i, ref in enumerate(body["built_graphs"]):
        g = casegraph_run.load(app.state.casegraph, ref["graph_id"])
        assert g.graph_id == casegraph_run.graph_id_for(p, ref["version"])
        ids = sorted({x["rule_id"] for x in (casegraph_run.graph_alerts(g) or [])})
        assert ref["alert_rule_ids"] == ids == case[5].get(i, [])
        union |= set(ids)
    assert body["graph_alert_rule_ids"] == sorted(union)
    assert body["escalation_required"] is bool(union) and body["alerts"] == []
    assert body["graph_id"] == body["built_graphs"][-1]["graph_id"]
    assert st.latest_version(p) == 1 + len(case[4])
    row = next(r["details"] for r in audit_rows() if r["action"] == "triage.assess"
               and r["details"]["assessment_id"] == body["assessment_id"])
    assert row["graph_alert_rule_ids"] == sorted(union) and row["built_graphs"] == body["built_graphs"]
    # stored assessment (GET) agrees with the response
    got = client.get(f"/api/triage/assessments/{body['assessment_id']}")
    if got.status_code == 200:
        assert got.json()["built_graphs"] == body["built_graphs"]
