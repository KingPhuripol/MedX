"""Slice d1: PUBLIC_DEMO mode (mock only, one-click role login, signed stateless sessions)."""

from __future__ import annotations

import threading

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select

from app.config import PUBLIC_DEMO_DATABASE_URL, Settings
from app.db import audit_events, make_engine, users
from app.demo import bootstrap, sign_session, verify_session
from app.deps import SESSION_COOKIE
from app.gateway.adapters.mock import MockProvider
from app.main import create_app
from app.roles import Role

SECRET = "s" * 40
ROLES = ["nurse", "physician", "pharmacist"]
USERNAME = {"nurse": "nurse1", "physician": "physician1", "pharmacist": "pharmacist1"}


def demo_settings(tmp_path, name: str = "demo.db", secret: str = SECRET) -> Settings:
    return Settings(database_url=f"sqlite:///{tmp_path / name}", public_demo=True, session_secret=secret)


@pytest.fixture
def demo_client(tmp_path):
    with TestClient(create_app(demo_settings(tmp_path))) as c:
        yield c


def _login(c: TestClient, role: str) -> str:
    resp = c.post("/api/auth/demo-login", json={"role": role})
    assert resp.status_code == 200, resp.text
    return resp.cookies[SESSION_COOKIE]


def test_demo_login_absent_when_disabled(client):
    assert client.post("/api/auth/demo-login", json={"role": "nurse"}).status_code == 404


@pytest.mark.parametrize(
    "env",
    [
        {"GATEWAY_PROVIDER": "openai_compatible"},
        {"GATEWAY_EXTERNAL_ENABLED": "1"},
        {"EXTERNAL_BASE_URL": "https://example.invalid/v1"},
        {"EXTERNAL_API_KEY": "sk-test"},
        {"SESSION_SECRET": "too-short"},
        {"SESSION_SECRET": ""},
    ],
    ids=["provider", "external_enabled", "base_url", "api_key", "short_secret", "no_secret"],
)
def test_public_demo_refuses_unsafe_config(monkeypatch, env):
    monkeypatch.setenv("PUBLIC_DEMO", "1")
    monkeypatch.setenv("SESSION_SECRET", SECRET)
    for key, value in env.items():
        monkeypatch.setenv(key, value)
    with pytest.raises(ValueError):
        Settings.from_env()


def test_public_demo_refusal_also_applies_to_direct_settings():
    with pytest.raises(ValueError):
        Settings(public_demo=True, session_secret=SECRET, gateway_provider="openai_compatible")


def test_public_demo_env_defaults(monkeypatch):
    monkeypatch.setenv("PUBLIC_DEMO", "1")
    monkeypatch.setenv("SESSION_SECRET", SECRET)
    s = Settings.from_env()
    assert s.database_url == PUBLIC_DEMO_DATABASE_URL == "sqlite:////tmp/medx-demo.sqlite3"
    assert s.gateway_provider == "mock" and not s.cookie_secure
    assert SECRET not in repr(s)
    monkeypatch.setenv("VERCEL", "1")
    assert Settings.from_env().cookie_secure


def test_off_by_default():
    s = Settings.from_env()
    assert not s.public_demo and s.database_url.endswith("backend/dev.db")


def test_cold_start_seeds_and_uses_mock(demo_client):
    app = demo_client.app
    assert isinstance(app.state.provider, MockProvider)
    with app.state.engine.connect() as conn:
        assert conn.execute(select(func.count()).select_from(users)).scalar() == 3


@pytest.mark.parametrize("role", ROLES)
def test_demo_login_each_role_and_rbac(demo_client, role):
    _login(demo_client, role)
    set_cookie = demo_client.post("/api/auth/demo-login", json={"role": role}).headers["set-cookie"].lower()
    assert "httponly" in set_cookie and "samesite=lax" in set_cookie
    me = demo_client.get("/api/me").json()["user"]
    assert me["username"] == USERNAME[role] and me["role"] == role and me["home"] == f"/{role}"
    for other in ROLES:
        assert demo_client.get(f"/api/home/{other}").status_code == (200 if other == role else 403)


def test_nurse_denied_physician_and_pharmacist_apis(demo_client):
    _login(demo_client, "nurse")
    assert demo_client.get("/api/care/cases").status_code == 403
    assert demo_client.get("/api/pharma/fixtures").status_code == 403
    assert demo_client.get("/api/home/physician").status_code == 403


def test_demo_login_rejects_unknown_role(demo_client):
    assert demo_client.post("/api/auth/demo-login", json={"role": "admin"}).status_code == 422


def test_password_login_disabled_in_demo(demo_client):
    resp = demo_client.post("/api/auth/login", json={"username": "nurse1", "password": "nurse1-dev-only"})
    assert resp.status_code == 404


def test_demo_login_is_audited(demo_client):
    _login(demo_client, "physician")
    with demo_client.app.state.engine.connect() as conn:
        rows = conn.execute(select(audit_events).where(audit_events.c.action == "auth.demo_login")).mappings().all()
    assert [(r["outcome"], r["actor_role"]) for r in rows] == [("success", "physician")]


def test_signed_session_survives_instance_switch(tmp_path):
    with TestClient(create_app(demo_settings(tmp_path, "a.db"))) as a:
        token = _login(a, "physician")
    # A different serverless instance: fresh /tmp database, same SESSION_SECRET.
    with TestClient(create_app(demo_settings(tmp_path, "b.db"))) as b:
        b.cookies.set(SESSION_COOKIE, token)
        assert b.get("/api/me").json()["user"]["username"] == "physician1"
        assert b.get("/api/home/nurse").status_code == 403
    # Same token, rotated secret: treated as no session.
    with TestClient(create_app(demo_settings(tmp_path, "c.db", secret="r" * 40))) as c:
        c.cookies.set(SESSION_COOKIE, token)
        assert c.get("/api/me").status_code == 401


@pytest.mark.parametrize(
    "token",
    [
        "garbage",
        "d1.not-base64!.sig",
        "d1..",
        sign_session(SECRET, "nurse1", Role.NURSE, ttl_s=-1),  # expired
        sign_session("x" * 40, "nurse1", Role.NURSE, ttl_s=600),  # wrong secret
        sign_session(SECRET, "ghost", Role.NURSE, ttl_s=600),  # user not in this instance
        sign_session(SECRET, "nurse1", Role.PHYSICIAN, ttl_s=600),  # role does not match the user
    ],
    ids=["garbage", "bad_b64", "empty_parts", "expired", "wrong_secret", "unknown_user", "role_mismatch"],
)
def test_unknown_or_invalid_session_is_401_not_crash(demo_client, token):
    demo_client.cookies.set(SESSION_COOKIE, token)
    assert demo_client.get("/api/me").status_code == 401
    assert demo_client.get("/api/home/nurse").status_code == 401
    assert demo_client.get("/api/care/cases").status_code == 401


def test_tampered_payload_rejected():
    token = sign_session(SECRET, "nurse1", Role.NURSE, ttl_s=600)
    version, body, sig = token.split(".")
    forged = sign_session(SECRET, "physician1", Role.PHYSICIAN, ttl_s=600).split(".")[1]
    assert verify_session(SECRET, token) == ("nurse1", Role.NURSE)
    assert verify_session(SECRET, f"{version}.{forged}.{sig}") is None


def test_db_session_token_not_accepted_in_demo(demo_client):
    demo_client.cookies.set(SESSION_COOKIE, "opaque-db-style-token")
    assert demo_client.get("/api/me").status_code == 401


def test_logout_clears_cookie(demo_client):
    _login(demo_client, "nurse")
    assert demo_client.post("/api/auth/logout").status_code == 204
    assert demo_client.get("/api/me").status_code == 401


def test_concurrent_cold_starts_same_file(tmp_path):
    url = f"sqlite:///{tmp_path / 'shared.db'}"
    errors: list[BaseException] = []

    def start() -> None:
        try:
            bootstrap(make_engine(url))
        except BaseException as exc:  # noqa: BLE001 - collected and asserted below
            errors.append(exc)

    threads = [threading.Thread(target=start) for _ in range(6)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert errors == []
    with make_engine(url).connect() as conn:
        assert conn.execute(select(func.count()).select_from(users)).scalar() == 3
