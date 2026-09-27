"""Voice append-only triggers on PostgreSQL. Run via `make test-pg`; skipped without Docker/TEST_PG_URL."""

import os

import pytest
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError

from app.db import create_schema, make_engine
from app.voice.db import create_voice_schema

pytestmark = pytest.mark.pg


@pytest.mark.enable_socket
def test_voice_append_only_pg():
    url = os.environ.get("TEST_PG_URL")
    if not url:
        pytest.skip("TEST_PG_URL not set (Docker PostgreSQL unavailable); run `make test-pg`")
    engine = make_engine(url)
    create_schema(engine)
    create_voice_schema(engine)
    create_voice_schema(engine)  # idempotent
    with engine.begin() as conn:
        conn.execute(text(
            "INSERT INTO voice_sessions (session_id, patient_ref, data_class, created_at, created_by, status) "
            "VALUES ('pgtest', 'SYN-PG', 'synthetic', '2026-01-01T00:00:00+00:00', 1, 'active') "
            "ON CONFLICT DO NOTHING"
        ))
        conn.execute(text(
            "INSERT INTO voice_turns (turn_id, session_id, seq, speaker, text, started_at, ended_at, nurse_attention) "
            "VALUES (md5(random()::text), 'pgtest', floor(random()*1e9)::int, 'patient', 'x', 'a', 'b', 0)"
        ))
    for stmt in (
        "UPDATE voice_turns SET text = 'tampered'", "DELETE FROM voice_turns", "TRUNCATE voice_turns",
        "UPDATE voice_facts SET state = 'KNOWN'", "DELETE FROM voice_facts", "TRUNCATE voice_facts",
        "UPDATE voice_sessions SET patient_ref = 'SYN-X'", "DELETE FROM voice_sessions",
    ):
        with pytest.raises(DBAPIError, match="append-only|cannot be deleted|only voice_sessions.status"):
            with engine.begin() as conn:
                conn.execute(text(stmt))
    with engine.begin() as conn:
        conn.execute(text("UPDATE voice_sessions SET status = 'active' WHERE session_id = 'pgtest'"))
