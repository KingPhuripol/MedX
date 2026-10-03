"""Staged runs: build every planned Case Graph version of one encounter (slice cg-t123, PROPOSAL 3.2.2).

``build_versions`` plans the stages (:mod:`casegraph.stages`), compiles each with ``compile_stage`` and executes it,
one version after the other. Stored versions are insert-only: version k+1 never touches version k's graph, run or
Output Store entries. A node whose cache key was produced before is served from the Output Store (``cached=True``,
0 gateway calls). A version is built even when an earlier checkpoint is still pending; each checkpoint is resumed
only by its own role (``Executor.resume``).
"""

from __future__ import annotations

from collections.abc import Callable, Iterable
from datetime import datetime

from .compiler import build_snapshot, compile_stage
from .data import Evidence
from .executor import Executor
from .export import ExportedGraph, GraphSpec
from .library import ProviderConfig
from .stages import StagePlan, is_order, is_result, plan_stages
from .store import next_version


def _merged(executor: Executor, items: Iterable[Evidence], patient_ref: str) -> list[Evidence]:
    """The supplied evidence plus the ConfirmedEvidence the checkpoints appended to the StateStore so far."""
    merged = {i.item_id: i for i in items}
    for extra in executor.state.evidence(patient_ref):
        merged.setdefault(extra.item_id, extra)
    return list(merged.values())


def build_version(
    executor: Executor, items: Iterable[Evidence], plan: StagePlan, config: ProviderConfig | None = None,
    *, patient_ref: str | None = None,
) -> ExportedGraph:
    """Compile and execute one planned version as the next version of the encounter."""
    all_items = list(items)
    patients = {i.patient_ref for i in all_items} | ({patient_ref} if patient_ref else set())
    if len(patients) != 1:
        raise ValueError(f"one encounter needs exactly one patient_ref, got {len(patients)}")
    (pr,) = patients
    snapshot = build_snapshot(_merged(executor, all_items, pr), plan.T, pr)  # items after T never enter
    version, parent = next_version(executor.state, pr)
    graph = compile_stage(snapshot, plan.stage, config, version, parent, trigger_refs=plan.trigger_item_ids)
    return executor.run_sync(graph)


def build_versions(
    executor: Executor,
    items: Iterable[Evidence],
    t1: datetime,
    horizon: datetime,
    config: ProviderConfig | None = None,
    *,
    after_version: Callable[[ExportedGraph], None] | None = None,
) -> list[ExportedGraph]:
    """Plan, compile and execute every version of one encounter in order. ``after_version`` runs after each
    version (e.g. a reviewer resuming that version's checkpoint before the next version is built)."""
    all_items = list(items)
    plans = plan_stages(all_items, t1, horizon)
    patients = {i.patient_ref for i in all_items}
    if len(patients) != 1:
        raise ValueError(f"one encounter needs exactly one patient_ref, got {len(patients)}")
    (pr,) = patients
    if executor.state.latest_version(pr) is not None:
        raise ValueError(f"{pr} already has stored versions; one StateStore namespace per encounter")
    out: list[ExportedGraph] = []
    for plan in plans:
        graph = build_version(executor, all_items, plan, config, patient_ref=pr)
        out.append(graph)
        if after_version is not None:
            after_version(graph)
    return out


def next_stage(parent: GraphSpec | None, items: Iterable[Evidence], as_of: datetime) -> tuple[str, tuple[str, ...]]:
    """The stage of the next version computed at ``as_of`` (backend ``run_graph``).

    Triggers newer than the parent's ``T`` (and at most ``as_of``) decide: the latest planned stage wins, with all
    of that stage's triggers. With no trigger the version inherits the parent's stage and triggers, or is T1
    when there is no parent."""
    if parent is None:
        return "T1", ()
    plans = plan_stages(list(items), parent.T, as_of)[1:]  # [0] is the parent's own T1 slot
    if not plans:
        return (parent.stage or "T1"), parent.trigger_refs
    last = plans[-1].stage
    refs = tuple(sorted({r for p in plans if p.stage == last for r in p.trigger_item_ids}))
    return last, refs
