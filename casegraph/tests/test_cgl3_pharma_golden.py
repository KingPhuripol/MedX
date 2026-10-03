"""Slice cg-l3: gates_version in every Pharma output, legacy outputs still replay, and the golden tripwire.
Synthetic, offline, mock only. Research prototype: not clinical performance. The golden file covers a fixed corpus."""

from __future__ import annotations

import copy
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

from casegraph import executor as executor_mod
from casegraph.data import MedicationIssues
from casegraph.executor import Executor
from casegraph.export import import_graph, to_json
from casegraph.staged import build_versions
from casegraph.store import OutputStore, SQLiteStateStore, replay
from casegraph.types import NodeType

from . import pharma_golden as pg
from .staged_fixtures import FIXTURES_STAGED, T1

ROOT = Path(__file__).resolve().parents[2]
LEGACY = Path(__file__).parent / "fixtures" / "legacy_28ac4d2"
GOLDEN = json.loads(pg.GOLDEN_PATH.read_text())


@pytest.fixture(scope="module")
def dataset(s1r_dataset):
    return s1r_dataset


@pytest.fixture(scope="module")
def current(dataset):
    return pg.build_corpus(dataset)


@pytest.fixture(scope="module")
def bumped(dataset):
    """The corpus built under a bumped version (no gate change)."""
    mp = pytest.MonkeyPatch()
    mp.setattr(executor_mod, "PHARMA_GATES_VERSION", "cg-pharma-gates-next")
    try:
        return pg.build_corpus(dataset)
    finally:
        mp.undo()


def _plant(monkeypatch):
    orig = Executor._conversation_allergy_gaps

    def drop_first(latest, facts):
        return orig(latest, facts)[1:]  # a silent behaviour change: one gap fewer, status stays ok

    monkeypatch.setattr(Executor, "_conversation_allergy_gaps", staticmethod(drop_first))


# ------------------------------------------------------------------------------------------------ L3a


def test_every_pharma_output_carries_gates_version(current):
    assert executor_mod.PHARMA_GATES_VERSION == "cg-pharma-gates-9"
    entries = current["entries"]
    assert len(entries) >= 200
    assert {e["gates_version"] for e in entries.values()} == {"cg-pharma-gates-9"}
    assert entries["anchor|model_path|-|v1"]["status"] == "not_evaluated"  # model path carries it too


def test_cached_pharma_output_carries_gates_version(env, monkeypatch):
    _, items, horizon = FIXTURES_STAGED["F-CXR"]()
    first = build_versions(env.executor(), items, T1, horizon)[-1].by_type(NodeType.PHARMA_AGENT)
    assert first.cached is False and first.output["MedicationIssues"]["gates_version"] == "cg-pharma-gates-9"
    again = Executor(env.gateways, OutputStore(env.root / "outputs"), SQLiteStateStore(env.root / "state2.db"))
    hit = build_versions(again, items, T1, horizon)[-1].by_type(NodeType.PHARMA_AGENT)
    assert hit.cached is True and hit.output["MedicationIssues"]["gates_version"] == "cg-pharma-gates-9"
    # stale-cache negative: an entry built under gates-8 is not served under gates-9
    monkeypatch.setattr(executor_mod, "PHARMA_GATES_VERSION", "cg-pharma-gates-8")
    old = Executor(env.gateways, OutputStore(env.root / "o8"), SQLiteStateStore(env.root / "s8.db"))
    old_node = build_versions(old, items, T1, horizon)[-1].by_type(NodeType.PHARMA_AGENT)
    assert old_node.output["MedicationIssues"]["gates_version"] == "cg-pharma-gates-8"
    monkeypatch.undo()
    new = Executor(env.gateways, OutputStore(env.root / "o8"), SQLiteStateStore(env.root / "s9.db"))
    new_node = build_versions(new, items, T1, horizon)[-1].by_type(NodeType.PHARMA_AGENT)
    assert new_node.cached is False and new_node.cache_key != old_node.cache_key
    assert new_node.output["MedicationIssues"]["gates_version"] == "cg-pharma-gates-9"


# ------------------------------------------------------------------------------------------ L3a-legacy

LEGACY_FILES = [("0.4-T3", "export_0_4_T3.json"), ("0.3-unstaged", "export_0_3_unstaged.json")]


@pytest.mark.parametrize("label,fname", LEGACY_FILES, ids=[x[0] for x in LEGACY_FILES])
def test_legacy_28ac4d2_replays_byte_identical(tmp_path, monkeypatch, label, fname):
    text = (LEGACY / fname).read_text()
    graph = import_graph(text)
    outputs = tmp_path / "outputs"
    shutil.copytree(LEGACY / "outputs", outputs)
    monkeypatch.setattr(Executor, "_body", lambda self, ctx: (_ for _ in ()).throw(AssertionError("body ran")))
    store = OutputStore(outputs)
    from_graph = replay(graph, store)
    state = SQLiteStateStore(tmp_path / "state.db")
    state.save_run(graph.graph_id, text)
    from_state = replay(graph.graph_id, store, state)
    for replayed in (from_graph, from_state):
        assert to_json(replayed) == text
        assert sum(n.gateway_calls for n in replayed.nodes) == sum(n.gateway_calls for n in graph.nodes)
        assert "gates_version" not in replayed.by_type(NodeType.PHARMA_AGENT).output["MedicationIssues"]


@pytest.mark.parametrize("label,fname", LEGACY_FILES, ids=[x[0] for x in LEGACY_FILES])
def test_legacy_medication_issues_has_null_gates_version(label, fname):
    node = import_graph((LEGACY / fname).read_text()).by_type(NodeType.PHARMA_AGENT)
    assert "gates_version" not in node.output["MedicationIssues"]
    assert MedicationIssues.model_validate(node.output["MedicationIssues"]).gates_version is None


# ------------------------------------------------------------------------------------------------ L3b


def test_pharma_golden_matches(current):
    rep = pg.compare(GOLDEN, current)
    assert rep.ok and set(rep.classes.values()) == {pg.OK}, rep.text()


def test_golden_detects_planted_gate_change(dataset, monkeypatch, tmp_path):
    _plant(monkeypatch)
    cur = pg.build_corpus(dataset)
    rep = pg.compare(GOLDEN, cur)
    assert rep.keys(pg.NO_BUMP) and not rep.keys(pg.INPUT_DRIFT) and not rep.ok
    assert all(e["node_status"] == "ok" for e in cur["entries"].values() if e["status"] is not None)  # silent change
    path = tmp_path / "g.json"
    path.write_text(pg.GOLDEN_PATH.read_text())
    before = path.read_bytes()
    assert pg.write_golden(path, cur, out=lambda *_: None) == 2 and path.read_bytes() == before
    assert pg.GOLDEN_PATH.read_bytes() == before  # the committed golden is untouched


def test_golden_detects_version_bump_without_regen(bumped, tmp_path):
    rep = pg.compare(GOLDEN, bumped)
    assert rep.version_mismatch and not rep.ok
    assert pg.main(["--check"], current=bumped) == 1


@pytest.mark.parametrize("planted", [False, True], ids=["plain", "planted"])
def test_regenerate_after_bump_passes(dataset, bumped, monkeypatch, tmp_path, capsys, planted):
    cur = bumped
    if planted:
        _plant(monkeypatch)
        monkeypatch.setattr(executor_mod, "PHARMA_GATES_VERSION", "cg-pharma-gates-next")
        cur = pg.build_corpus(dataset)
    path = tmp_path / "g.json"
    path.write_text(pg.GOLDEN_PATH.read_text())
    assert pg.main(["--write", "--golden", str(path)], current=cur) == 0
    printed = capsys.readouterr().out
    changed = pg.changed_semantics(GOLDEN, cur)
    assert bool(changed) is planted and f"changed for {len(changed)} keys" in printed
    assert pg.compare(json.loads(path.read_text()), cur).ok


def test_input_drift_is_reported_separately(current, tmp_path):
    golden = copy.deepcopy(GOLDEN)
    key = sorted(golden["entries"])[3]
    golden["entries"][key]["input_sha256"] = "0" * 64
    rep = pg.compare(golden, current)
    assert rep.keys(pg.INPUT_DRIFT) == [key] and not rep.keys(pg.NO_BUMP)
    path = tmp_path / "g.json"
    path.write_text(json.dumps(golden))
    before = path.read_bytes()
    assert pg.write_golden(path, current, out=lambda *_: None) == 2 and path.read_bytes() == before
    assert pg.write_golden(path, current, accept_input_drift=True, out=lambda *_: None) == 0


def test_corpus_is_deterministic(current, dataset):
    assert pg.build_corpus(dataset) == current
    for seed in ("0", "1"):
        r = subprocess.run([sys.executable, "-m", "casegraph.tests.pharma_golden", "--check", "--dataset", str(dataset)],
                           cwd=ROOT, env={**os.environ, "PYTHONHASHSEED": seed, "PYTHONPATH": f"backend:{ROOT}"},
                           capture_output=True, text=True)
        assert r.returncode == 0, r.stdout + r.stderr


# ------------------------------------------------------------------------------------------------ L3c


def test_golden_corpus_coverage(current, dataset):
    assert GOLDEN["corpus_id"] == "cg-l3-corpus-1" and GOLDEN["syn_subset"] == current["syn_subset"]
    assert len(GOLDEN["syn_subset"]) == 8 and len(GOLDEN["entries"]) >= 200
    for corpus in (GOLDEN, current):
        e = corpus["entries"].values()
        assert {"evaluated", "partially_evaluated", "not_evaluated"} <= {x["status"] for x in e}
        assert {"used", "partial", "not_used", "superseded"} <= {u for x in e for u in x["fact_use"]}
