"""SQLite persistence for journeys, recommendations, reviews and audit events.

`PRODUCT_SPEC.md` §Non-functional requirements: "Immutable audit event sequence;
correction is a new event." `SAFETY_SPEC.md` §Incident response: "Do not delete audit
evidence to make the failure disappear."

Those are properties of the store, not of the code that happens to call it, so they are
enforced by the database. Every table carries triggers that abort on UPDATE and DELETE.
Code that tries to rewrite history fails loudly instead of succeeding quietly — including
code written later by someone who never read this docstring.

Uses `sqlite3` from the standard library: no new dependency, and the harness keeps
running with nothing installed.
"""

from __future__ import annotations

import json
import sqlite3
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

from shared.contracts.journey import JourneyEvent, PatientJourney

SCHEMA_VERSION = "1.0.0"


class AppendOnlyViolation(RuntimeError):
    """An attempt to modify or remove a record that may only ever be appended."""


#: Tables that are append-only. The triggers below are the enforcement, not a convention.
_APPEND_ONLY_TABLES = ("journeys", "journey_events", "recommendations", "reviews", "audit_events")

_SCHEMA = """
CREATE TABLE IF NOT EXISTS journeys (
    journey_id          TEXT PRIMARY KEY,
    patient_id          TEXT NOT NULL,
    encounter_id        TEXT NOT NULL,
    split               TEXT NOT NULL,
    data_classification TEXT NOT NULL,
    schema_version      TEXT NOT NULL,
    source_system       TEXT NOT NULL,
    source_version      TEXT NOT NULL,
    encounter_start     TEXT NOT NULL,
    created_at          TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS journey_events (
    journey_id  TEXT NOT NULL,
    seq         INTEGER NOT NULL,
    event_id    TEXT NOT NULL,
    event_json  TEXT NOT NULL,
    written_at  TEXT NOT NULL,
    PRIMARY KEY (journey_id, event_id)
);

CREATE TABLE IF NOT EXISTS recommendations (
    recommendation_id TEXT PRIMARY KEY,
    journey_id        TEXT NOT NULL,
    request_id        TEXT NOT NULL,
    decision_time     TEXT NOT NULL,
    snapshot_checksum TEXT NOT NULL,
    response_json     TEXT NOT NULL,
    created_at        TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS reviews (
    seq               INTEGER PRIMARY KEY AUTOINCREMENT,
    recommendation_id TEXT NOT NULL,
    reviewer_id       TEXT NOT NULL,
    action            TEXT NOT NULL,
    reason_code       TEXT,
    note              TEXT,
    reviewed_at       TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS audit_events (
    seq         INTEGER PRIMARY KEY AUTOINCREMENT,
    request_id  TEXT NOT NULL,
    record_json TEXT NOT NULL,
    written_at  TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_events_journey ON journey_events (journey_id, seq);
CREATE INDEX IF NOT EXISTS idx_rec_journey ON recommendations (journey_id, created_at);
CREATE INDEX IF NOT EXISTS idx_reviews_rec ON reviews (recommendation_id, seq);
CREATE INDEX IF NOT EXISTS idx_audit_request ON audit_events (request_id, seq);
"""


def _append_only_triggers() -> str:
    statements = []
    for table in _APPEND_ONLY_TABLES:
        for verb in ("UPDATE", "DELETE"):
            statements.append(
                f"""
CREATE TRIGGER IF NOT EXISTS {table}_no_{verb.lower()}
BEFORE {verb} ON {table}
BEGIN
    SELECT RAISE(ABORT, '{table} is append-only: a correction is a new record, never a {verb.lower()}');
END;
"""
            )
    return "\n".join(statements)


class SqliteStore:
    """Append-only store. Survives a restart; refuses to rewrite history."""

    def __init__(self, path: Path | str = ":memory:") -> None:
        self.path = str(path)
        if self.path != ":memory:":
            Path(self.path).parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(self.path, check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        #: Serialises writes across FastAPI's threadpool. See _write.
        self._lock = threading.Lock()
        if self.path != ":memory:":
            # WAL lets readers proceed during a write; busy_timeout waits rather than
            # raising "database is locked" the moment two requests overlap. Neither
            # applies to an in-memory database.
            self._conn.execute("PRAGMA journal_mode=WAL")
            self._conn.execute("PRAGMA busy_timeout=5000")
        self._conn.execute("PRAGMA foreign_keys=ON")
        self._conn.executescript(_SCHEMA)
        self._conn.executescript(_append_only_triggers())
        self._conn.commit()

    def close(self) -> None:
        self._conn.close()

    # ------------------------------------------------------------------- internals

    def _write(self, sql: str, params: Iterable[Any]) -> None:
        # One connection is shared across FastAPI's threadpool with check_same_thread
        # disabled, so execute-then-commit is not atomic between threads: a second
        # thread's write can land inside the first one's transaction and be committed by
        # it. Invisible with one user, a real corruption path with several.
        with self._lock:
            try:
                self._conn.execute(sql, tuple(params))
                self._conn.commit()
            except sqlite3.IntegrityError as exc:
                if "append-only" in str(exc):
                    raise AppendOnlyViolation(str(exc)) from exc
                raise

    @staticmethod
    def _now() -> str:
        return datetime.now(timezone.utc).isoformat()

    # -------------------------------------------------------------------- journeys

    def put_journey(self, journey: PatientJourney) -> None:
        """Insert the journey header once, then append any events not yet stored.

        Re-storing a journey after an append writes only the new events; the header and
        the existing rows are untouched, because the triggers would refuse anything else.
        """
        # Read-then-insert under the same lock the write takes, so two threads storing
        # the same journey cannot both observe "absent" and both insert.
        with self._lock:
            existing = self._conn.execute(
                "SELECT 1 FROM journeys WHERE journey_id = ?", (journey.journey_id,)
            ).fetchone()
        if existing is None:
            self._write(
                "INSERT INTO journeys (journey_id, patient_id, encounter_id, split, "
                "data_classification, schema_version, source_system, source_version, "
                "encounter_start, created_at) VALUES (?,?,?,?,?,?,?,?,?,?)",
                (
                    journey.journey_id, journey.patient_id, journey.encounter_id,
                    journey.split, journey.data_classification, journey.schema_version,
                    journey.source.system, journey.source.version,
                    journey.encounter_start.isoformat(), self._now(),
                ),
            )

        stored = {
            row["event_id"]
            for row in self._conn.execute(
                "SELECT event_id FROM journey_events WHERE journey_id = ?", (journey.journey_id,)
            )
        }
        for seq, event in enumerate(journey.events, start=1):
            if event.event_id in stored:
                continue
            self._write(
                "INSERT INTO journey_events (journey_id, seq, event_id, event_json, written_at) "
                "VALUES (?,?,?,?,?)",
                (
                    journey.journey_id, seq, event.event_id,
                    event.model_dump_json(exclude_unset=True), self._now(),
                ),
            )

    def get_journey(self, journey_id: str) -> PatientJourney | None:
        header = self._conn.execute(
            "SELECT * FROM journeys WHERE journey_id = ?", (journey_id,)
        ).fetchone()
        if header is None:
            return None

        events = [
            JourneyEvent.model_validate(json.loads(row["event_json"]))
            for row in self._conn.execute(
                "SELECT event_json FROM journey_events WHERE journey_id = ? ORDER BY seq",
                (journey_id,),
            )
        ]
        return PatientJourney(
            schema_version=header["schema_version"],
            journey_id=header["journey_id"],
            patient_id=header["patient_id"],
            encounter_id=header["encounter_id"],
            split=header["split"],
            data_classification=header["data_classification"],
            source={"system": header["source_system"], "version": header["source_version"]},
            encounter_start=header["encounter_start"],
            events=events,
        )

    def journey_ids(self) -> tuple[str, ...]:
        return tuple(
            row["journey_id"]
            for row in self._conn.execute("SELECT journey_id FROM journeys ORDER BY created_at")
        )

    # ------------------------------------------------------------- recommendations

    def put_recommendation(
        self,
        *,
        recommendation_id: str,
        journey_id: str,
        request_id: str,
        decision_time: datetime,
        snapshot_checksum: str,
        response_json: str,
    ) -> None:
        if self._conn.execute(
            "SELECT 1 FROM recommendations WHERE recommendation_id = ?", (recommendation_id,)
        ).fetchone():
            return  # already recorded; re-assessing the same question is idempotent
        self._write(
            "INSERT INTO recommendations (recommendation_id, journey_id, request_id, "
            "decision_time, snapshot_checksum, response_json, created_at) VALUES (?,?,?,?,?,?,?)",
            (
                recommendation_id, journey_id, request_id, decision_time.isoformat(),
                snapshot_checksum, response_json, self._now(),
            ),
        )

    def get_recommendation(self, recommendation_id: str) -> dict | None:
        row = self._conn.execute(
            "SELECT * FROM recommendations WHERE recommendation_id = ?", (recommendation_id,)
        ).fetchone()
        return dict(row) if row else None

    def recommendations_for(self, journey_id: str) -> tuple[dict, ...]:
        return tuple(
            dict(row)
            for row in self._conn.execute(
                "SELECT * FROM recommendations WHERE journey_id = ? ORDER BY created_at",
                (journey_id,),
            )
        )

    # --------------------------------------------------------------------- reviews

    def append_review(
        self,
        *,
        recommendation_id: str,
        reviewer_id: str,
        action: str,
        reason_code: str | None,
        note: str | None,
        reviewed_at: datetime,
    ) -> None:
        """Every review is a new row. Changing one's mind appends; it never overwrites."""
        self._write(
            "INSERT INTO reviews (recommendation_id, reviewer_id, action, reason_code, note, "
            "reviewed_at) VALUES (?,?,?,?,?,?)",
            (recommendation_id, reviewer_id, action, reason_code, note, reviewed_at.isoformat()),
        )

    def reviews_for(self, recommendation_id: str) -> tuple[dict, ...]:
        return tuple(
            dict(row)
            for row in self._conn.execute(
                "SELECT * FROM reviews WHERE recommendation_id = ? ORDER BY seq",
                (recommendation_id,),
            )
        )

    # ---------------------------------------------------------------------- audit

    def append_audit(self, request_id: str, record_json: str) -> None:
        self._write(
            "INSERT INTO audit_events (request_id, record_json, written_at) VALUES (?,?,?)",
            (request_id, record_json, self._now()),
        )

    def audit_for(self, request_id: str) -> tuple[dict, ...]:
        return tuple(
            dict(row)
            for row in self._conn.execute(
                "SELECT * FROM audit_events WHERE request_id = ? ORDER BY seq", (request_id,)
            )
        )

    def audit_count(self) -> int:
        return self._conn.execute("SELECT COUNT(*) AS n FROM audit_events").fetchone()["n"]
