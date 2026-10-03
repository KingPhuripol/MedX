"""Conversation medication/allergy facts as Pharma inputs (slice cg-t123 rounds 4-5, PROPOSAL 3.2.4). Pure, no I/O.

One place defines how a Reader:Text ``current_medications`` fact becomes an S5 ``patient_reported`` source, how the
executor later checks that the fact was actually *consumed* (gate on use, never on "the reader failed"), and how
conversation facts of one kind are ORDERED. Ordering is shared by the gate, the per-fact use report and the
supersede rule: timestamps are compared as parsed aware datetimes (never as strings), and a same-time tie is
resolved conservatively (a non-KNOWN fact wins; differing same-time facts are reported as a conflict).
A fact that cannot be consumed for any reason is reported, never dropped (data rule 6).
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

MED_KIND = "current_medications"
MAX_ENTRY = 500  # S5 MedEntry.text limit: a longer name is unparseable here, never truncated silently
_MIN = datetime.min.replace(tzinfo=timezone.utc)


def parse_ts(value: Any) -> datetime:
    """An aware datetime from an ISO string/datetime. Naive is read as UTC; unparseable sorts oldest (never newest)."""
    if isinstance(value, str):
        try:
            value = datetime.fromisoformat(value)
        except ValueError:
            return _MIN
    if not isinstance(value, datetime):
        return _MIN
    return value if value.tzinfo is not None else value.replace(tzinfo=timezone.utc)


def _payload(f: dict[str, Any]) -> str:
    return json.dumps([f["state"], f.get("value"), f.get("value_text", "")], sort_keys=True, default=str)


def order_key(f: dict[str, Any]) -> tuple[datetime, int, str]:
    """Total order on conversation facts: time, then non-KNOWN above KNOWN (conservative tie-break), then content."""
    return parse_ts(f["available_at_time"]), 0 if f["state"] == "KNOWN" else 1, _payload(f)


def ordered(facts: Any) -> list[dict[str, Any]]:
    return sorted(facts, key=order_key)


def newest(facts: Any) -> dict[str, Any] | None:
    """The fact every consumer treats as current (same helper for gate, fact_use and supersede)."""
    return max(facts, key=order_key, default=None)


def same_time_conflict(facts: Any, fact: dict[str, Any]) -> bool:
    """Another fact of the same kind at the same instant that says something different."""
    t = parse_ts(fact["available_at_time"])
    return any(g is not fact and parse_ts(g["available_at_time"]) == t and _payload(g) != _payload(fact)
               for g in facts)


def fact_refs(facts: tuple[dict[str, Any], ...]) -> dict[int, str]:
    """Evidence ref per fact (keyed by ``id(fact)``): the real source item id plus the ordinal among facts of that
    kind from that item, in the order the Reader:Text node emitted them."""
    seen: dict[tuple[str, str], int] = {}
    out: dict[int, str] = {}
    for f in facts:
        src = str(f.get("source_item") or "turns")[:70]
        k = seen.get((f["kind"], src), 0)
        seen[(f["kind"], src)] = k + 1
        out[id(f)] = f"conversation:{f['kind']}:{src}#{k}"
    return out


@dataclass(frozen=True)
class ConversationMeds:
    ref: str  # evidence ref of the S5 source this fact becomes
    fact: dict[str, Any]
    names: tuple[str, ...]  # medication names the adapter hands to S5 (valid entries only)
    problem: str | None  # why the fact cannot be (fully) used, or None
    superseded: bool = False  # a later KNOWN statement closed this open (non-KNOWN) fact


def parse_medication_facts(facts: tuple[dict[str, Any], ...]) -> tuple[ConversationMeds, ...]:
    """Every ``current_medications`` fact, in a deterministic order, with its S5 ref and any problem."""
    refs = fact_refs(facts)
    same = ordered(f for f in facts if f["kind"] == MED_KIND)
    out = []
    for fact in same:
        ref = refs[id(fact)]
        names: tuple[str, ...] = ()
        problem: str | None = None
        if fact["state"] != "KNOWN":
            problem = f"conversation.{MED_KIND}={fact['state']}"
        elif not isinstance(fact["value"], (list, tuple)):
            problem = f"conversation.{MED_KIND}:unparseable"
        else:
            raw = list(fact["value"])
            names = tuple(s.strip() for s in raw if isinstance(s, str) and s.strip() and len(s.strip()) <= MAX_ENTRY)
            if len(names) != len(raw):
                problem = f"conversation.{MED_KIND}:unparseable"
        superseded = fact["state"] != "KNOWN" and any(
            g["state"] == "KNOWN" and parse_ts(g["available_at_time"]) > parse_ts(fact["available_at_time"])
            for g in same)  # strictly later only: a same-time KNOWN never closes it
        if superseded:
            problem = None  # superseded by a later KNOWN statement: not an open input
        out.append(ConversationMeds(ref, fact, names, problem, superseded))
    return tuple(out)


def consumed_refs(checks: Any) -> set[str]:
    """Evidence refs a provider's checks actually evaluated on (``MedicationCheck.evaluated_on``)."""
    return {r for c in checks for r in c.evaluated_on}
