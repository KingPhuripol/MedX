"""Slice cg-t123 round 4: medications and allergies the patient states in the conversation are consumed by the S5
Pharma Agent or reported as not evaluated (never silently dropped, never 'evaluated'). Synthetic, offline, mock only.
Research prototype: not clinical performance."""

from __future__ import annotations

import pytest

from casegraph.executor import PHARMA_FACT_KINDS
from casegraph.sources import s1r
from casegraph.staged import build_versions
from casegraph.types import NodeType

from .fixtures import M
from .staged_fixtures import FIXTURES_STAGED, T1, allergy, base, conv_meds, order

CONV_REF = "conversation:current_medications#0"


@pytest.fixture(scope="module")
def dataset(s1r_dataset):
    return s1r_dataset


def _t3(env, items, horizon=None):
    t3 = build_versions(env.executor(), items, T1, horizon or T1 + 120 * M)[-1]
    assert t3.stage == "T3"
    return t3, t3.by_type(NodeType.PHARMA_AGENT).output["MedicationIssues"]


def _med_items(p, meds, **kw):
    return [*base(p, with_allergy=False), allergy(p, f"{p}-al", T1 - 48 * 60 * M, status="no_known_allergy"),
            conv_meds(p, f"{p}-conv", T1 - 15 * M, meds=meds, **kw), order(p, f"{p}-o", T1 + 30 * M)]


def _rows(mi, check):
    return [c for c in mi["check_results"] if c["check"] == check]


def test_warfarin_known_becomes_patient_reported_source_and_reaches_the_pharmacist(env):
    t3, mi = _t3(env, _med_items("SYN-WARF", ("KNOWN", ["warfarin"])))
    pharma = t3.by_type(NodeType.PHARMA_AGENT)
    # S5 evaluated on the conversation source (it is a read ref of the Pharma node's checks)
    assert any(CONV_REF in c["evaluated_on"] for c in mi["check_results"])
    # S5 omission rule: warfarin (patient reported) is absent from the new order -> an issue citing the conversation ref
    omissions = [i for i in mi["issues"] if "warfarin" in i["ingredients"]]
    assert omissions, mi["issues"]
    srcs = {(s["source_type"], s["evidence_ref"]) for i in omissions for s in i["conflicting_sources"]}
    assert ("patient_reported", CONV_REF) in srcs
    # pharmacist payload (structured) shows the medication fact and that it was used
    shown = t3.by_type(NodeType.HUMAN_CHECKPOINT).output["pending_review"]["for_review"]["pharma_agent"][
        "MedicationIssues"]
    assert [f["value"] for f in shown["conversation_medication_facts"]] == [["warfarin"]]
    use = [u for u in shown["conversation_fact_use"] if u["kind"] == "current_medications"]
    assert use == [{"kind": "current_medications", "evidence_ref": CONV_REF, "state": "KNOWN", "used": True,
                    "reason": None}]
    assert pharma.errored_inputs == ()
    assert not _rows(mi, "medication_conversation")


def test_unknown_conversation_meds_not_evaluated_with_missing_input(env):
    t3, mi = _t3(env, _med_items("SYN-MUNK", ("UNKNOWN", None)))
    (row,) = _rows(mi, "medication_conversation")
    assert row["status"] == "not_evaluated" and row["fired"] is None
    assert row["missing_inputs"] == ["conversation.current_medications=UNKNOWN"]
    assert mi["status"] != "evaluated" and "conversation.current_medications=UNKNOWN" in mi["missing_inputs"]
    use = [u for u in mi["conversation_fact_use"] if u["kind"] == "current_medications"]
    assert [(u["used"], u["reason"]) for u in use] == [(False, "conversation.current_medications=UNKNOWN")]


def test_refused_and_malformed_conversation_meds_not_evaluated(env):
    for n, (meds, token) in enumerate([(("REFUSED", None), "conversation.current_medications=REFUSED"),
                                       (("KNOWN", "warfarin"), "conversation.current_medications:unparseable"),
                                       (("KNOWN", ["warfarin", 7]), "conversation.current_medications:unparseable")]):
        env.root = env.root / f"c{n}"
        _, mi = _t3(env, _med_items(f"SYN-MBAD{n}", meds))
        assert token in mi["missing_inputs"] and mi["status"] != "evaluated", (meds, mi["status"])


def test_unmapped_drug_name_is_not_silently_dropped(env):
    t3, mi = _t3(env, _med_items("SYN-MUNM", ("KNOWN", ["zzzdrugx"])))
    rows = [c for c in mi["check_results"] if c["check"] == "unrecognised_drug"]
    assert rows and rows[0]["status"] == "not_evaluated"
    assert rows[0]["missing_inputs"] == [f"formulary@{CONV_REF}"]
    assert mi["status"] != "evaluated"
    assert [f["value"] for f in mi["conversation_medication_facts"]] == [["zzzdrugx"]]


def test_known_empty_list_is_an_explicit_none_not_a_gap(env):
    _, mi = _t3(env, _med_items("SYN-MNONE", ("KNOWN", [])))
    assert not _rows(mi, "medication_conversation")
    assert [u["used"] for u in mi["conversation_fact_use"] if u["kind"] == "current_medications"] == [True]


def test_superseded_unknown_is_not_an_open_input(env):
    p = "SYN-MSUP"
    items = [*_med_items(p, ("UNKNOWN", None)), conv_meds(p, f"{p}-conv2", T1 - 10 * M, meds=("KNOWN", ["warfarin"]))]
    _, mi = _t3(env, items)
    assert not _rows(mi, "medication_conversation")


def test_conversation_allergy_status_unknown_is_not_evaluated(env):
    _, mi = _t3(env, _med_items("SYN-ASTAT", ("KNOWN", []), allergy_status=("UNKNOWN", None)))
    assert "conversation.allergy_status=UNKNOWN" in mi["missing_inputs"] and mi["status"] != "evaluated"


def test_unparseable_conversation_allergen_is_not_dropped(env):
    _, mi = _t3(env, _med_items("SYN-AUNP", ("KNOWN", []), allergy_status=("KNOWN", "present"),
                                allergens=("KNOWN", ["sulfa", 3])))
    assert "conversation.allergens:unparseable" in mi["missing_inputs"] and mi["status"] != "evaluated"


# ------------------------------------------------------------------ property: unused fact => never 'evaluated'

VARIANTS = {
    "none": {},
    "warfarin": {"meds": ("KNOWN", ["warfarin"])},
    "unmapped": {"meds": ("KNOWN", ["zzzdrugx"])},
    "unknown": {"meds": ("UNKNOWN", None)},
    "malformed": {"meds": ("KNOWN", ["warfarin", 7])},
    "allergy_unknown": {"meds": ("KNOWN", ["warfarin"]), "allergy_status": ("UNKNOWN", None)},
}


def _check_property(graphs, label):
    t3 = [g for g in graphs if g.stage == "T3"]
    if not t3:
        return 0
    node = t3[0].by_type(NodeType.PHARMA_AGENT)
    mi = node.output["MedicationIssues"]
    reader = t3[0].by_type(NodeType.READER_TEXT)
    assert reader is not None and reader.status == "ok", label
    present = [v for v in reader.output["Findings"].get("intake", ()) if v["kind"] in PHARMA_FACT_KINDS]
    use = mi["conversation_fact_use"]
    assert len(use) == len(present), (label, len(use), len(present))  # every conversation fact is accounted for
    for u in use:
        if not u["used"]:
            assert mi["status"] != "evaluated", (label, u)
            assert u["reason"] in mi["missing_inputs"], (label, u, mi["missing_inputs"])
    for c in mi["check_results"]:
        if c["status"] == "evaluated" and c["check"] in ("allergy_conversation", "medication_conversation"):
            raise AssertionError((label, c))
    return 1


@pytest.mark.parametrize("variant", sorted(VARIANTS))
def test_no_pharma_output_is_evaluated_while_a_conversation_fact_is_unused(env, dataset, variant):
    checked = 0
    cases = []
    for name, fx in sorted(FIXTURES_STAGED.items()):
        p, items, horizon = fx()
        cases.append((name, p, items, T1, horizon))
    for path in s1r.snapshot_paths(dataset, "dev"):
        if path.name == "snapshot_T1.json":
            sc = s1r.load_staged_case(dataset, "dev", path.parent.name, "T2")
            cases.append((path.parent.name, sc.items[0].patient_ref, sc.items, sc.t1, sc.horizon))
    assert len(cases) >= 40
    for n, (name, p, items, t1, horizon) in enumerate(cases):
        if VARIANTS[variant]:
            items = [*items, conv_meds(p, f"{p}-cm-{variant}", t1 - 15 * M, **VARIANTS[variant])]
        env.root = env.root / f"v{n}"
        graphs = build_versions(env.executor(), items, t1, horizon)
        checked += _check_property(graphs, (variant, name))
    assert checked >= 20
