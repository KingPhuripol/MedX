"""PostgreSQL checks. Run via `make test-pg`; skipped (non-gating) without Docker/TEST_PG_URL."""

import os
import shutil
import subprocess

import pytest
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError

from app.audit import write_audit
from app.db import create_schema, make_engine

from .conftest import REPO_ROOT

pytestmark = pytest.mark.pg


@pytest.mark.enable_socket
def test_audit_append_only_pg():
    url = os.environ.get("TEST_PG_URL")
    if not url:
        pytest.skip("TEST_PG_URL not set (Docker PostgreSQL unavailable); run `make test-pg`")
    engine = make_engine(url)
    create_schema(engine)
    create_schema(engine)  # idempotent
    write_audit(engine, action="test.pg", target="t", outcome="ok", request_id="pg")
    for stmt in ("UPDATE audit_events SET outcome = 'tampered'", "DELETE FROM audit_events", "TRUNCATE audit_events"):
        with pytest.raises(DBAPIError, match="append-only"):
            with engine.begin() as conn:
                conn.execute(text(stmt))


def test_compose_config_valid():
    if shutil.which("docker") is None:
        pytest.skip("docker CLI not installed")
    proc = subprocess.run(
        ["docker", "compose", "-f", str(REPO_ROOT / "docker-compose.yml"), "config", "-q"],
        capture_output=True,
        text=True,
        timeout=60,
    )
    if proc.returncode != 0 and "compose" in proc.stderr and "not a docker command" in proc.stderr:
        pytest.skip("docker compose plugin not installed")
    assert proc.returncode == 0, proc.stderr
