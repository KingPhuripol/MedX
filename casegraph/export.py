"""Graph schema, JSON export/import and ``inspect`` (PROPOSAL 3.2.3, Scope 7).

The exported graph *is* the executed structure: nodes (type, provider, version, params, cache key,
status, timing, gateway calls, output + hash), typed edges, evidence references and totals.
Import followed by export is byte-identical.

s2r (``casegraph-export/0.2``): a required graph-level ``red_flag_screening`` summary. Importing any
other schema version raises :class:`ExportVersionError`; a missing summary is never defaulted.
"""

from __future__ import annotations

import json
from typing import Any, Literal

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, model_validator

from .data import RedFlagScreening
from .types import NodeType

SCHEMA_VERSION = "casegraph-export/0.2"


class ExportVersionError(ValueError):
    """An export with a schema version other than :data:`SCHEMA_VERSION` (never migrated silently)."""

NodeStatus = Literal["ok", "error", "abstained", "pending_confirmation", "confirmed", "edited", "rejected"]


class _Frozen(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")


class EvidenceRef(_Frozen):
    item_id: str
    data_type: str
    event_time: AwareDatetime
    available_at_time: AwareDatetime
    source: str
    version: str
    data_class: str
    sha256: str


class EdgeSpec(_Frozen):
    src: str
    dst: str
    data_type: str


class NodeSpec(_Frozen):
    id: str
    type: NodeType
    provider: str
    model_version: str
    params: dict[str, Any]
    data_class: str  # most restrictive data class among the node's (transitive) inputs
    reproducible: bool  # False for external_model: "may differ on rerun" (3.2.3)
    evidence_refs: tuple[str, ...]


class GraphSpec(_Frozen):
    schema_version: str = SCHEMA_VERSION
    graph_id: str
    patient_ref: str
    T: AwareDatetime
    snapshot_id: str
    version: int = Field(ge=1)
    parent_version: int | None
    nodes: tuple[NodeSpec, ...]
    edges: tuple[EdgeSpec, ...]
    evidence: tuple[EvidenceRef, ...]

    def node(self, node_id: str) -> NodeSpec:
        return next(n for n in self.nodes if n.id == node_id)

    def to_json(self) -> str:
        return to_json(self)


class ExportedNode(NodeSpec):
    cache_key: str | None = None
    status: NodeStatus | None = None
    started_at: str | None = None
    ended_at: str | None = None
    gateway_calls: int = 0
    cached: bool = False
    output: dict[str, Any] | None = None
    output_sha256: str | None = None
    missing_inputs: tuple[str, ...] = ()
    errored_inputs: tuple[str, ...] = ()
    reason: str | None = None
    confirmation: dict[str, Any] | None = None


class Totals(_Frozen):
    gateway_calls: int
    node_executions: int
    wall_time_ms: float


class ExportedGraph(GraphSpec):
    nodes: tuple[ExportedNode, ...]  # type: ignore[assignment]
    red_flag_screening: RedFlagScreening  # required, no default (s2r)
    totals: Totals | None = None

    @model_validator(mode="after")
    def _screening_matches_red_flag(self) -> "ExportedGraph":
        if self.schema_version != SCHEMA_VERSION:
            raise ExportVersionError(f"unsupported export schema {self.schema_version!r}; expected {SCHEMA_VERSION}")
        rf = self.by_type(NodeType.RED_FLAG)
        alerts = (rf.output or {}).get("Alerts") if rf is not None and rf.status == "ok" else None
        expected = "unavailable" if alerts is None else alerts.get("status")
        if self.red_flag_screening.status != expected:
            raise ValueError(f"red_flag_screening.status {self.red_flag_screening.status!r} != red_flag node {expected!r}")
        return self

    def node(self, node_id: str) -> ExportedNode:  # type: ignore[override]
        return next(n for n in self.nodes if n.id == node_id)

    def by_type(self, node_type: NodeType) -> ExportedNode | None:
        return next((n for n in self.nodes if n.type == node_type), None)

    def spec(self) -> GraphSpec:
        data = self.model_dump(mode="json", exclude={"totals", "red_flag_screening"})
        run_fields = set(ExportedNode.model_fields) - set(NodeSpec.model_fields)
        data["nodes"] = [{k: v for k, v in n.items() if k not in run_fields} for n in data["nodes"]]
        return GraphSpec.model_validate(data)


def to_json(model: BaseModel) -> str:
    return json.dumps(model.model_dump(mode="json"), sort_keys=True, indent=2, ensure_ascii=False) + "\n"


def import_graph(text: str | bytes) -> ExportedGraph:
    data = json.loads(text)
    version = data.get("schema_version") if isinstance(data, dict) else None
    if version != SCHEMA_VERSION:
        raise ExportVersionError(f"unsupported export schema {version!r}; expected {SCHEMA_VERSION}")
    return ExportedGraph.model_validate_json(text)


def inspect_lines(graph: ExportedGraph) -> list[str]:
    lines = [
        f"graph {graph.graph_id} patient={graph.patient_ref} T={graph.T.isoformat()} "
        f"version={graph.version} parent={graph.parent_version} snapshot={graph.snapshot_id[:12]}"
    ]
    rfs = graph.red_flag_screening
    if rfs.status == "partially_evaluated":
        lines.append(f"!! {rfs.banner} not_evaluated={list(rfs.rules_not_evaluated)} missing={list(rfs.missing_inputs)}")
    elif not rfs.performed:
        lines.append(f"!! {rfs.banner} missing={list(rfs.missing_inputs)}")
    for n in graph.nodes:
        screening = f" screening={rfs.status}" if n.type is NodeType.RED_FLAG else ""
        extra = f" missing={list(n.missing_inputs)}" if n.missing_inputs else ""
        lines.append(f"node {n.id} type={n.type.value} provider={n.provider} status={n.status}{screening}{extra}")
    for e in graph.edges:
        lines.append(f"edge {e.src} -> {e.dst} [{e.data_type}]")
    if graph.totals:
        lines.append(
            f"totals gateway_calls={graph.totals.gateway_calls} node_executions={graph.totals.node_executions} "
            f"wall_time_ms={graph.totals.wall_time_ms}"
        )
    return lines
