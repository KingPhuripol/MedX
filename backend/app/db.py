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

_SQLITE_TRIGGERS = (
    """CREATE TRIGGER IF NOT EXISTS audit_events_no_update BEFORE UPDATE ON audit_events
       BEGIN SELECT RAISE(ABORT, 'audit_events is append-only'); END""",
    """CREATE TRIGGER IF NOT EXISTS audit_events_no_delete BEFORE DELETE ON audit_events
       BEGIN SELECT RAISE(ABORT, 'audit_events is append-only'); END""",
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
