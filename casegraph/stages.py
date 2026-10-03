"""Stage planner for staged Case Graph versions (PROPOSAL 3.2.2, Figure 3.2; slice cg-t123).

Pure, deterministic, fixed-rule, no model call. Each new arrival of a result (lab, CXR, CT/MRI) after the
nurse assessment time ``t1`` creates a physician version (T2); each new arrival of a physician order creates a
pharmacist version (T3). The first version is always T1 at ``t1``. Items available at or before ``t1`` are in the
T1 snapshot and never trigger a version; other arrivals (new vitals, transcripts, ConfirmedEvidence) never create a
version by themselves and enter the next version's snapshot.

This module is a staging rule, not clinical validation: fixtures and gold come from the same authors (D1).
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from .types import NodeType

STAGES: tuple[str, ...] = ("T1", "T2", "T3")
STAGE_ROLE: dict[str, str] = {"T1": "nurse", "T2": "physician", "T3": "pharmacist"}
# Reasoning params.task per stage; T3 has no Reasoning node (decision P-1).
REASONING_TASK: dict[str, str | None] = {"T1": "department", "T2": "care", "T3": None}
RESULT_TYPES: frozenset[str] = frozenset({"LabSeries", "CXRImage", "CTVolume", "MRIVolume"})
ORDER_SOURCE = "new_order"
RESULT_READER: dict[str, NodeType] = {
    "LabSeries": NodeType.READER_VITALS_LABS, "CXRImage": NodeType.READER_CXR,
    "CTVolume": NodeType.READER_CT_MRI, "MRIVolume": NodeType.READER_CT_MRI,
}


def is_result(item: Any) -> bool:
    return getattr(item, "data_type", None) in RESULT_TYPES


def is_order(item: Any) -> bool:
    return getattr(item, "data_type", None) == "MedicationList" and getattr(item, "list_source", None) == ORDER_SOURCE


@dataclass(frozen=True)
class StagePlan:
    stage: str
    T: datetime
    trigger_item_ids: tuple[str, ...] = ()


def plan_stages(items: Iterable[Any], t1: datetime, horizon: datetime) -> list[StagePlan]:
    """The ordered version plan: ``T1@t1`` then, per distinct trigger time ``e`` in ``(t1, horizon]`` ascending,
    ``T2@e`` if a result is available at ``e``, then ``T3@e`` if an order is available at ``e``."""
    if t1.tzinfo is None or horizon.tzinfo is None:
        raise ValueError("t1 and horizon must be timezone-aware")
    plans = [StagePlan("T1", t1)]
    triggers = [i for i in items if t1 < i.available_at_time <= horizon and (is_result(i) or is_order(i))]
    for e in sorted({i.available_at_time for i in triggers}):
        at = [i for i in triggers if i.available_at_time == e]
        results = tuple(sorted(i.item_id for i in at if is_result(i)))
        orders = tuple(sorted(i.item_id for i in at if is_order(i)))
        if results:
            plans.append(StagePlan("T2", e, results))
        if orders:
            plans.append(StagePlan("T3", e, orders))
    return plans
