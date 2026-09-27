"""Red-flag input for care: reuse the s4 Red-flag Node (rf-1.1.0) unchanged; never compute or rank red flags here.

Structured items only: Demographics -> ``age``/``sex``; each Vitals parameter -> ``vital.*`` with the item's
``available_at_time``. Consciousness: ``A`` -> ``avpu=A`` and ``new_confusion=false``; ``C`` -> ``new_confusion=true``
only; ``V|P|U`` -> ``avpu``. No symptom facts are produced (no NLP in this slice), so symptom rules are not
evaluable and the screening is ``partially_evaluated`` with the INCOMPLETE banner. Any error is ``unavailable``.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

from casegraph.data import RedFlagScreening, banner_for, screening_status

from ..triage import redflags
from ..triage.models import Alert, Case, IntakeFact, Snapshot
from .snapshot import SnapshotView

NUMERIC = ("sbp", "dbp", "hr", "rr", "temp_c", "spo2")


@dataclass(frozen=True)
class Screening:
    alerts: list[Alert]
    screening: RedFlagScreening


def _fact(item, kind: str, value) -> dict:
    return {"fact_id": f"{item.item_id}:{kind}", "kind": kind, "value": value,
            "available_at_time": item.available_at_time, "source": item.source,
            "provenance": item.provenance, "version": item.version}


def to_facts(view: SnapshotView) -> list[IntakeFact]:
    facts: list[dict] = []
    d = view.demographics()
    if d is not None:
        facts += [_fact(d, k, v) for k, v in (("age", d.age_years), ("sex", d.sex)) if v is not None]
    for v in view.of_type("Vitals"):
        for p in NUMERIC:
            if getattr(v, p) is not None:
                facts.append(_fact(v, f"vital.{p}", getattr(v, p)))
        c = v.consciousness
        if c == "A":
            facts += [_fact(v, "vital.avpu", "A"), _fact(v, "vital.new_confusion", False)]
        elif c == "C":
            facts.append(_fact(v, "vital.new_confusion", True))
        elif c in ("V", "P", "U"):
            facts.append(_fact(v, "vital.avpu", c))
    return [IntakeFact(**f) for f in facts]


def item_id_of(fact_id: str) -> str:
    return fact_id.split(":", 1)[0]


def declared_rules() -> list[str]:
    return [r["id"] for r in redflags.rules()]


def screen(view: SnapshotView, extra_facts: Sequence[IntakeFact] = ()) -> Screening:
    """Run the s4 engine on the snapshot. ``extra_facts`` lets tests supply symptom facts (never used by the API)."""
    try:
        case = Case(case_ref=view.case_id, data_class="synthetic", facts=[*to_facts(view), *extra_facts])
        alerts, not_evaluable = redflags.evaluate(Snapshot(case, view.as_of))
        ids = declared_rules()
        missing = sorted({m for n in not_evaluable for m in n.missing_inputs})
        not_eval = {n.rule_id for n in not_evaluable}
        status = screening_status([rid not in not_eval for rid in ids], missing)
        scr = RedFlagScreening(status=status, performed=status == "evaluated", banner=banner_for(status),
                               rules_evaluated=tuple(sorted(set(ids) - not_eval)),
                               rules_not_evaluated=tuple(sorted(not_eval)), missing_inputs=tuple(missing))
        return Screening(alerts, scr)
    except Exception:  # fail safe: an adapter/engine error is "unavailable", never "passed"
        return unavailable()


def unavailable() -> Screening:
    try:
        ids = declared_rules()
    except Exception:  # the rule file itself failed to load
        ids = []
    return Screening([], RedFlagScreening.from_alerts(None, ids))
