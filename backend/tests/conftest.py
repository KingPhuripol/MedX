from __future__ import annotations

import json
from collections.abc import Callable
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from app.config import Settings
from app.db import audit_events
from app.main import create_app
from app.seed import DEV_USERS, dev_password, seed_dev_users

REPO_ROOT = Path(__file__).resolve().parents[2]
ENV_KEYS = (
    "DATABASE_URL",
    "GATEWAY_PROVIDER",
    "GATEWAY_EXTERNAL_ENABLED",
    "EXTERNAL_BASE_URL",
    "EXTERNAL_API_KEY",
    "EXTERNAL_MODEL",
    "GATEWAY_TIMEOUT_S",
    "SESSION_TTL_MINUTES",
    "SESSION_COOKIE_SECURE",
    "TRIAGE_AS_OF_SKEW_S",
    "CASEGRAPH_DIR",
    "SEED_NURSE1_PASSWORD",
    "SEED_PHYSICIAN1_PASSWORD",
    "SEED_PHARMACIST1_PASSWORD",
)
PASSWORDS = {username: dev_password(env, default) for username, _, env, default in DEV_USERS}
ROLES = {username: role.value for username, role, _, _ in DEV_USERS}


@pytest.fixture(autouse=True)
def _clean_env(monkeypatch):
    """Tests never inherit a developer's .env or shell config."""
    for key in ENV_KEYS:
        monkeypatch.delenv(key, raising=False)


@pytest.fixture
def settings(tmp_path) -> Settings:
    return Settings(database_url=f"sqlite:///{tmp_path / 'test.db'}")


@pytest.fixture
def app(settings):
    application = create_app(settings)
    seed_dev_users(application.state.engine)
    return application


@pytest.fixture
def client(app):
    with TestClient(app) as c:
        yield c


@pytest.fixture
def login(client) -> Callable[[str], TestClient]:
    def _login(username: str) -> TestClient:
        resp = client.post("/api/auth/login", json={"username": username, "password": PASSWORDS[username]})
        assert resp.status_code == 200, resp.text
        return client

    return _login


@pytest.fixture
def audit_rows(app) -> Callable[[], list[dict]]:
    def _rows() -> list[dict]:
        with app.state.engine.connect() as conn:
            rows = conn.execute(select(audit_events).order_by(audit_events.c.id)).mappings().all()
        return [dict(r) | {"details": json.loads(r["details_json"])} for r in rows]

    return _rows
