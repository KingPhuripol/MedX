"""Output Store, Replay, Regenerate: S2-A01..A05, A16, A17, A21."""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone

import pytest

from casegraph.compiler import build_snapshot, compile_graph
from casegraph.executor import Executor, PENDING_KEY, ResumeError
from casegraph.library import MODEL_PROVIDERS, ProviderAssignment
from casegraph.providers import mock_gateways
from casegraph.store import (
    MemoryStateStore,
    OutputStore,
    ReplayError,
    SQLiteStateStore,
    cache_key,
    regenerate,
    replay,
)
from casegraph.types import NodeType as N

from .conftest import Env, compile_case
from .fixtures import CASES, F1_T1, F1_T2, F2_T, f1

REPLAY_CASES = [c for c in CASES if c[0] in {"F1", "F2", "F3", "F4", "F5"}]
CONFIRM_AT = datetime(2026, 1, 2, 9, 0, tzinfo=timezone.utc)
EXT = ProviderAssignment(provider="external_model", model_version="ext-mock-0.1")


def _descendants(graph, node_id: str) -> set[str]:
    out, stack = set(), [node_id]
    while stack:
        cur = stack.pop()
        for e in graph.edges:
            if e.src == cur and e.dst not in out:
                out.add(e.dst)
                stack.append(e.dst)
    return out


def _recomputed(graph) -> set[str]:
    return {n.id for n in graph.nodes if not n.cached}


def _forbid_node_bodies(monkeypatch):
    def _boom(self, ctx):
        raise AssertionError("replay executed a node body")

    monkeypatch.setattr(Executor, "_body", _boom)


# ------------------------------------------------------------------------------------ A01/A02


@pytest.mark.parametrize("name,T", REPLAY_CASES)
def test_replay_reproduces_all_outputs(env, name, T, monkeypatch):
    original = env.executor().run_sync(compile_case(name, T))
    calls = env.calls
    _forbid_node_bodies(monkeypatch)
    # fresh process-equivalent: new store instances on the same files, new Executor
    fresh = env.executor()
    replayed = replay(original.graph_id, OutputStore(env.root / "outputs"), SQLiteStateStore(env.root / "state.db"))
    assert [n.output_sha256 for n in replayed.nodes] == [n.output_sha256 for n in original.nodes]
    assert [n.output for n in replayed.nodes] == [n.output for n in original.nodes]
    assert env.calls == calls and sum(fresh.node_executions.values()) == 0


@pytest.mark.parametrize("damage", ["missing", "tampered"])
def test_replay_missing_or_tampered_entry_fails(env, damage, monkeypatch):
    graph = env.executor().run_sync(compile_case("F1", F1_T1))
    calls = env.calls
    _forbid_node_bodies(monkeypatch)
    store = OutputStore(env.root / "outputs")
    path = store.path(graph.node("reasoning").cache_key)
    if damage == "missing":
        path.unlink()
    else:
        data = json.loads(path.read_text())
        data["output"]["CaseSummary"]["text"] = "tampered"
        path.write_text(json.dumps(data))
    with pytest.raises(ReplayError, match="reasoning"):
        replay(graph.graph_id, store, SQLiteStateStore(env.root / "state.db"))
    with pytest.raises(ReplayError):
        replay(graph, store)  # the exported/imported form as well
    with pytest.raises(ReplayError):
        replay("SYN-F1/v99", store, SQLiteStateStore(env.root / "state.db"))
    assert env.calls == calls


# ------------------------------------------------------------------------------------ A03


@pytest.mark.parametrize(
    "name,T,swap,expected",
    [
        ("F1", F1_T2, N.READER_CXR, {"reader_cxr", "red_flag", "pharma_agent", "reasoning", "human_checkpoint"}),
        ("F2", F2_T, N.READER_TEXT, {"reader_text", "red_flag", "reasoning", "human_checkpoint"}),
    ],
)
def test_regenerate_swap_provider_recomputes_only_descendants(env, name, T, swap, expected):
    ex = env.executor()
    v1 = ex.run_sync(compile_case(name, T))
    calls = env.calls
    v2 = regenerate(ex, v1.graph_id, swap_provider={swap: EXT})
    assert (v2.version, v2.parent_version) == (2, 1)
    assert v2.node(swap.value).provider == "external_model" and v2.node(swap.value).reproducible is False
    recomputed = _recomputed(v2)
    assert recomputed == {swap.value} | _descendants(v2, swap.value) == expected
    assert len(recomputed) == len(expected) < len(v2.nodes)
    for n in v2.nodes:
        if n.id not in recomputed:
            assert n.cached and n.gateway_calls == 0
            assert n.output_sha256 == v1.node(n.id).output_sha256
    model_backed = {n.id for n in v2.nodes if n.id in recomputed and n.provider in MODEL_PROVIDERS}
    assert env.calls - calls == len(model_backed) == sum(n.gateway_calls for n in v2.nodes)
    assert model_backed == {swap.value, "reasoning"}


# ------------------------------------------------------------------------------------ A04


@pytest.mark.parametrize(
    "T,reader,abstain_missing",
    [(F1_T1, N.READER_VITALS_LABS, ["Findings<-Vitals"]), (F1_T2, N.READER_CXR, None)],
)
def test_ablation_remove_reader(env, T, reader, abstain_missing):
    ex = env.executor()
    v1 = ex.run_sync(compile_case("F1", T))
    v2 = regenerate(ex, v1.graph_id, remove_node=reader)
    assert reader.value not in {n.id for n in v2.nodes}
    assert _recomputed(v2) == _descendants(v1, reader.value)
    r = v2.node("reasoning")
    if abstain_missing:
        assert r.status == "abstained" and list(r.missing_inputs) == abstain_missing and r.gateway_calls == 0
    else:
        assert r.status == "ok"
    # the removed reader's evidence stays in the snapshot but is read by no node
    assert v2.snapshot_id == v1.snapshot_id


# ------------------------------------------------------------------------------------ A05


def test_rerun_without_cache_is_identical(tmp_path):
    def run_all(root):
        e = Env(root)
        return [e.executor().run_sync(compile_case(name, T)) for name, T in CASES if name != "F1" or T == F1_T1] + [
            Env(root / "t2").executor().run_sync(compile_case("F1", F1_T2))
        ]

    a, b = run_all(tmp_path / "a"), run_all(tmp_path / "b")
    for ga, gb in zip(a, b, strict=True):
        assert all(not n.cached for n in gb.nodes)
        assert [n.output_sha256 for n in ga.nodes] == [n.output_sha256 for n in gb.nodes]
        assert [n.cache_key for n in ga.nodes] == [n.cache_key for n in gb.nodes]


# ------------------------------------------------------------------------------------ A16/A17


@pytest.mark.parametrize("action", ["confirm", "edit", "reject"])
def test_confirmed_result_is_new_evidence(env, action):
    ex = env.executor(clock=lambda: CONFIRM_AT)
    ex.run_sync(compile_case("F1", F1_T1))
    ex.resume("SYN-F1/v1", action, "dr-01", "physician", edited_payload={"note": "synthetic edit"})
    added = env.executor().state.evidence("SYN-F1")
    if action == "reject":
        assert added == []
        return
    (item,) = added
    assert item.data_type == "ConfirmedResult" and item.available_at_time == CONFIRM_AT
    assert item.result.action == action and item.result.reviewer_id == "dr-01"
    record = f1() + added
    assert item.item_id in {i.item_id for i in build_snapshot(record, CONFIRM_AT).items}
    assert item.item_id in {i.item_id for i in build_snapshot(record, CONFIRM_AT + timedelta(days=1)).items}
    assert item.item_id not in {i.item_id for i in build_snapshot(record, CONFIRM_AT - timedelta(microseconds=1)).items}
    later = compile_graph(build_snapshot(record, CONFIRM_AT), version=2, parent_version=1)
    assert item.item_id in {r.item_id for r in later.spec.evidence}


@pytest.mark.parametrize("action", ["confirm", "edit", "reject"])
def test_confirmation_before_T_refused(env, action):
    """A clock earlier than the graph's T is refused; nothing is written (data rule 3)."""
    T = F1_T1
    early = T - timedelta(days=3)  # e.g. wall clock behind a date-shifted record
    ex = env.executor(clock=lambda: early)
    ex.run_sync(compile_case("F1", T))
    with pytest.raises(ResumeError, match="earlier than graph T"):
        ex.resume("SYN-F1/v1", action, "dr-01", "physician", edited_payload={"note": "synthetic edit"})
    fresh = env.executor()
    assert fresh.state.evidence("SYN-F1") == []
    assert fresh.export("SYN-F1/v1").node("human_checkpoint").status == "pending_confirmation"


@pytest.mark.parametrize("offset", [timedelta(0), timedelta(microseconds=1), timedelta(days=400)])
def test_confirmed_result_never_visible_before_T(env, offset):
    """Whatever the (accepted) clock, no snapshot earlier than the source graph's T sees the result."""
    T = F1_T1
    ex = env.executor(clock=lambda: T + offset)
    ex.run_sync(compile_case("F1", T))
    ex.resume("SYN-F1/v1", "confirm", "dr-01", "physician")
    (item,) = env.executor().state.evidence("SYN-F1")
    assert item.available_at_time >= T and item.result.confirmed_at >= T
    record = f1() + [item]
    for t in (T - timedelta(microseconds=1), T - timedelta(hours=1), T - timedelta(days=365)):
        assert item.item_id not in {i.item_id for i in build_snapshot(record, t).items}


def test_naive_confirmation_clock_refused(env):
    ex = env.executor(clock=lambda: datetime(2026, 1, 2, 9, 0))
    ex.run_sync(compile_case("F1", F1_T1))
    with pytest.raises(ResumeError, match="naive"):
        ex.resume("SYN-F1/v1", "confirm", "dr-01", "physician")


@pytest.mark.parametrize("change", [True, False])
def test_confirmation_not_reused_after_change(env, change):
    ex = env.executor(clock=lambda: CONFIRM_AT)
    v1 = ex.run_sync(compile_case("F1", F1_T1))
    confirmed = ex.resume("SYN-F1/v1", "confirm", "dr-01", "physician")
    v2 = regenerate(ex, v1.graph_id, swap_provider={N.READER_TEXT: EXT} if change else None)
    hc = v2.node("human_checkpoint")
    assert hc.status == "pending_confirmation" and hc.confirmation is None
    new_hash = hc.output[PENDING_KEY]["input_hash"]
    assert (new_hash != confirmed.checkpoint_input_hash) is change
    assert ex.export("SYN-F1/v1").node("human_checkpoint").status == "confirmed"


# ------------------------------------------------------------------------------------ A21


def test_cache_key_components():
    base = dict(node_type="reader_text", provider="project_model", model_version="m1",
                params={"temperature": 0}, input_hash="0" * 64)
    k = cache_key(**base)
    assert k == cache_key(**dict(base)) and len(k) == 64
    variants = {
        "node_type": "reasoning",
        "provider": "external_model",
        "model_version": "m2",
        "params": {"temperature": 0, "max_tokens": 8},
        "input_hash": "0" * 63 + "1",
    }
    keys = {field: cache_key(**{**base, field: v}) for field, v in variants.items()}
    assert len(keys) == 5 and all(v != k for v in keys.values()) and len(set(keys.values())) == 5
    # one input byte changes the executed node's key
    snap_a = build_snapshot(f1(), F1_T1)
    items = f1()
    items[0] = items[0].model_copy(update={"text": items[0].text + "."})
    snap_b = build_snapshot(items, F1_T1)
    run = lambda s: Executor(mock_gateways(), OutputStore(), MemoryStateStore()).run_sync(compile_graph(s))
    ga, gb = run(snap_a), run(snap_b)
    assert ga.node("reader_text").cache_key != gb.node("reader_text").cache_key
    assert ga.node("reader_vitals_labs").cache_key == gb.node("reader_vitals_labs").cache_key
