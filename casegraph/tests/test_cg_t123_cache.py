"""Slice cg-t123 A3a/A3b: cache reuse across staged versions and the time-correct cache key.

Planner finding: the Red-flag node (rf-1.1.0) derives vital freshness and age from T; a key without T would serve a
later version an output whose vitals were fresh at the earlier T (C1: stale vitals read as an all-clear).
"""

from __future__ import annotations

from dataclasses import replace
from datetime import timedelta
from pathlib import Path

import pytest

from casegraph import executor as executor_module
from casegraph.compiler import build_snapshot, compile_stage
from casegraph.data import sha256_json
from casegraph.executor import Executor
from casegraph.providers import mock_gateways
from casegraph.sources import s1r
from casegraph.staged import build_versions
from casegraph.store import MemoryStateStore, OutputStore
from casegraph.types import NodeType

from .staged_fixtures import FIXTURES_STAGED, T1


@pytest.fixture(scope="module")
def dataset(s1r_dataset) -> Path:
    return s1r_dataset


def _reexecute(ex: Executor, graph, gateways):
    """Re-run a stored version with an EMPTY Output Store at the same version number."""
    spec, items = ex.state.load_graph(graph.graph_id)
    snapshot = build_snapshot(items, spec.T, patient_ref=spec.patient_ref)
    validated = compile_stage(snapshot, spec.stage, None, spec.version, spec.parent_version,
                              trigger_refs=spec.trigger_refs)
    fresh = Executor(gateways, OutputStore(), MemoryStateStore())
    return fresh.run_sync(validated)


def _run_counted(env, items, horizon, t1=T1):
    """Build all versions; return (graphs, per-version (audited calls, gateway_calls counter delta))."""
    ex = env.executor()
    seen: list[tuple[int, int]] = []
    state = {"audit": len(env.audit), "calls": env.calls}

    def after(graph):
        seen.append((len(env.audit) - state["audit"], env.calls - state["calls"]))
        state["audit"], state["calls"] = len(env.audit), env.calls

    graphs = build_versions(ex, items, t1, horizon, after_version=after)
    return ex, graphs, seen


def _check_reuse(graphs, seen):
    produced: set[str] = set()
    for k, (g, (audited, counted)) in enumerate(zip(graphs, seen)):
        assert g.totals.gateway_calls == sum(n.gateway_calls for n in g.nodes) == audited == counted
        for n in g.nodes:
            if k >= 1 and n.cache_key in produced:
                assert n.cached and n.gateway_calls == 0, (g.graph_id, n.id)
            elif k >= 1:
                assert not n.cached, (g.graph_id, n.id)
        if k >= 1:
            rt = g.by_type(NodeType.READER_TEXT)
            assert rt.cached and rt.gateway_calls == 0  # its evidence is unchanged
        produced |= {n.cache_key for n in g.nodes}


@pytest.mark.parametrize("name", ["F-CXR", "F-SAME", "F-T3ONLY", "F-RED", "F-STALE"])
def test_stage_cache_reuse(env, name):
    _, items, horizon = FIXTURES_STAGED[name]()
    _, graphs, seen = _run_counted(env, items, horizon)
    _check_reuse(graphs, seen)


def test_f_cxr_readers_are_cache_hits(env):
    _, items, horizon = FIXTURES_STAGED["F-CXR"]()
    _, (t1, t2, t3), _ = _run_counted(env, items, horizon)
    assert t1.by_type(NodeType.READER_CXR) is None and t2.by_type(NodeType.READER_CXR).cached is False
    assert t3.by_type(NodeType.READER_CXR).cached is True  # the CXR is unchanged at T3
    for g in (t2, t3):
        assert g.by_type(NodeType.READER_TEXT).cached and g.by_type(NodeType.READER_VITALS_LABS).cached
    assert t3.by_type(NodeType.PHARMA_AGENT).cached is False and t3.by_type(NodeType.RED_FLAG).cached is False


def test_stage_cache_reuse_syn_dev(env, dataset):
    n = 0
    for path in s1r.snapshot_paths(dataset, "dev"):
        if path.name != "snapshot_T1.json":
            continue
        sc = s1r.load_staged_case(dataset, "dev", path.parent.name, "T2")
        env.root = env.root / f"c{n}"
        _, graphs, seen = _run_counted(env, sc.items, sc.horizon, sc.t1)
        _check_reuse(graphs, seen)
        n += 1
    assert n >= 30


# ------------------------------------------------------------------------------------------ A3b


@pytest.mark.parametrize("name", ["F-CXR", "F-SAME", "F-T3ONLY", "F-RED", "F-STALE"])
def test_no_false_cache_hit(env, name):
    _, items, horizon = FIXTURES_STAGED[name]()
    ex, graphs, _ = _run_counted(env, items, horizon)
    n_cached = 0
    for g in graphs:
        again = _reexecute(ex, g, env.gateways)
        for a, b in zip(g.nodes, again.nodes):
            if a.cached:
                n_cached += 1
                assert a.output_sha256 == b.output_sha256, (g.graph_id, a.id)
    assert n_cached > 0 or name == "F-STALE"


def test_no_false_cache_hit_syn_dev(env, dataset):
    n = n_cached = 0
    for path in s1r.snapshot_paths(dataset, "dev"):
        if path.name != "snapshot_T1.json":
            continue
        sc = s1r.load_staged_case(dataset, "dev", path.parent.name, "T2")
        env.root = env.root / f"c{n}"
        ex, graphs, _ = _run_counted(env, sc.items, sc.horizon, sc.t1)
        for g in graphs:
            again = _reexecute(ex, g, env.gateways)
            for a, b in zip(g.nodes, again.nodes):
                if a.cached:
                    n_cached += 1
                    assert a.output_sha256 == b.output_sha256, (g.graph_id, a.id)
        n += 1
    assert n >= 30 and n_cached > 0


def _readings(g):
    return {r["vital"]: r for r in g.by_type(NodeType.RED_FLAG).output["Alerts"]["readings"]}


def test_red_flag_freshness_across_versions(env):
    """F-STALE: the only vitals are fresh at T1 and stale at T3; Red-flag must say so, never replay T1's output."""
    _, items, horizon = FIXTURES_STAGED["F-STALE"]()
    _, (t1, t3), _ = _run_counted(env, items, horizon)
    assert all(r["fresh"] for r in _readings(t1).values()) and _readings(t1)
    assert t3.by_type(NodeType.RED_FLAG).cached is False
    assert _readings(t3) and not any(r["fresh"] for r in _readings(t3).values())
    rf3 = t3.by_type(NodeType.RED_FLAG).output["Alerts"]
    assert any(m.startswith("vital.spo2:stale") for m in rf3["missing_inputs"])
    assert t3.red_flag_screening.status in ("partially_evaluated", "not_evaluated")
    assert t3.red_flag_screening.status != "evaluated" and t3.red_flag_screening.performed is False
    # Red-flag is a rules node: re-executing it at every version costs no gateway call
    assert t3.by_type(NodeType.RED_FLAG).gateway_calls == 0


def test_without_t_in_the_key_the_stale_vital_would_be_served(env, monkeypatch):
    """Mutation: with a T-free key Red-flag at T3 is a cache hit that still reads the vitals as fresh."""
    monkeypatch.setattr(executor_module, "t_dependent", lambda node: False)
    _, items, horizon = FIXTURES_STAGED["F-STALE"]()
    _, (t1, t3), _ = _run_counted(env, items, horizon)
    rf3 = t3.by_type(NodeType.RED_FLAG)
    if rf3.cached:  # the hazard the T-keyed Red-flag removes
        assert all(r["fresh"] for r in _readings(t3).values())
    else:  # outputs differ only through other inputs; the test must not pass vacuously
        pytest.fail("expected the T-free key to serve Red-flag from the cache at T3")


# ------------------------------------------------ which node bodies read T (proved, not assumed)


def test_t_independence_of_untimed_node_bodies(env, monkeypatch):
    """Reader:Text, Reader:Vitals/Labs, Reader:CXR, Reasoning, Pharma and Human Checkpoint produce the same output
    for the same evidence and upstream when only T moves later (so they do not need T in their key)."""
    captured: list[tuple] = []
    original = Executor._body

    def spy(self, ctx):
        result = original(self, ctx)
        captured.append((ctx, result))
        return result

    monkeypatch.setattr(Executor, "_body", spy)
    _, items, horizon = FIXTURES_STAGED["F-CXR"]()
    ex, graphs, _ = _run_counted(env, items, horizon)
    seen_types = set()
    for ctx, result in captured:
        for later in (timedelta(hours=3), timedelta(hours=30)):
            moved = original(ex, replace(ctx, T=ctx.T + later))
            if ctx.node.type is NodeType.RED_FLAG:
                continue
            if executor_module.t_dependent(ctx.node):  # S5 Pharma takes T as its snapshot as_of: keyed on T instead
                assert ctx.node.type is NodeType.PHARMA_AGENT
                continue
            assert sha256_json(moved.output) == sha256_json(result.output), (ctx.node.id, later)
            seen_types.add(ctx.node.type)
    assert seen_types >= {NodeType.READER_TEXT, NodeType.READER_VITALS_LABS, NodeType.READER_CXR,
                          NodeType.REASONING, NodeType.HUMAN_CHECKPOINT}
    # ... while Red-flag does read T: 30 hours later the same vitals are stale and the output differs
    rf = next((c, r) for c, r in captured if c.node.type is NodeType.RED_FLAG)
    assert sha256_json(original(ex, replace(rf[0], T=rf[0].T + timedelta(hours=30))).output) != sha256_json(rf[1].output)
