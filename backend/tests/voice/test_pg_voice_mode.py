"""V2A-A11 on PostgreSQL: voice_sessions.mode is immutable and the v2a columns exist. Run via `make test-pg`."""

import os

import pytest
from sqlalchemy import inspect, text
from sqlalchemy.exc import DBAPIError

from app.db import create_schema, make_engine
from app.voice.db import create_voice_schema

pytestmark = pytest.mark.pg


@pytest.mark.enable_socket
def test_voice_mode_immutable_pg():
    url = os.environ.get("TEST_PG_URL")
    if not url:
        pytest.skip("TEST_PG_URL not set (Docker PostgreSQL unavailable); run `make test-pg`")
    engine = make_engine(url)
    create_schema(engine)
    create_voice_schema(engine)
    create_voice_schema(engine)  # idempotent
    insp = inspect(engine)
    assert "mode" in {c["name"] for c in insp.get_columns("voice_sessions")}
    assert "held_json" in {c["name"] for c in insp.get_columns("voice_extractions")}
    with engine.begin() as conn:
        conn.execute(text(
            "INSERT INTO voice_sessions (session_id, patient_ref, data_class, created_at, created_by, status, mode) "
            "VALUES ('pgmode', 'SYN-PG', 'synthetic', '2026-01-01T00:00:00+00:00', 1, 'active', 'ambient') "
            "ON CONFLICT DO NOTHING"
        ))
    with pytest.raises(DBAPIError, match="only voice_sessions.status"):
        with engine.begin() as conn:
            conn.execute(text("UPDATE voice_sessions SET mode = 'guided' WHERE session_id = 'pgmode'"))
    with engine.begin() as conn:
        conn.execute(text("UPDATE voice_sessions SET status = 'active' WHERE session_id = 'pgmode'"))
    engine.dispose()
