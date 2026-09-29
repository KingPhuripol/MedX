"""Deterministic, declarative red-flag engine (Red-flag Node). No model or gateway in this path.

The rules file is pinned by SHA-256 to ``RULESET_VERSION``; a changed file without a version bump
fails to load (fail closed). Logic is three-valued so missing input is never read as negative.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Any

from .models import Alert, NotEvaluable, Snapshot

RULES_PATH = Path(__file__).with_name("rules") / "redflag_rules_v1.json"
RULESET_VERSION = "rf-1.1.0"
RULESET_SHA256 = "086e0a29bde7fe7395cfd650342434920314fda8f5df7f96f8e091ab26f11a3a"

_OPS = {
    "<=": lambda a, b: a <= b,
    "<": lambda a, b: a < b,
    ">=": lambda a, b: a >= b,
    ">": lambda a, b: a > b,
    "==": lambda a, b: a == b,
    "!=": lambda a, b: a != b,
    "in": lambda a, b: a in b,
}


@dataclass(frozen=True)
class _Result:
    value: bool | None  # None = unknown
    evidence: tuple[str, ...] = ()
    missing: tuple[str, ...] = ()


def file_sha256(path: Path = RULES_PATH) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load_rules(path: Path = RULES_PATH, pinned_sha256: str | None = None) -> list[dict[str, Any]]:
    pinned = RULESET_SHA256 if pinned_sha256 is None else pinned_sha256
    if file_sha256(path) != pinned:
        raise RuntimeError("red-flag rules file changed without a ruleset version bump")
    doc = json.loads(path.read_text(encoding="utf-8"))
    if doc.get("version") != RULESET_VERSION:
        raise RuntimeError("red-flag rules file version does not match RULESET_VERSION")
    return doc["rules"]


@lru_cache(maxsize=1)
def rules() -> tuple[dict[str, Any], ...]:
    return tuple(load_rules())


def _leaf(cond: dict[str, Any], snap: Snapshot) -> _Result:
    op = _OPS[cond["op"]] if "op" in cond else None
    if "symptom" in cond:
        state, fact_id = snap.symptom(cond["symptom"])
        if state == "unknown":
            return _Result(None, missing=(f"symptom.{cond['symptom']}",))
        return _Result(state == "present", (fact_id,) if state == "present" else ())
    kind = f"vital.{cond['vital']}" if "vital" in cond else cond["field"]
    if kind in snap.flagged:  # i2: a conflicting same-timestamp value is unknown, never guessed
        return _Result(None, missing=(f"conflict:{kind}",))
    facts = snap.values(kind)
    if not facts:
        if "missing_as" in cond:  # an explicit "not known" value, e.g. pregnancy status
            return _Result(bool(op(cond["missing_as"], cond["value"])))
        return _Result(None, missing=(kind,))
    # i2: tied same-timestamp values of hr/rr/sbp/dbp/temp_c are all checked; true if any hits.
    hits = tuple(f.fact_id for f in facts if op(f.value, cond["value"]))
    return _Result(bool(hits), hits)


def evaluate_condition(cond: dict[str, Any], snap: Snapshot) -> _Result:
    if "any" in cond or "all" in cond or "at_least" in cond:
        parts = [evaluate_condition(c, snap) for c in cond.get("any") or cond.get("all") or cond["of"]]
        trues = [p for p in parts if p.value is True]
        unknowns = [p for p in parts if p.value is None]
        missing = tuple(m for p in unknowns for m in p.missing)
        evidence = tuple(e for p in trues for e in p.evidence)
        if "any" in cond:
            if trues:
                return _Result(True, evidence)
            return _Result(None, missing=missing) if unknowns else _Result(False)
        if "all" in cond:
            if any(p.value is False for p in parts):
                return _Result(False)
            return _Result(None, missing=missing) if unknowns else _Result(True, evidence)
        need = int(cond["at_least"])
        if len(trues) >= need:
            return _Result(True, evidence)
        if len(trues) + len(unknowns) < need:
            return _Result(False)
        return _Result(None, missing=missing)
    return _leaf(cond, snap)


def evaluate(snap: Snapshot) -> tuple[list[Alert], list[NotEvaluable]]:
    """Return alerts (rule order) and rules that could not be checked because inputs are missing."""
    alerts: list[Alert] = []
    not_evaluable: list[NotEvaluable] = []
    for rule in rules():
        result = evaluate_condition(rule["condition"], snap)
        if result.value is True:
            alerts.append(
                Alert(
                    rule_id=rule["id"],
                    ruleset_version=RULESET_VERSION,
                    name_en=rule["name_en"],
                    name_th=rule["name_th"],
                    severity=rule["severity"],
                    evidence_refs=sorted(set(result.evidence)),
                    message_en=rule["message_en"],
                    message_th=rule["message_th"],
                )
            )
        elif result.value is None:
            not_evaluable.append(
                NotEvaluable(
                    rule_id=rule["id"],
                    name_en=rule["name_en"],
                    name_th=rule["name_th"],
                    missing_inputs=sorted(set(result.missing)),
                )
            )
    return alerts, not_evaluable
