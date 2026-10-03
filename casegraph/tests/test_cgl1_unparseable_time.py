"""Slice cg-l1 (closes CONDITIONS cg-t123 L1): a conversation fact with an unparseable time fails closed.

Synthetic, offline, mock only. Defence-in-depth for a path that is unreachable today (``IntakeValue.available_at_time``
is an ``AwareDatetime``): it shows the Pharma gates fail closed on crafted input, not clinical performance."""

from __future__ import annotations

import re

import itertools
import json
from datetime import timezone

import pytest

from casegraph import executor as executor_mod
from casegraph.compiler import build_snapshot, compile_graph
from casegraph.conversation_meds import (newest, order_key, ordered, parse_medication_facts, same_time_conflict,
                                         time_problem)
from casegraph.executor import Executor
from casegraph.staged import build_versions
from casegraph.types import NodeType

from .conftest import Env
from .fixtures import H, M
from .staged_fixtures import T1, allergy, base, conv_meds, order

MISSING = object()
BAD = [MISSING, None, "", "not-a-time", "2026-02-30T10:00:00+00:00", 12345]
BAD_IDS = ["missing", "none", "empty", "garbage", "feb30", "int"]
KINDS = ["allergy_status", "allergens", "current_medications"]
KNOWN_VALUE = {"allergy_status": "present", "allergens": ["penicillin"], "current_medications": ["warfarin"]}
OTHER_KNOWN = {"allergy_status": "absent", "allergens": ["latex"], "current_medications": ["ibuprofen"]}
MODES = ["staged", "unstaged"]


def tok(kind):
    return f"conversation.{kind}:unparseable_time"


def fact(kind, state="KNOWN", value=None, t="2026-01-01T10:00:00+00:00", **kw):
    f = {"kind": kind, "state": state, "value": value, "value_text": str(value), "available_at_time": t, **kw}
    if t is MISSING:
        del f["available_at_time"]
    return f


def _mi(g):
    return g.by_type(NodeType.PHARMA_AGENT).output["MedicationIssues"]


def _node(g):
    return g.by_type(NodeType.PHARMA_AGENT)


def _spec(kind, state, value):
    return {kind: (state, value)}


def _items(p, mode, specs, *, allergy_status_record="known"):
    """specs: [(item_id, t_offset_minutes, {kind: (state, value)})] as conversation items, then one order."""
    items = [*base(p, with_allergy=False), allergy(p, f"{p}-allergy", T1 - 48 * H, status=allergy_status_record)]
    for iid, off, kinds in specs:
        kw = {"meds": None, "allergy_status": None, "allergens": None}
        for k, v in kinds.items():
            kw["meds" if k == "current_medications" else k] = v
        items.append(conv_meds(p, f"{p}-{iid}", T1 + off * M, **kw))
    items.append(order(p, f"{p}-o", T1 if mode == "unstaged" else T1 + 30 * M))
    return items


def _run(env, items, p, mode):
    ex = env.executor()
    if mode == "staged":
        return build_versions(ex, items, T1, T1 + 2 * H)[-1]
    graph = compile_graph(build_snapshot(items, T1, p), None, version=1, parent_version=None)
    return ex.run_sync(graph)


def _craft(monkeypatch, p, item_id, bad):
    orig = Executor._conversation_facts

    def wrapped(ctx):
        out = []
        for f in orig(ctx):
            if f.get("source_item") == f"{p}-{item_id}":
                f = dict(f)
                if bad is MISSING:
                    f.pop("available_at_time", None)
                else:
                    f["available_at_time"] = bad
            out.append(f)
        return tuple(out)

    monkeypatch.setattr(Executor, "_conversation_facts", staticmethod(wrapped))


def _gap_rows(mi, kind):
    check = "medication_conversation" if kind == "current_medications" else "allergy_conversation"
    return [c for c in mi["check_results"] if c["check"] == check and tok(kind) in c["missing_inputs"]]


# ------------------------------------------------------------------------------------------------ L1c helpers

@pytest.mark.parametrize("bad", BAD, ids=BAD_IDS)
def test_cgl1_helpers_total_on_bad_time(bad):
    for kind in KINDS:
        f = fact(kind, "KNOWN", KNOWN_VALUE[kind], t=bad)
        assert time_problem(f) == tok(kind)
        order_key(f)
        assert ordered([f]) == [f]
        assert newest([f]) is None  # a single bad-time fact alone is never "current"
        assert same_time_conflict([f, fact(kind, "UNKNOWN", None, t=bad)], f) is False
        parse_medication_facts((f,))
        good = fact(kind, "UNKNOWN", None)
        assert newest([f, good]) is good
        assert time_problem(good) is None
    assert time_problem({}) == "conversation.unknown:unparseable_time"  # no kind, no time: still no raise
    assert time_problem("not a dict") == "conversation.unknown:unparseable_time"


def test_cgl1_valid_time_forms_unchanged():
    naive = fact("allergens", t="2026-01-01T10:00:00")
    bkk = fact("allergens", t="2026-01-01T17:00:00+07:00")
    assert time_problem(naive) is None and time_problem(bkk) is None
    assert order_key(naive)[0] == order_key(bkk)[0] and order_key(naive)[0].tzinfo is not None
    assert order_key(naive)[0].astimezone(timezone.utc).hour == 10  # naive is read as UTC


def test_cgl1_order_permutation_invariant():
    kind = "current_medications"
    facts = [fact(kind, "KNOWN", ["warfarin"], t="2026-01-01T10:00:00+00:00"),
             fact(kind, "UNKNOWN", None, t="2026-01-01T09:00:00+00:00"),
             fact(kind, "KNOWN", ["ibuprofen"], t="not-a-time"),
             fact(kind, "UNKNOWN", None, t=MISSING)]
    results = set()
    for perm in itertools.permutations(facts):
        o = ordered(perm)
        n = newest(perm)
        meds = [(m.fact["state"], str(m.fact.get("value")), m.problem, m.superseded) for m in parse_medication_facts(perm)]
        results.add((json.dumps([[f["state"], str(f.get("value")), str(f.get("available_at_time"))] for f in o]),
                     json.dumps([n["state"], str(n["value"])]), json.dumps(meds)))
    assert len(results) == 1


def test_cgl1_all_bad_list_has_no_newest_and_every_fact_is_a_gap():
    facts = [fact("allergens", t=b) for b in BAD]
    assert newest(facts) is None
    gaps = Executor._conversation_allergy_gaps(None, tuple(facts))
    assert ("allergy_conversation", (tok("allergens"),)) in gaps


# ------------------------------------------------------------------------------------------------ gates, direct

@pytest.mark.parametrize("bad", BAD, ids=BAD_IDS)
@pytest.mark.parametrize("kind", ["allergy_status", "allergens"])
@pytest.mark.parametrize("state", ["KNOWN", "UNKNOWN", "REFUSED"])
def test_cgl1_allergy_gate_row(kind, state, bad):
    v = KNOWN_VALUE[kind] if state == "KNOWN" else None
    facts = (fact(kind, "KNOWN", OTHER_KNOWN[kind], t="2026-01-01T09:00:00+00:00"), fact(kind, state, v, t=bad))
    rows = Executor._conversation_allergy_gaps(None, facts)
    assert ("allergy_conversation", (tok(kind),)) in rows
    assert not any(":unparseable" == m[-len(":unparseable"):] for _, ms in rows for m in ms)  # bad value token not reused


@pytest.mark.parametrize("bad", BAD, ids=BAD_IDS)
@pytest.mark.parametrize("state", ["KNOWN", "UNKNOWN", "REFUSED"])
def test_cgl1_medication_gate_row(state, bad):
    kind = "current_medications"
    facts = (fact(kind, "KNOWN", ["warfarin"], t="2026-01-01T09:00:00+00:00"),
             fact(kind, state, ["ibuprofen"] if state == "KNOWN" else None, t=bad))
    rows = Executor._conversation_medication_gaps(facts, (), 2)
    assert ("medication_conversation", (tok(kind),)) in rows


@pytest.mark.parametrize("bad", BAD, ids=BAD_IDS)
@pytest.mark.parametrize("state", ["UNKNOWN", "REFUSED", "KNOWN"])
def test_cgl1_parse_medication_facts_bad_time_not_superseded(state, bad):
    kind = "current_medications"
    good = fact(kind, "KNOWN", ["warfarin"], t="2026-01-01T10:00:00+00:00")
    b = fact(kind, state, ["ibuprofen"] if state == "KNOWN" else None, t=bad)
    parsed = {id(m.fact): m for m in parse_medication_facts((good, b))}
    assert parsed[id(b)].superseded is False and parsed[id(b)].names == ()
    assert parsed[id(b)].problem == tok(kind)
    assert parsed[id(good)].superseded is False  # a bad-time KNOWN never closes anything
    older = fact(kind, "UNKNOWN", None, t="2026-01-01T08:00:00+00:00")
    parsed = {id(m.fact): m for m in parse_medication_facts((older, b))}
    assert parsed[id(older)].superseded is False  # still open: a bad-time KNOWN does not supersede it


# ------------------------------------------------------------------------------------------------ end to end

@pytest.mark.parametrize("mode", MODES)
@pytest.mark.parametrize("bad", BAD, ids=BAD_IDS)
@pytest.mark.parametrize("state", ["UNKNOWN", "REFUSED"])
@pytest.mark.parametrize("kind", KINDS)
def test_cgl1_nonknown_bad_time_never_superseded(env, monkeypatch, kind, state, bad, mode):
    p = "SYN-L1A"
    items = _items(p, mode, [("c0", -15, _spec(kind, "KNOWN", KNOWN_VALUE[kind])), ("c1", -10, _spec(kind, state, None))])
    _craft(monkeypatch, p, "c1", bad)
    g = _run(env, items, p, mode)
    mi = _mi(g)
    assert _node(g).status == "ok" and mi["status"] != "evaluated"
    assert tok(kind) in mi["missing_inputs"]
    assert _gap_rows(mi, kind) and all(c["status"] == "not_evaluated" for c in _gap_rows(mi, kind))
    if kind == "current_medications":
        assert [f["state"] for f in mi["conversation_medication_facts"]] == ["KNOWN"]  # typed echo lists valid times only
        uses = [u for u in mi["conversation_fact_use"] if u["kind"] == kind and u["state"] == state]
        assert [(u["use"], u["reason"]) for u in uses] == [("not_used", tok(kind))]  # never "superseded"


@pytest.mark.parametrize("mode", MODES)
def test_cgl1_control_valid_times_flip_the_result(env, tmp_path, monkeypatch, mode):
    p = "SYN-L1CTL"
    items = _items(p, mode, [("c0", -15, _spec("current_medications", "KNOWN", ["warfarin"])),
                             ("c1", -10, _spec("current_medications", "UNKNOWN", None))])
    mi = _mi(_run(env, items, p, mode))
    assert tok("current_medications") not in mi["missing_inputs"]  # valid times: the later UNKNOWN is a plain open fact
    assert "conversation.current_medications=UNKNOWN" in mi["missing_inputs"]
    _craft(monkeypatch, p, "c1", "not-a-time")
    mi2 = _mi(_run(Env(tmp_path / "bad"), items, p, mode))  # same items, a fresh executor/store: only the time differs
    assert tok("current_medications") in mi2["missing_inputs"]


@pytest.mark.parametrize("mode", MODES)
@pytest.mark.parametrize("bad", BAD, ids=BAD_IDS)
@pytest.mark.parametrize("kind", KINDS)
def test_cgl1_known_bad_time_never_newest(env, monkeypatch, kind, bad, mode):
    p = "SYN-L1B"
    if kind == "current_medications":
        valid = _spec(kind, "UNKNOWN", None)
        record = "known"
    else:
        valid = _spec(kind, "KNOWN", KNOWN_VALUE[kind])
        record = "no_known_allergy"
    items = _items(p, mode, [("c0", -15, valid), ("c1", -10, _spec(kind, "KNOWN", OTHER_KNOWN[kind]))],
                   allergy_status_record=record)
    _craft(monkeypatch, p, "c1", bad)
    g = _run(env, items, p, mode)
    mi = _mi(g)
    assert _node(g).status == "ok" and mi["status"] != "evaluated"
    assert tok(kind) in mi["missing_inputs"]
    if kind == "current_medications":
        assert "conversation.current_medications=UNKNOWN" in mi["missing_inputs"]  # the older UNKNOWN stays open
    if kind == "allergy_status":  # the valid "present" is still the newest: the contradiction is found
        assert any(c["check"] == "allergy_contradiction" for c in mi["check_results"])


@pytest.mark.parametrize("mode", MODES)
@pytest.mark.parametrize("bad", BAD, ids=BAD_IDS)
def test_cgl1_known_bad_time_not_sent_to_provider(env, monkeypatch, bad, mode):
    p = "SYN-L1P"
    items = _items(p, mode, [("c1", -10, {"current_medications": ("KNOWN", ["warfarin"]),
                                           "allergens": ("KNOWN", ["latexzz"])})])
    _craft(monkeypatch, p, "c1", bad)
    mi = _mi(_run(env, items, p, mode))
    assert tok("current_medications") in mi["missing_inputs"] and mi["status"] != "evaluated"
    blob = json.dumps(mi["check_results"])
    assert f"{p}-c1" not in blob  # no check evaluated on a ref from the bad-time item
    assert "latexzz" not in blob and "warfarin" not in blob.lower()


# ------------------------------------------------------------------------------------------------ L1e

def test_cgl1_gates_version_bumped(env, monkeypatch):
    # L1 bumped to 6; later slices bump further. Require the format and a version at or past 6 (never a rollback).
    m = re.fullmatch(r"cg-pharma-gates-(\d+)", executor_mod.PHARMA_GATES_VERSION)
    assert m and int(m.group(1)) >= 6
    p = "SYN-L1V"
    items = _items(p, "unstaged", [])
    ex = env.executor()
    graph = lambda v: compile_graph(build_snapshot(items, T1, p), None, version=v, parent_version=v - 1 or None)  # noqa: E731
    a = ex.run_sync(graph(1))
    monkeypatch.setattr(executor_mod, "PHARMA_GATES_VERSION", "cg-pharma-gates-5")
    b = ex.run_sync(graph(2))
    assert _node(a).cache_key != _node(b).cache_key and not _node(b).cached


# ------------------------------------------------------------------------------------- one fact, one evidence ref

def test_cgl1_fact_refs_independent_of_bad_time_filter():
    from casegraph.conversation_meds import fact_refs
    a = fact("current_medications", value=["aspirin"], t="not-a-time", source_item="P-c1")
    w = fact("current_medications", value=["warfarin"], source_item="P-c1")
    w2 = fact("current_medications", value=["ibuprofen"], source_item="P-c1")
    full, filt = fact_refs((a, w, w2)), fact_refs((w, w2))
    assert full[id(w)] == filt[id(w)] == "conversation:current_medications:P-c1#0"
    assert full[id(w2)] == filt[id(w2)] == "conversation:current_medications:P-c1#1"
    assert full[id(a)] == "conversation:current_medications:P-c1#bad-time-0"


@pytest.mark.parametrize("mode", MODES)
@pytest.mark.parametrize("kind", ["current_medications", "allergens"])
def test_cgl1_same_source_item_refs_agree(env, monkeypatch, kind, mode):
    """Bad-time fact FIRST, valid fact of the same kind in the SAME source item: every ref the provider evidence
    cites must be the executor's own ref of the valid fact, and the consumed fact is not reported not_consumed."""
    p = "SYN-L1R"
    bad_name, good_name = ("aspirin", "warfarin") if kind == "current_medications" else ("latex", "penicillin")
    items = _items(p, mode, [("c1", -10, {kind: ("KNOWN", [good_name])})])
    orig = Executor._conversation_facts

    def wrapped(ctx):
        out = []
        for f in orig(ctx):
            if f.get("source_item") == f"{p}-c1" and f["kind"] == kind:
                bad = {**f, "value": [bad_name], "value_text": bad_name, "available_at_time": "not-a-time"}
                out += [bad, f]
            else:
                out.append(f)
        return tuple(out)

    monkeypatch.setattr(Executor, "_conversation_facts", staticmethod(wrapped))
    mi = _mi(_run(env, items, p, mode))
    good_ref, bad_ref = f"conversation:{kind}:{p}-c1#0", f"conversation:{kind}:{p}-c1#bad-time-0"
    assert tok(kind) in mi["missing_inputs"] and mi["status"] != "evaluated"
    blob = json.dumps(mi["check_results"])
    assert bad_ref not in blob and bad_name not in blob.lower()
    assert not any(f"not_consumed@{good_ref}" in m for m in mi["missing_inputs"])  # consumed valid fact: not a gap
    cited = {r for c in mi["check_results"] for r in c.get("evaluated_on", []) if r.startswith(f"conversation:{kind}:")}
    assert all(r.startswith(good_ref) for r in cited), cited  # never the bad fact's (or a shifted) ref
    if kind == "current_medications":
        assert good_ref in cited
        uses = {u["evidence_ref"]: u for u in mi["conversation_fact_use"] if u["kind"] == kind}
        assert uses[good_ref]["use"] != "not_used" and uses[bad_ref]["reason"] == tok(kind)


@pytest.mark.parametrize("mode", MODES)
@pytest.mark.parametrize("bad", BAD, ids=BAD_IDS)
@pytest.mark.parametrize("order", ["bad_newer", "bad_older"])
@pytest.mark.parametrize("kind", ["allergy_status", "allergens"])
def test_cgl1_f1_bad_time_allergy_fact_use_is_not_used(env, monkeypatch, kind, order, bad, mode):
    """L1-F1: an allergy-kind fact with a bad time is never sent to the provider, so fact_use must say not_used with the
    unparseable_time reason (never used / superseded), whether it would sort newer or older than the valid fact."""
    p = f"SYN-L1F1-{kind}-{order}"
    off_bad = -10 if order == "bad_newer" else -20
    items = _items(p, mode, [("c0", -15, _spec(kind, "KNOWN", KNOWN_VALUE[kind])),
                             ("c1", off_bad, _spec(kind, "KNOWN", OTHER_KNOWN[kind]))])
    _craft(monkeypatch, p, "c1", bad)
    mi = _mi(_run(env, items, p, mode))
    rows = [u for u in mi["conversation_fact_use"] if u["kind"] == kind and f"{p}-c1" in u["evidence_ref"]]
    assert [(u["use"], u["used"], u["reason"]) for u in rows] == [("not_used", False, tok(kind))]
    assert tok(kind) in mi["missing_inputs"] and mi["status"] != "evaluated"
