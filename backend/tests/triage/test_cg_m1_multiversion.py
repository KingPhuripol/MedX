"""Slice cg-m1 (closes CONDITIONS M1): one assess may build several Case Graph versions; every built version's
alerts escalate and every graph_id is linked. Synthetic, offline, mock provider. Not clinical performance."""

from __future__ import annotations

import json
from datetime import datetime

import pytest

from app.triage import casegraph_run, router
from app.triage.models import TriageAssessment
from casegraph.executor import Executor
from casegraph.tests.fixtures import H, M, labs, s4_intake, vitals
from casegraph.tests.staged_fixtures import FRESH, URGENT, allergy, home, order

from .helpers import T0, make_case

# Each pattern: (urgent_spo2_at, extra_vitals [(minutes, values)], events [(kind, minutes)], as_of,
#                versions [(stage, minutes)], alerts-by-version-index)
SPO2 = ["RF-SPO2"]
PATTERNS = {
    "P1": (5, [], [("lab", 40), ("order", 70)], 80, [("T2", 40), ("T3", 80)], {0: SPO2}),
    "P2": (5, [], [("order", 30), ("lab", 40)], 80, [("T3", 30), ("T2", 80)], {0: SPO2}),
    "P3": (40, [], [("lab", 20), ("order", 50), ("lab", 75)], 130, [("T2", 20), ("T3", 50), ("T2", 130)], {1: SPO2}),
    "P4": (5, [], [("lab", 40), ("order", 40)], 110, [("T2", 40), ("T3", 110)], {0: SPO2}),
    "P5": (5, [(109, {"rr": 32.0})], [("lab", 40), ("order", 100)], 110, [("T2", 40), ("T3", 110)],
           {0: SPO2, 1: ["RF-RR"]}),
}
P0 = (None, [], [("lab", 40), ("order", 70)], 80, [("T2", 40), ("T3", 80)], {})


def _evidence(p, pattern):
    urgent, extra, events, as_of, *_ = pattern
    t = lambda m: T0 + m * M  # noqa: E731
    items = [*s4_intake(p, p, T0 - 20 * M), vitals(p, f"{p}-vs1", T0 - 10 * M, T0 - 9 * M, **FRESH),
             home(p, f"{p}-home", T0 - 24 * H), allergy(p, f"{p}-allergy", T0 - 48 * H)]
    if urgent is not None:
        items.append(vitals(p, f"{p}-urgent", t(urgent), t(urgent + 1), **URGENT))
    for i, (m, values) in enumerate(extra):
        items.append(vitals(p, f"{p}-x{i}", t(m), t(m), **values))
    for i, (kind, m) in enumerate(events):
        items.append(labs(p, f"{p}-e{i}", t(m), t(m)) if kind == "lab" else order(p, f"{p}-e{i}", t(m)))
    return items


def _setup(app, client, login, monkeypatch, p, pattern):
    """Parent T1 built by a first assess at T0; returns a function making the second assess at as_of."""
    as_of = T0 + pattern[3] * M
    case = make_case(case_ref=p, late=[("vital.hr", 80, pattern[3])])
    monkeypatch.setattr(router, "engine_cases", lambda: {p: case})
    items = _evidence(p, pattern)
    monkeypatch.setattr(casegraph_run, "evidence_from_case", lambda c: items)
    login("nurse1")
    first = client.post(f"/api/triage/cases/{p}/assess", json={"as_of": T0.isoformat()})
    assert first.status_code == 201, first.text
    assert [g["stage"] for g in first.json()["built_graphs"]] == ["T1"]
    return lambda: client.post(f"/api/triage/cases/{p}/assess", json={"as_of": as_of.isoformat()})


def _assess_row(audit_rows, assessment_id):
    return next(r["details"] for r in audit_rows()
                if r["action"] == "triage.assess" and r["details"]["assessment_id"] == assessment_id)


def _sequence(pattern):
    return [(s, T0 + m * M) for s, m in pattern[4]]


@pytest.mark.parametrize("name", list(PATTERNS))
def test_intermediate_alert_escalates(app, client, login, audit_rows, monkeypatch, name):
    pattern = PATTERNS[name]
    p = f"SYN-M1-{name}"
    second = _setup(app, client, login, monkeypatch, p, pattern)
    resp = second()
    assert resp.status_code == 201, resp.text
    body = resp.json()
    built = body["built_graphs"]
    assert [(g["stage"], datetime.fromisoformat(g["T"])) for g in built] == _sequence(pattern)  # sequence first
    expected = pattern[5]
    assert body["alerts"] == [] and expected  # the engine raised nothing: the graph union is the only cause
    stores = app.state.casegraph
    union = set()
    for i, ref in enumerate(built):  # oracle: load every built graph, not versions()
        g = casegraph_run.load(stores, ref["graph_id"])
        ids = sorted({x["rule_id"] for x in (casegraph_run.graph_alerts(g) or [])})
        assert ref["alert_rule_ids"] == ids == sorted(expected.get(i, []))
        assert ref["escalation"] is bool(ids)
        union |= set(ids)
    assert union and body["graph_alert_rule_ids"] == sorted(union)
    if name != "P5":
        assert built[-1]["alert_rule_ids"] == []
    assert body["escalation_required"] is True
    row = _assess_row(audit_rows, body["assessment_id"])
    assert row["graph_alert_rule_ids"] == sorted(union) and row["escalation_required"] is True
    assert row["built_graphs"] == built and row["graph_failure"] is None and row["graph_id"] == built[-1]["graph_id"]


def test_no_alert_any_version_does_not_escalate(app, client, login, audit_rows, monkeypatch):
    p = "SYN-M1-P0"
    body = _setup(app, client, login, monkeypatch, p, P0)().json()
    assert [g["stage"] for g in body["built_graphs"]] == ["T2", "T3"]
    assert body["graph_alert_rule_ids"] == [] and body["alerts"] == []
    assert body["escalation_required"] is False
    assert all(g["alert_rule_ids"] == [] and g["escalation"] is False for g in body["built_graphs"])


@pytest.mark.parametrize("name", ["P0", *PATTERNS])
def test_built_graphs_linked_in_order(app, client, login, audit_rows, monkeypatch, name):
    pattern = P0 if name == "P0" else PATTERNS[name]
    p = f"SYN-M1-L-{name}"
    second = _setup(app, client, login, monkeypatch, p, pattern)
    st = app.state.casegraph.state
    before = st.latest_version(p)
    body = second().json()
    after = st.latest_version(p)
    built = body["built_graphs"]
    assert [g["version"] for g in built] == list(range(before + 1, after + 1))
    for g in built:
        spec, _ = st.load_graph(casegraph_run.graph_id_for(p, g["version"]))
        assert (g["graph_id"], g["stage"], datetime.fromisoformat(g["T"])) == (spec.graph_id, spec.stage, spec.T)
    assert body["graph_id"] == built[-1]["graph_id"]
    assert _assess_row(audit_rows, body["assessment_id"])["built_graphs"] == built


def _fail_kth(monkeypatch, target, name, k):
    calls = {"n": 0}
    orig = getattr(target, name)

    def wrapper(*a, **kw):
        calls["n"] += 1
        if calls["n"] == k:
            raise RuntimeError("injected")
        return orig(*a, **kw)

    monkeypatch.setattr(target, name, wrapper)


@pytest.mark.parametrize("mode", ["compile", "execute"])
def test_last_version_failure_records_built_and_escalates(app, client, login, audit_rows, monkeypatch, mode):
    p = f"SYN-M1-F-{mode}"
    second = _setup(app, client, login, monkeypatch, p, PATTERNS["P1"])
    _fail_kth(monkeypatch, *((casegraph_run, "compile_stage") if mode == "compile" else (Executor, "run_sync")), 2)
    body = second().json()
    assert [g["stage"] for g in body["built_graphs"]] == ["T2"]  # T3 (the last) failed
    assert body["graph_alert_rule_ids"] == ["RF-SPO2"] and body["built_graphs"][0]["escalation"] is True
    assert body["graph_id"] is None and body["screening"]["status"] == "unavailable"
    assert body["escalation_required"] is True
    assert body["graph_failure"] == {"error_type": "RuntimeError", "stage": "T3", "version": 3}
    row = _assess_row(audit_rows, body["assessment_id"])
    assert row["built_graphs"] == body["built_graphs"] and row["graph_failure"] == body["graph_failure"]
    assert row["graph_id"] is None and row["graph_error"] == "RuntimeError"
    assert row["graph_alert_rule_ids"] == ["RF-SPO2"] and row["screening_status"] == "unavailable"
    assert row["escalation_required"] is True


def test_middle_version_failure_stops_and_escalates(app, client, login, audit_rows, monkeypatch):
    p = "SYN-M1-mid"
    second = _setup(app, client, login, monkeypatch, p, PATTERNS["P3"])
    _fail_kth(monkeypatch, casegraph_run, "compile_stage", 2)
    st = app.state.casegraph.state
    body = second().json()
    assert [g["stage"] for g in body["built_graphs"]] == ["T2"]  # version 2 of 3 failed; the 3rd was never built
    assert st.latest_version(p) == 2 and body["graph_failure"]["stage"] == "T3"  # the 2nd planned version (T3@50)
    assert body["graph_id"] is None and body["escalation_required"] is True
    assert _assess_row(audit_rows, body["assessment_id"])["built_graphs"] == body["built_graphs"]


def test_single_version_audit_keys_unchanged(app, client, login, audit_rows):
    login("nurse1")
    from app.triage.fixtures import engine_cases
    ref = "SYN-S4-002"
    case = engine_cases()[ref]
    body = client.post(f"/api/triage/cases/{ref}/assess",
                       json={"as_of": max(f.available_at_time for f in case.facts).isoformat()}).json()
    row = _assess_row(audit_rows, body["assessment_id"])
    assert len(body["built_graphs"]) == 1
    only = body["built_graphs"][0]
    assert row["graph_id"] == body["graph_id"] == only["graph_id"] and row["graph_error"] is None
    assert row["graph_alert_rule_ids"] == only["alert_rule_ids"]
    assert row["screening_status"] == body["screening"]["status"] == only["screening_status"]
    assert row["built_graphs"] == body["built_graphs"] and row["graph_failure"] is None


def test_legacy_payload_without_built_graphs_loads(app, client, login):
    login("nurse1")
    from app.triage.fixtures import engine_cases
    case = engine_cases()["SYN-S4-002"]
    body = client.post("/api/triage/cases/SYN-S4-002/assess",
                       json={"as_of": max(f.available_at_time for f in case.facts).isoformat()}).json()
    for k in ("built_graphs", "graph_alert_rule_ids", "graph_failure"):
        body.pop(k)
    a = TriageAssessment.model_validate(json.loads(json.dumps(body)))
    assert a.built_graphs == [] and a.graph_alert_rule_ids == [] and a.graph_failure is None


def test_rerun_is_deterministic(app, client, login, monkeypatch):
    outs = []
    for n in ("a", "b"):
        body = _setup(app, client, login, monkeypatch, f"SYN-M1-det-{n}", PATTERNS["P5"])().json()
        outs.append([{k: v for k, v in g.items() if k not in ("graph_id", "version")} for g in body["built_graphs"]])
    assert outs[0] == outs[1]
