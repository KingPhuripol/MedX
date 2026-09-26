"""Compiler: S2-A06..A11, A08 and the A20 data policy."""

from __future__ import annotations

import pytest

from casegraph.compiler import (
    GraphValidationError,
    ValidatedGraph,
    build_draft,
    build_snapshot,
    compile_graph,
    validate,
)
from casegraph.export import EdgeSpec, to_json
from casegraph.library import ProviderAssignment, ProviderConfig
from casegraph.store import GraphVersionExists, MemoryStateStore, OutputStore, next_version, regenerate
from casegraph.executor import Executor
from casegraph.providers import mock_gateways
from casegraph.types import NodeType as N
from app.gateway.contract import GatewayRequest

from .conftest import compile_case
from .fixtures import CASES, F1_T1, F1_T2, F2_T, F4_T, F6_T, FIXTURES, f1, f3, f4, f6, sweep_times

READER_T = {"reader_text", "red_flag", "reasoning", "human_checkpoint"}
EXPECTED_NODES = {
    ("F1", F1_T1): READER_T | {"reader_vitals_labs"},
    ("F1", F1_T2): READER_T | {"reader_vitals_labs", "reader_cxr", "pharma_agent"},
    ("F2", F2_T): READER_T | {"reader_vitals_labs", "reader_ct_mri"},
    ("F3", CASES[3][1]): READER_T,
    ("F4", F4_T): READER_T | {"reader_vitals_labs"},  # labs (T+1s) and CXR (T+1d) are future
    ("F5", CASES[5][1]): READER_T | {"reader_vitals_labs"},
    ("F6", F6_T): READER_T | {"reader_vitals_labs"},
}
ALL_SWEEP = [(name, t) for name in FIXTURES for t in sweep_times(name)]


def _ext(node_type=N.REASONING, version="ext-mock-0.1"):
    return ProviderConfig().with_assignment(node_type, ProviderAssignment(provider="external_model", model_version=version))


def _spec(name="F1", T=F1_T1, config=None):
    snap = build_snapshot(FIXTURES[name](), T)
    return build_draft(snap, config), snap


# ------------------------------------------------------------------------------------ A06


@pytest.mark.parametrize("name,T", ALL_SWEEP)
def test_mandatory_nodes_present(name, T):
    spec = compile_case(name, T).spec
    types = {n.type for n in spec.nodes}
    assert {N.RED_FLAG, N.HUMAN_CHECKPOINT} <= types
    assert EdgeSpec(src="red_flag", dst="human_checkpoint", data_type="Alerts") in spec.edges


@pytest.mark.parametrize("what", ["red_flag", "checkpoint", "alerts_edge"])
def test_missing_mandatory_node_rejected(what):
    spec, snap = _spec()
    if what == "alerts_edge":
        bad = spec.model_copy(update={"edges": tuple(e for e in spec.edges if e.dst != "human_checkpoint"
                                                     or e.data_type != "Alerts")})
        # keep Reasoning reaching the checkpoint so only the direct Alerts edge is missing
        code = "alerts_edge"
    else:
        drop = "red_flag" if what == "red_flag" else "human_checkpoint"
        bad = spec.model_copy(update={
            "nodes": tuple(n for n in spec.nodes if n.id != drop),
            "edges": tuple(e for e in spec.edges if drop not in (e.src, e.dst)),
        })
        code = "missing_mandatory"
    with pytest.raises(GraphValidationError) as exc:
        validate(bad, snap)
    assert exc.value.code == code
    # the compiler path refuses too
    exclude = {"red_flag": [N.RED_FLAG], "checkpoint": [N.HUMAN_CHECKPOINT], "alerts_edge": []}[what]
    if exclude:
        with pytest.raises(GraphValidationError):
            compile_graph(snap, exclude=exclude)


@pytest.mark.parametrize("node_type", [N.RED_FLAG, N.HUMAN_CHECKPOINT])
def test_cannot_remove_mandatory_node(env, node_type):
    ex = env.executor()
    ex.run_sync(compile_case("F1", F1_T1))
    with pytest.raises(GraphValidationError) as exc:
        regenerate(ex, "SYN-F1/v1", remove_node=node_type)
    assert exc.value.code == "missing_mandatory"
    assert ex.state.latest_version("SYN-F1") == 1


# ------------------------------------------------------------------------------------ A07


@pytest.mark.parametrize("name", list(FIXTURES))
def test_snapshot_excludes_future_items(name):
    times = sweep_times(name)
    assert len(times) >= 3
    for T in times:
        items = FIXTURES[name]()
        snap = build_snapshot(items, T)
        future = {i.item_id for i in items if i.available_at_time > T}
        assert [i for i in snap.items if i.available_at_time > T] == []
        assert {i.item_id for i in snap.items} == {i.item_id for i in items} - future  # boundary == T included
        ex = Executor(mock_gateways(), OutputStore(), MemoryStateStore())
        graph = ex.run_sync(compile_graph(snap))
        assert all(r.available_at_time <= T for r in graph.evidence)
        refs = {r for n in graph.nodes for r in n.evidence_refs}
        assert refs <= {i.item_id for i in snap.items} and not refs & future
        text = to_json(graph)
        assert not any(fid in text for fid in future), "future item id leaked into export"


def test_boundary_item_at_T_included():
    snap = build_snapshot(f4(), F4_T)
    ids = {i.item_id for i in snap.items}
    assert "f4-vitals-at-T" in ids and "f4-labs-future" not in ids and "f4-cxr-future" not in ids


def test_foreign_snapshot_item_rejected():
    spec, snap = _spec("F1", F1_T1)
    rt = spec.node("reader_text")
    bad = spec.model_copy(update={"nodes": tuple(
        n.model_copy(update={"evidence_refs": (*n.evidence_refs, "f1-cxr")}) if n.id == rt.id else n
        for n in spec.nodes)})
    with pytest.raises(GraphValidationError) as exc:
        validate(bad, snap)
    assert exc.value.code == "foreign_evidence"
    # a graph validated against a different snapshot (T2) is rejected
    snap_t2 = build_snapshot(f1(), F1_T2)
    with pytest.raises(GraphValidationError) as exc:
        validate(spec, snap_t2)
    assert exc.value.code == "foreign_evidence"
    # smuggling a future ref into the evidence list breaks the snapshot id
    fut = build_snapshot(f1(), F1_T2).refs()
    with pytest.raises(GraphValidationError) as exc:
        validate(spec.model_copy(update={"evidence": fut}))
    assert exc.value.code == "foreign_evidence"


def test_mixed_patient_rejected():
    with pytest.raises(GraphValidationError) as exc:
        build_snapshot(f1() + f3(), F1_T2)
    assert exc.value.code == "mixed_patient"
    spec, snap = _spec("F1", F1_T1)
    with pytest.raises(GraphValidationError):
        validate(spec, build_snapshot(f3(), F1_T1))


# ------------------------------------------------------------------------------------ A08


def test_imagetokens_to_external_rejected(env):
    snap = build_snapshot(f1(), F1_T2)
    with pytest.raises(GraphValidationError) as exc:
        compile_graph(snap, _ext(N.REASONING))
    assert exc.value.code == "image_tokens_route"
    # ImageTokens to any non-Reasoning node
    spec = build_draft(snap)
    bad = spec.model_copy(update={"edges": (*spec.edges, EdgeSpec(src="reader_cxr", dst="red_flag",
                                                                    data_type="ImageTokens"))})
    with pytest.raises(GraphValidationError) as exc:
        validate(bad, snap)
    assert exc.value.code == "image_tokens_route"
    ex = env.executor()
    for rejected in (bad, build_draft(snap, _ext(N.REASONING))):
        with pytest.raises(TypeError):
            ex.run_sync(rejected)  # type: ignore[arg-type]
    assert sum(ex.node_executions.values()) == 0 and env.calls == 0


def test_imagetokens_to_project_model_ok():
    g = compile_case("F1", F1_T2)
    assert EdgeSpec(src="reader_cxr", dst="reasoning", data_type="ImageTokens") in g.spec.edges
    assert g.spec.node("reasoning").provider == "project_model"
    assert not [e for e in g.spec.edges if e.data_type == "ImageTokens" and e.dst != "reasoning"]


# ------------------------------------------------------------------------------------ A09


@pytest.mark.parametrize("what", ["cycle", "type_mismatch", "provider", "unreviewed_output"])
def test_validation_rejects(what):
    spec, snap = _spec("F1", F1_T1)
    if what == "cycle":
        bad = spec.model_copy(update={"edges": (*spec.edges, EdgeSpec(src="reasoning", dst="red_flag",
                                                                        data_type="Findings"))})
        code = "cycle"
    elif what == "type_mismatch":
        bad = spec.model_copy(update={"edges": tuple(
            e.model_copy(update={"data_type": "Alerts"}) if (e.src, e.dst) == ("reader_text", "red_flag") else e
            for e in spec.edges)})
        code = "type_mismatch"
    elif what == "provider":
        bad = spec.model_copy(update={"nodes": tuple(
            n.model_copy(update={"provider": "project_model", "params": {"temperature": 0}}) if n.id == "red_flag"
            else n for n in spec.nodes)})
        code = "provider_not_allowed"
        with pytest.raises(GraphValidationError):
            compile_graph(snap, ProviderConfig().with_assignment(
                N.RED_FLAG, ProviderAssignment(provider="external_model", model_version="x")))
    else:
        bad = spec.model_copy(update={"edges": tuple(e for e in spec.edges if e.src != "reasoning")})
        code = "unreviewed_output"
    with pytest.raises(GraphValidationError) as exc:
        validate(bad, snap)
    assert exc.value.code == code


def test_executor_requires_validated_graph(env):
    spec, snap = _spec()
    ex = env.executor()
    with pytest.raises(TypeError):
        ValidatedGraph(spec, snap, _token=object())
    for bogus in (spec, object(), None):
        with pytest.raises(TypeError):
            ex.run_sync(bogus)  # type: ignore[arg-type]
    fake = object.__new__(ValidatedGraph)
    object.__setattr__(fake, "spec", spec)
    object.__setattr__(fake, "snapshot", snap)
    object.__setattr__(fake, "_token", object())
    with pytest.raises(TypeError):
        ex.run_sync(fake)
    assert sum(ex.node_executions.values()) == 0 and env.calls == 0


# ------------------------------------------------------------------------------------ A10


@pytest.mark.parametrize("case", list(EXPECTED_NODES), ids=lambda c: f"{c[0]}@{c[1].isoformat()}")
def test_node_selection_matrix(case):
    name, T = case
    spec = compile_case(name, T).spec
    assert {n.id for n in spec.nodes} == EXPECTED_NODES[case]


@pytest.mark.parametrize("name,T", ALL_SWEEP)
def test_pharma_iff_medication_list(name, T):
    snap = build_snapshot(FIXTURES[name](), T)
    has_meds = "MedicationList" in snap.data_types()
    assert (N.PHARMA_AGENT in {n.type for n in compile_graph(snap).spec.nodes}) is has_meds


def test_fig_3_2_versions(env):
    ex = env.executor()
    v1 = ex.run_sync(compile_case("F1", F1_T1))
    version, parent = next_version(ex.state, "SYN-F1")
    v2 = ex.run_sync(compile_case("F1", F1_T2, version=version, parent_version=parent))
    assert (v2.version, v2.parent_version) == (2, 1)
    assert {n.id for n in v2.nodes} - {n.id for n in v1.nodes} == {"reader_cxr", "pharma_agent"}
    assert {n.id for n in v1.nodes} - {n.id for n in v2.nodes} == set()


# ------------------------------------------------------------------------------------ A11


def test_new_data_new_version_old_kept(env):
    ex = env.executor()
    ex.run_sync(compile_case("F1", F1_T1))
    v1_bytes = to_json(ex.export("SYN-F1/v1"))
    version, parent = next_version(ex.state, "SYN-F1")
    ex.run_sync(compile_case("F1", F1_T2, version=version, parent_version=parent))
    regenerate(ex, "SYN-F1/v2", remove_node=N.READER_CXR)
    assert ex.state.latest_version("SYN-F1") == 3
    assert to_json(env.executor().export("SYN-F1/v1")) == v1_bytes
    # stored versions are never overwritten
    with pytest.raises(GraphVersionExists):
        ex.run_sync(compile_case("F1", F1_T1))
    assert to_json(ex.export("SYN-F1/v1")) == v1_bytes


def test_compile_deterministic():
    for name, T in CASES:
        a = compile_case(name, T).spec.to_json()
        b = compile_graph(build_snapshot(list(reversed(FIXTURES[name]())), T)).spec.to_json()
        assert a.encode() == b.encode()


# ------------------------------------------------------------------------------------ A20 policy


def test_non_synthetic_to_external_rejected(env):
    snap = build_snapshot(f6(), F6_T)
    for node_type in (N.READER_TEXT, N.REASONING):  # direct and transitive (Findings derived from mimic)
        with pytest.raises(GraphValidationError) as exc:
            compile_graph(snap, _ext(node_type))
        assert exc.value.code == "data_policy"
    assert compile_graph(snap).spec.node("reasoning").data_class == "mimic"
    # the runtime gateway enforces the same policy
    ext = env.gateways["external_model"]
    resp = ext.invoke(GatewayRequest(task="reader_text", inputs={"x": 1}, data_class="mimic"))
    assert (resp.status, resp.reason, resp.output) == ("rejected", "policy_non_synthetic", None)
    # a mimic item wired to a non-external provider compiles
    assert compile_graph(snap, _ext(N.READER_CXR)).spec.node("reader_text").data_class == "mimic"
