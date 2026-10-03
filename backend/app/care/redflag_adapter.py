"""Red-flag input for care: reuse the s4 Red-flag Node (rf-1.1.0) unchanged; never compute or rank red flags here.

Structured items only: Demographics -> ``age``/``sex``; each Vitals parameter -> ``vital.*`` with the item's
``available_at_time``. Consciousness: ``A`` -> ``avpu=A`` and ``new_confusion=false``; ``C`` -> ``new_confusion=true``
only; ``V|P|U`` -> ``avpu``. No symptom facts are produced (care does not read the transcript for red flags, S6 D2),
so symptom rules are not evaluable and the screening is ``partially_evaluated`` with the INCOMPLETE banner.

Slice int2: the result is the I2 ``casegraph.data.RedFlagScreening`` block (rule set, label, care scope, counts,
vital readings, conflicts). Vital freshness (I2 C1) is applied conservatively: a fired rule stays fired whatever
the age of its inputs; a rule that did not fire and cannot be decided once its stale vitals are set aside (the I2
Red-flag node's drop, applied to non-fired rules only) is ``not_evaluated`` with
``vital.<k>:stale(read_at=..., age_min=...)``. Proposed default D-int2-1. Any error is ``unavailable``.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

from casegraph.data import (
    DECLARED_RULES,
    RF_110,
    RULE_SET_LABELS,
    RedFlagScreening,
    VitalReadingInfo,
    banner_for,
    screening_status,
)
from casegraph.triage_bridge import load_freshness, stale_input

from ..triage import redflags
from ..triage.models import Alert, Case, IntakeFact, Snapshot
from .snapshot import SnapshotView

NUMERIC = ("sbp", "dbp", "hr", "rr", "temp_c", "spo2")
CARE_SCREENING_SCOPE = (
    "rf-1.1.0: 16 declared rules; care screening uses the latest structured vitals and demographics only "
    "(a stale normal vital is not counted as screened; an abnormal one still alerts). Symptom rules are not "
    "evaluated in care, because care does not read the intake transcript for red-flag symptoms; an unmentioned "
    "symptom is unknown, not absent"
)


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
        if v.on_oxygen is not None:
            facts.append(_fact(v, "vital.on_oxygen", v.on_oxygen))
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


def rule_set_version() -> str:
    """The S4 rule file's version; it must be rf-1.1.0 with exactly its declared rule ids, else unavailable."""
    if redflags.RULESET_VERSION != RF_110 or sorted(declared_rules()) != sorted(DECLARED_RULES[RF_110]):
        raise RuntimeError(f"S4 red-flag rules are not {RF_110}")
    return RF_110


def readings(view: SnapshotView, facts: Sequence[IntakeFact], snap: Snapshot
             ) -> tuple[list[VitalReadingInfo], dict[str, str]]:
    """The reading of each care-mapped vital (``facts`` = :func:`to_facts`; the fact the S4 snapshot uses), its
    read time (the item's ``event_time``) and age at T.

    Returns the readings and, for each stale kind, its missing-input text (``triage_bridge.stale_input``).
    """
    windows = load_freshness().windows_min
    by_kind: dict[str, list[IntakeFact]] = {}
    for f in facts:
        if f.kind.startswith("vital.") and f.available_at_time <= view.as_of:
            by_kind.setdefault(f.kind, []).append(f)
    out: list[VitalReadingInfo] = []
    stale: dict[str, str] = {}
    for kind in sorted(by_kind):
        fact = snap.get(kind)
        if fact is None or fact not in by_kind[kind]:  # a flagged conflict, or a test-supplied extra fact
            fact = max(by_kind[kind], key=lambda f: (f.available_at_time, f.fact_id))
        item = view.by_id[item_id_of(fact.fact_id)]
        name = kind.removeprefix("vital.")
        age_s = (view.as_of - item.event_time).total_seconds()
        r = VitalReadingInfo(vital=name, value=fact.value, read_at=item.event_time, age_min=age_s / 60,
                             window_min=windows[name], fresh=age_s <= windows[name] * 60, item_id=item.item_id)
        out.append(r)
        if not r.fresh:
            stale[kind] = stale_input(kind, item.event_time, r.age_min)
    return out, stale


def screen(view: SnapshotView, extra_facts: Sequence[IntakeFact] = ()) -> Screening:
    """Run the s4 engine on the snapshot. ``extra_facts`` lets tests supply symptom facts (never used by the API)."""
    try:
        version = rule_set_version()
        facts = to_facts(view)
        snap = Snapshot(Case(case_ref=view.case_id, data_class="synthetic", facts=[*facts, *extra_facts]), view.as_of)
        alerts, not_evaluable = redflags.evaluate(snap)
        ids = declared_rules()
        fired = {a.rule_id for a in alerts}
        missing_by_rule = {n.rule_id: set(n.missing_inputs) for n in not_evaluable}
        reads, stale = readings(view, facts, snap)
        if stale:  # C1, conservative: only a rule that did not fire can become not_evaluated
            kept = [f for f in [*facts, *extra_facts] if f.kind not in stale]
            _, without = redflags.evaluate(Snapshot(Case(case_ref=view.case_id, data_class="synthetic",
                                                         facts=kept), view.as_of))
            for n in without:  # undecidable once its stale vitals are set aside
                if n.rule_id not in fired:
                    missing_by_rule[n.rule_id] = {stale.get(m, m) for m in n.missing_inputs}
        not_eval = set(missing_by_rule)
        missing = sorted({m for ms in missing_by_rule.values() for m in ms})
        status = screening_status([rid not in not_eval for rid in ids], missing)
        evaluated = tuple(sorted(set(ids) - not_eval))
        scr = RedFlagScreening(
            status=status, performed=status == "evaluated", banner=banner_for(status),
            rules_evaluated=evaluated, rules_not_evaluated=tuple(sorted(not_eval)), missing_inputs=tuple(missing),
            rule_set_version=version, label=RULE_SET_LABELS[version], scope=CARE_SCREENING_SCOPE,
            n_declared=len(ids), n_evaluated=len(evaluated), n_not_evaluated=len(not_eval), n_fired=len(alerts),
            readings=tuple(reads), conflicts=tuple(c.model_dump(mode="json") for c in snap.conflicts))
        return Screening(alerts, scr)
    except Exception:  # fail safe: an adapter/engine error is "unavailable", never "passed"
        return unavailable()


def unavailable() -> Screening:
    """Every declared rf-1.1.0 rule not evaluated, with the care scope (validated as the I2 type)."""
    base = RedFlagScreening.from_alerts(None, RF_110)
    return Screening([], RedFlagScreening.model_validate({**base.model_dump(), "scope": CARE_SCREENING_SCOPE}))
