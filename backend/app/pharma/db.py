"""Append-only pharma tables. Issue status is derived from decisions; nothing is ever updated.

Same trigger pattern as ``audit_events``. The pharma module only INSERTs into ``pharma_*``
tables (plus audit via ``write_audit``); it has no UPDATE/DELETE statements.
"""

from __future__ import annotations

from sqlalchemy import Column, Engine, Integer, MetaData, String, Table, Text, text

pharma_metadata = MetaData()

pharma_runs = Table(
    "pharma_runs",
    pharma_metadata,
    Column("run_id", String(64), primary_key=True),
    Column("ts_utc", String(40), nullable=False),
    Column("actor_id", Integer, nullable=True),
    Column("actor_role", String(16), nullable=True),
    Column("patient_ref", String(128), nullable=False),
    Column("snapshot_sha256", String(64), nullable=False),
    Column("mode", String(32), nullable=False),
    Column("status", String(32), nullable=False),
    Column("formulary_version", String(64), nullable=False),
    Column("rules_version", String(64), nullable=False),
    Column("run_json", Text, nullable=False),
)

pharma_issues = Table(
    "pharma_issues",
    pharma_metadata,
    Column("issue_id", String(96), primary_key=True),
    Column("run_id", String(64), nullable=False, index=True),
    Column("type", String(48), nullable=False),
    Column("rule_id", String(64), nullable=False),
    Column("severity_rank", Integer, nullable=False),
    Column("issue_json", Text, nullable=False),
)

pharma_issue_decisions = Table(
    "pharma_issue_decisions",
    pharma_metadata,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("issue_id", String(96), nullable=False, unique=True),  # one decision per issue
    Column("run_id", String(64), nullable=False),
    Column("rule_id", String(64), nullable=False),
    Column("decision", String(16), nullable=False),
    Column("reason", Text, nullable=True),
    Column("reason_sha256", String(64), nullable=True),
    Column("reviewer_id", Integer, nullable=False),
    Column("reviewer_role", String(16), nullable=False),
    Column("ts_utc", String(40), nullable=False),
)

PHARMA_TABLES = ("pharma_runs", "pharma_issues", "pharma_issue_decisions")


def _sqlite_triggers() -> list[str]:
    out = []
    for t in PHARMA_TABLES:
        for op in ("UPDATE", "DELETE"):
            out.append(
                f"CREATE TRIGGER IF NOT EXISTS {t}_no_{op.lower()} BEFORE {op} ON {t} "
                f"BEGIN SELECT RAISE(ABORT, '{t} is append-only'); END"
            )
    return out


def _pg_triggers() -> list[str]:
    out = [
        """CREATE OR REPLACE FUNCTION pharma_append_only() RETURNS trigger AS $$
           BEGIN RAISE EXCEPTION '% is append-only', TG_TABLE_NAME; END; $$ LANGUAGE plpgsql"""
    ]
    for t in PHARMA_TABLES:
        out += [
            f"DROP TRIGGER IF EXISTS {t}_no_update_delete ON {t}",
            f"""CREATE TRIGGER {t}_no_update_delete BEFORE UPDATE OR DELETE ON {t}
                FOR EACH ROW EXECUTE FUNCTION pharma_append_only()""",
            f"DROP TRIGGER IF EXISTS {t}_no_truncate ON {t}",
            f"""CREATE TRIGGER {t}_no_truncate BEFORE TRUNCATE ON {t}
                FOR EACH STATEMENT EXECUTE FUNCTION pharma_append_only()""",
        ]
    return out


def create_pharma_schema(engine: Engine) -> None:
    pharma_metadata.create_all(engine)
    dialect = engine.dialect.name
    if dialect == "sqlite":
        statements = _sqlite_triggers()
    elif dialect == "postgresql":
        statements = _pg_triggers()
    else:  # fail closed
        raise RuntimeError(f"unsupported database dialect for pharma triggers: {dialect}")
    with engine.begin() as conn:
        for stmt in statements:
            conn.execute(text(stmt))
