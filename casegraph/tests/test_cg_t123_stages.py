"""Slice cg-t123 A1/A2: the stage planner and the shape of every staged version. Synthetic, offline, mock only.

Claim boundary: system-behaviour check. The staging rule, fixtures and gold come from the same authors, so
agreement shows only that the compiler follows its own declared rule.
"""

from __future__ import annotations

import json
from collections import Counter
from datetime import datetime
from pathlib import Path

import pytest

from casegraph.compiler import GraphValidationError, build_snapshot, compile_stage, validate
from casegraph.sources import s1r
from casegraph.staged import build_versions
from casegraph.stages import plan_stages
from casegraph.types import NodeType

from .staged_fixtures import FIXTURES_STAGED, GOLD_STAGES, T1, stage_list

ROLE = {"T1": "human:nurse", "T2": "human:physician", "T3": "human:pharmacist"}
REASONING_TASK = {"T1": "department", "T2": "care", "T3": None}


@pytest.fixture(scope="module")
def dataset(s1r_dataset) -> Path:
    return s1r_dataset


def _iso(s: str) -> datetime:
    return datetime.fromisoformat(s)


def gold_stages(raw_items: list[dict], t1: datetime, horizon: datetime) -> list[str]:
    """Independent gold from raw JSON ``available_at_time`` only (not from casegraph.stages)."""
    arrivals: dict[datetime, set[str]] = {}
    for it in raw_items:
        at = _iso(it["available_at_time"])
        if not (t1 < at <= horizon):
            continue
        if it["data_type"] in ("LabSeries", "CXRImage", "CTVolume", "MRIVolume"):
            arrivals.setdefault(at, set()).add("T2")
        elif it["data_type"] == "MedicationList" and it.get("list_source") == "new_order":
            arrivals.setdefault(at, set()).add("T3")
    out = ["T1"]
    for at in sorted(arrivals):
        out += [s for s in ("T2", "T3") if s in arrivals[at]]
    return out


# ------------------------------------------------------------------------------------------ A1


@pytest.mark.parametrize("name", sorted(FIXTURES_STAGED))
def test_stage_plan_fixtures(name):
    _, items, horizon = FIXTURES_STAGED[name]()
    plans = plan_stages(items, T1, horizon)
    assert [p.stage for p in plans] == GOLD_STAGES[name]
    assert plans[0].T == T1 and plans[0].trigger_item_ids == ()
    assert all(T1 < p.T <= horizon for p in plans[1:])


def test_f_same_has_equal_t_and_f_cxr_triggers():
    p, items, horizon = FIXTURES_STAGED["F-SAME"]()
    plans = plan_stages(items, T1, horizon)
    assert plans[1].T == plans[2].T and (plans[1].stage, plans[2].stage) == ("T2", "T3")
    assert plans[1].trigger_item_ids == (f"{p}-labs",) and plans[2].trigger_item_ids == (f"{p}-order",)
    p, items, horizon = FIXTURES_STAGED["F-CXR"]()
    assert [x.trigger_item_ids for x in plan_stages(items, T1, horizon)] == [(), (f"{p}-cxr",), (f"{p}-order",)]


def test_nontrigger_arrivals_never_create_a_version():
    from .fixtures import M, s4_intake, vitals
    from .staged_fixtures import home

    p, items, horizon = FIXTURES_STAGED["F-PRE"]()
    late_vitals = vitals(p, f"{p}-vs-late", horizon - 10 * M, horizon - 9 * M)
    late_intake = s4_intake(p, f"{p}-late", horizon - 30 * M)  # new facts/demographics after t1
    late_home = home(p, f"{p}-late-home", horizon)  # a home list is not an order
    assert stage_list([*items, late_vitals, *late_intake, late_home], horizon) == ["T1"]


def test_horizon_bounds_are_inclusive_exclusive():
    p, items, _ = FIXTURES_STAGED["F-CXR"]()
    order_at = next(i.available_at_time for i in items if i.item_id.endswith("order"))
    assert stage_list(items, order_at) == ["T1", "T2", "T3"]  # available_at_time == horizon is a trigger
    assert stage_list(items, order_at - (order_at - T1) / 1000) == ["T1", "T2"]
    assert plan_stages(items, order_at, order_at) == [plan_stages(items, order_at, order_at)[0]]  # t1 itself: none


def test_stage_plan_synthetic_v1(dataset):
    """SYN seed 20260926, all 3 splits (200 cases = 400 lists): the emitted list equals the independent gold."""
    counts: dict[str, Counter] = {"T1": Counter(), "T2": Counter()}
    for split in s1r.SPLITS:
        for path in s1r.snapshot_paths(dataset, split):
            if path.name != "snapshot_T1.json":
                continue
            case = path.parent.name
            raw = json.loads((path.parent / "journey.json").read_text())["items"]
            for point in ("T1", "T2"):
                sc = s1r.load_staged_case(dataset, split, case, point)
                got = [p.stage for p in plan_stages(sc.items, sc.t1, sc.horizon)]
                assert got == gold_stages(raw, sc.t1, sc.horizon), (case, point)
                counts[point][tuple(got)] += 1
    assert counts["T1"] == {("T1",): 200}
    assert counts["T2"] == {("T1", "T3", "T2"): 180, ("T1", "T2"): 20}


# ------------------------------------------------------------------------------------------ A2


def _check_structure(graphs):
    for g in graphs:
        spec_nodes = {n.type: n for n in g.nodes}
        hcs = [n for n in g.nodes if n.type is NodeType.HUMAN_CHECKPOINT]
        rfs = [n for n in g.nodes if n.type is NodeType.RED_FLAG]
        assert len(hcs) == 1 and hcs[0].provider == ROLE[g.stage]
        assert len(rfs) == 1
        assert any(e.src == rfs[0].id and e.dst == hcs[0].id and e.data_type == "Alerts" for e in g.edges)
        assert (NodeType.PHARMA_AGENT in spec_nodes) == (g.stage == "T3")
        task = REASONING_TASK[g.stage]
        if task is None:
            assert NodeType.REASONING not in spec_nodes
        else:
            assert spec_nodes[NodeType.REASONING].params["task"] == task
        validate(g.spec())  # the exported structure is a valid graph
        assert all(r.available_at_time <= g.T for r in g.evidence)


@pytest.mark.parametrize("name", ["F-CXR", "F-T3ONLY", "F-SAME", "F-PRE", "F-FUTURE", "F-RED", "F-STALE"])
def test_stage_structure_fixtures(env, name):
    _, items, horizon = FIXTURES_STAGED[name]()
    graphs = build_versions(env.executor(), items, T1, horizon)
    assert [g.stage for g in graphs] == GOLD_STAGES[name]
    assert [g.version for g in graphs] == list(range(1, len(graphs) + 1))
    assert [g.parent_version for g in graphs] == [None, *range(1, len(graphs))]
    _check_structure(graphs)
    assert all(g.schema_version == "casegraph-export/0.4" for g in graphs)


def test_stage_structure_syn_dev(env, dataset):
    n = 0
    for path in s1r.snapshot_paths(dataset, "dev"):
        if path.name != "snapshot_T1.json":
            continue
        sc = s1r.load_staged_case(dataset, "dev", path.parent.name, "T2")
        graphs = build_versions(env.executor(), sc.items, sc.t1, sc.horizon)
        assert [g.stage for g in graphs] == [p.stage for p in plan_stages(sc.items, sc.t1, sc.horizon)]
        _check_structure(graphs)
        t1_graph = graphs[0]
        assert NodeType.PHARMA_AGENT not in {x.type for x in t1_graph.nodes}  # home/patient lists never trigger Pharma
        n += 1
        env.root = env.root / f"c{n}"  # one StateStore namespace per encounter: a fresh store per case
    assert n >= 30


def test_t2_requires_trigger_reader_output(env):
    p, items, horizon = FIXTURES_STAGED["F-CXR"]()
    t2 = build_versions(env.executor(), items, T1, horizon)[1]
    reasoning = t2.by_type(NodeType.REASONING)
    assert "ImageTokens<-CXRImage" in reasoning.params["required_inputs"]
    assert reasoning.status == "ok" and t2.by_type(NodeType.READER_CXR).status == "ok"
    assert {e.src for e in t2.edges if e.dst == "reasoning" and e.data_type == "ImageTokens"} == {"reader_cxr"}


def test_t3_has_no_reasoning_and_pharma_reads_only_reader_text_findings(env):
    p, items, horizon = FIXTURES_STAGED["F-CXR"]()
    t3 = build_versions(env.executor(), items, T1, horizon)[2]
    into_pharma = [(e.src, e.data_type) for e in t3.edges if e.dst == "pharma_agent"]
    assert into_pharma == [("reader_text", "Findings")]
    assert t3.by_type(NodeType.READER_CXR) is not None  # context Readers stay (cache hits)


# ------------------------------------------------------------------- compile_stage input guards


def test_compile_stage_rejects_wrong_triggers():
    p, items, horizon = FIXTURES_STAGED["F-CXR"]()
    snap = build_snapshot(items, horizon, p)
    with pytest.raises(GraphValidationError) as e:
        compile_stage(snap, "T2", trigger_refs=[f"{p}-order"])  # an order cannot trigger T2
    assert e.value.code == "stage_trigger"
    with pytest.raises(GraphValidationError) as e:
        compile_stage(snap, "T3", trigger_refs=[])  # T3 needs a trigger
    assert e.value.code == "stage_trigger"
    with pytest.raises(GraphValidationError) as e:
        compile_stage(snap, "T1", trigger_refs=[f"{p}-cxr"])
    assert e.value.code == "stage_trigger"
    with pytest.raises(GraphValidationError) as e:
        compile_stage(snap, "T9")
    assert e.value.code == "stage_structure"


def test_forged_stage_structure_is_rejected():
    p, items, horizon = FIXTURES_STAGED["F-CXR"]()
    snap = build_snapshot(items, horizon, p)
    spec = compile_stage(snap, "T3", trigger_refs=[f"{p}-order"]).spec
    nodes = tuple(n.model_copy(update={"provider": "human:nurse"}) if n.type is NodeType.HUMAN_CHECKPOINT else n
                  for n in spec.nodes)
    with pytest.raises(GraphValidationError) as e:
        validate(spec.model_copy(update={"nodes": nodes}), snap)
    assert e.value.code == "stage_structure"
    with pytest.raises(GraphValidationError) as e:
        validate(spec.model_copy(update={"stage": "T1", "trigger_refs": ()}), snap)  # Pharma at T1
    assert e.value.code == "stage_structure"
