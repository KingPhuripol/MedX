"""Conversation medication/allergy facts as Pharma inputs (slice cg-t123 round 4, PROPOSAL 3.2.4). Pure, no I/O.

One place defines how a Reader:Text ``current_medications`` fact becomes an S5 ``patient_reported`` source and how
the executor later checks that the fact was actually *consumed* (gate on use, never on "the reader failed").
A fact that cannot be consumed for any reason is reported, never dropped (data rule 6).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

MED_KIND = "current_medications"
MAX_ENTRY = 500  # S5 MedEntry.text limit: a longer name is unparseable here, never truncated silently


@dataclass(frozen=True)
class ConversationMeds:
    ref: str  # evidence ref of the S5 source this fact becomes
    fact: dict[str, Any]
    names: tuple[str, ...]  # medication names the adapter hands to S5 (valid entries only)
    problem: str | None  # why the fact cannot be (fully) used, or None


def parse_medication_facts(facts: tuple[dict[str, Any], ...]) -> tuple[ConversationMeds, ...]:
    """Every ``current_medications`` fact, in a deterministic order, with its S5 ref and any problem."""
    same = sorted((f for f in facts if f["kind"] == MED_KIND),
                  key=lambda f: (str(f["available_at_time"]), str(f.get("value_text", ""))))
    out = []
    for n, fact in enumerate(same):
        ref = f"conversation:{MED_KIND}#{n}"
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
        if fact["state"] != "KNOWN" and any(g["state"] == "KNOWN" and str(g["available_at_time"]) >
                                            str(fact["available_at_time"]) for g in same):
            problem = None  # superseded by a later KNOWN statement: not an open input
        out.append(ConversationMeds(ref, fact, names, problem))
    return tuple(out)


def consumed_refs(checks: Any) -> set[str]:
    """Evidence refs a provider's checks actually evaluated on (``MedicationCheck.evaluated_on``)."""
    return {r for c in checks for r in c.evaluated_on}
