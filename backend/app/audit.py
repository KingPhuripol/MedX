"""Append-only audit writer. There is deliberately no update/delete function."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import Engine

from .db import audit_events


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds")


def write_audit(
    engine: Engine,
    *,
    action: str,
    target: str,
    outcome: str,
    request_id: str,
    actor_id: int | None = None,
    actor_role: str | None = None,
    details: dict[str, Any] | None = None,
) -> None:
    """Insert one audit row. Callers must pass references/hashes only, never raw inputs,
    passwords, or tokens."""
    with engine.begin() as conn:
        conn.execute(
            audit_events.insert().values(
                ts_utc=utc_now_iso(),
                actor_id=actor_id,
                actor_role=actor_role,
                action=action,
                target=target,
                outcome=outcome,
                details_json=json.dumps(details or {}, sort_keys=True),
                request_id=request_id,
            )
        )
