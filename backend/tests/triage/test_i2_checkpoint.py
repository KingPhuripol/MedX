"""Slice i2 scope 7 (I2-A15) and C2 at the API: ``/assess`` runs the Case Graph; the nurse confirm / edit / reject
endpoints are the only path that resumes its Human Checkpoint (``human:nurse``).

Synthetic S4 author fixtures only; mock provider; offline. Research prototype — not for clinical use.
"""

from __future__ import annotations

import ast
import re
from datetime import timedelta
from pathlib import Path

import pytest

from app.triage import casegraph_run
from app.triage.fixtures import load_entries
from casegraph.data import RF_120, RULE_SET_LABELS, RULE_SET_SCOPES, ConfirmedEvidence
from casegraph.executor import PENDING_KEY
from casegraph.types import NodeType

from .helpers import api_as_of

REPO = Path(__file__).resolve().parents[3]
BY_REF = {e.case.case_ref: e for e in load_entries()}
RED_REF = "SYN-S4-002"  # RF-CHEST, RF-HR, RF-SBP
OVERCLAIM = re.compile(r"no red.?flags?|all clear|ไม่มี.*(สัญญาณอันตราย|red flag)", re.IGNORECASE)
STATUS = {"confirm": "confirmed", "edit": "edited", "reject": "rejected"}


def _assess(client, ref=RED_REF):
    entry = BY_REF[ref]
    resp = client.post(f"/api/triage/cases/{ref}/assess", json={"as_of": api_as_of(entry.case, entry.as_of).isoformat()})
    assert resp.status_code == 201, resp.text
    return resp.json()


def _body(action, a, ack=None):
    ack = [x["rule_id"] for x in a["alerts"]] if ack is None else ack
    if action == "confirm":
        return {"department_code": a["department"]["top3"][0]["code"], "acknowledged_alert_ids": ack}
    if action == "edit":
        return {"department_code": "MED", "reason": "synthetic edit reason", "acknowledged_alert_ids": ack}
    return {"reason": "synthetic reject reason", "acknowledged_alert_ids": ack}


def _graph(app, graph_id):
    return casegraph_run.load(app.state.casegraph, graph_id)


def _login(client, username):
    from ..conftest import PASSWORDS

    client.cookies.clear()
    assert client.post("/api/auth/login", json={"username": username, "password": PASSWORDS[username]}).status_code == 200


@pytest.mark.parametrize("action", ["confirm", "edit", "reject"])
def test_checkpoint_via_triage_endpoints(app, client, login, audit_rows, action):
    login("nurse1")
    a = _assess(client)
    graph = _graph(app, a["graph_id"])
    hc = graph.by_type(NodeType.HUMAN_CHECKPOINT)
    # /assess ran the graph: rf-1.1.0 Red-flag, nurse checkpoint pending, screening block returned
    assert (hc.provider, hc.status) == ("human:nurse", "pending_confirmation")
    assert graph.by_type(NodeType.RED_FLAG).model_version == RF_120
    s = a["screening"]
    assert (s["rule_set_version"], s["label"], s["scope"], s["n_declared"]) == (
        RF_120, RULE_SET_LABELS[RF_120], RULE_SET_SCOPES[RF_120], 17)
    assert s["n_evaluated"] + s["n_not_evaluated"] == 17 and s["summary"] == graph.red_flag_screening.summary()
    assert sorted(x["rule_id"] for x in hc.output[PENDING_KEY]["alerts"]["alerts"]) == sorted(
        x["rule_id"] for x in a["alerts"])  # graph and engine agree on this fresh-vitals case
    url = f"/api/triage/assessments/{a['assessment_id']}/{action}"
    # unacknowledged alerts -> 409; the checkpoint stays pending
    assert client.post(url, json=_body(action, a, ack=[])).status_code == 409
    # a non-nurse -> 403; the checkpoint stays pending
    _login(client, "physician1")
    assert client.post(url, json=_body(action, a)).status_code == 403
    assert client.get(f"/api/triage/assessments/{a['assessment_id']}").json()["graph_checkpoint_status"] == \
        "pending_confirmation"
    assert app.state.casegraph.state.evidence(graph.patient_ref) == []
    _login(client, "nurse1")
    before = len(audit_rows())
    resp = client.post(url, json=_body(action, a))
    assert resp.status_code == 200, resp.text
    assert resp.json()["graph_checkpoint_status"] == STATUS[action]
    after = _graph(app, a["graph_id"])
    hc2 = after.by_type(NodeType.HUMAN_CHECKPOINT)
    assert hc2.status == STATUS[action]
    assert hc2.confirmation["reviewer_role"] == "nurse" and hc2.confirmation["action"] == action
    appended = [e for e in app.state.casegraph.state.evidence(graph.patient_ref) if isinstance(e, ConfirmedEvidence)]
    if action == "reject":
        assert appended == []  # reject appends nothing
    else:
        (item,) = appended
        assert item.result.graph_id == a["graph_id"] and item.result.action == action
        assert item.available_at_time == item.result.confirmed_at >= graph.T
    review = [r for r in audit_rows()[before:] if r["action"] == f"triage.review.{action}"]
    assert review[0]["details"]["graph_checkpoint"]["graph_id"] == a["graph_id"]
    # a second review cannot resume the checkpoint again
    assert client.post(url, json=_body(action, a)).status_code == 409


def test_single_resume_path():
    """0 production code paths other than the nurse review endpoints call ``Executor.resume``."""
    callers: list[str] = []
    router_calls: list[str] = []
    for root in ("backend/app", "casegraph", "eval", "eval_i2", "data_factory", "scripts", "research"):
        for path in sorted((REPO / root).rglob("*.py")):
            if "tests" in path.parts:
                continue
            tree = ast.parse(path.read_text(encoding="utf-8"))
            for node in ast.walk(tree):
                if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute) and node.func.attr == "resume":
                    callers.append(str(path.relative_to(REPO)))
                    target = node.func.value
                    if getattr(target, "id", None) == "casegraph_run":
                        router_calls.append(str(path.relative_to(REPO)))
    # casegraph_run.resume -> Executor.resume (1 call) and router -> casegraph_run.resume (1 call, in _review)
    assert sorted(callers) == ["backend/app/triage/casegraph_run.py", "backend/app/triage/router.py"]
    assert router_calls == ["backend/app/triage/router.py"]
    tree = ast.parse((REPO / "backend/app/triage/router.py").read_text(encoding="utf-8"))
    review = next(n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == "_review")
    assert any(isinstance(n, ast.Attribute) and n.attr == "resume" for n in ast.walk(review))


def test_never_no_red_flags_api(client, login):
    """C2 at the API: no assess response or review view over the 40 S4 fixtures reads as an all-clear."""
    login("nurse1")
    statuses = set()
    for ref in BY_REF:
        a = _assess(client, ref)
        statuses.add(a["screening"]["status"])
        view = client.get(f"/api/triage/assessments/{a['assessment_id']}").text
        for text in (view, str(a)):
            assert not OVERCLAIM.search(text), ref
        s = a["screening"]
        if s["status"] == "evaluated" and s["n_fired"] == 0:
            assert s["summary"].startswith("0 of 17 declared rules fired")
        else:
            assert s["banner"] is not None or s["n_fired"] > 0
    assert statuses


def test_assess_graph_failure_fails_safe(client, login, monkeypatch, audit_rows):
    def boom(*args, **kwargs):
        raise RuntimeError("synthetic compile failure")

    monkeypatch.setattr(casegraph_run, "run_graph", boom)
    login("nurse1")
    a = _assess(client, "SYN-S4-029")  # no engine alert
    assert a["graph_id"] is None and a["escalation_required"] is True
    assert a["screening"]["status"] == "unavailable" and a["screening"]["banner"] == "RED-FLAG SCREENING NOT PERFORMED"
    row = [r for r in audit_rows() if r["action"] == "triage.assess"][-1]
    assert row["details"]["graph_error"] == "RuntimeError" and row["details"]["screening_status"] == "unavailable"


def test_confirmation_clock_never_before_T(app, client, login):
    login("nurse1")
    a = _assess(client)
    graph = _graph(app, a["graph_id"])
    early = graph.T - timedelta(days=30)
    late = graph.T + timedelta(hours=1)
    assert casegraph_run.confirmation_clock(graph, lambda: early)() == graph.T  # synthetic simulated timeline
    assert casegraph_run.confirmation_clock(graph, lambda: late)() == late
    real = graph.model_copy(update={"nodes": tuple(
        n.model_copy(update={"data_class": "hospital"}) if n.type is NodeType.HUMAN_CHECKPOINT else n
        for n in graph.nodes)})
    assert casegraph_run.confirmation_clock(real, lambda: early)() == early  # refused by resume_refusal
