"""Voice tables on the shared engine. Turns, facts and extraction records are append-only;
the only mutable column is ``voice_sessions.status``."""

from __future__ import annotations

from sqlalchemy import Column, Engine, Integer, MetaData, String, Table, Text, UniqueConstraint, text

voice_metadata = MetaData()

voice_sessions = Table(
    "voice_sessions",
    voice_metadata,
    Column("session_id", String(32), primary_key=True),
    Column("patient_ref", String(64), nullable=False),
    Column("data_class", String(16), nullable=False),
    Column("created_at", String(40), nullable=False),
    Column("created_by", Integer, nullable=False),
    Column("status", String(16), nullable=False),
)

voice_turns = Table(
    "voice_turns",
    voice_metadata,
    Column("turn_id", String(32), primary_key=True),
    Column("session_id", String(32), nullable=False, index=True),
    Column("seq", Integer, nullable=False),
    Column("speaker", String(16), nullable=False),
    Column("text", Text, nullable=False),
    Column("started_at", String(40), nullable=False),
    Column("ended_at", String(40), nullable=False),
    Column("field", String(32), nullable=True),  # agent turns: the field asked
    Column("utterance_id", String(64), nullable=True),  # agent turns: allowlist id
    Column("nurse_attention", Integer, nullable=False, default=0),
    UniqueConstraint("session_id", "seq", name="uq_voice_turns_session_seq"),
)

voice_facts = Table(
    "voice_facts",
    voice_metadata,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("fact_id", String(32), nullable=False, unique=True),
    Column("session_id", String(32), nullable=False, index=True),
    Column("field", String(32), nullable=False),
    Column("state", String(16), nullable=False),
    Column("value_json", Text, nullable=False),
    Column("value_text", Text, nullable=False),
    Column("span_turn_ids_json", Text, nullable=False),
    Column("event_time", String(40), nullable=False),
    Column("available_at_time", String(40), nullable=False),
    Column("extractor", String(64), nullable=False),
    Column("provider", String(64), nullable=False),
    Column("model_version", String(128), nullable=False),
    Column("request_sha256", String(64), nullable=False),
    Column("supersedes_fact_id", String(32), nullable=True),
)

# One row per extraction call; records the fail-safe outcome immutably.
voice_extractions = Table(
    "voice_extractions",
    voice_metadata,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("session_id", String(32), nullable=False, index=True),
    Column("turn_id", String(32), nullable=False),
    Column("status", String(16), nullable=False),  # ok | error
    Column("reason", String(64), nullable=True),
    Column("provider", String(64), nullable=False),
    Column("model_version", String(128), nullable=False),
    Column("request_sha256", String(64), nullable=False),
    Column("latency_ms", String(32), nullable=False),
)

APPEND_ONLY = ("voice_turns", "voice_facts", "voice_extractions")
_SESSION_FIXED_COLS = ("session_id", "patient_ref", "data_class", "created_at", "created_by")


def _sqlite_statements() -> list[str]:
    stmts = []
    for table in APPEND_ONLY:
        for op in ("UPDATE", "DELETE"):
            stmts.append(
                f"""CREATE TRIGGER IF NOT EXISTS {table}_no_{op.lower()} BEFORE {op} ON {table}
                    BEGIN SELECT RAISE(ABORT, '{table} is append-only'); END"""
            )
    stmts.append(
        """CREATE TRIGGER IF NOT EXISTS voice_sessions_no_delete BEFORE DELETE ON voice_sessions
           BEGIN SELECT RAISE(ABORT, 'voice_sessions rows cannot be deleted'); END"""
    )
    stmts.append(
        f"""CREATE TRIGGER IF NOT EXISTS voice_sessions_fixed_cols
            BEFORE UPDATE OF {", ".join(_SESSION_FIXED_COLS)} ON voice_sessions
            BEGIN SELECT RAISE(ABORT, 'only voice_sessions.status is mutable'); END"""
    )
    return stmts


def _pg_statements() -> list[str]:
    stmts = [
        """CREATE OR REPLACE FUNCTION voice_append_only() RETURNS trigger AS $$
           BEGIN RAISE EXCEPTION '% is append-only', TG_TABLE_NAME; END; $$ LANGUAGE plpgsql""",
    ]
    for table in APPEND_ONLY:
        stmts += [
            f"DROP TRIGGER IF EXISTS {table}_no_update_delete ON {table}",
            f"""CREATE TRIGGER {table}_no_update_delete BEFORE UPDATE OR DELETE ON {table}
                FOR EACH ROW EXECUTE FUNCTION voice_append_only()""",
            f"DROP TRIGGER IF EXISTS {table}_no_truncate ON {table}",
            f"""CREATE TRIGGER {table}_no_truncate BEFORE TRUNCATE ON {table}
                FOR EACH STATEMENT EXECUTE FUNCTION voice_append_only()""",
        ]
    changed = " OR ".join(f"NEW.{c} IS DISTINCT FROM OLD.{c}" for c in _SESSION_FIXED_COLS)
    stmts += [
        f"""CREATE OR REPLACE FUNCTION voice_sessions_guard() RETURNS trigger AS $$
            BEGIN
              IF TG_OP = 'DELETE' THEN RAISE EXCEPTION 'voice_sessions rows cannot be deleted'; END IF;
              IF {changed} THEN RAISE EXCEPTION 'only voice_sessions.status is mutable'; END IF;
              RETURN NEW;
            END; $$ LANGUAGE plpgsql""",
        "DROP TRIGGER IF EXISTS voice_sessions_guard ON voice_sessions",
        """CREATE TRIGGER voice_sessions_guard BEFORE UPDATE OR DELETE ON voice_sessions
           FOR EACH ROW EXECUTE FUNCTION voice_sessions_guard()""",
    ]
    return stmts


def create_voice_schema(engine: Engine) -> None:
    """Idempotently create the voice tables and their append-only triggers."""
    voice_metadata.create_all(engine)
    dialect = engine.dialect.name
    if dialect == "sqlite":
        statements = _sqlite_statements()
    elif dialect == "postgresql":
        statements = _pg_statements()
    else:  # fail closed
        raise RuntimeError(f"unsupported database dialect for voice triggers: {dialect}")
    with engine.begin() as conn:
        for stmt in statements:
            conn.execute(text(stmt))
