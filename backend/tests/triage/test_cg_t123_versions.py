"""Slice cg-t123 A8: ``GET /api/triage/cases/{case_ref}/graph-versions`` and the staged ``run_graph``.

Synthetic, offline, mock provider. Data only: no UI. Research prototype: not clinical performance.
"""

from __future__ import annotations

import pytest

from app.triage import casegraph_run
from app.triage.fixtures import load_entries
from casegraph.executor import Executor
from casegraph.providers import mock_gateways
from casegraph.staged import build_versions
from casegraph.stages import plan_stages
from casegraph.tests.fixtures import M
from casegraph.tests.staged_fixtures import FIXTURES_STAGED, GOLD_STAGES, T1

from .helpers import api_as_of

REF = "SYN-S4-002"
BY_REF = {e.case.case_ref: e for e in load_entries()}
ROLE = {"T1": "nurse", "T2": "physician", "T3": "pharmacist"}


def _seed(app, name):
    """Build the staged versions of a hand fixture into the app's Case Graph stores (the case_ref = patient_ref)."""
    p, items, horizon = FIXTURES_STAGED[name]()
    stores = app.state.casegraph
    ex = Executor(mock_gateways(), stores.outputs, stores.state)
    build_versions(ex, items, T1, horizon)
    return p, items, horizon


@pytest.mark.parametrize("name", ["F-CXR", "F-T3ONLY", "F-SAME", "F-PRE"])
def test_graph_versions_lists_the_stage_list(app, client, login, audit_rows, name):
    p, items, horizon = _seed(app, name)
    login("nurse1")
    resp = client.get(f"/api/triage/cases/{p}/graph-versions")
    assert resp.status_code == 200, resp.text
    body = resp.json()
    versions = body["versions"]
    assert [v["stage"] for v in versions] == GOLD_STAGES[name] == [x.stage for x in plan_stages(items, T1, horizon)]
    assert [v["version"] for v in versions] == list(range(1, len(versions) + 1))
    assert [v["parent_version"] for v in versions] == [None, *range(1, len(versions))]
    for v, plan in zip(versions, plan_stages(items, T1, horizon)):
        assert v["checkpoint_role"] == ROLE[v["stage"]] and v["checkpoint_status"] == "pending_confirmation"
        assert v["T"] == plan.T.isoformat() and v["trigger_refs"] == list(plan.trigger_item_ids)
        assert isinstance(v["escalation"], bool) and isinstance(v["alert_rule_ids"], list)
        assert {"id", "cached", "gateway_calls"} <= set(v["nodes"][0])
        assert v["totals"]["gateway_calls"] == sum(n["gateway_calls"] for n in v["nodes"])
    assert body["data_class"] == "synthetic"
    rows = [r for r in audit_rows() if r["action"] == "triage.graph_versions.read"]
    assert len(rows) == 1 and rows[0]["outcome"] == "success" and rows[0]["details"]["stages"] == GOLD_STAGES[name]


def test_graph_versions_later_versions_reuse_cached_nodes(app, client, login):
    p, _, _ = _seed(app, "F-CXR")
    login("pharmacist1")
    versions = client.get(f"/api/triage/cases/{p}/graph-versions").json()["versions"]
    t3 = versions[2]
    cached = {n["id"] for n in t3["nodes"] if n["cached"]}
    assert {"reader_text", "reader_vitals_labs", "reader_cxr"} <= cached
    assert all(n["gateway_calls"] == 0 for n in t3["nodes"] if n["cached"])


@pytest.mark.parametrize("user", ["nurse1", "physician1", "pharmacist1"])
def test_graph_versions_readable_by_each_stage_role(app, client, login, user):
    p, _, _ = _seed(app, "F-CXR")
    login(user)
    assert client.get(f"/api/triage/cases/{p}/graph-versions").status_code == 200


def test_graph_versions_unauthenticated_and_unknown(app, client, login, audit_rows):
    p, _, _ = _seed(app, "F-CXR")
    assert client.get(f"/api/triage/cases/{p}/graph-versions").status_code in (401, 403)  # no session
    login("nurse1")
    assert client.get("/api/triage/cases/NO-SUCH-CASE/graph-versions").status_code == 404
    reads = [r for r in audit_rows() if r["action"] == "triage.graph_versions.read"]
    assert [r["outcome"] for r in reads] == ["denied"]  # the unknown-case read is audited too


def test_triage_assess_stays_t1_nurse(app, client, login):
    login("nurse1")
    entry = BY_REF[REF]
    as_of = api_as_of(entry.case, entry.as_of)
    first = client.post(f"/api/triage/cases/{REF}/assess", json={"as_of": as_of.isoformat()})
    assert first.status_code == 201, first.text
    second = client.post(f"/api/triage/cases/{REF}/assess", json={"as_of": as_of.isoformat()})
    assert second.status_code == 201
    versions = client.get(f"/api/triage/cases/{REF}/graph-versions").json()["versions"]
    assert [(v["stage"], v["checkpoint_role"], v["trigger_refs"]) for v in versions] == [("T1", "nurse", [])] * 2
    assert [v["parent_version"] for v in versions] == [None, 1]
    graph = casegraph_run.load(app.state.casegraph, versions[0]["graph_id"])
    assert graph.stage == "T1" and graph.schema_version == "casegraph-export/0.4"
