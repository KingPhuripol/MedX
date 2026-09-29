"""PostgreSQL append-only check for triage tables. Run via `make test-pg`; skipped otherwise."""

import os
import uuid

import pytest
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError

from app.db import create_schema, make_engine

pytestmark = pytest.mark.pg


@pytest.mark.enable_socket
def test_triage_tables_append_only_pg():
    url = os.environ.get("TEST_PG_URL")
    if not url:
        pytest.skip("TEST_PG_URL not set (Docker PostgreSQL unavailable); run `make test-pg`")
    engine = make_engine(url)
    create_schema(engine)
    create_schema(engine)  # idempotent
    aid = uuid.uuid4().hex
    with engine.begin() as conn:  # rows must exist: row-level triggers do not fire on empty tables
        conn.execute(text(
            "INSERT INTO triage_assessments (assessment_id, case_ref, as_of, created_at, created_by, "
            "ruleset_version, payload_json) VALUES (:aid, 'PG', 't', 't', 1, 'rf', '{}')"
        ), {"aid": aid})
        conn.execute(text(
            "INSERT INTO triage_reviews (assessment_id, action, reviewer_id, reviewer_role, ts_utc, "
            "acknowledged_alert_ids_json) VALUES (:aid, 'reject', 1, 'nurse', 't', '[]')"
        ), {"aid": aid})
    for table in ("triage_assessments", "triage_reviews"):
        for stmt in (f"UPDATE {table} SET assessment_id = assessment_id", f"DELETE FROM {table}", f"TRUNCATE {table} CASCADE"):
            with pytest.raises(DBAPIError, match="append-only"):
                with engine.begin() as conn:
                    conn.execute(text(stmt))
