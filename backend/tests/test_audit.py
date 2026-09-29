from dataclasses import replace

import httpx
import pytest
from fastapi.routing import APIRoute
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError

from app.gateway import build_provider

from .conftest import PASSWORDS

PASSWORD_SENTINEL = "SENTINEL-pw-7f3a9c"
INPUT_SENTINEL = "SENTINEL-input-51be02"
GATEWAY_DETAIL_KEYS = {
    "provider", "model_version", "contract_version", "data_class", "request_sha256", "status", "latency_ms",
}


def _all_text(rows) -> str:
    return "\n".join(repr(r) for r in rows)


def test_audit_login_events(client, audit_rows):
    before = len(audit_rows())
    attempts = [
        ({"username": "nurse1", "password": PASSWORDS["nurse1"]}, 200),
        ({"username": "nurse1", "password": PASSWORD_SENTINEL}, 401),
        ({"username": "ghost-user", "password": PASSWORD_SENTINEL}, 401),
        ({"username": "physician1", "password": PASSWORDS["physician1"]}, 200),
    ]
    n = 0
    for creds, expected in attempts:
        assert client.post("/api/auth/login", json=creds).status_code == expected
        n += 1
        if expected == 200:
            assert client.post("/api/auth/logout").status_code == 204
            n += 1
    rows = audit_rows()[before:]
    assert len(rows) == n
    for row in rows:
        assert row["ts_utc"].endswith("+00:00")
        assert row["action"] in {"auth.login", "auth.logout"} and row["outcome"]
        assert row["request_id"]
    known = [r for r in rows if r["action"] == "auth.login" and r["outcome"] == "success"]
    assert [(r["actor_id"] is not None, r["actor_role"]) for r in known] == [(True, "nurse"), (True, "physician")]
    wrong_pw = rows[2]
    assert (wrong_pw["outcome"], wrong_pw["actor_role"]) == ("failure", "nurse")
    unknown = rows[3]
    assert (unknown["outcome"], unknown["actor_id"], unknown["actor_role"]) == ("failure", None, None)
    assert PASSWORD_SENTINEL not in _all_text(rows)
    for username, pw in PASSWORDS.items():
        assert pw not in _all_text(rows)


def test_audit_role_home_denial(client, login, audit_rows):
    login("nurse1")
    before = len(audit_rows())
    assert client.get("/api/home/physician").status_code == 403
    rows = audit_rows()[before:]
    assert len(rows) == 1
    assert (rows[0]["action"], rows[0]["outcome"], rows[0]["actor_role"]) == ("home.access", "denied", "nurse")


def _failing(request):
    return httpx.Response(500)


CASES = {
    "ok": ("mock", None, "synthetic", "ok"),
    "policy": ("openai_compatible", True, "hospital", "rejected"),
    "disabled": ("openai_compatible", False, "synthetic", "rejected"),
    "error": ("openai_compatible", True, "synthetic", "error"),
}


@pytest.mark.parametrize("case", list(CASES))
def test_audit_gateway_events(app, settings, client, login, audit_rows, case):
    provider, enabled, data_class, status = CASES[case]
    if provider != "mock":
        s = replace(settings, external_enabled=enabled, external_base_url="http://external.invalid/v1")
        app.state.provider = build_provider(provider, s, transport=httpx.MockTransport(_failing))
    login("pharmacist1")
    before = len(audit_rows())
    payload = {"task": "echo", "inputs": {"free_text": INPUT_SENTINEL}, "data_class": data_class}
    resp = client.post("/api/gateway/invoke", json=payload)
    assert resp.json()["status"] == status
    rows = audit_rows()[before:]
    assert len(rows) == 1
    row = rows[0]
    assert row["action"] == "gateway.invoke" and row["outcome"] == status
    assert row["actor_role"] == "pharmacist"
    assert GATEWAY_DETAIL_KEYS <= set(row["details"])
    assert row["details"]["data_class"] == data_class
    assert row["details"]["request_sha256"] == resp.json()["request_sha256"]
    assert INPUT_SENTINEL not in _all_text(audit_rows())


def test_audit_append_only_sqlite(client, audit_rows, app):
    client.post("/api/auth/login", json={"username": "nobody", "password": "x"})
    assert audit_rows()
    engine = app.state.engine
    for stmt in ("UPDATE audit_events SET outcome = 'tampered'", "DELETE FROM audit_events"):
        with pytest.raises(DBAPIError, match="append-only"):
            with engine.begin() as conn:
                conn.execute(text(stmt))
    assert all(r["outcome"] != "tampered" for r in audit_rows())


def test_no_audit_mutation_routes(app):
    mutating = {"PUT", "PATCH", "DELETE"}
    for route in app.routes:
        if isinstance(route, APIRoute):
            assert not (route.methods & mutating), f"mutating route found: {route.path}"
            if "audit" in route.path:
                raise AssertionError(f"no audit routes expected in s0: {route.path}")
