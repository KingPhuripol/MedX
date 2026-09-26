"""Typed Graph Executor (PROPOSAL 3.2.3).

Topological order via ``graphlib.TopologicalSorter``; independent ready nodes run concurrently on
``asyncio`` (sync provider/rule bodies via ``asyncio.to_thread``). Every node result goes to the
Output Store. Execution halts at the Human Checkpoint with ``pending_confirmation`` persisted in a
StateStore; ``resume`` records the reviewer decision. Failures are fail-safe: ``error`` with
``output=null``; Reasoning abstains when required inputs are missing or errored.
"""

from __future__ import annotations

import asyncio
import time
from collections import Counter
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from datetime import datetime, timezone
from graphlib import TopologicalSorter
from typing import Any

from app.gateway.contract import DataClass, GatewayRequest

from .compiler import ValidatedGraph, validate
from .data import (
    Alerts,
    CareSuggestion,
    CaseSummary,
    ConfirmedEvidence,
    ConfirmedResult,
    DepartmentSuggestion,
    Evidence,
    Findings,
    ImageTokens,
    MedicationIssues,
    MedicationList,
    Vitals,
    dump_evidence,
    sha256_json,
)
from .export import EdgeSpec, ExportedGraph, ExportedNode, GraphSpec, NodeSpec, Totals, import_graph, to_json
from .library import MODEL_PROVIDERS, RULES_VERSIONS, output_types
from .providers import GatewayClient, pharma_rules, red_flag_rules, vitals_reader_rules
from .store import OutputStore, StateStore, StoreEntry, cache_key
from .types import NodeType

PENDING_KEY = "pending_review"
_ACTION_STATUS = {"confirm": "confirmed", "edit": "edited", "reject": "rejected"}


class ResumeError(Exception):
    """A Human Checkpoint resume request was refused (wrong role, not pending, bad action)."""


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _iso(dt: datetime) -> str:
    return dt.isoformat(timespec="microseconds")


@dataclass
class _Result:
    status: str
    output: dict[str, Any] | None = None
    missing_inputs: tuple[str, ...] = ()
    errored_inputs: tuple[str, ...] = ()
    reason: str | None = None
    gateway_calls: int = 0


@dataclass
class _Upstream:
    edge: EdgeSpec
    node: ExportedNode

    @property
    def ok(self) -> bool:
        return self.node.status == "ok" and self.node.output is not None

    @property
    def ref(self) -> str:
        return f"{self.node.id}:{self.node.output_sha256}"


@dataclass
class _Ctx:
    node: NodeSpec
    evidence: list[Evidence]
    upstream: list[_Upstream]
    input_hash: str
    calls: int = field(default=0)


def _dump(*models) -> dict[str, Any]:
    return {type(m).__name__: m.model_dump(mode="json") for m in models}


class _SchemaInvalid(Exception):
    pass


class Executor:
    def __init__(
        self,
        gateways: Mapping[str, GatewayClient],
        output_store: OutputStore,
        state_store: StateStore,
        *,
        clock: Callable[[], datetime] = _now,
    ) -> None:
        self.gateways = gateways
        self.outputs = output_store
        self.state = state_store
        self.clock = clock  # used for confirmation times (injectable for tests)
        self.node_executions: Counter[str] = Counter()  # node bodies actually run (incl. rules)

    # ------------------------------------------------------------------------------------ run

    def run_sync(self, graph: ValidatedGraph) -> ExportedGraph:
        return asyncio.run(self.run(graph))

    async def run(self, graph: ValidatedGraph) -> ExportedGraph:
        if not isinstance(graph, ValidatedGraph) or not graph.is_authentic:
            raise TypeError("Executor accepts only a ValidatedGraph issued by casegraph.compiler.validate")
        if graph.snapshot is None:
            raise ValueError("graph carries no snapshot payload; use casegraph.store.replay")
        # Re-check the exact (spec, snapshot) pair about to run, so a token can never vouch for a
        # graph other than the one validated. Raises GraphValidationError before any side effect.
        validate(graph.spec, graph.snapshot)
        spec, items = graph.spec, {i.item_id: i for i in graph.snapshot.items}
        self.state.save_graph(spec, graph.snapshot.items)  # insert-only: versions are immutable
        t0 = time.perf_counter()
        preds = {n.id: {e.src for e in spec.edges if e.dst == n.id} for n in spec.nodes}
        sorter = TopologicalSorter(preds)
        sorter.prepare()
        results: dict[str, ExportedNode] = {}
        running: dict[asyncio.Task, str] = {}
        while sorter.is_active():
            for nid in sorter.get_ready():
                # All predecessors are done here: a node never starts before them.
                task = asyncio.create_task(self._run_node(spec, spec.node(nid), items, dict(results)))
                running[task] = nid
            done, _ = await asyncio.wait(running, return_when=asyncio.FIRST_COMPLETED)
            for task in done:
                nid = running.pop(task)
                results[nid] = task.result()
                sorter.done(nid)
        nodes = tuple(results[n.id] for n in spec.nodes)
        exported = ExportedGraph(
            **spec.model_dump(exclude={"nodes"}),
            nodes=nodes,
            totals=Totals(
                gateway_calls=sum(n.gateway_calls for n in nodes),
                node_executions=sum(not n.cached for n in nodes),
                wall_time_ms=round((time.perf_counter() - t0) * 1000, 3),
            ),
        )
        self.state.save_run(spec.graph_id, to_json(exported))
        return exported

    async def _run_node(
        self, spec: GraphSpec, node: NodeSpec, items: dict[str, Evidence], results: dict[str, ExportedNode]
    ) -> ExportedNode:
        started = _now()
        upstream = [_Upstream(e, results[e.src]) for e in spec.edges if e.dst == node.id]
        evidence = [items[r] for r in node.evidence_refs]
        input_hash = sha256_json(
            {
                "evidence": [[i.item_id, i.content_sha256()] for i in evidence],
                "upstream": sorted([u.node.id, u.edge.data_type, u.node.status, u.node.output_sha256] for u in upstream),
            }
        )
        key = cache_key(node.type.value, node.provider, node.model_version, node.params, input_hash)
        base = node.model_dump()
        entry = self.outputs.get(key)
        if entry is not None and entry.status != "error":
            return ExportedNode(
                **base, cache_key=key, status=entry.status, started_at=_iso(started), ended_at=_iso(_now()),
                gateway_calls=0, cached=True, output=entry.output, output_sha256=entry.output_sha256,
                missing_inputs=entry.missing_inputs, errored_inputs=entry.errored_inputs, reason=entry.reason,
            )
        self.node_executions[node.id] += 1
        ctx = _Ctx(node, evidence, upstream, input_hash)
        try:
            res = await asyncio.to_thread(self._body, ctx)
        except Exception:  # fail safe: never fabricate an output
            res = _Result("error", reason="node_exception")
        res.gateway_calls = ctx.calls
        if res.status == "error":
            res.output = None
        ended = _now()
        out_sha = sha256_json(res.output)
        self.outputs.put(
            StoreEntry(
                cache_key=key, node_type=node.type.value, status=res.status, output=res.output,  # type: ignore[arg-type]
                output_sha256=out_sha, missing_inputs=res.missing_inputs, errored_inputs=res.errored_inputs,
                reason=res.reason, started_at=_iso(started), ended_at=_iso(ended), gateway_calls=res.gateway_calls,
            )
        )
        return ExportedNode(
            **base, cache_key=key, status=res.status, started_at=_iso(started), ended_at=_iso(ended),
            gateway_calls=res.gateway_calls, cached=False, output=res.output, output_sha256=out_sha,
            missing_inputs=res.missing_inputs, errored_inputs=res.errored_inputs, reason=res.reason,
        )

    # --------------------------------------------------------------------------------- bodies

    def _body(self, ctx: _Ctx) -> _Result:
        t = ctx.node.type
        if t is NodeType.RED_FLAG:
            return self._red_flag(ctx)
        if t is NodeType.REASONING:
            return self._reasoning(ctx)
        if t is NodeType.HUMAN_CHECKPOINT:
            return self._checkpoint(ctx)
        if t is NodeType.PHARMA_AGENT:
            return self._pharma(ctx)
        return self._reader(ctx)

    def _derived(self, ctx: _Ctx, extra_refs: list[str] | None = None) -> dict[str, Any]:
        refs = [i.item_id for i in ctx.evidence] + [u.ref for u in ctx.upstream if u.ok] + (extra_refs or [])
        return {"produced_by": ctx.node.id, "input_refs": tuple(refs), "provider": ctx.node.provider,
                "model_version": ctx.node.model_version}

    def _call(self, ctx: _Ctx, inputs: dict[str, Any]) -> tuple[dict[str, Any] | None, str | None, str | None]:
        """One gateway call. Returns (output, request_sha256, error_reason)."""
        gateway = self.gateways.get(ctx.node.provider)
        if gateway is None:
            return None, None, "provider_unavailable"
        request = GatewayRequest(
            task=ctx.node.type.value,
            inputs={"model_version": ctx.node.model_version, "params": ctx.node.params, **inputs},
            data_class=DataClass(ctx.node.data_class),
        )
        ctx.calls += 1
        response = gateway.invoke(request)
        if response.status != "ok" or response.output is None:
            return None, response.request_sha256, f"gateway_{response.status}:{response.reason}"
        return response.output, response.request_sha256, None

    @staticmethod
    def _text(output: dict[str, Any]) -> str:
        text = output.get("text")
        if not isinstance(text, str) or not text:
            raise _SchemaInvalid("output.text must be a non-empty string")
        return text

    def _reader(self, ctx: _Ctx) -> _Result:
        node = ctx.node
        source_types = tuple(sorted({i.data_type for i in ctx.evidence}))
        if node.provider == "rules":
            statements = vitals_reader_rules(ctx.evidence)  # type: ignore[arg-type]
            return _Result("ok", _dump(Findings(**self._derived(ctx), source_data_types=source_types,
                                                statements=statements)))
        if node.provider not in MODEL_PROVIDERS:
            return _Result("error", reason="provider_unsupported")
        output, req_sha, err = self._call(ctx, {"evidence": dump_evidence(ctx.evidence)})
        if err:
            return _Result("error", reason=err)
        try:
            text = self._text(output)  # type: ignore[arg-type]
        except _SchemaInvalid:
            return _Result("error", reason="schema_invalid")
        if output_types(node.type, node.provider) == ("ImageTokens",):
            tokens = ImageTokens(
                **self._derived(ctx), modality="+".join(source_types), encoder_provider=node.provider,
                token_ref=f"gateway-request:{req_sha}", token_sha256=sha256_json({"text": text}),
            )
            return _Result("ok", _dump(tokens))
        return _Result("ok", _dump(Findings(**self._derived(ctx), source_data_types=source_types,
                                            statements=(text,))))

    def _red_flag(self, ctx: _Ctx) -> _Result:
        vitals = [i for i in ctx.evidence if isinstance(i, Vitals)]
        findings = [u for u in ctx.upstream if u.edge.data_type == "Findings" and u.ok]
        errored = tuple(sorted(u.node.id for u in ctx.upstream if u.node.status == "error"))
        missing = tuple(name for name, have in (("Findings", findings), ("Vitals", vitals)) if not have)
        version = RULES_VERSIONS[NodeType.RED_FLAG]
        if not vitals and not findings:
            alerts = Alerts(**self._derived(ctx), status="not_evaluated", alerts=(), missing_inputs=missing,
                            rule_set_version=version)
        else:
            alerts = Alerts(**self._derived(ctx), status="evaluated", alerts=red_flag_rules(vitals),
                            missing_inputs=missing, rule_set_version=version)
        return _Result("ok", _dump(alerts), missing_inputs=missing, errored_inputs=errored)

    def _pharma(self, ctx: _Ctx) -> _Result:
        lists = [i for i in ctx.evidence if isinstance(i, MedicationList)]
        if ctx.node.provider == "rules":
            issues = MedicationIssues(**self._derived(ctx), issues=pharma_rules(lists),
                                      rule_set_version=RULES_VERSIONS[NodeType.PHARMA_AGENT])
            return _Result("ok", _dump(issues))
        upstream = {u.node.id: u.node.output for u in ctx.upstream if u.ok}
        output, _, err = self._call(ctx, {"evidence": dump_evidence(lists), "upstream": upstream})
        if err:
            return _Result("error", reason=err)
        try:
            text = self._text(output)  # type: ignore[arg-type]
        except _SchemaInvalid:
            return _Result("error", reason="schema_invalid")
        return _Result("ok", _dump(MedicationIssues(**self._derived(ctx), issues=(), summary=text)))

    def _reasoning(self, ctx: _Ctx) -> _Result:
        errored = tuple(sorted(u.node.id for u in ctx.upstream if u.node.status == "error"))
        missing = []
        for req in ctx.node.params.get("required_inputs", []):
            data_type, _, source = req.partition("<-")
            satisfied = any(
                u.ok and u.edge.data_type == data_type
                and (not source or source in u.node.output.get(data_type, {}).get("source_data_types", ()))
                for u in ctx.upstream
            )
            if not satisfied:
                missing.append(req)
        if missing:  # abstain: 0 gateway calls, no Summary/Suggestion object
            return _Result("abstained", None, missing_inputs=tuple(missing), errored_inputs=errored)
        upstream = {u.node.id: u.node.output for u in ctx.upstream if u.ok}
        output, _, err = self._call(ctx, {"upstream": upstream})
        if err:
            return _Result("error", reason=err, errored_inputs=errored)
        try:
            text = self._text(output)  # type: ignore[arg-type]
            department = output.get("department")  # type: ignore[union-attr]
            care = output.get("care", [])  # type: ignore[union-attr]
            if department is not None and not isinstance(department, str):
                raise _SchemaInvalid("department")
            if not isinstance(care, list) or not all(isinstance(c, str) for c in care):
                raise _SchemaInvalid("care")
        except _SchemaInvalid:
            return _Result("error", reason="schema_invalid", errored_inputs=errored)
        d = self._derived(ctx)
        return _Result(
            "ok",
            _dump(CaseSummary(**d, text=text), DepartmentSuggestion(**d, department=department),
                  CareSuggestion(**d, items=tuple(care))),
            errored_inputs=errored,
        )

    def _checkpoint(self, ctx: _Ctx) -> _Result:
        rf = next((u for u in ctx.upstream if u.edge.data_type == "Alerts"), None)
        alerts = rf.node.output.get("Alerts") if rf is not None and rf.ok else None
        reasons = []
        if alerts is None:
            reasons.append("red_flag_unavailable")
        elif alerts["status"] == "not_evaluated":
            reasons.append("red_flag_not_evaluated")
        elif any(a["severity"] == "urgent" for a in alerts["alerts"]):
            reasons.append("urgent_red_flag")
        by_node: dict[str, ExportedNode] = {u.node.id: u.node for u in ctx.upstream}
        payload = {
            "required_role": ctx.node.provider.split(":", 1)[1],
            "escalation": bool(reasons),
            "escalation_reasons": reasons,
            "alerts": alerts,
            "for_review": {nid: n.output for nid, n in sorted(by_node.items()) if n.status == "ok" and nid != "red_flag"},
            "abstained": {nid: list(n.missing_inputs) for nid, n in sorted(by_node.items()) if n.status == "abstained"},
            # direct upstream failures plus failures that upstream nodes reported from further up
            "errored": sorted({nid for nid, n in by_node.items() if n.status == "error"}
                              | {e for n in by_node.values() for e in n.errored_inputs}),
            "input_hash": ctx.input_hash,
        }
        return _Result("pending_confirmation", {PENDING_KEY: payload})

    # --------------------------------------------------------------------------- export/resume

    def export(self, graph_id: str) -> ExportedGraph:
        run_json = self.state.load_run(graph_id)
        if run_json is None:
            raise KeyError(graph_id)
        return import_graph(run_json)

    def resume(
        self,
        graph_id: str,
        action: str,
        reviewer_id: str,
        reviewer_role: str,
        edited_payload: dict[str, Any] | None = None,
    ) -> ConfirmedResult:
        """Record a reviewer decision at the Human Checkpoint. Makes no gateway call."""
        if action not in _ACTION_STATUS:
            raise ResumeError(f"unknown action {action!r}")
        graph = self.export(graph_id)
        hc = graph.by_type(NodeType.HUMAN_CHECKPOINT)
        if hc is None or hc.status != "pending_confirmation" or hc.output is None:
            raise ResumeError(f"{graph_id}: checkpoint is not pending confirmation")
        if hc.provider != f"human:{reviewer_role}":
            raise ResumeError(f"{graph_id}: checkpoint requires {hc.provider}, not human:{reviewer_role}")
        if action == "edit" and edited_payload is None:
            raise ResumeError("edit requires edited_payload")
        pending = hc.output[PENDING_KEY]
        now = self.clock()
        result = ConfirmedResult(
            produced_by=hc.id, input_refs=(f"{hc.id}:{hc.output_sha256}",), provider=hc.provider,
            model_version=hc.model_version, action=action, graph_id=graph_id,  # type: ignore[arg-type]
            reviewer_id=reviewer_id, reviewer_role=reviewer_role,  # type: ignore[arg-type]
            confirmed_at=now, checkpoint_input_hash=pending["input_hash"],
            payload={"confirm": pending, "edit": edited_payload, "reject": None}[action],
        )
        updated = hc.model_copy(update={"status": _ACTION_STATUS[action],
                                        "confirmation": result.model_dump(mode="json")})
        graph = graph.model_copy(update={"nodes": tuple(updated if n.id == hc.id else n for n in graph.nodes)})
        self.state.save_run(graph_id, to_json(graph))
        if action != "reject":  # the confirmed result re-enters the record, visible from `now` onwards
            self.state.append_evidence(
                ConfirmedEvidence(
                    item_id=f"confirmed:{graph_id}:{hc.id}", patient_ref=graph.patient_ref,
                    event_time=now, available_at_time=now, source="human_checkpoint",
                    provenance=f"casegraph/{graph_id}/{hc.id}", version="1", data_class=hc.data_class,  # type: ignore[arg-type]
                    result=result,
                )
            )
        return result
