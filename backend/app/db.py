"""Database engine and schema. One module creates the schema on SQLite and PostgreSQL,
including the append-only triggers on ``audit_events``."""

from __future__ import annotations

from pathlib import Path

from sqlalchemy import (
    Column,
    Engine,
    ForeignKey,
    Integer,
    MetaData,
    String,
    Table,
    Text,
    create_engine,
    text,
)
from sqlalchemy.engine import make_url

metadata = MetaData()

users = Table(
    "users",
    metadata,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("username", String(64), nullable=False, unique=True),
    Column("role", String(16), nullable=False),
    Column("password_hash", String(256), nullable=False),
)

sessions = Table(
    "sessions",
    metadata,
    Column("token_sha256", String(64), primary_key=True),
    Column("user_id", Integer, ForeignKey("users.id"), nullable=False),
    Column("created_at", Integer, nullable=False),
    Column("expires_at", Integer, nullable=False),
)

audit_events = Table(
    "audit_events",
    metadata,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("ts_utc", String(40), nullable=False),
    Column("actor_id", Integer, nullable=True),
    Column("actor_role", String(16), nullable=True),
    Column("action", String(64), nullable=False),
    Column("target", String(128), nullable=False),
    Column("outcome", String(32), nullable=False),
    Column("details_json", Text, nullable=False),
    Column("request_id", String(64), nullable=False),
)

# Slice s4: immutable triage assessments and single human reviews (append-only, like audit_events).
triage_assessments = Table(
    "triage_assessments",
    metadata,
    Column("assessment_id", String(32), primary_key=True),
    Column("case_ref", String(64), nullable=False, index=True),
    Column("as_of", String(40), nullable=False),
    Column("created_at", String(40), nullable=False),
    Column("created_by", Integer, nullable=False),
    Column("ruleset_version", String(32), nullable=False),
    Column("payload_json", Text, nullable=False),
)

triage_reviews = Table(
    "triage_reviews",
    metadata,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("assessment_id", String(32), ForeignKey("triage_assessments.assessment_id"), nullable=False, unique=True),
    Column("action", String(16), nullable=False),
    Column("final_department", String(16), nullable=True),
    Column("reviewer_id", Integer, nullable=False),
    Column("reviewer_role", String(16), nullable=False),
    Column("ts_utc", String(40), nullable=False),
    Column("acknowledged_alert_ids_json", Text, nullable=False),
    Column("reason", Text, nullable=True),
    Column("reason_sha256", String(64), nullable=True),
)

# Slice s6: immutable care assessments and single physician reviews (append-only).
care_assessments = Table(
    "care_assessments",
    metadata,
    Column("assessment_id", String(32), primary_key=True),
    Column("case_id", String(64), nullable=False, index=True),
    Column("decision_point", String(8), nullable=False),
    Column("as_of", String(40), nullable=False),
    Column("created_at", String(40), nullable=False),
    Column("created_by", Integer, nullable=False),
    Column("rules_version", String(32), nullable=False),
    Column("payload_json", Text, nullable=False),
)

care_reviews = Table(
    "care_reviews",
    metadata,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("assessment_id", String(32), ForeignKey("care_assessments.assessment_id"), nullable=False, unique=True),
    Column("action", String(16), nullable=False),
    Column("final_codes_json", Text, nullable=True),
    Column("reviewer_id", Integer, nullable=False),
    Column("reviewer_role", String(16), nullable=False),
    Column("ts_utc", String(40), nullable=False),
    Column("acknowledged_alert_ids_json", Text, nullable=False),
    Column("screening_acknowledged", Integer, nullable=False),
    Column("reason", Text, nullable=True),
    Column("reason_sha256", String(64), nullable=True),
)

# Presentation-safe synthetic demo runs. Runs and events are immutable; current task
# state is derived by folding events, so a presenter never needs reset/delete.
demo_runs = Table(
    "demo_runs",
    metadata,
    Column("run_id", String(36), primary_key=True),
    Column("journey_id", String(64), nullable=False),
    Column("created_at", String(40), nullable=False),
    Column("created_by", Integer, nullable=False),
    Column("created_by_role", String(16), nullable=False),
    Column("version", Integer, nullable=False),
)

demo_events = Table(
    "demo_events",
    metadata,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("event_id", String(36), nullable=False, unique=True),
    Column("run_id", String(36), ForeignKey("demo_runs.run_id"), nullable=False, index=True),
    Column("case_id", String(64), nullable=False),
    Column("task_id", String(64), nullable=True),
    Column("event_type", String(32), nullable=False),
    Column("actor_id", Integer, nullable=False),
    Column("actor_role", String(16), nullable=False),
    Column("ts_utc", String(40), nullable=False),
    Column("version", Integer, nullable=False),
    Column("payload_json", Text, nullable=False),
)

APPEND_ONLY_TRIAGE_TABLES = (
    "triage_assessments",
    "triage_reviews",
    "care_assessments",
    "care_reviews",
    "demo_runs",
    "demo_events",
)

_SQLITE_TRIGGERS = (
    """CREATE TRIGGER IF NOT EXISTS audit_events_no_update BEFORE UPDATE ON audit_events
       BEGIN SELECT RAISE(ABORT, 'audit_events is append-only'); END""",
    """CREATE TRIGGER IF NOT EXISTS audit_events_no_delete BEFORE DELETE ON audit_events
       BEGIN SELECT RAISE(ABORT, 'audit_events is append-only'); END""",
) + tuple(
    f"""CREATE TRIGGER IF NOT EXISTS {t}_no_{op.lower()} BEFORE {op} ON {t}
       BEGIN SELECT RAISE(ABORT, '{t} is append-only'); END"""
    for t in APPEND_ONLY_TRIAGE_TABLES
    for op in ("UPDATE", "DELETE")
)

_PG_TRIGGERS = (
    """CREATE OR REPLACE FUNCTION audit_events_append_only() RETURNS trigger AS $$
       BEGIN RAISE EXCEPTION 'audit_events is append-only'; END; $$ LANGUAGE plpgsql""",
    "DROP TRIGGER IF EXISTS audit_events_no_update_delete ON audit_events",
    """CREATE TRIGGER audit_events_no_update_delete BEFORE UPDATE OR DELETE ON audit_events
       FOR EACH ROW EXECUTE FUNCTION audit_events_append_only()""",
    "DROP TRIGGER IF EXISTS audit_events_no_truncate ON audit_events",
    """CREATE TRIGGER audit_events_no_truncate BEFORE TRUNCATE ON audit_events
       FOR EACH STATEMENT EXECUTE FUNCTION audit_events_append_only()""",
    """CREATE OR REPLACE FUNCTION triage_append_only() RETURNS trigger AS $$
       BEGIN RAISE EXCEPTION USING MESSAGE = TG_TABLE_NAME || ' is append-only'; END; $$ LANGUAGE plpgsql""",
) + tuple(
    stmt
    for t in APPEND_ONLY_TRIAGE_TABLES
    for stmt in (
        f"DROP TRIGGER IF EXISTS {t}_no_update_delete ON {t}",
        f"""CREATE TRIGGER {t}_no_update_delete BEFORE UPDATE OR DELETE ON {t}
       FOR EACH ROW EXECUTE FUNCTION triage_append_only()""",
        f"DROP TRIGGER IF EXISTS {t}_no_truncate ON {t}",
        f"""CREATE TRIGGER {t}_no_truncate BEFORE TRUNCATE ON {t}
       FOR EACH STATEMENT EXECUTE FUNCTION triage_append_only()""",
    )
)


def make_engine(database_url: str) -> Engine:
    url = make_url(database_url)
    if url.get_backend_name() == "sqlite":
        if url.database and url.database != ":memory:":
            Path(url.database).parent.mkdir(parents=True, exist_ok=True)
        return create_engine(url, connect_args={"check_same_thread": False})
    return create_engine(url, pool_pre_ping=True)


def create_schema(engine: Engine) -> None:
    """Idempotently create tables and append-only triggers for the engine's dialect."""
    metadata.create_all(engine)
    dialect = engine.dialect.name
    if dialect == "sqlite":
        statements = _SQLITE_TRIGGERS
    elif dialect == "postgresql":
        statements = _PG_TRIGGERS
    else:  # fail closed: never run without append-only protection
        raise RuntimeError(f"unsupported database dialect for audit triggers: {dialect}")
    with engine.begin() as conn:
        for stmt in statements:
            conn.execute(text(stmt))
