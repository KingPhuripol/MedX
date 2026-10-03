"""Slice cg-t123 round 5 (backend): ``run_graph`` builds every pending stage; a corrupt stored run is an audited,
explicit integrity error. Synthetic, offline, mock provider. Research prototype: not clinical performance."""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from app.deps import CurrentUser
from app.roles import Role
from app.triage import casegraph_run
from casegraph.stages import plan_stages
from casegraph.tests.fixtures import M, labs
from casegraph.tests.staged_fixtures import T1, base, order


def _items(p, spec):
    out = list(base(p))
    for kind, iid, minutes in spec:
        t = T1 + minutes * M
        out.append(labs(p, iid, t, t) if kind == "lab" else order(p, iid, t))
    return out


def _run(app, monkeypatch, p, items, as_of):
    monkeypatch.setattr(casegraph_run, "evidence_from_case", lambda case: items)
    user = CurrentUser(id=1, username="nurse1", role=Role.NURSE)
    return casegraph_run.run_graph(app.state.casegraph, SimpleNamespace(case_ref=p), as_of, app.state.engine,
                                   app.state.provider, user, "req-r5")


def _stored(app, p):
    st = app.state.casegraph.state
    out = []
    for v in range(1, (st.latest_version(p) or 0) + 1):
        spec, _ = st.load_graph(casegraph_run.graph_id_for(p, v))
        out.append((spec.stage, tuple(spec.trigger_refs)))
    return out


@pytest.mark.parametrize("name,spec,stages", [
    ("lab-then-order", [("lab", "lab1", 40), ("order", "o1", 70)], ["T1", "T2", "T3"]),
    ("order-then-lab", [("order", "o1", 30), ("lab", "lab1", 40)], ["T1", "T3", "T2"]),
])
def test_run_graph_builds_every_pending_stage(app, monkeypatch, name, spec, stages):
    p = f"SYN-R5-{name}"
    items = _items(p, spec)
    _run(app, monkeypatch, p, items, T1)  # the parent: T1
    last = _run(app, monkeypatch, p, items, T1 + 80 * M)
    planned = plan_stages(items, T1, T1 + 80 * M)
    assert [s for s, _ in _stored(app, p)] == stages == [x.stage for x in planned]
    assert [t for _, t in _stored(app, p)][1:] == [x.trigger_item_ids for x in planned][1:]
    assert last.stage == stages[-1] and last.version == len(stages)
    assert last.T == T1 + 80 * M  # the final version is computed at as_of


def test_run_graph_without_trigger_inherits_parent_stage(app, monkeypatch):
    p = "SYN-R5-inherit"
    items = _items(p, [("order", "o1", 30)])
    _run(app, monkeypatch, p, items, T1 + 40 * M)  # first call: T1 only (no parent)
    _run(app, monkeypatch, p, items, T1 + 50 * M)  # no new trigger: inherits
    assert [s for s, _ in _stored(app, p)] == ["T1", "T1"]


def test_graph_versions_corrupt_stored_run_is_audited_integrity_error(app, client, login, audit_rows, monkeypatch):
    p = "SYN-R5-corrupt"
    items = _items(p, [("lab", "lab1", 40)])
    _run(app, monkeypatch, p, items, T1)
    st = app.state.casegraph.state
    gid = casegraph_run.graph_id_for(p, 1)
    run = st.load_run(gid)
    assert run is not None
    st.save_run(gid, run.replace('"output_sha256": "', '"output_sha256": "0', 1))
    login("nurse1")
    resp = client.get(f"/api/triage/cases/{p}/graph-versions")
    assert resp.status_code == 500 and resp.json()["detail"] == "stored_graph_integrity"
    rows = [r for r in audit_rows() if r["action"] == "triage.graph_versions.read"]
    assert [r["outcome"] for r in rows] == ["failure"]
    assert rows[0]["details"]["reason"] == "stored_graph_integrity"
