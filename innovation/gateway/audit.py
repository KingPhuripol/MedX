"""Audit records for every gateway call, including the ones that were refused.

`CLAUDE.md` §Product and safety invariants requires logging the model/provider version,
contract version, timestamps, inputs *by approved reference*, outputs, overrides and
reviewer identity. "By approved reference" is the load-bearing part: this module records
evidence IDs and payload references, never payloads, so the audit trail cannot itself
become a copy of the patient record.
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:  # pragma: no cover - import cycle guard
    from innovation.store import SqliteStore


@dataclass(frozen=True)
class AuditRecord:
    """One gateway call. Written whether the call succeeded, abstained or was refused."""

    request_id: str
    journey_id: str
    decision_time: str
    task: str
    contract_version: str
    provider: str
    provider_version: str | None
    model_version: str | None
    policy_version: str
    status: str
    urgency_level: str
    #: Evidence admitted to the provider, by reference only.
    evidence_ids: tuple[str, ...]
    #: Evidence refused, with the reason, so a refusal is explainable after the fact.
    rejected_evidence: tuple[tuple[str, str], ...]
    applied_safety_rules: tuple[str, ...]
    error_codes: tuple[str, ...]
    started_at: str
    completed_at: str
    #: Set once a human acts on the recommendation. Absent means not yet reviewed —
    #: it must never be read as approved.
    reviewer_id: str | None = None
    review_action: str | None = None
    overridden_from: str | None = None
    notes: tuple[str, ...] = field(default=())

    def to_json(self) -> str:
        return json.dumps(asdict(self), sort_keys=True, separators=(",", ":"), default=str)


class AuditLog:
    """Append-only audit sink, with up to three destinations.

    In-memory by default so tests and the offline demo need no storage. `path` appends
    JSON Lines; `store` appends rows to a database whose triggers refuse UPDATE and
    DELETE outright. Two durable sinks is deliberate — the JSONL file is readable without
    tooling during an incident, and the database makes tampering fail loudly.

    Nothing here ever rewrites: audit evidence is not deleted to make a failure disappear
    (`SAFETY_SPEC.md` §Incident response).
    """

    def __init__(self, path: Path | None = None, store: "SqliteStore | None" = None) -> None:
        self._path = path
        self._store = store
        self._records: list[AuditRecord] = []

    def append(self, record: AuditRecord) -> None:
        self._records.append(record)
        payload = record.to_json()
        if self._path is not None:
            self._path.parent.mkdir(parents=True, exist_ok=True)
            with self._path.open("a", encoding="utf-8") as handle:
                handle.write(payload + "\n")
        if self._store is not None:
            self._store.append_audit(record.request_id, payload)

    def records(self) -> tuple[AuditRecord, ...]:
        return tuple(self._records)

    def find(self, request_id: str) -> tuple[AuditRecord, ...]:
        return tuple(r for r in self._records if r.request_id == request_id)


def utc_now_iso(moment: datetime) -> str:
    """Serialise a timestamp for the audit trail."""
    return moment.isoformat()
