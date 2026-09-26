"""Export, import and inspect: S2-A22."""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import pytest

from casegraph.export import import_graph, to_json
from casegraph.library import ProviderAssignment, ProviderConfig
from casegraph.store import OutputStore, replay
from casegraph.types import NodeType as N

from .conftest import compile_case
from .fixtures import CASES, F1_T1, F2_T

REPO = Path(__file__).resolve().parents[2]
TOP = {"schema_version", "graph_id", "patient_ref", "T", "snapshot_id", "version", "parent_version",
       "nodes", "edges", "evidence", "totals"}
NODE = {"id", "type", "provider", "model_version", "params", "cache_key", "status", "started_at", "ended_at",
        "gateway_calls", "reproducible", "output", "output_sha256"}
EDGE = {"src", "dst", "data_type"}
EVIDENCE = {"item_id", "data_type", "event_time", "available_at_time", "source", "version"}


@pytest.mark.parametrize("name,T", CASES)
def test_export_roundtrip(env, name, T):
    graph = env.executor().run_sync(compile_case(name, T))
    text = to_json(graph)
    again = to_json(import_graph(text))
    assert again.encode() == text.encode()
    assert to_json(import_graph(again)).encode() == text.encode()
    spec_text = graph.spec().to_json()
    assert spec_text == compile_case(name, T).spec.to_json()


def test_roundtrip_after_confirmation(env):
    ex = env.executor()
    ex.run_sync(compile_case("F1", F1_T1))
    ex.resume("SYN-F1/v1", "edit", "dr-01", "physician", edited_payload={"x": [1, 2.5, "ก"]})
    text = to_json(ex.export("SYN-F1/v1"))
    assert to_json(import_graph(text)) == text


def test_export_fields(env):
    cfg = ProviderConfig().with_assignment(N.READER_TEXT,
                                           ProviderAssignment(provider="external_model", model_version="ext-mock-0.1"))
    graph = env.executor().run_sync(compile_case("F2", F2_T, cfg))
    data = graph.model_dump(mode="json")
    assert TOP <= set(data)
    for n in data["nodes"]:
        assert NODE <= set(n), NODE - set(n)
        assert n["status"] is not None and n["cache_key"] and n["started_at"] and n["ended_at"]
        assert n["reproducible"] is (n["provider"] != "external_model")
    assert [n["id"] for n in data["nodes"] if not n["reproducible"]] == ["reader_text"]
    for e in data["edges"]:
        assert EDGE <= set(e)
    assert {r["item_id"] for r in data["evidence"]} == {"f2-text", "f2-vitals", "f2-labs", "f2-ct", "f2-mri"}
    for r in data["evidence"]:
        assert EVIDENCE <= set(r)
    assert data["totals"]["gateway_calls"] == sum(n["gateway_calls"] for n in data["nodes"]) == 3
    assert data["totals"]["wall_time_ms"] >= 0
    assert data["nodes"][0]["params"] == {} or "temperature" not in data["nodes"][0]["params"]
    reasoning = graph.node("reasoning")
    assert reasoning.params["temperature"] == 0 and reasoning.params["decoding"] == "greedy"


def test_inspect_cli(env, tmp_path):
    graph = env.executor().run_sync(compile_case("F1", F1_T1.replace(hour=10)))
    path = tmp_path / "graph.json"
    path.write_text(to_json(graph), encoding="utf-8")
    proc = subprocess.run(
        [sys.executable, "-m", "casegraph", "inspect", str(path)],
        cwd=REPO, capture_output=True, text=True, timeout=60,
        env={**os.environ, "PYTHONPATH": f"{REPO}{os.pathsep}{REPO / 'backend'}"},
    )
    assert proc.returncode == 0, proc.stderr
    lines = proc.stdout.splitlines()
    node_lines = [line for line in lines if line.startswith("node ")]
    assert len(node_lines) == len(graph.nodes) == 7
    for n in graph.nodes:
        assert f"node {n.id} type={n.type.value} provider={n.provider} status={n.status}" in node_lines
    assert len([line for line in lines if line.startswith("edge ")]) == len(graph.edges)

    # an imported graph replays with 0 gateway calls
    calls = env.calls
    replayed = replay(import_graph(path.read_bytes()), OutputStore(env.root / "outputs"))
    assert [n.output_sha256 for n in replayed.nodes] == [n.output_sha256 for n in graph.nodes]
    assert env.calls == calls
