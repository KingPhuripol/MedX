"""Snapshot-only access to the synthetic dataset: ``inputs/<split>/<case_id>/snapshot_T{1,2}.json``.

Nothing else under the dataset (``journey.json``, ``gold/``) is read here. The path comes from
``CARE_DATASET`` (default ``data/synthetic/v1``, relative paths resolved from the repository root).
"""

from __future__ import annotations

import json
import os
import re
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[3]
DEFAULT_DATASET = "data/synthetic/v1"
DECISION_POINTS = ("T1", "T2")
_CASE_ID = re.compile(r"^[A-Za-z0-9_-]{1,64}$")


class DatasetMissing(RuntimeError):
    pass


def root() -> Path:
    p = Path(os.environ.get("CARE_DATASET", "").strip() or DEFAULT_DATASET)
    return p if p.is_absolute() else REPO_ROOT / p


def _split_dir(split: str) -> Path:
    d = root() / "inputs" / split
    if not d.is_dir():
        raise DatasetMissing("dataset_missing: run make data")
    return d


def case_ids(split: str) -> list[str]:
    return sorted(p.parent.name for p in _split_dir(split).glob("*/snapshot_T1.json"))


def load_snapshot(split: str, case_id: str, decision_point: str) -> dict[str, Any] | None:
    if not _CASE_ID.match(case_id) or decision_point not in DECISION_POINTS:
        return None
    p = _split_dir(split) / case_id / f"snapshot_{decision_point}.json"
    return json.loads(p.read_text(encoding="utf-8")) if p.is_file() else None
