"""Slice i2, condition C4 (S4 MEDIUM): same-timestamp conflicts resolve to the worst value, check every tied
value, or flag and abstain; the result does not depend on fact order (I2-A12). Synthetic unit cases only.
"""

from __future__ import annotations

import itertools
import random

import pytest

from app.gateway import build_provider
from app.gateway.contract import GatewayResponse, canonical_sha256
from app.config import Settings
from app.triage import engine, redflags
from app.triage.models import Case, Snapshot

from .helpers import T0, make_case

AS_OF = T0.replace(hour=T0.hour + 1)
SAME = 0  # minutes after T0: every conflicting fact shares this available_at_time (the latest)


def _case(extra: list[tuple[str, object]], drop: tuple[str, ...] = ()) -> Case:
    """BASE facts at T0 minus the conflicting kinds, then two same-time facts per conflicting kind at T0 + 10."""
    kinds = {k for k, _ in extra} | set(drop)
    from .helpers import BASE, DROP

    return make_case({k: DROP for k in kinds}, late=[(k, v, 10) for k, v in extra])


def _invoke():
    provider = build_provider("mock", Settings())

    def invoke(req):
        res = provider.invoke(req, canonical_sha256(req))
        return GatewayResponse(status=res.status, provider="mock", model_version=res.model_version, output=res.output,
                               reason=res.reason, latency_ms=0.0, request_sha256=canonical_sha256(req))

    return invoke


def _ids(alerts):
    return sorted(a.rule_id for a in alerts)


CASES = {
    # min: spo2 98 and 88 tied -> 88 (worst); RF-SPO2 fires on the 88 fact
    "min": ([("vital.spo2", 98), ("vital.spo2", 88)], "vital.spo2", "worst", 88, {"RF-SPO2"}),
    # ordinal: avpu A and P tied -> P; RF-CONSC fires
    "ordinal": ([("vital.avpu", "A"), ("vital.avpu", "P")], "vital.avpu", "worst", "P", {"RF-CONSC"}),
    # bidirectional any-hit: hr 80 and 35 tied -> both checked, RF-HR fires on the 35 fact
    "bidirectional": ([("vital.hr", 80), ("vital.hr", 35)], "vital.hr", "any_hit", None, {"RF-HR"}),
    # flag-and-abstain: sex male and female tied -> flagged, department abstains with conflict:sex
    "flag": ([("sex", "male"), ("sex", "female")], "sex", "flagged", None, set()),
}


@pytest.mark.parametrize("name", list(CASES))
def test_same_timestamp_worst(name):
    extra, kind, resolution, resolved, fired = CASES[name]
    case = _case(extra)
    snap = Snapshot(case, AS_OF)
    (conflict,) = snap.conflicts
    assert (conflict.kind, conflict.resolution) == (kind, resolution)
    assert len(conflict.fact_ids) == 2
    if resolution == "worst":
        assert conflict.resolved_value == resolved and snap.get(kind).value == resolved
    if resolution == "any_hit":
        assert sorted(f.value for f in snap.values(kind)) == sorted(v for _, v in extra)
    alerts, not_evaluable = redflags.evaluate(snap)
    assert fired <= set(_ids(alerts))
    for a in alerts:
        if a.rule_id in fired:  # the alert cites the worst / hitting fact (the second value), never the benign one
            hit = [f.value for f in case.facts if f.fact_id in a.evidence_refs and f.kind == kind]
            assert hit == [extra[1][1]]
    a = engine.assess(case, AS_OF, _invoke(), actor_id=1)
    assert [c.kind for c in a.conflicts] == [kind]  # conflicts[] is on the assessment shown at review
    if resolution == "flagged":
        assert a.department.status == "abstained" and a.department.reason == "conflicting_information"
        assert a.department.missing_information == ["conflict:sex"] and a.department.request_sha256 is None
        assert "sex" in snap.flagged and snap.get("sex") is None  # treated as unknown, never guessed
    else:  # a resolved conflict does not make the department abstain
        assert a.department.reason != "conflicting_information" and a.department.request_sha256 is not None


def test_symptom_conflict_present_wins():
    snap = Snapshot(_case([("symptom.acute_chest_pain", "absent"), ("symptom.acute_chest_pain", "present")]), AS_OF)
    assert snap.symptom("acute_chest_pain")[0] == "present"
    assert "RF-CHEST" in _ids(redflags.evaluate(snap)[0])


def test_latest_wins_across_timestamps_unchanged():
    """D-I2-3: across different timestamps S4 latest-wins is unchanged (reported, not a conflict)."""
    case = make_case({"vital.spo2": 85}, late=[("vital.spo2", 97, 10)])
    snap = Snapshot(case, AS_OF)
    assert snap.conflicts == [] and snap.get("vital.spo2").value == 97
    assert "RF-SPO2" not in _ids(redflags.evaluate(snap)[0])


def _strip(a):
    d = a.model_dump(mode="json")
    d.pop("assessment_id"), d.pop("created_at")
    return d


@pytest.mark.parametrize("name", list(CASES))
def test_conflict_order_invariant(name):
    extra = CASES[name][0] + [("vital.rr", 12), ("vital.rr", 30), ("pregnancy_status", "negative"),
                              ("pregnancy_status", "unknown")]
    case = _case(extra)
    invoke = _invoke()
    ref = _strip(engine.assess(case, AS_OF, invoke, actor_id=1))
    facts = list(case.facts)
    perms = list(itertools.permutations(facts[-len(extra):]))
    rng = random.Random(20260926)
    for tail in perms[:24]:
        shuffled = facts[: -len(extra)]
        rng.shuffle(shuffled)
        other = Case(case_ref=case.case_ref, data_class="synthetic", facts=list(tail) + shuffled)
        assert _strip(engine.assess(other, AS_OF, invoke, actor_id=1)) == ref
