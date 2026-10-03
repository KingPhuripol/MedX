"""S1r synthetic dataset loader (slice i2). Research prototype - not for clinical use.

* Reads only ``inputs/<split>/<case>/snapshot_T*.json`` (the S1r model-input glob) plus ``manifest.json`` for
  ``data_class``. It never opens ``journey.json`` or anything under ``gold/``.
* ``data_class`` comes from ``manifest.json`` and is never defaulted: a manifest without it is refused.
* Lossless: every source field of every item is kept; only ``data_class`` is added (:func:`roundtrip`).
"""

from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

from ..data import EVIDENCE_ADAPTER, Evidence

SNAPSHOT_NAME = re.compile(r"^snapshot_(T\d+)\.json$")
SPLITS = ("train", "dev", "test")


class S1rLoadError(RuntimeError):
    """Malformed dataset, missing data_class, or an item available after the snapshot time."""


@dataclass(frozen=True)
class S1rSnapshot:
    split: str
    case_id: str
    decision_point: str  # T1, T2, ...
    patient_ref: str
    T: datetime
    items: tuple[Evidence, ...]

    @property
    def dp_id(self) -> str:
        return f"{self.case_id}/{self.decision_point}"


def manifest_data_class(dataset: Path) -> str:
    manifest = json.loads((Path(dataset) / "manifest.json").read_text(encoding="utf-8"))
    dc = manifest.get("data_class")
    if not isinstance(dc, str) or not dc:
        raise S1rLoadError(f"{dataset}/manifest.json has no data_class; it is never defaulted")
    return dc


def snapshot_paths(dataset: Path, split: str) -> list[Path]:
    if split not in SPLITS:
        raise S1rLoadError(f"unknown split {split!r}")
    root = Path(dataset) / "inputs" / split
    out: list[Path] = []
    for case in sorted(e.name for e in os.scandir(root) if e.is_dir()):
        names = sorted(e.name for e in os.scandir(root / case) if e.is_file() and SNAPSHOT_NAME.match(e.name))
        out += [root / case / n for n in names]
    return out


def parse_snapshot(doc: dict[str, Any], data_class: str, split: str, decision_point: str) -> S1rSnapshot:
    T = datetime.fromisoformat(doc["as_of"])
    items = tuple(EVIDENCE_ADAPTER.validate_python({**it, "data_class": data_class}) for it in doc["items"])
    late = [i.item_id for i in items if i.available_at_time > T]
    if late:
        raise S1rLoadError(f"{doc['case_id']}/{decision_point}: items available after T: {late}")
    if any(i.patient_ref != doc["patient_ref"] for i in items):
        raise S1rLoadError(f"{doc['case_id']}/{decision_point}: item patient_ref differs from the snapshot")
    return S1rSnapshot(split, doc["case_id"], decision_point, doc["patient_ref"], T, items)


def load_snapshot(path: Path, data_class: str, split: str) -> S1rSnapshot:
    m = SNAPSHOT_NAME.match(Path(path).name)
    if m is None:
        raise S1rLoadError(f"{path}: not a snapshot_T*.json model input")
    doc = json.loads(Path(path).read_text(encoding="utf-8"))
    if doc.get("case_id") != Path(path).parent.name:
        raise S1rLoadError(f"{path}: case_id {doc.get('case_id')!r} does not match its directory")
    return parse_snapshot(doc, data_class, split, m.group(1))


def load_split(dataset: Path, split: str) -> list[S1rSnapshot]:
    dc = manifest_data_class(dataset)
    return [load_snapshot(p, dc, split) for p in snapshot_paths(dataset, split)]


def roundtrip(item: Evidence) -> dict[str, Any]:
    """The item as source JSON: exactly the fields that were given (plus ``data_class``)."""
    return json.loads(item.model_dump_json(exclude_unset=True))


@dataclass(frozen=True)
class StagedCase:
    """One encounter for staged versions (cg-t123): every item up to ``horizon`` and the nurse time ``t1``."""

    split: str
    case_id: str
    patient_ref: str
    t1: datetime
    horizon: datetime
    items: tuple[Evidence, ...]


def load_staged_case(dataset: Path, split: str, case_id: str, horizon_point: str = "T2") -> StagedCase:
    """``t1`` = ``snapshot_T1.as_of``; items and ``horizon`` = the ``snapshot_<horizon_point>`` (a superset of T1)."""
    dc = manifest_data_class(dataset)
    case_dir = Path(dataset) / "inputs" / split / case_id
    first = load_snapshot(case_dir / "snapshot_T1.json", dc, split)
    last = load_snapshot(case_dir / f"snapshot_{horizon_point}.json", dc, split)
    return StagedCase(split, case_id, last.patient_ref, first.T, last.T, last.items)
