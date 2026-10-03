"""The Case Graph behind a triage assessment (slice i2 scope 7). Research prototype — not for clinical use.

``/api/triage/cases/{ref}/assess`` compiles and executes the Case Graph over the case evidence at ``as_of``
(S4 ``Case`` -> ``casegraph.triage_bridge.evidence_from_case``), with the default provider config: Red-flag
rf-1.1.0 with vital freshness windows, Reasoning = S4 ``department.suggest``, Human Checkpoint ``human:nurse``.
Every gateway call of the graph goes through the audited Model Gateway service (one ``gateway.invoke`` audit
row per call, hashes only) as the requesting nurse.

The nurse review endpoints (confirm / edit / reject) are the only code path that resumes the checkpoint
(:func:`resume`). Graph state and outputs are kept next to a file SQLite database (``<db>.casegraph.db`` and
``<db>.casegraph-outputs/``), or under ``CASEGRAPH_DIR``; any other database uses in-memory stores (lost on
restart: a review then fails safe with ``checkpoint_not_pending``).
"""

from __future__ import annotations

import threading
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from sqlalchemy import Engine

from casegraph.compiler import build_snapshot, compile_stage, graph_id_for
from casegraph.data import RF_110, RedFlagScreening
from casegraph.executor import Executor, ResumeError
from casegraph.export import ExportedGraph, import_graph
from casegraph.library import VOICE_EXTRACT, ProviderConfig
from casegraph.providers import with_explicit_reasoning_keys
from casegraph.staged import next_stages
from casegraph.store import MemoryStateStore, OutputStore, SQLiteStateStore, StateStore, next_version
from casegraph.triage_bridge import evidence_from_case
from casegraph.types import NodeType

from ..config import Settings
from ..deps import CurrentUser
from ..gateway import service as gateway_service
from ..gateway.contract import GatewayRequest, GatewayResponse
from ..gateway.provider import Provider
from .models import Case

GRAPH_PROVIDERS = ("project_model", VOICE_EXTRACT)  # the model provider ids of the default config


@dataclass
class GraphStores:
    outputs: OutputStore
    state: StateStore
    lock: threading.Lock


def stores_for(settings: Settings) -> GraphStores:
    """Persistent stores beside a file SQLite DB (or under ``casegraph_dir``); in-memory otherwise."""
    base: Path | None = None
    if settings.casegraph_dir:
        base = Path(settings.casegraph_dir)
        base.mkdir(parents=True, exist_ok=True)
        state_path, out_dir = base / "casegraph_state.db", base / "outputs"
    elif settings.database_url.startswith("sqlite:///") and ":memory:" not in settings.database_url:
        db = Path(settings.database_url.removeprefix("sqlite:///"))
        state_path, out_dir = db.with_name(db.stem + ".casegraph.db"), db.with_name(db.stem + ".casegraph-outputs")
        base = db.parent
    if base is None:
        return GraphStores(OutputStore(), MemoryStateStore(), threading.Lock())
    return GraphStores(OutputStore(out_dir), SQLiteStateStore(state_path), threading.Lock())


class AuditedGateway:
    """``GatewayClient`` for graph nodes: every call is one audited Model Gateway call by the acting user."""

    def __init__(self, engine: Engine, provider: Provider, user: CurrentUser, request_id: str) -> None:
        self._engine, self._provider, self._user, self._request_id = engine, provider, user, request_id
        self.calls = 0

    def invoke(self, request: GatewayRequest) -> GatewayResponse:
        self.calls += 1
        return gateway_service.invoke(self._engine, self._provider, request, self._user, request_id=self._request_id)


def _graph_provider(provider: Provider) -> Provider:
    # The offline mock states Reasoning's department/care keys explicitly (s2r); a real provider is used as is.
    return with_explicit_reasoning_keys(provider) if provider.name == "mock" else provider


def _executor(stores: GraphStores, gateways: dict[str, Any] | None = None, clock=None) -> Executor:
    kw = {"clock": clock} if clock is not None else {}
    return Executor(gateways or {}, stores.outputs, stores.state, **kw)


def run_graph(stores: GraphStores, case: Case, as_of: datetime, engine: Engine, provider: Provider,
              user: CurrentUser, request_id: str) -> ExportedGraph:
    """Compile and execute the next graph version for ``case`` at ``as_of``. Raises on a compile error."""
    gw = _graph_provider(provider)
    gateways = {pid: AuditedGateway(engine, gw, user, request_id) for pid in GRAPH_PROVIDERS}
    items = evidence_from_case(case)
    with stores.lock:  # one version number per graph (versions are insert-only)
        # cg-t123: every pending stage is built in order (a T2 trigger then a T3 trigger builds both; none is skipped).
        # The stages come from results/orders newer than the previous version's T; with none the version inherits the
        # parent's stage (T1 / nurse when there is no parent). Triage cases carry no results or orders.
        _, parent = next_version(stores.state, case.case_ref)
        parent_spec = stores.state.load_graph(graph_id_for(case.case_ref, parent))[0] if parent else None
        executor = _executor(stores, gateways)
        graph = None
        for plan in next_stages(parent_spec, items, as_of):
            version, parent = next_version(stores.state, case.case_ref)
            compiled = compile_stage(build_snapshot(items, plan.T, case.case_ref), plan.stage, ProviderConfig(),
                                     version, parent, trigger_refs=tuple(sorted(plan.trigger_item_ids)))
            graph = executor.run_sync(compiled)
        assert graph is not None
        return graph


def versions(stores: GraphStores, case_ref: str) -> list[dict[str, Any]]:
    """Every stored version of ``case_ref`` (data only; cg-t123): stage, T, triggers, checkpoint, alerts, cost.

    A version whose run was not recorded (execution failed) is listed with ``executed: false``, never hidden.
    """
    out: list[dict[str, Any]] = []
    latest = stores.state.latest_version(case_ref) or 0
    for v in range(1, latest + 1):
        graph_id = graph_id_for(case_ref, v)
        graph = load(stores, graph_id)
        if graph is None:
            try:
                spec, _ = stores.state.load_graph(graph_id)
            except KeyError:
                continue
            out.append({"graph_id": graph_id, "version": v, "parent_version": spec.parent_version,
                        "stage": spec.stage, "T": spec.T.isoformat(), "trigger_refs": list(spec.trigger_refs),
                        "executed": False})
            continue
        hc = graph.by_type(NodeType.HUMAN_CHECKPOINT)
        payload = (hc.output or {}).get("pending_review") if hc is not None else None
        out.append({
            "graph_id": graph_id, "version": v, "parent_version": graph.parent_version, "stage": graph.stage,
            "T": graph.T.isoformat(), "trigger_refs": list(graph.trigger_refs), "executed": True,
            "data_class": hc.data_class if hc is not None else "unknown",
            "checkpoint_role": hc.provider.split(":", 1)[1] if hc is not None else None,
            "checkpoint_status": hc.status if hc is not None else None,
            "escalation": bool(payload["escalation"]) if payload else None,
            "alert_rule_ids": sorted({a["rule_id"] for a in (graph_alerts(graph) or [])}),
            "screening_status": graph.red_flag_screening.status,
            "nodes": [{"id": n.id, "type": n.type.value, "provider": n.provider, "status": n.status,
                       "cached": n.cached, "gateway_calls": n.gateway_calls} for n in graph.nodes],
            "totals": graph.totals.model_dump(mode="json") if graph.totals else None,
        })
    return out


def unavailable_screening() -> dict[str, Any]:
    """The screening block when no graph ran: ``unavailable`` (NOT PERFORMED), never an all-clear."""
    return RedFlagScreening.from_alerts(None, RF_110).model_dump(mode="json")


def screening_block(graph: ExportedGraph) -> dict[str, Any]:
    block = graph.red_flag_screening.model_dump(mode="json")
    block["summary"] = graph.red_flag_screening.summary()  # never "no red flags" (C2)
    return block


def graph_alerts(graph: ExportedGraph) -> list[dict[str, Any]] | None:
    """The alerts the graph's Red-flag node raised (None: the node did not produce Alerts)."""
    rf = graph.by_type(NodeType.RED_FLAG)
    if rf is None or rf.status != "ok" or rf.output is None:
        return None
    return list(rf.output["Alerts"]["alerts"])


def load(stores: GraphStores, graph_id: str) -> ExportedGraph | None:
    run_json = stores.state.load_run(graph_id)
    return import_graph(run_json) if run_json is not None else None


def checkpoint_status(stores: GraphStores, graph_id: str) -> str | None:
    graph = load(stores, graph_id)
    hc = graph.by_type(NodeType.HUMAN_CHECKPOINT) if graph is not None else None
    return hc.status if hc is not None else None


def confirmation_clock(graph: ExportedGraph, wall=None):
    """The Human Checkpoint confirmation clock (data rule 3: a confirmation is never stamped before T).

    Synthetic fixtures live on a simulated timeline (some S4 author cases are dated after today). For a graph
    whose checkpoint data class is ``synthetic`` the confirmation time is the wall clock, or T when the wall
    clock is earlier; any other data class uses the wall clock and is refused before T. Either way the
    ConfirmedEvidence is available at or after T, so it never enters a snapshot before T.
    """
    wall = wall or (lambda: datetime.now(timezone.utc))
    hc = graph.by_type(NodeType.HUMAN_CHECKPOINT)
    if hc is not None and hc.data_class == "synthetic":
        return lambda: max(wall(), graph.T)
    return wall


def resume_refusal(stores: GraphStores, graph_id: str, role: str, wall=None) -> str | None:
    """Why the checkpoint cannot be resumed by ``role`` now (None: it can). Checked before any review write."""
    graph = load(stores, graph_id)
    hc = graph.by_type(NodeType.HUMAN_CHECKPOINT) if graph is not None else None
    if hc is None or hc.status != "pending_confirmation":
        return "checkpoint_not_pending"
    if hc.provider != f"human:{role}":
        return "checkpoint_role_mismatch"
    if confirmation_clock(graph, wall)() < graph.T:  # type: ignore[arg-type,union-attr]
        return "confirmation_before_decision_time"
    return None


def resume(stores: GraphStores, graph_id: str, action: str, reviewer_id: str, role: str,
           edited_payload: dict[str, Any] | None = None, wall=None):
    """The single production caller of ``Executor.resume`` (the nurse confirm / edit / reject endpoints).

    confirm and edit append ``ConfirmedEvidence`` at the confirmation time; reject appends nothing.
    """
    graph = load(stores, graph_id)
    if graph is None:
        raise RuntimeError(f"checkpoint resume failed for {graph_id}: no executed graph")
    try:
        return _executor(stores, clock=confirmation_clock(graph, wall)).resume(
            graph_id, action, reviewer_id, role, edited_payload=edited_payload)
    except (ResumeError, KeyError) as exc:  # pre-checked by resume_refusal; a race still fails loudly
        raise RuntimeError(f"checkpoint resume failed for {graph_id}: {type(exc).__name__}") from None
