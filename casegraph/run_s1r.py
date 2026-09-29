"""``python -m casegraph run-s1r``: compile, execute and replay the Case Graph over S1r decision points (slice i2).

For every S1r case x T of the requested splits (I2-A04, A05, A17):

* compile from the snapshot (items with ``available_at_time <= T``) and execute on the mock gateways;
* check the invariants: 0 ``GraphValidationError``, 0 node ``error``, Red-flag and Human Checkpoint present,
  Reader:Text present iff the snapshot has a transcript, every evidence ref and every cited turn at or before T,
  Red-flag = rf-1.1.0 with exactly its declared rule results;
* replay from the Output Store: 0 gateway calls, 0 node executions, identical ``output_sha256`` per node;
* ``--no-cache``: re-execute into an empty Output Store and compare every node output hash;
* regenerate after bumping the Reasoning ``model_version``: only Reasoning and the Human Checkpoint re-execute.

Mock providers only; synthetic data; offline. System Evaluation on synthetic data — not clinical performance.
The summary is deterministic; wall time goes to a separate ``timing`` block that callers may drop.
"""

from __future__ import annotations

import json
import statistics
import time
from collections import Counter
from collections.abc import Iterable
from datetime import datetime
from pathlib import Path
from typing import Any

from .compiler import GraphValidationError, build_snapshot, compile_graph
from .data import RF_120, IntakeTranscript
from .executor import Executor
from .export import ExportedGraph
from .library import ProviderAssignment
from .providers import mock_gateways
from .sources.s1r import S1rSnapshot, load_split
from .store import MemoryStateStore, OutputStore, next_version, regenerate, replay
from .types import NodeType

BANNER = "System Evaluation on synthetic data — not clinical performance"
REGEN_REASONING_VERSION = "proj-mock-0.1+regen"


def _calls(gateways) -> int:
    return sum(g.calls for g in gateways.values())


def _time_violations(graph: ExportedGraph) -> list[str]:
    out = [f"evidence:{r.item_id}" for r in graph.evidence if r.available_at_time > graph.T]
    for n in graph.nodes:
        findings = (n.output or {}).get("Findings") if n.type is NodeType.READER_TEXT else None
        for fact in (findings or {}).get("facts", []) + (findings or {}).get("intake", []):
            for t in fact.get("evidence_turns", []):
                if datetime.fromisoformat(t["spoken_at"]) > graph.T:
                    out.append(f"turn:{t['item_id']}#{t['turn_index']}")
    return out


def _hashes(graph: ExportedGraph) -> dict[str, str | None]:
    return {n.id: n.output_sha256 for n in graph.nodes}


def check_graph(snap: S1rSnapshot, graph: ExportedGraph) -> list[str]:
    """Invariant violations for one executed S1r graph (empty when all hold)."""
    bad: list[str] = []
    types = {n.type for n in graph.nodes}
    for mandatory in (NodeType.RED_FLAG, NodeType.HUMAN_CHECKPOINT):
        if mandatory not in types:
            bad.append(f"missing:{mandatory.value}")
    has_tx = any(isinstance(i, IntakeTranscript) for i in snap.items if i.available_at_time <= snap.T)
    if (NodeType.READER_TEXT in types) != has_tx:
        bad.append("reader_text_iff_transcript")
    bad += [f"node_error:{n.id}" for n in graph.nodes if n.status == "error"]
    rf = graph.by_type(NodeType.RED_FLAG)
    if rf is not None and rf.output is not None:
        alerts = rf.output["Alerts"]
        if alerts.get("rule_set_version") != RF_120:
            bad.append("red_flag_not_rf110")
        if len(alerts.get("rule_results", [])) != 17:
            bad.append("red_flag_rule_count")
    bad += [f"future:{x}" for x in _time_violations(graph)]
    return bad


def run(
    dataset: Path, splits: Iterable[str], *, replay_check: bool = True, no_cache: bool = False,
    regenerate_check: bool = True,
) -> dict[str, Any]:
    gateways = mock_gateways()
    outputs, state = OutputStore(), MemoryStateStore()
    executor = Executor(gateways, outputs, state)
    per_split: dict[str, Any] = {}
    timing: dict[str, list[float]] = {}
    for split in splits:
        snaps = load_split(Path(dataset), split)
        shapes: Counter[str] = Counter()
        status: Counter[str] = Counter()
        screening: Counter[str] = Counter()
        calls_per_node: Counter[str] = Counter()
        violations: dict[str, list[str]] = {}
        compile_errors: dict[str, str] = {}
        replay_bad: list[str] = []
        nocache_bad: list[str] = []
        regen_counts: Counter[str] = Counter()
        total_calls = 0
        walls: list[float] = []
        for snap in snaps:
            try:
                version, parent = next_version(state, snap.patient_ref)
                graph_v = compile_graph(build_snapshot(snap.items, snap.T, snap.patient_ref),
                                        version=version, parent_version=parent)
            except GraphValidationError as exc:
                compile_errors[snap.dp_id] = exc.code
                continue
            t0 = time.perf_counter()
            graph = executor.run_sync(graph_v)
            walls.append((time.perf_counter() - t0) * 1000)
            shapes["+".join(n.id for n in graph.nodes)] += 1
            status.update(n.status for n in graph.nodes)
            screening[graph.red_flag_screening.status] += 1
            for n in graph.nodes:
                calls_per_node[n.id] += n.gateway_calls
            total_calls += graph.totals.gateway_calls
            bad = check_graph(snap, graph)
            if bad:
                violations[snap.dp_id] = bad

            if replay_check:
                c0, e0 = _calls(gateways), sum(executor.node_executions.values())
                replayed = replay(graph.graph_id, outputs, state)
                if (_calls(gateways) != c0 or sum(executor.node_executions.values()) != e0
                        or _hashes(replayed) != _hashes(graph)):
                    replay_bad.append(snap.dp_id)
            if no_cache:
                fresh = Executor(gateways, OutputStore(), MemoryStateStore())
                again = fresh.run_sync(compile_graph(build_snapshot(snap.items, snap.T, snap.patient_ref),
                                                     version=version, parent_version=parent))
                if _hashes(again) != _hashes(graph):
                    nocache_bad.append(snap.dp_id)
            if regenerate_check and NodeType.REASONING in {n.type for n in graph.nodes}:
                reasoning = graph.by_type(NodeType.REASONING)
                bumped = ProviderAssignment(provider=reasoning.provider, model_version=REGEN_REASONING_VERSION)
                regen = regenerate(executor, graph.graph_id, swap_provider={NodeType.REASONING: bumped})
                regen_counts["+".join(n.id for n in regen.nodes if not n.cached)] += 1

        n_dp = len(snaps)
        n_exec = n_dp - len(compile_errors)
        per_split[split] = {
            "n_dp": n_dp,
            "n_patients": len({s.patient_ref for s in snaps}),
            "compiled": n_exec,
            "compile_errors": compile_errors,
            "node_status": dict(sorted(status.items())),
            "node_errors": status.get("error", 0),
            "graph_shape_histogram": dict(sorted(shapes.items())),
            "red_flag_screening_status": dict(sorted(screening.items())),
            "invariant_violations": violations,
            "gateway_calls": {"total": total_calls, "mean_per_dp": round(total_calls / n_exec, 4) if n_exec else None,
                              "per_node": dict(sorted(calls_per_node.items()))},
            "replay": None if not replay_check else {
                "checked": n_exec, "failed": replay_bad, "gateway_calls": 0 if not replay_bad else None,
                "node_executions": 0 if not replay_bad else None},
            "no_cache_rerun": None if not no_cache else {"checked": n_exec, "hash_mismatch": nocache_bad},
            "regenerate_reasoning_bump": None if not regenerate_check else {
                "bumped_model_version": REGEN_REASONING_VERSION,
                "re_executed_nodes_histogram": dict(sorted(regen_counts.items()))},
        }
        timing[split] = walls
    ok = all(
        not s["compile_errors"] and not s["node_errors"] and not s["invariant_violations"]
        and (s["replay"] is None or not s["replay"]["failed"])
        and (s["no_cache_rerun"] is None or not s["no_cache_rerun"]["hash_mismatch"])
        and (s["regenerate_reasoning_bump"] is None
             or set(s["regenerate_reasoning_bump"]["re_executed_nodes_histogram"]) <= {"reasoning+human_checkpoint"})
        for s in per_split.values()
    )
    manifest = json.loads((Path(dataset) / "manifest.json").read_text(encoding="utf-8"))
    return {
        "label": BANNER,
        "circularity_note": "Rules, fixtures, extractor lexicon and gold share authors; results are circular.",
        "dataset": {"path": str(dataset), "data_class": manifest["data_class"],
                    "seed": manifest.get("seed"), "dataset_version": manifest.get("dataset_version")},
        "providers": "mock only",
        "pass": ok,
        "splits": per_split,
        "timing": {sp: {"wall_ms_median": round(statistics.median(w), 3) if w else None,
                        "wall_ms_p95": round(sorted(w)[max(0, int(0.95 * len(w)) - 1)], 3) if w else None,
                        "note": "in-process orchestration time with mock providers; not model latency"}
                   for sp, w in timing.items()},
    }
