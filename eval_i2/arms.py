"""Both arms over every S1r case x T of one split, built from snapshot inputs only (no gold, no journey).

* Arm A (Case Graph): compile + execute through the Executor on the mock gateways, then replay from the Output
  Store (0 calls, identical node hashes).
* Arm B (single prompt): one gateway call per DP, task ``casegraph.single_prompt.v1``, whole snapshot serialized.
  Its handler composes the same registered handler versions; no graph-only steps.

The arms alternate per DP (A first on even DPs, B first on odd DPs); wall time is measured in-process and returned
separately (orchestration overhead with a mock provider, not model latency). Research prototype - not for clinical
use.
"""

from __future__ import annotations

import time
from pathlib import Path
from typing import Any

from app.config import Settings
from app.gateway import build_provider
from app.gateway.contract import DataClass, GatewayRequest
from app.triage import department
from casegraph import single_prompt
from casegraph.compiler import build_snapshot, compile_graph
from casegraph.executor import Executor
from casegraph.providers import LocalGateway, mock_gateways
from casegraph.sources.s1r import S1rSnapshot, load_split
from casegraph.store import MemoryStateStore, OutputStore, next_version, replay
from casegraph.types import NodeType

ARM_A, ARM_B = "case_graph", "single_prompt"


def _arm_a(executor: Executor, state: MemoryStateStore, outputs: OutputStore, gateways, snap: S1rSnapshot
           ) -> dict[str, Any]:
    version, parent = next_version(state, snap.patient_ref)
    graph = executor.run_sync(compile_graph(build_snapshot(snap.items, snap.T, snap.patient_ref),
                                            version=version, parent_version=parent))
    calls0 = sum(g.calls for g in gateways.values())
    replayed = replay(graph.graph_id, outputs, state)
    replay_ok = (sum(g.calls for g in gateways.values()) == calls0
                 and [n.output_sha256 for n in replayed.nodes] == [n.output_sha256 for n in graph.nodes])
    reasoning = graph.by_type(NodeType.REASONING)
    dept = ((reasoning.output or {}).get("DepartmentSuggestion") if reasoning else None) or {}
    alerts = graph.node("red_flag").output["Alerts"]
    return {
        "graph_id": graph.graph_id,
        "shape": [n.id for n in graph.nodes],
        "node_status": {n.id: n.status for n in graph.nodes},
        "calls": graph.totals.gateway_calls,
        "calls_per_node": {n.id: n.gateway_calls for n in graph.nodes},
        "department": {
            "status": dept.get("status", reasoning.status if reasoning else "absent"),
            "top3": [e["code"] for e in dept.get("top3", [])],
            "reason": dept.get("reason") or (reasoning.reason if reasoning else "no_reasoning_node"),
            "missing_information": list(dept.get("missing_information", reasoning.missing_inputs if reasoning else ())),
        },
        "red_flag": {
            "rule_set_version": alerts["rule_set_version"],
            "status": alerts["status"],
            "fired": sorted({a["rule_id"] for a in alerts["alerts"]}),
            "not_evaluated": list(alerts["rules_not_evaluated"]),
            "missing_inputs": {r["rule_id"]: list(r["missing_inputs"]) for r in alerts["rule_results"]
                               if r["status"] == "not_evaluated"},
            "evaluated_on": {r["rule_id"]: list(r["evaluated_on"]) for r in alerts["rule_results"]
                             if r["status"] == "evaluated"},
        },
        "handler_versions": _versions_a(graph, dept),
        "node_hashes": {n.id: n.output_sha256 for n in graph.nodes},
        "replay_ok": replay_ok,
    }


def _versions_a(graph, dept: dict[str, Any]) -> dict[str, str]:
    """task -> handler version actually used by Arm A (from the Reader:Text statements and the S4 call)."""
    out: dict[str, str] = {}
    rt = graph.by_type(NodeType.READER_TEXT)
    for st in ((rt.output or {}).get("Findings", {}).get("statements", []) if rt else []):
        if ": read by " in st:
            for part in st.split(": read by ", 1)[1].split(", "):
                task, _, mv = part.partition("=")
                out[task] = mv.removeprefix("mock-0.1.0+")
    if dept.get("gateway_model_version"):
        out[department.TASK] = dept["gateway_model_version"].removeprefix("mock-0.1.0+")
    return out


def _arm_b(gateway: LocalGateway, snap: S1rSnapshot) -> dict[str, Any]:
    items = list(build_snapshot(snap.items, snap.T, snap.patient_ref).items)  # the same time filter as Arm A
    request = GatewayRequest(task=single_prompt.TASK, data_class=DataClass.SYNTHETIC,
                             inputs=single_prompt.request_inputs(snap.patient_ref, snap.T, items))
    calls0 = gateway.calls
    response = gateway.invoke(request)
    ranking = department.parse_ranking({"ranking": (response.output or {}).get("ranking", [])}) \
        if response.status == "ok" else None
    top3 = [e.code for e in department.top3_of(ranking)] if ranking else []
    return {
        "calls": gateway.calls - calls0,
        "status": response.status,
        "model_version": response.model_version,
        "handler_versions": (response.output or {}).get("handler_versions"),
        "department": {"status": "suggested" if top3 else "abstained", "top3": top3,
                       "reason": None if top3 else ("no_evidence_matched" if response.status == "ok"
                                                    else f"gateway_{response.status}")},
        "red_flag": None,
    }


def run_split(dataset: Path, split: str) -> tuple[list[dict[str, Any]], dict[str, dict[str, float]]]:
    """(one record per DP with both arms, {dp_id: {arm: wall_ms}}). Deterministic except the timing map."""
    snaps = load_split(Path(dataset), split)
    gateways = mock_gateways()
    outputs, state = OutputStore(), MemoryStateStore()
    executor = Executor(gateways, outputs, state)
    gateway_b = LocalGateway(build_provider("mock", Settings()))
    records, timing = [], {}
    for i, snap in enumerate(snaps):
        order = (ARM_A, ARM_B) if i % 2 == 0 else (ARM_B, ARM_A)
        res, wall = {}, {}
        for arm in order:
            t0 = time.perf_counter()
            res[arm] = (_arm_a(executor, state, outputs, gateways, snap) if arm == ARM_A else _arm_b(gateway_b, snap))
            wall[arm] = round((time.perf_counter() - t0) * 1000, 3)
        timing[snap.dp_id] = wall
        records.append({"dp_id": snap.dp_id, "case_id": snap.case_id, "decision_point": snap.decision_point,
                        "patient_ref": snap.patient_ref, "split": split, "T": snap.T.isoformat(),
                        "first_arm": order[0], ARM_A: res[ARM_A], ARM_B: res[ARM_B]})
    return records, timing


def handler_versions() -> dict[str, str]:
    return single_prompt.handler_versions()
