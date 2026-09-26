"""S5 API tests: roles, decisions, audit, append-only tables, and no order mutation (A10, A11)."""

import ast
import hashlib
import json
import re

import pytest
from sqlalchemy import func, select, text
from sqlalchemy.exc import DBAPIError

from app.pharma.db import PHARMA_TABLES, pharma_issue_decisions
from app.pharma.models import ConflictingSource, DismissBody, Issue, MedEntry, MedSnapshot, MedSource

from .conftest import REPO_ROOT

PHARMA_DIR = REPO_ROOT / "backend" / "app" / "pharma"
REASON_SENTINEL = "SENTINEL-reason-5c1e9a synthetic"
ORDER_FIELD = re.compile(r"order_(edit|change|replacement|update)|replacement|new_dose|edited|suggested_(dose|order)|substitute_with")


def _reconcile(client, ref="demo-01", mode="rules_plus_model"):
    resp = client.post("/api/pharma/reconcile", json={"fixture_ref": ref, "mode": mode})
    assert resp.status_code == 200, resp.text
    return resp.json()


def _inventory(app) -> set[tuple[str, str]]:
    # FastAPI wraps included routers, so read the generated OpenAPI paths (every API route).
    return {(m.upper(), path) for path, ops in app.openapi()["paths"].items() for m in ops}


def test_pharma_route_inventory(app):
    inventory = _inventory(app)
    pharma = {(m, p) for m, p in inventory if p.startswith("/api/pharma")}
    assert pharma == {
        ("GET", "/api/pharma/fixtures"),
        ("POST", "/api/pharma/reconcile"),
        ("GET", "/api/pharma/runs/{run_id}"),
        ("POST", "/api/pharma/issues/{issue_id}/confirm"),
        ("POST", "/api/pharma/issues/{issue_id}/dismiss"),
    }
    assert not [p for _, p in inventory if "order" in p.lower()]
    assert not [(m, p) for m, p in inventory if m in {"PUT", "PATCH", "DELETE"}]


def test_no_order_mutation_static():
    mutation = re.compile(r"\bUPDATE\s+\w+\s+SET\b|\bDELETE\s+FROM\b|\bTRUNCATE\s+(?:TABLE\s+)?(?!ON\b)\w+|\bINSERT\s+INTO\b", re.IGNORECASE)
    allowed_tables = set(PHARMA_TABLES)
    for path in PHARMA_DIR.rglob("*.py"):
        src = path.read_text(encoding="utf-8")
        assert not mutation.search(src), f"{path}: raw SQL mutation"
        tree = ast.parse(src)
        for node in ast.walk(tree):
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute):
                attr = node.func.attr
                assert attr not in {"update", "delete"} or not isinstance(node.func.value, ast.Name) or (
                    node.func.value.id not in {"pharma_runs", "pharma_issues", "pharma_issue_decisions", "audit_events"}
                ), f"{path}: {attr}() on a table"
                if attr == "insert" and isinstance(node.func.value, ast.Name):
                    table = node.func.value.id
                    assert table in allowed_tables or table == "audit_events", f"{path}: insert into {table}"
    # audit is written only through the shared append-only writer
    assert "audit_events" not in (PHARMA_DIR / "router.py").read_text(encoding="utf-8")


def test_issue_model_has_no_order_fields():
    for model in (Issue, ConflictingSource, DismissBody, MedSnapshot, MedSource, MedEntry):
        for name in model.model_fields:
            assert not ORDER_FIELD.search(name), f"{model.__name__}.{name}"
    cols = [c.name for c in pharma_issue_decisions.columns]
    assert not [c for c in cols if ORDER_FIELD.search(c) or "dose" in c or "order" in c]


def test_snapshot_immutable(client, login):
    login("pharmacist1")
    fixture_file = PHARMA_DIR / "fixtures" / "demo.json"
    before_file = hashlib.sha256(fixture_file.read_bytes()).hexdigest()
    snap = json.loads(fixture_file.read_text(encoding="utf-8"))["cases"][0]["snapshot"]
    raw = json.dumps(snap, sort_keys=True, ensure_ascii=False)
    resp = client.post("/api/pharma/reconcile", json={"snapshot": snap})
    assert resp.status_code == 200
    run = resp.json()
    first_sha = run["snapshot_sha256"]
    issues = run["issues"]
    assert client.post(f"/api/pharma/issues/{issues[0]['issue_id']}/confirm").status_code == 200
    assert client.post(f"/api/pharma/issues/{issues[1]['issue_id']}/dismiss", json={"reason": "synthetic"}).status_code == 200
    again = client.post("/api/pharma/reconcile", json={"snapshot": snap}).json()
    assert again["snapshot_sha256"] == first_sha
    assert json.dumps(snap, sort_keys=True, ensure_ascii=False) == raw
    assert hashlib.sha256(fixture_file.read_bytes()).hexdigest() == before_file
    stored = client.get(f"/api/pharma/runs/{run['run_id']}").json()
    assert stored["snapshot_sha256"] == first_sha


@pytest.mark.parametrize("username", ["nurse1", "physician1"])
def test_decision_roles(client, login, username):
    login("pharmacist1")
    issue_id = _reconcile(client)["issues"][0]["issue_id"]
    client.post("/api/auth/logout")
    for method, path, body in (
        ("post", f"/api/pharma/issues/{issue_id}/confirm", None),
        ("post", f"/api/pharma/issues/{issue_id}/dismiss", {"reason": "x"}),
        ("post", "/api/pharma/reconcile", {"fixture_ref": "demo-01"}),
        ("get", "/api/pharma/fixtures", None),
    ):
        assert getattr(client, method)(path, **({"json": body} if body else {})).status_code == 401
    login(username)
    assert client.post(f"/api/pharma/issues/{issue_id}/confirm").status_code == 403
    assert client.post(f"/api/pharma/issues/{issue_id}/dismiss", json={"reason": "x"}).status_code == 403
    assert client.post("/api/pharma/reconcile", json={"fixture_ref": "demo-01"}).status_code == 403
    assert client.get("/api/pharma/fixtures").status_code == 403


def _decision_rows(app):
    with app.state.engine.connect() as conn:
        return conn.execute(select(pharma_issue_decisions)).mappings().all()


MISSING_FIELD_SNAPSHOT = {
    "patient_ref": "t-api-mf",
    "as_of": "2026-06-10T10:00:00+07:00",
    "data_class": "synthetic",
    "sources": [
        {"source_type": st, "evidence_ref": f"t-api-mf/{st}/1", "available_at_time": "2026-06-10T09:00:00+07:00",
         "provenance": "synthetic: unit test", "version": "1", "entries": entries}
        for st, entries in (
            ("home_list", ["Metformin 500 mg bid", "Amlodipine 5 mg daily", "Simvastatin 40 mg daily"]),
            ("new_order", ["Metformin bid", "Amlodipine 5 mg"]),
        )
    ],
    "allergies": [],
}


@pytest.mark.parametrize("kind", ["demo", "missing_field"])
def test_decision_audit(app, client, login, audit_rows, kind):
    login("pharmacist1")
    if kind == "missing_field":
        resp = client.post("/api/pharma/reconcile", json={"snapshot": MISSING_FIELD_SNAPSHOT})
        assert resp.status_code == 200, resp.text
        run = resp.json()
        # confirm one missing_field issue, dismiss the other; the omission stays open
        assert [i["type"] for i in run["issues"]] == ["missing_field", "missing_field", "omission"]
        assert {i["field"] for i in run["issues"][:2]} == {"dose", "frequency"}
    else:
        run = _reconcile(client)
    rec_audit = [r for r in audit_rows() if r["action"] == "pharma.reconcile"][-1]
    assert set(rec_audit["details"]) == {
        "run_id", "snapshot_sha256", "formulary_version", "rules_version", "mode", "issue_count", "notice_count",
        "unchecked_comparison_count",
    }
    for issue, action, body in (
        (run["issues"][0], "confirm", None),
        (run["issues"][1], "dismiss", {"reason": REASON_SENTINEL}),
    ):
        before_audit, before_rows = len(audit_rows()), len(_decision_rows(app))
        kw = {"json": body} if body else {}
        resp = client.post(f"/api/pharma/issues/{issue['issue_id']}/{action}", **kw)
        assert resp.status_code == 200
        new_audit = audit_rows()[before_audit:]
        assert len(new_audit) == 1 and len(_decision_rows(app)) == before_rows + 1
        row = new_audit[0]
        assert row["action"] == f"pharma.issue.{action}" and row["actor_role"] == "pharmacist"
        d = row["details"]
        assert d["reviewer_role"] == "pharmacist" and d["reviewer_id"] == row["actor_id"]
        assert d["ts_utc"].endswith("+00:00")
        assert (d["run_id"], d["issue_id"], d["rule_id"]) == (run["run_id"], issue["issue_id"], issue["rule_id"])
        if body:
            assert d["reason_sha256"] == hashlib.sha256(REASON_SENTINEL.encode()).hexdigest()
    all_audit = "\n".join(repr(r) for r in audit_rows())
    assert REASON_SENTINEL not in all_audit
    # no raw snapshot text in audit
    assert "Simvastatin 40 mg" not in all_audit
    statuses = {i["issue_id"]: i["status"] for i in client.get(f"/api/pharma/runs/{run['run_id']}").json()["issues"]}
    assert statuses[run["issues"][0]["issue_id"]] == "confirmed"
    assert statuses[run["issues"][1]["issue_id"]] == "dismissed"
    assert statuses[run["issues"][2]["issue_id"]] == "open"


def test_dismiss_requires_reason(client, login):
    login("pharmacist1")
    issue_id = _reconcile(client)["issues"][0]["issue_id"]
    for body in ({}, {"reason": ""}, {"reason": "   "}, None):
        kw = {"json": body} if body is not None else {}
        assert client.post(f"/api/pharma/issues/{issue_id}/dismiss", **kw).status_code == 422
    assert client.get(f"/api/pharma/runs/{issue_id.rsplit('-', 1)[0]}").json()["issues"][0]["status"] == "open"


def test_decision_once(client, login):
    login("pharmacist1")
    issues = _reconcile(client)["issues"]
    a, b = issues[0]["issue_id"], issues[1]["issue_id"]
    assert client.post(f"/api/pharma/issues/{a}/confirm").status_code == 200
    assert client.post(f"/api/pharma/issues/{a}/confirm").status_code == 409
    assert client.post(f"/api/pharma/issues/{a}/dismiss", json={"reason": "late"}).status_code == 409
    assert client.post(f"/api/pharma/issues/{b}/dismiss", json={"reason": "synthetic"}).status_code == 200
    assert client.post(f"/api/pharma/issues/{b}/confirm").status_code == 409
    assert client.post("/api/pharma/issues/nope/confirm").status_code == 404


def test_pharma_tables_append_only(app, client, login):
    login("pharmacist1")
    run = _reconcile(client)
    client.post(f"/api/pharma/issues/{run['issues'][0]['issue_id']}/confirm")
    engine = app.state.engine
    for table in PHARMA_TABLES:
        with engine.connect() as conn:
            assert conn.execute(select(func.count()).select_from(text(table))).scalar() > 0
        for stmt in (f"UPDATE {table} SET run_id = 'tampered'", f"DELETE FROM {table}"):
            with pytest.raises(DBAPIError, match="append-only"):
                with engine.begin() as conn:
                    conn.execute(text(stmt))


def test_reconcile_body_validation(client, login):
    login("pharmacist1")
    assert client.post("/api/pharma/reconcile", json={}).status_code == 422
    assert client.post("/api/pharma/reconcile", json={"fixture_ref": "nope"}).status_code == 404
    snap = json.loads((PHARMA_DIR / "fixtures" / "demo.json").read_text(encoding="utf-8"))["cases"][0]["snapshot"]
    no_class = {k: v for k, v in snap.items() if k != "data_class"}
    assert client.post("/api/pharma/reconcile", json={"snapshot": no_class}).status_code == 422
    fixtures = client.get("/api/pharma/fixtures").json()
    assert fixtures["data_class"] == "synthetic" and len(fixtures["fixtures"]) >= 33
    rules_only = _reconcile(client, mode="rules_only")
    assert {i["phrasing"]["source"] for i in rules_only["issues"]} == {"template"}
