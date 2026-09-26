"""Case Graph Compiler (PROPOSAL 3.2.2).

snapshot at T -> select nodes by data present -> assign providers -> wire by type -> validate.
Only :func:`validate` issues a :class:`ValidatedGraph`; the Executor accepts nothing else.
Compilation is a pure function of (snapshot, config, version, parent_version, exclude).
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from datetime import datetime
from graphlib import CycleError, TopologicalSorter

from .data import Evidence, most_restrictive, sha256_json
from .export import EdgeSpec, EvidenceRef, GraphSpec, NodeSpec
from .library import (
    LIBRARY,
    READERS,
    LibraryConfig,
    ProviderAssignment,
    ProviderConfig,
    output_types,
)
from .types import NodeType

NODE_ORDER: tuple[NodeType, ...] = (
    *READERS, NodeType.RED_FLAG, NodeType.PHARMA_AGENT, NodeType.REASONING, NodeType.HUMAN_CHECKPOINT,
)


class GraphValidationError(Exception):
    """Typed compile/validation failure. ``code`` is a stable machine-readable reason."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(f"{code}: {message}")
        self.code = code


# ------------------------------------------------------------------------------------- snapshot


@dataclass(frozen=True)
class Snapshot:
    patient_ref: str
    T: datetime
    items: tuple[Evidence, ...]
    snapshot_id: str

    def refs(self) -> tuple[EvidenceRef, ...]:
        return tuple(evidence_ref(i) for i in self.items)

    def data_types(self) -> set[str]:
        return {i.data_type for i in self.items}


def evidence_ref(item: Evidence) -> EvidenceRef:
    return EvidenceRef(
        item_id=item.item_id,
        data_type=item.data_type,
        event_time=item.event_time,
        available_at_time=item.available_at_time,
        source=item.source,
        version=item.version,
        data_class=item.data_class,
        sha256=item.content_sha256(),
    )


def snapshot_id_for(patient_ref: str, T: datetime, refs: Iterable[EvidenceRef]) -> str:
    return sha256_json(
        {"patient_ref": patient_ref, "T": T.isoformat(), "refs": [r.model_dump(mode="json") for r in refs]}
    )


def build_snapshot(items: Iterable[Evidence], T: datetime, patient_ref: str | None = None) -> Snapshot:
    """Items with ``available_at_time <= T`` from exactly one patient (step 1)."""
    if T.tzinfo is None:
        raise GraphValidationError("naive_time", "T must be timezone-aware")
    all_items = list(items)
    patients = {i.patient_ref for i in all_items} | ({patient_ref} if patient_ref else set())
    if len(patients) != 1:
        raise GraphValidationError("mixed_patient", f"snapshot needs exactly one patient_ref, got {len(patients)}")
    ids = [i.item_id for i in all_items]
    if len(ids) != len(set(ids)):
        raise GraphValidationError("structure", "duplicate evidence item_id")
    visible = sorted((i for i in all_items if i.available_at_time <= T), key=lambda i: (i.available_at_time, i.item_id))
    (patient_ref,) = patients
    refs = tuple(evidence_ref(i) for i in visible)
    return Snapshot(patient_ref, T, tuple(visible), snapshot_id_for(patient_ref, T, refs))


# ------------------------------------------------------------------------------------ compiling


def graph_id_for(patient_ref: str, version: int) -> str:
    return f"{patient_ref}/v{version}"


def _node_params(node_type: NodeType, a: ProviderAssignment, lib: LibraryConfig) -> dict:
    params = dict(a.params)
    if a.provider == "project_model":  # greedy decoding for reproducibility (3.2.3)
        params.update(decoding="greedy", temperature=0)
    if node_type is NodeType.REASONING:
        params["required_inputs"] = list(lib.reasoning_required_inputs)
    return params


def build_draft(
    snapshot: Snapshot,
    config: ProviderConfig | None = None,
    *,
    version: int = 1,
    parent_version: int | None = None,
    exclude: Iterable[NodeType] = (),
) -> GraphSpec:
    """Steps 2-4: select nodes from the data present, assign providers, wire by type. Not validated."""
    cfg = config or ProviderConfig()
    excluded = set(exclude)
    present = snapshot.data_types()
    selected: list[NodeType] = []
    for t in NODE_ORDER:
        decl = LIBRARY[t]
        if t in READERS or t is NodeType.PHARMA_AGENT:
            if not present & set(decl.evidence_types):
                continue
        if t not in excluded:
            selected.append(t)

    specs: dict[str, NodeSpec] = {}
    for t in selected:
        a = cfg.assignments[t]
        decl = LIBRARY[t]
        refs = tuple(sorted(i.item_id for i in snapshot.items if i.data_type in decl.evidence_types))
        specs[t.value] = NodeSpec(
            id=t.value, type=t, provider=a.provider, model_version=a.model_version,
            params=_node_params(t, a, cfg.library), data_class="synthetic",
            reproducible=a.provider != "external_model", evidence_refs=refs,
        )

    edges = []
    for src in specs.values():
        for data_type in output_types(src.type, src.provider):
            for dst in specs.values():
                if dst.id != src.id and data_type in LIBRARY[dst.type].input_types:
                    edges.append(EdgeSpec(src=src.id, dst=dst.id, data_type=data_type))
    edges.sort(key=lambda e: (NODE_ORDER.index(NodeType(e.src)), NODE_ORDER.index(NodeType(e.dst)), e.data_type))

    nodes = _with_data_classes(tuple(specs.values()), tuple(edges), snapshot.refs())
    return GraphSpec(
        graph_id=graph_id_for(snapshot.patient_ref, version),
        patient_ref=snapshot.patient_ref,
        T=snapshot.T,
        snapshot_id=snapshot.snapshot_id,
        version=version,
        parent_version=parent_version,
        nodes=nodes,
        edges=tuple(edges),
        evidence=snapshot.refs(),
    )


def _effective_data_classes(
    nodes: tuple[NodeSpec, ...], edges: tuple[EdgeSpec, ...], refs: tuple[EvidenceRef, ...]
) -> dict[str, str]:
    ref_class = {r.item_id: r.data_class for r in refs}
    preds = {n.id: {e.src for e in edges if e.dst == n.id} for n in nodes}
    out: dict[str, str] = {}
    by_id = {n.id: n for n in nodes}
    for nid in TopologicalSorter(preds).static_order():
        classes = {ref_class.get(r, "unknown") for r in by_id[nid].evidence_refs} | {out[p] for p in preds[nid]}
        out[nid] = most_restrictive(classes)
    return out


def _with_data_classes(nodes, edges, refs) -> tuple[NodeSpec, ...]:
    dc = _effective_data_classes(nodes, edges, refs)
    return tuple(n.model_copy(update={"data_class": dc[n.id]}) for n in nodes)


# ----------------------------------------------------------------------------------- validation

_TOKEN = object()


class ValidatedGraph:
    """Proof that a graph passed validation. Only :func:`validate` can create one.

    Immutable after creation: a token issued for one (spec, snapshot) pair cannot be re-pointed at
    another. The Executor additionally re-validates the carried pair before running (defence in
    depth against ``object.__setattr__`` bypasses).
    """

    __slots__ = ("spec", "snapshot", "_token")

    def __init__(self, spec: GraphSpec, snapshot: Snapshot | None, *, _token: object) -> None:
        if _token is not _TOKEN:
            raise TypeError("ValidatedGraph is issued only by casegraph.compiler.validate")
        object.__setattr__(self, "spec", spec)
        object.__setattr__(self, "snapshot", snapshot)
        object.__setattr__(self, "_token", _token)

    def __setattr__(self, name: str, value: object) -> None:
        raise AttributeError("ValidatedGraph is immutable; compile or validate a new graph instead")

    def __delattr__(self, name: str) -> None:
        raise AttributeError("ValidatedGraph is immutable; compile or validate a new graph instead")

    @property
    def is_authentic(self) -> bool:
        return self._token is _TOKEN


def _reachable(start: str, edges: tuple[EdgeSpec, ...]) -> set[str]:
    seen, stack = set(), [start]
    while stack:
        cur = stack.pop()
        for e in edges:
            if e.src == cur and e.dst not in seen:
                seen.add(e.dst)
                stack.append(e.dst)
    return seen


def validate(spec: GraphSpec, snapshot: Snapshot | None = None) -> ValidatedGraph:
    """Step 5. Raises :class:`GraphValidationError`; an invalid graph is never executable."""
    E = GraphValidationError
    by_id = {n.id: n for n in spec.nodes}
    if len(by_id) != len(spec.nodes) or len({n.type for n in spec.nodes}) != len(spec.nodes):
        raise E("structure", "duplicate node id or node type")
    if spec.graph_id != graph_id_for(spec.patient_ref, spec.version):
        raise E("structure", "graph_id does not match patient_ref/version")
    if spec.parent_version is not None and not 1 <= spec.parent_version < spec.version:
        raise E("structure", "parent_version must be an earlier version")
    for e in spec.edges:
        if e.src not in by_id or e.dst not in by_id:
            raise E("structure", f"edge {e.src}->{e.dst} references an unknown node")

    preds = {nid: {e.src for e in spec.edges if e.dst == nid} for nid in by_id}
    try:
        tuple(TopologicalSorter(preds).static_order())
    except CycleError as exc:
        raise E("cycle", f"graph has a cycle: {exc.args[1]}") from None

    for n in spec.nodes:
        decl = LIBRARY[n.type]
        if n.provider not in decl.allowed_providers:
            raise E("provider_not_allowed", f"{n.id}: provider {n.provider!r} not in {decl.allowed_providers}")
        if n.provider == "project_model" and n.params.get("temperature") != 0:
            raise E("nondeterministic_params", f"{n.id}: project_model must use greedy decoding (temperature=0)")
        if n.reproducible != (n.provider != "external_model"):
            raise E("structure", f"{n.id}: reproducible flag inconsistent with provider")

    for e in spec.edges:
        src, dst = by_id[e.src], by_id[e.dst]
        if e.data_type == "ImageTokens" and not (dst.type is NodeType.REASONING and dst.provider == "project_model"):
            raise E("image_tokens_route", f"ImageTokens may only reach a project_model Reasoning node, not {e.dst}")
        if e.data_type not in output_types(src.type, src.provider) or e.data_type not in LIBRARY[dst.type].input_types:
            raise E("type_mismatch", f"edge {e.src}->{e.dst} carries {e.data_type}")

    types = {n.type: n for n in spec.nodes}
    for mandatory in (NodeType.RED_FLAG, NodeType.HUMAN_CHECKPOINT):
        if mandatory not in types:
            raise E("missing_mandatory", f"mandatory node {mandatory.value} is missing")
    rf, hc = types[NodeType.RED_FLAG], types[NodeType.HUMAN_CHECKPOINT]
    if not any(e.src == rf.id and e.dst == hc.id and e.data_type == "Alerts" for e in spec.edges):
        raise E("alerts_edge", "no direct Alerts -> Human Checkpoint edge")
    for t in (NodeType.REASONING, NodeType.PHARMA_AGENT):
        if t in types and hc.id not in _reachable(types[t].id, spec.edges):
            raise E("unreviewed_output", f"{t.value} output does not reach a Human Checkpoint")

    ref_by_id = {r.item_id: r for r in spec.evidence}
    if len(ref_by_id) != len(spec.evidence):
        raise E("structure", "duplicate evidence ref")
    if snapshot_id_for(spec.patient_ref, spec.T, spec.evidence) != spec.snapshot_id:
        raise E("foreign_evidence", "evidence refs do not match snapshot_id")
    if snapshot is not None and (
        snapshot.snapshot_id != spec.snapshot_id or snapshot.patient_ref != spec.patient_ref
        or snapshot.refs() != spec.evidence or any(i.patient_ref != spec.patient_ref for i in snapshot.items)
    ):
        raise E("foreign_evidence", "graph was not compiled from this snapshot")
    for r in spec.evidence:
        if r.available_at_time > spec.T:
            raise E("future_evidence", f"{r.item_id} is available after T")
    for n in spec.nodes:
        for rid in n.evidence_refs:
            if rid not in ref_by_id:
                raise E("foreign_evidence", f"{n.id} references {rid} outside this graph's snapshot")
            if ref_by_id[rid].data_type not in LIBRARY[n.type].evidence_types:
                raise E("type_mismatch", f"{n.id} cannot read evidence type {ref_by_id[rid].data_type}")

    dc = _effective_data_classes(spec.nodes, spec.edges, spec.evidence)
    for n in spec.nodes:
        if n.data_class != dc[n.id]:
            raise E("data_policy", f"{n.id}: recorded data_class {n.data_class} != derived {dc[n.id]}")
        if n.provider == "external_model" and dc[n.id] != "synthetic":
            raise E("data_policy", f"{n.id}: external_model may only receive synthetic data, got {dc[n.id]}")

    return ValidatedGraph(spec, snapshot, _token=_TOKEN)


def compile_graph(
    snapshot: Snapshot,
    config: ProviderConfig | None = None,
    *,
    version: int = 1,
    parent_version: int | None = None,
    exclude: Iterable[NodeType] = (),
) -> ValidatedGraph:
    spec = build_draft(snapshot, config, version=version, parent_version=parent_version, exclude=exclude)
    return validate(spec, snapshot)


def config_from_spec(spec: GraphSpec) -> tuple[ProviderConfig, set[NodeType]]:
    """Recover the ProviderConfig and the excluded node types a graph was compiled with."""
    base = ProviderConfig()
    assignments = dict(base.assignments)
    library = base.library
    for n in spec.nodes:
        params = {k: v for k, v in n.params.items() if k not in ("decoding", "temperature", "required_inputs")}
        if n.provider != "project_model":
            params = {k: v for k, v in n.params.items() if k != "required_inputs"}
        assignments[n.type] = ProviderAssignment(provider=n.provider, model_version=n.model_version, params=params)
        if n.type is NodeType.REASONING:
            library = LibraryConfig(reasoning_required_inputs=tuple(n.params["required_inputs"]))
    present = {n.type for n in spec.nodes}
    return ProviderConfig(assignments=assignments, library=library), set(NodeType) - present
