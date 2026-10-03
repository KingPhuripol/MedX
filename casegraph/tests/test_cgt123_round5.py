"""Slice cg-t123 round 5: Pharma gates apply whenever Pharma runs (staged or not), one shared timestamp ordering for
conversation facts (parsed aware datetimes, conservative tie-break), every pending stage is built, fact_use accuracy
and real evidence refs. Synthetic, offline, mock only. Research prototype: not clinical performance."""

from __future__ import annotations

from datetime import timedelta, timezone

import pytest

from casegraph import executor as executor_mod
from casegraph.compiler import build_snapshot, compile_graph, compile_stage
from casegraph.conversation_meds import newest, order_key, parse_ts, same_time_conflict
from casegraph.stages import plan_stages
from casegraph.staged import build_versions, next_stage, next_stages
from casegraph.store import OutputStore, SQLiteStateStore
from casegraph.types import NodeType

from .fixtures import H, M, labs
from .staged_fixtures import T1, allergy, base, conv_meds, order

BKK = timezone(timedelta(hours=7))


def _pharma(g):
    return g.by_type(NodeType.PHARMA_AGENT)


def _mi(g):
    return _pharma(g).output["MedicationIssues"]


def _unstaged(env, items, p, ex=None, version=1):
    graph = compile_graph(build_snapshot(items, T1, p), None, version=version, parent_version=version - 1 or None)
    return (ex or env.executor()).run_sync(graph)


def _t3_graph(items, p, ex, version=2):
    return ex.run_sync(compile_stage(build_snapshot(items, T1, p), "T3", None, version, version - 1 or None,
                                     trigger_refs=(f"{p}-o",)))


def _fresh_executor(env, tmp_path, name):
    return executor_mod.Executor(env.gateways, OutputStore(tmp_path / f"{name}-o"),
                                 SQLiteStateStore(tmp_path / f"{name}.db"))


# ------------------------------------------------------------------------------------------------------- R5-1

def test_unstaged_s5_without_allergy_list_is_not_evaluated(env):
    p = "SYN-R5-NOAL"
    mi = _mi(_unstaged(env, [*base(p, with_allergy=False), order(p, f"{p}-o", T1)], p))
    assert mi["status"] != "evaluated" and "AllergyList" in mi["missing_inputs"]
    assert any(c["check"] == "allergy_record" and c["status"] == "not_evaluated" for c in mi["check_results"])


def test_unstaged_s5_with_unknown_conversation_meds_is_not_evaluated(env):
    p = "SYN-R5-UNKM"
    items = [*base(p), conv_meds(p, f"{p}-cm", T1 - 15 * M, meds=("UNKNOWN", None)), order(p, f"{p}-o", T1)]
    mi = _mi(_unstaged(env, items, p))
    assert mi["status"] != "evaluated" and "conversation.current_medications=UNKNOWN" in mi["missing_inputs"]
    assert [u["used"] for u in mi["conversation_fact_use"]] == [False]  # facts and use are reported unstaged too


@pytest.mark.parametrize("meds", [None, ("UNKNOWN", None)])
def test_unstaged_then_t3_on_a_shared_store_equals_a_fresh_t3(env, tmp_path, meds):
    p = "SYN-R5-SHARE"
    items = [*base(p, with_allergy=False), order(p, f"{p}-o", T1)]
    if meds:
        items.append(conv_meds(p, f"{p}-cm", T1 - 15 * M, meds=meds))
    shared = env.executor()
    first = _unstaged(env, items, p, ex=shared)
    served = _t3_graph(items, p, shared)  # same Output Store: a hit must be the T3-correct output
    fresh = _t3_graph(items, p, _fresh_executor(env, tmp_path, "fresh"), version=1)
    assert _pharma(served).output_sha256 == _pharma(fresh).output_sha256
    # the gates no longer depend on how the graph was compiled (derived refs differ, the gate outcome does not)
    assert (_mi(first)["status"], _mi(first)["missing_inputs"]) == (_mi(fresh)["status"], _mi(fresh)["missing_inputs"])
    assert _mi(served)["status"] != "evaluated" and "AllergyList" in _mi(served)["missing_inputs"]


def test_pharma_input_hash_carries_the_gate_semantics_version(env, monkeypatch):
    p = "SYN-R5-VER"
    items = [*base(p), order(p, f"{p}-o", T1)]
    ex = env.executor()
    a = _unstaged(env, items, p, ex=ex)
    monkeypatch.setattr(executor_mod, "PHARMA_GATES_VERSION", "cg-pharma-gates-next")
    b = _unstaged(env, items, p, ex=ex, version=2)
    assert _pharma(a).cache_key != _pharma(b).cache_key and not _pharma(b).cached  # an old entry is never served


# ------------------------------------------------------------------------------------------------------- R5-2

def test_shared_ordering_helper_uses_parsed_datetimes_and_conservative_tie():
    early_bkk = {"kind": "k", "state": "KNOWN", "value": "absent", "available_at_time": "2026-01-01T15:30:00+07:00"}
    late_utc = {"kind": "k", "state": "KNOWN", "value": "present", "available_at_time": "2026-01-01T08:45:00Z"}
    assert "15:30" > "08:45"  # string order would call the older fact newest
    assert parse_ts(early_bkk["available_at_time"]) < parse_ts(late_utc["available_at_time"])
    assert newest([early_bkk, late_utc]) is late_utc and newest([late_utc, early_bkk]) is late_utc
    tie_known = {**late_utc, "value": "absent"}
    tie_unknown = {**late_utc, "state": "UNKNOWN", "value": None}
    assert newest([tie_known, late_utc, tie_unknown]) is tie_unknown  # a non-KNOWN fact wins a tie
    assert newest([tie_unknown, late_utc]) is newest([late_utc, tie_unknown])  # input-order independent
    assert same_time_conflict([late_utc, tie_known], late_utc) and not same_time_conflict([late_utc], late_utc)
    assert order_key(late_utc) == order_key(dict(late_utc))


def _contradiction_items(p, early_tz, late_tz):
    return [*base(p, with_allergy=False), allergy(p, f"{p}-al", T1 - 48 * 60 * M, status="no_known_allergy"),
            conv_meds(p, f"{p}-c1", (T1 - 30 * M).astimezone(early_tz), meds=None, allergy_status=("KNOWN", "absent")),
            conv_meds(p, f"{p}-c2", (T1 - 15 * M).astimezone(late_tz), meds=None, allergy_status=("KNOWN", "present"),
                      allergens=("KNOWN", ["penicillin"])),
            order(p, f"{p}-o", T1 + 30 * M)]


@pytest.mark.parametrize("early_tz,late_tz", [(BKK, timezone.utc), (timezone.utc, BKK), (timezone.utc, timezone.utc)])
def test_mixed_offsets_allergy_contradiction_is_always_found(env, early_tz, late_tz):
    p = "SYN-R5-TZA"
    t3 = build_versions(env.executor(), _contradiction_items(p, early_tz, late_tz), T1, T1 + 2 * H)[-1]
    mi = _mi(t3)
    assert mi["status"] != "evaluated"
    assert any(c["check"] == "allergy_contradiction" for c in mi["check_results"]), mi["missing_inputs"]


def test_mixed_offsets_unknown_meds_newer_than_a_known_list_stays_open(env):
    p = "SYN-R5-TZM"
    items = [*base(p), conv_meds(p, f"{p}-c1", (T1 - 10 * M).astimezone(BKK), meds=("KNOWN", ["warfarin"])),
             conv_meds(p, f"{p}-c2", T1 - 5 * M, meds=("UNKNOWN", None)), order(p, f"{p}-o", T1 + 30 * M)]
    mi = _mi(build_versions(env.executor(), items, T1, T1 + 2 * H)[-1])
    assert "conversation.current_medications=UNKNOWN" in mi["missing_inputs"] and mi["status"] != "evaluated"
    unknown = [u for u in mi["conversation_fact_use"] if u["kind"] == "current_medications" and u["state"] == "UNKNOWN"]
    assert [(u["use"], u["used"]) for u in unknown] == [("not_used", False)]


@pytest.mark.parametrize("kind,specs", [
    ("allergy_status", [("KNOWN", "present"), ("UNKNOWN", None)]),
    ("allergens", [("KNOWN", ["penicillin"]), ("KNOWN", ["sulfa"])]),
])
def test_same_time_tie_is_a_reported_conflict_never_safe(env, kind, specs):
    p = "SYN-R5-TIE"
    items = [*base(p, with_allergy=False), allergy(p, f"{p}-al", T1 - 48 * 60 * M, status="known")]
    for k, spec in enumerate(specs):
        items.append(conv_meds(p, f"{p}-c{k}", T1 - 15 * M, meds=None, **{kind: spec}))
    items.append(order(p, f"{p}-o", T1 + 30 * M))
    mi = _mi(build_versions(env.executor(), items, T1, T1 + 2 * H)[-1])
    assert f"conversation.{kind}:same_time_conflict" in mi["missing_inputs"] and mi["status"] != "evaluated"
    open_ = [u for u in mi["conversation_fact_use"] if u["kind"] == kind and not u["used"]]
    assert open_ and all(u["reason"] in mi["missing_inputs"] for u in open_)


def test_tie_outcome_is_independent_of_item_order(env, tmp_path):
    p = "SYN-R5-TIEO"
    c = [conv_meds(p, f"{p}-c{k}", T1 - 15 * M, meds=None, allergy_status=s)
         for k, s in enumerate([("KNOWN", "present"), ("UNKNOWN", None)])]
    out = []
    for n, items_c in enumerate((c, c[::-1])):
        items = [*base(p, with_allergy=False), allergy(p, f"{p}-al", T1 - 48 * 60 * M), *items_c,
                 order(p, f"{p}-o", T1 + 30 * M)]
        mi = _mi(build_versions(_fresh_executor(env, tmp_path, f"t{n}"), items, T1, T1 + 2 * H)[-1])
        out.append(sorted((u["kind"], u["state"], u["used"], u["reason"]) for u in mi["conversation_fact_use"]))
    assert out[0] == out[1]


# ------------------------------------------------------------------------------------------------------- R5-3

@pytest.mark.parametrize("spec,as_of_min", [
    ([("lab", "lab1", 40), ("order", "o1", 70)], 80),
    ([("lab", "lab1", 40), ("order", "o1", 70)], 50),
    ([("order", "o1", 30), ("lab", "lab1", 40)], 50),
    ([("order", "o1", 30), ("lab", "lab1", 30)], 50),
])
def test_next_stages_equals_the_planned_stage_list(spec, as_of_min):
    p = "SYN-R5-NS"
    items = list(base(p))
    for kind, iid, minutes in spec:
        t = T1 + minutes * M
        items.append(labs(p, iid, t, t) if kind == "lab" else order(p, iid, t))
    parent = compile_stage(build_snapshot(items, T1, p), "T1", None, 1, None).spec
    as_of = T1 + as_of_min * M
    got = next_stages(parent, items, as_of)
    want = plan_stages(items, T1, as_of)[1:]
    assert [(g.stage, g.trigger_item_ids) for g in got] == [(w.stage, w.trigger_item_ids) for w in want]
    assert [g.T for g in got[:-1]] == [w.T for w in want[:-1]] and got[-1].T == as_of
    assert next_stage(parent, items, as_of)[0] == want[-1].stage


# ------------------------------------------------------------------------------------------------------- R5-4

def test_superseded_older_non_known_allergy_fact_is_marked_superseded(env):
    p = "SYN-R5-SUPA"
    items = [*base(p, with_allergy=False), allergy(p, f"{p}-al", T1 - 48 * 60 * M, status="known"),
             conv_meds(p, f"{p}-c1", T1 - 30 * M, meds=None, allergy_status=("UNKNOWN", None)),
             conv_meds(p, f"{p}-c2", T1 - 15 * M, meds=None, allergy_status=("KNOWN", "present"),
                       allergens=("KNOWN", ["penicillin"])), order(p, f"{p}-o", T1 + 30 * M)]
    mi = _mi(build_versions(env.executor(), items, T1, T1 + 2 * H)[-1])
    st = [(u["state"], u["use"], u["used"], u["reason"]) for u in mi["conversation_fact_use"]
          if u["kind"] == "allergy_status"]
    assert st == [("UNKNOWN", "superseded", False, None), ("KNOWN", "used", True, None)]
    assert "conversation.allergy_status=UNKNOWN" not in mi["missing_inputs"]


def test_partly_unmapped_known_medication_fact_is_partial_not_used(env):
    p = "SYN-R5-PART"
    items = [*base(p), conv_meds(p, f"{p}-cm", T1 - 15 * M, meds=("KNOWN", ["warfarin", "zzzdrugx"])),
             order(p, f"{p}-o", T1 + 30 * M)]
    mi = _mi(build_versions(env.executor(), items, T1, T1 + 2 * H)[-1])
    (u,) = [u for u in mi["conversation_fact_use"] if u["kind"] == "current_medications"]
    ref = f"conversation:current_medications:{p}-cm#0"
    assert (u["evidence_ref"], u["use"], u["used"]) == (ref, "partial", False)
    assert u["reason"] == f"formulary@{ref}" and u["reason"] in mi["missing_inputs"] and mi["status"] != "evaluated"


def test_conversation_refs_are_real_item_ids_and_unique(env):
    p = "SYN-R5-REFS"
    items = [*base(p, with_allergy=False), allergy(p, f"{p}-al", T1 - 48 * 60 * M, status="known"),
             conv_meds(p, f"{p}-c1", T1 - 30 * M, meds=("KNOWN", ["warfarin"]), allergens=("KNOWN", ["sulfa"])),
             conv_meds(p, f"{p}-c2", T1 - 15 * M, meds=("KNOWN", ["warfarin"]), allergens=("KNOWN", ["latex"])),
             order(p, f"{p}-o", T1 + 30 * M)]
    mi = _mi(build_versions(env.executor(), items, T1, T1 + 2 * H)[-1])
    refs = [u["evidence_ref"] for u in mi["conversation_fact_use"]]
    assert len(refs) == len(set(refs)) == 4  # two medication facts, two allergens facts: no collisions
    assert sorted(refs) == sorted(f"conversation:{k}:{p}-{c}#0" for k in ("current_medications", "allergens")
                                  for c in ("c1", "c2"))
    cited = {s["evidence_ref"] for i in mi["issues"] for s in i["conflicting_sources"]}
    assert not any(r.startswith(("conversation:allergens#", "conversation:current_medications#")) for r in cited)


@pytest.mark.parametrize("old_value,use", [
    (["penicillin", {"name": "amoxicillin"}], "partial"),
    (["penicillin", 7], "partial"),
    (["penicillin", "  "], "partial"),
    ("penicillin", "not_used"),
])
@pytest.mark.parametrize("staged", [True, False])
def test_older_unparseable_allergens_fact_is_never_silently_dropped(env, old_value, use, staged):
    """Integration audit round 5 (B1-r5): S5 reads every KNOWN allergens fact, so a bad entry in an OLDER fact is a gap
    too, not only in the newest one."""
    p = f"SYN-R5-OLDAL-{staged}-{use}-{len(str(old_value))}"
    items = [*base(p, with_allergy=False), allergy(p, f"{p}-al", T1 - 48 * 60 * M, status="known"),
             conv_meds(p, f"{p}-c1", T1 - 30 * M, meds=None, allergy_status=("KNOWN", "present"),
                       allergens=("KNOWN", old_value)),
             conv_meds(p, f"{p}-c2", T1 - 15 * M, meds=None, allergens=("KNOWN", ["sulfa"])),
             order(p, f"{p}-o", T1 + 30 * M if staged else T1)]
    g = build_versions(env.executor(), items, T1, T1 + 2 * H)[-1] if staged else _unstaged(env, items, p)
    assert g.stage == ("T3" if staged else None)
    mi = _mi(g)
    assert mi["status"] != "evaluated"
    assert "conversation.allergens:unparseable" in mi["missing_inputs"]
    old = [u for u in mi["conversation_fact_use"] if u["kind"] == "allergens" and f"{p}-c1" in u["evidence_ref"]]
    assert [(u["use"], u["used"], u["reason"]) for u in old] == [(use, False, "conversation.allergens:unparseable")]


@pytest.mark.parametrize("value", ["Present", "yes", 7, {"present": True}])
def test_unrecognised_known_allergy_status_is_a_gap_not_no_allergy(env, value):
    """Safety review L8 / audit N1: a KNOWN allergy_status outside the closed set is never read as "not present"."""
    p = f"SYN-R5-ALST-{len(str(value))}-{type(value).__name__}"
    items = [*base(p, with_allergy=False), allergy(p, f"{p}-al", T1 - 48 * 60 * M, status="no_known_allergy"),
             conv_meds(p, f"{p}-c1", T1 - 15 * M, meds=None, allergy_status=("KNOWN", value)),
             order(p, f"{p}-o", T1 + 30 * M)]
    mi = _mi(build_versions(env.executor(), items, T1, T1 + 2 * H)[-1])
    assert mi["status"] != "evaluated"
    assert "conversation.allergy_status:unrecognised" in mi["missing_inputs"]
    st = [(u["use"], u["used"]) for u in mi["conversation_fact_use"] if u["kind"] == "allergy_status"]
    assert st == [("not_used", False)]
