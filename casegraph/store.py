"""Output Store, StateStore, Replay and Regenerate (PROPOSAL 3.2.3).

* Cache key = sha256(canonical_json{node_type, provider, model_version, params, input_hash}).
* ``replay`` reads stored outputs only: no provider, no node body. Miss or hash mismatch -> ReplayError.
* ``regenerate`` compiles a new version; unchanged cache keys are served from the store.
"""

from __future__ import annotations

import json
import os
import sqlite3
import threading
from contextlib import closing
from pathlib import Path
from typing import TYPE_CHECKING, Any, Protocol

from pydantic import BaseModel, ConfigDict

from .compiler import build_snapshot, compile_graph, compile_stage, config_from_spec
from .data import Evidence, dump_evidence, load_evidence, sha256_json
from .export import ExportedGraph, GraphSpec, NodeStatus, import_graph, to_json
from .library import ProviderAssignment
from .types import NodeType

if TYPE_CHECKING:
    from .executor import Executor


class ReplayError(Exception):
    """Replay could not reproduce the stored graph. Replay never falls back to recomputing."""


class GraphVersionExists(Exception):
    """Stored graph versions are immutable and never overwritten."""


def cache_key(node_type: str, provider: str, model_version: str, params: dict[str, Any], input_hash: str) -> str:
    return sha256_json(
        {"node_type": node_type, "provider": provider, "model_version": model_version,
         "params": params, "input_hash": input_hash}
    )


class StoreEntry(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    cache_key: str
    node_type: str
    status: NodeStatus
    output: dict[str, Any] | None
    output_sha256: str
    missing_inputs: tuple[str, ...] = ()
    errored_inputs: tuple[str, ...] = ()
    reason: str | None = None
    started_at: str
    ended_at: str
    gateway_calls: int


class OutputStore:
    """Cache-keyed node outputs. File-backed when ``directory`` is given, else in-memory.

    Entries are immutable, except that an ``error`` entry may be replaced by a later result
    (errors are never served from cache, so a transient failure is not pinned).
    """

    def __init__(self, directory: str | Path | None = None) -> None:
        self._dir = Path(directory) if directory is not None else None
        self._mem: dict[str, str] = {}
        self._lock = threading.Lock()
        if self._dir is not None:
            self._dir.mkdir(parents=True, exist_ok=True)

    def path(self, key: str) -> Path:
        if self._dir is None:
            raise ValueError("in-memory OutputStore has no path")
        return self._dir / f"{key}.json"

    def _read(self, key: str) -> str | None:
        if self._dir is None:
            return self._mem.get(key)
        p = self.path(key)
        return p.read_text(encoding="utf-8") if p.exists() else None

    def get(self, key: str) -> StoreEntry | None:
        raw = self._read(key)
        return StoreEntry.model_validate_json(raw) if raw is not None else None

    def put(self, entry: StoreEntry) -> None:
        with self._lock:
            existing = self.get(entry.cache_key)
            if existing is not None and existing.status != "error":
                return
            text = to_json(entry)
            if self._dir is None:
                self._mem[entry.cache_key] = text
                return
            tmp = self.path(entry.cache_key).with_suffix(".tmp")
            tmp.write_text(text, encoding="utf-8")
            os.replace(tmp, self.path(entry.cache_key))


# ----------------------------------------------------------------------------------- state store


class StateStore(Protocol):
    def save_graph(self, spec: GraphSpec, items: list[Evidence] | tuple[Evidence, ...]) -> None: ...
    def load_graph(self, graph_id: str) -> tuple[GraphSpec, list[Evidence]]: ...
    def latest_version(self, patient_ref: str) -> int | None: ...
    def save_run(self, graph_id: str, run_json: str) -> None: ...
    def load_run(self, graph_id: str) -> str | None: ...
    def append_evidence(self, item: Evidence) -> None: ...
    def evidence(self, patient_ref: str) -> list[Evidence]: ...


class MemoryStateStore:
    def __init__(self) -> None:
        self._graphs: dict[str, tuple[str, str, int, str]] = {}
        self._runs: dict[str, str] = {}
        self._evidence: list[tuple[str, str]] = []
        self._lock = threading.Lock()

    def save_graph(self, spec, items) -> None:
        with self._lock:
            if spec.graph_id in self._graphs:
                raise GraphVersionExists(spec.graph_id)
            self._graphs[spec.graph_id] = (spec.to_json(), json.dumps(dump_evidence(items)), spec.version,
                                           spec.patient_ref)

    def load_graph(self, graph_id):
        spec_json, items_json, _, _ = self._graphs[graph_id]
        return GraphSpec.model_validate_json(spec_json), load_evidence(json.loads(items_json))

    def latest_version(self, patient_ref):
        return max((v for _, _, v, p in self._graphs.values() if p == patient_ref), default=None)

    def save_run(self, graph_id, run_json) -> None:
        self._runs[graph_id] = run_json

    def load_run(self, graph_id):
        return self._runs.get(graph_id)

    def append_evidence(self, item) -> None:
        self._evidence.append((item.patient_ref, item.model_dump_json()))

    def evidence(self, patient_ref):
        return load_evidence([json.loads(j) for p, j in self._evidence if p == patient_ref])


class SQLiteStateStore:
    """stdlib ``sqlite3`` StateStore (the backend DATABASE_URL plugs in here in a later slice)."""

    def __init__(self, path: str | Path) -> None:
        self._path = str(path)
        with closing(self._conn()) as c, c:
            c.executescript(
                """
                CREATE TABLE IF NOT EXISTS graphs (graph_id TEXT PRIMARY KEY, patient_ref TEXT NOT NULL,
                    version INTEGER NOT NULL, spec_json TEXT NOT NULL, items_json TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS runs (graph_id TEXT PRIMARY KEY, run_json TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS evidence (seq INTEGER PRIMARY KEY AUTOINCREMENT,
                    patient_ref TEXT NOT NULL, item_json TEXT NOT NULL);
                """
            )

    def _conn(self) -> sqlite3.Connection:
        return sqlite3.connect(self._path, timeout=10)

    def save_graph(self, spec, items) -> None:
        try:
            with closing(self._conn()) as c, c:
                c.execute(
                    "INSERT INTO graphs VALUES (?,?,?,?,?)",
                    (spec.graph_id, spec.patient_ref, spec.version, spec.to_json(), json.dumps(dump_evidence(items))),
                )
        except sqlite3.IntegrityError:
            raise GraphVersionExists(spec.graph_id) from None

    def load_graph(self, graph_id):
        with closing(self._conn()) as c:
            row = c.execute("SELECT spec_json, items_json FROM graphs WHERE graph_id=?", (graph_id,)).fetchone()
        if row is None:
            raise KeyError(graph_id)
        return GraphSpec.model_validate_json(row[0]), load_evidence(json.loads(row[1]))

    def latest_version(self, patient_ref):
        with closing(self._conn()) as c:
            return c.execute("SELECT MAX(version) FROM graphs WHERE patient_ref=?", (patient_ref,)).fetchone()[0]

    def save_run(self, graph_id, run_json) -> None:
        with closing(self._conn()) as c, c:
            c.execute("INSERT OR REPLACE INTO runs VALUES (?,?)", (graph_id, run_json))

    def load_run(self, graph_id):
        with closing(self._conn()) as c:
            row = c.execute("SELECT run_json FROM runs WHERE graph_id=?", (graph_id,)).fetchone()
        return row[0] if row else None

    def append_evidence(self, item) -> None:
        with closing(self._conn()) as c, c:
            c.execute("INSERT INTO evidence (patient_ref, item_json) VALUES (?,?)",
                      (item.patient_ref, item.model_dump_json()))

    def evidence(self, patient_ref):
        with closing(self._conn()) as c:
            rows = c.execute("SELECT item_json FROM evidence WHERE patient_ref=? ORDER BY seq",
                             (patient_ref,)).fetchall()
        return load_evidence([json.loads(r[0]) for r in rows])


# -------------------------------------------------------------------------------- replay/regenerate


def replay(source: str | ExportedGraph, output_store: OutputStore, state_store: StateStore | None = None
           ) -> ExportedGraph:
    """Rebuild an executed graph from stored outputs only. Never calls a provider or a node body."""
    if isinstance(source, ExportedGraph):
        graph = source
    else:
        run_json = state_store.load_run(source) if state_store is not None else None
        if run_json is None:
            raise ReplayError(f"no executed graph recorded for {source}")
        graph = import_graph(run_json)
    nodes = []
    for n in graph.nodes:
        if n.cache_key is None or n.output_sha256 is None:
            raise ReplayError(f"{n.id}: node has no recorded execution")
        entry = output_store.get(n.cache_key)
        if entry is None:
            raise ReplayError(f"{n.id}: cache miss for {n.cache_key}")
        if sha256_json(entry.output) != entry.output_sha256 or entry.output_sha256 != n.output_sha256:
            raise ReplayError(f"{n.id}: stored output hash mismatch")
        nodes.append(n.model_copy(update={"output": entry.output}))
    return graph.model_copy(update={"nodes": tuple(nodes)})


def next_version(state_store: StateStore, patient_ref: str) -> tuple[int, int | None]:
    latest = state_store.latest_version(patient_ref)
    return (1, None) if latest is None else (latest + 1, latest)


def regenerate(
    executor: "Executor",
    graph_id: str,
    *,
    swap_provider: dict[NodeType, ProviderAssignment] | None = None,
    remove_node: NodeType | None = None,
) -> ExportedGraph:
    """Compile a new version from the same snapshot with a changed config and execute it.

    Removing Red-flag or Human Checkpoint raises ``GraphValidationError``. Ablation is
    ``regenerate(remove_node=<Reader>)``.
    """
    spec, items = executor.state.load_graph(graph_id)
    config, excluded = config_from_spec(spec)
    for node_type, assignment in (swap_provider or {}).items():
        config = config.with_assignment(node_type, assignment)
    if remove_node is not None:
        excluded.add(remove_node)
    snapshot = build_snapshot(items, spec.T, patient_ref=spec.patient_ref)
    version, _ = next_version(executor.state, spec.patient_ref)
    if spec.stage is not None:  # cg-t123: a staged version regenerates as the same stage with the same triggers
        graph = compile_stage(snapshot, spec.stage, config, version, spec.version, trigger_refs=spec.trigger_refs,
                              exclude=excluded)
    else:
        graph = compile_graph(snapshot, config, version=version, parent_version=spec.version, exclude=excluded)
    return executor.run_sync(graph)
