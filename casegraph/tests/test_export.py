"""Export, import and inspect: S2-A22, S2R-A07."""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest
from pydantic import ValidationError

from casegraph.compiler import build_snapshot, compile_graph
from casegraph.executor import PENDING_KEY
from casegraph.export import SCHEMA_VERSION, ExportVersionError, import_graph, inspect_lines, to_json
from casegraph.library import ProviderAssignment, ProviderConfig
from casegraph.store import OutputStore, replay
from casegraph.types import NodeType as N

from .conftest import compile_case, s2_config
from .fixtures import CASES, DAY, F1_T1, F2_T, F3_T, F5_T, H, text, vitals

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
    cfg = s2_config().with_assignment(N.READER_TEXT,
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
    assert {r["item_id"] for r in data["evidence"]} == {"f2-text", "f2-vitals", "f2-labs", "f2-ct", "f2-mri",
                                                        "f2-demo", "f2-intake"}  # i2: S4 intake added to F2
    for r in data["evidence"]:
        assert EVIDENCE <= set(r)
    # i2: Reasoning makes 2 calls (S4 department + mock summary) -> 1 reader + 2 + 1 CT/MRI encoder = 4
    assert data["totals"]["gateway_calls"] == sum(n["gateway_calls"] for n in data["nodes"]) == 4
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
        # s2r: the red_flag line always carries screening=<status>
        screening = f" screening={graph.red_flag_screening.status}" if n.type is N.RED_FLAG else ""
        assert f"node {n.id} type={n.type.value} provider={n.provider} status={n.status}{screening}" in node_lines
    assert len([line for line in lines if line.startswith("edge ")]) == len(graph.edges)

    # an imported graph replays with 0 gateway calls
    calls = env.calls
    replayed = replay(import_graph(path.read_bytes()), OutputStore(env.root / "outputs"))
    assert [n.output_sha256 for n in replayed.nodes] == [n.output_sha256 for n in graph.nodes]
    assert env.calls == calls


# ------------------------------------------------------------------------ S2R-A07 (s2r)


def _cli_inspect(path):
    return subprocess.run(
        [sys.executable, "-m", "casegraph", "inspect", str(path)],
        cwd=REPO, capture_output=True, text=True, timeout=60,
        env={**os.environ, "PYTHONPATH": f"{REPO}{os.pathsep}{REPO / 'backend'}"},
    )


def _partial_graph(env):
    items = [text("SYN-EXP-P", "p-text", DAY + 8 * H, DAY + 8 * H),
             vitals("SYN-EXP-P", "p-vitals", DAY + 9 * H, DAY + 9 * H, spo2=97.0, hr=80.0)]
    return env.executor().run_sync(compile_graph(build_snapshot(items, DAY + 12 * H), s2_config()))


@pytest.mark.parametrize("name,T", CASES)
def test_export_red_flag_screening(env, name, T):
    graph = env.executor().run_sync(compile_case(name, T))
    data = json.loads(to_json(graph))
    assert data["schema_version"] == SCHEMA_VERSION == "casegraph-export/0.4"  # cg-t123: 0.4 adds stage/trigger_refs
    payload = graph.node("human_checkpoint").output[PENDING_KEY]
    assert data["red_flag_screening"] == payload["red_flag_screening"]
    assert data["red_flag_screening"]["status"] == graph.node("red_flag").output["Alerts"]["status"]
    text_ = to_json(graph)
    assert to_json(import_graph(text_)).encode() == text_.encode()


@pytest.mark.parametrize("damage", ["v0_1", "field_absent"])
def test_export_rejects_missing_screening(env, damage):
    graph = env.executor().run_sync(compile_case("F3", F3_T))
    data = json.loads(to_json(graph))
    if damage == "v0_1":
        data["schema_version"] = "casegraph-export/0.1"
        del data["red_flag_screening"]  # a genuine 0.1 export has no summary
        with pytest.raises(ExportVersionError, match="0.1"):
            import_graph(json.dumps(data))
    else:
        del data["red_flag_screening"]
        with pytest.raises(ValidationError, match="red_flag_screening"):
            import_graph(json.dumps(data))
    # a summary that contradicts the executed Red-flag node is rejected too (never read as evaluated)
    forged = json.loads(to_json(graph))
    forged["red_flag_screening"].update(status="evaluated", performed=True, banner=None)
    with pytest.raises(ValidationError):
        import_graph(json.dumps(forged))


@pytest.mark.parametrize("case", ["not_evaluated", "partial"])
def test_inspect_banner(env, tmp_path, case):
    graph = env.executor().run_sync(compile_case("F3", F3_T)) if case == "not_evaluated" else _partial_graph(env)
    path = tmp_path / "graph.json"
    path.write_text(to_json(graph), encoding="utf-8")
    proc = _cli_inspect(path)
    assert proc.returncode == 0, proc.stderr
    lines = proc.stdout.splitlines()
    assert lines[0].startswith(f"graph {graph.graph_id} ")
    if case == "not_evaluated":
        assert lines[1] == ("!! RED-FLAG SCREENING NOT PERFORMED "
                            "missing=['Vitals', 'Vitals.hr', 'Vitals.sbp', 'Vitals.spo2', 'Vitals.temp_c']")
    else:
        assert lines[1] == ("!! RED-FLAG SCREENING INCOMPLETE not_evaluated=['RF-PH-002', 'RF-PH-004'] "
                            "missing=['Vitals.sbp', 'Vitals.temp_c']")
    (rf_line,) = [line for line in lines if line.startswith("node red_flag ")]
    status = {"not_evaluated": "not_evaluated", "partial": "partially_evaluated"}[case]
    assert f"status=ok screening={status}" in rf_line
    assert not any(line.startswith("!!") for line in lines[2:])


def test_inspect_no_banner_when_evaluated(env):
    lines = inspect_lines(env.executor().run_sync(compile_case("F5", F5_T)))
    assert not lines[1].startswith("!!") and not any(line.startswith("!!") for line in lines)
    assert any(line.startswith("node red_flag ") and "screening=evaluated" in line for line in lines)


def test_replay_preserves_screening_flag(env, tmp_path):
    graph = env.executor().run_sync(compile_case("F3", F3_T))
    path = tmp_path / "graph.json"
    path.write_text(to_json(graph), encoding="utf-8")
    calls = env.calls
    replayed = replay(import_graph(path.read_bytes()), OutputStore(env.root / "outputs"))
    assert env.calls == calls
    assert replayed.red_flag_screening == graph.red_flag_screening
    assert replayed.red_flag_screening.status == "not_evaluated" and replayed.red_flag_screening.performed is False
    assert (replayed.node("human_checkpoint").output[PENDING_KEY]["red_flag_screening"]
            == graph.red_flag_screening.model_dump(mode="json"))
    assert to_json(replayed) == to_json(graph)
