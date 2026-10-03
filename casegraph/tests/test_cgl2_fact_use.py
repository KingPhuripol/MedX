"""Slice cg-l2: ConversationFactUse.used is derived from use (a superseded fact is not reported as used).
Synthetic, offline, mock only. Research prototype: not clinical performance."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from casegraph import executor as executor_mod
from casegraph.compiler import build_snapshot, compile_graph
from casegraph.data import ConversationFactUse
from casegraph.staged import build_versions
from casegraph.types import NodeType

from .fixtures import H, M
from .staged_fixtures import T1, allergy, base, conv_meds, order

USES = ["used", "partial", "not_used", "superseded"]
REASON = {"used": None, "partial": "formulary@x", "not_used": "conversation.allergens=UNKNOWN", "superseded": None}


def _row(use, **kw):
    return dict(kind="allergens", evidence_ref="conversation:allergens:c#0", state="KNOWN", use=use,
                reason=REASON[use], **kw)


@pytest.mark.parametrize("use", USES)
def test_used_is_derived_from_use(use):
    assert ConversationFactUse(**_row(use)).used is (use == "used")


@pytest.mark.parametrize("use", USES)
def test_inconsistent_used_is_rejected(use):
    with pytest.raises(ValidationError):
        ConversationFactUse(**_row(use, used=use != "used"))
    assert ConversationFactUse(**_row(use, used=use == "used")).used is (use == "used")  # consistent: accepted


@pytest.mark.parametrize("use", USES)
def test_reason_contract(use):
    bad = None if REASON[use] else "some:token"
    with pytest.raises(ValidationError):
        ConversationFactUse(**{**_row(use), "reason": bad})


def test_round_trip():
    for use in USES:
        a = ConversationFactUse(**_row(use))
        assert ConversationFactUse.model_validate(a.model_dump()) == a
        assert ConversationFactUse.model_validate_json(a.model_dump_json()) == a


CASES = {  # kind, state of the older fact -> (older conv kwargs, newer conv kwargs, token fragment that must be absent)
    ("allergy_status", "UNKNOWN"): ({"allergy_status": ("UNKNOWN", None)},
                                    {"allergy_status": ("KNOWN", "present"), "allergens": ("KNOWN", ["penicillin"])}),
    ("allergy_status", "REFUSED"): ({"allergy_status": ("REFUSED", None)}, {"allergy_status": ("KNOWN", "absent")}),
    ("allergens", "UNKNOWN"): ({"allergens": ("UNKNOWN", None)},
                               {"allergy_status": ("KNOWN", "present"), "allergens": ("KNOWN", ["sulfa"])}),
    ("current_medications", "UNKNOWN"): ({"meds": ("UNKNOWN", None)}, {"meds": ("KNOWN", ["warfarin"])}),
}


def _case_items(p, old, new, with_old):
    items = [*base(p, with_allergy=False), allergy(p, f"{p}-al", T1 - 48 * 60 * M, status="known")]
    if with_old:
        items.append(conv_meds(p, f"{p}-c1", T1 - 30 * M, **({"meds": None} | old)))
    items.append(conv_meds(p, f"{p}-c2", T1 - 15 * M, **({"meds": None} | new)))
    items.append(order(p, f"{p}-o", T1 + 30 * M))
    return items


def _mi(env, items):
    return build_versions(env.executor(), items, T1, T1 + 2 * H)[-1].by_type(NodeType.PHARMA_AGENT).output[
        "MedicationIssues"]


@pytest.mark.parametrize("kind,state", sorted(CASES))
def test_superseded_is_not_a_gap(env, kind, state):
    old, new = CASES[(kind, state)]
    p = f"SYN-L2-{kind}-{state}"
    with_old = _mi(env, _case_items(p, old, new, True))
    env.root = env.root / "without"
    without = _mi(env, _case_items(p, old, new, False))
    rows = [u for u in with_old["conversation_fact_use"] if u["kind"] == kind and u["state"] == state]
    assert [(u["use"], u["used"], u["reason"]) for u in rows] == [("superseded", False, None)]
    assert not any(rows[0]["evidence_ref"] in t or t.endswith(f"={state}") and kind in t
                   for t in with_old["missing_inputs"]), with_old["missing_inputs"]
    assert (with_old["status"], with_old["missing_inputs"]) == (without["status"], without["missing_inputs"])


def test_gates_7_constant_and_no_stale_hit(env, monkeypatch):
    assert executor_mod.PHARMA_GATES_VERSION == "cg-pharma-gates-9"
    p = "SYN-L2-VER"
    items = [*base(p), order(p, f"{p}-o", T1)]
    ex = env.executor()
    run = lambda v: ex.run_sync(compile_graph(build_snapshot(items, T1, p), None, version=v,  # noqa: E731
                                              parent_version=v - 1 or None)).by_type(NodeType.PHARMA_AGENT)
    monkeypatch.setattr(executor_mod, "PHARMA_GATES_VERSION", "cg-pharma-gates-6")
    old = run(1)
    monkeypatch.undo()
    new = run(2)
    assert not new.cached and new.cache_key != old.cache_key
