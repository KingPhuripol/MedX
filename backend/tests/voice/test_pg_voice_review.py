"""V2D-D7 on PostgreSQL: voice_reviews / voice_review_decisions reject UPDATE, DELETE and TRUNCATE.
Run via `make test-pg`; skipped when TEST_PG_URL is not set."""

import os

import pytest
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError

from app.db import create_schema, make_engine
from app.voice.db import create_voice_schema

pytestmark = pytest.mark.pg


@pytest.mark.enable_socket
@pytest.mark.parametrize("table", ["voice_reviews", "voice_review_decisions"])
def test_voice_review_append_only_pg(table):
    url = os.environ.get("TEST_PG_URL")
    if not url:
        pytest.skip("TEST_PG_URL not set (Docker PostgreSQL unavailable); run `make test-pg`")
    engine = make_engine(url)
    create_schema(engine)
    create_voice_schema(engine)
    create_voice_schema(engine)  # idempotent
    with engine.begin() as conn:
        conn.execute(text(
            "INSERT INTO voice_reviews (review_id, session_id, patient_ref, case_ref, reviewer_id, reviewer_role, "
            "submitted_at, consent_acknowledged_at, red_flag, attention_turn_ids_json, evidence_json, case_facts_json) "
            "VALUES ('pgrev', 'pgrevsess', 'SYN-PG', 'V-SYN-PG', 1, 'nurse', '2026-01-01T00:00:00+00:00', "
            "'2026-01-01T00:00:00+00:00', 0, '[]', '[]', '[]') ON CONFLICT DO NOTHING"))
        conn.execute(text(
            "INSERT INTO voice_review_decisions (review_id, session_id, field, action, final_state, actor_id, "
            "decided_at) VALUES ('pgrev', 'pgrevsess', 'severity', 'reject', 'none', 1, "
            "'2026-01-01T00:00:00+00:00') ON CONFLICT DO NOTHING"))
    for stmt in (f"UPDATE {table} SET session_id = 'x'", f"DELETE FROM {table}", f"TRUNCATE {table}"):
        with pytest.raises(DBAPIError, match="append-only"):
            with engine.begin() as conn:
                conn.execute(text(stmt))
    engine.dispose()
