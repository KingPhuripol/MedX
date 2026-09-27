"""Snapshot-only input builder (slice e1). Research prototype - not for clinical use.

Reads only ``inputs/<split>/<case_id>/snapshot_T*.json`` (the S1r model-input glob). It never opens
``journey.json`` or anything under ``gold/``; scoring labels come from ``gold.py``. Every item must have
``available_at_time <= T`` (the snapshot ``as_of``), otherwise the build fails (data-integrity failure).
"""

from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

from .mapping import nfc

SNAPSHOT = re.compile(r"^snapshot_(T\d+)\.json$")


class InputIntegrityError(RuntimeError):
    """A snapshot item is later than the decision time, or the snapshot is malformed."""


def t(value: str) -> datetime:
    return datetime.fromisoformat(value)


@dataclass(frozen=True)
class CaseInputs:
    case_id: str
    patient_ref: str
    snapshots: dict[str, dict[str, Any]]  # decision point -> snapshot


def _read_json(path: str) -> Any:
    with open(path, encoding="utf-8") as f:  # the only file access of the input builder
        return json.load(f)


def check_time_valid(snap: dict[str, Any], where: str) -> None:
    as_of = t(snap["as_of"])
    late = [i["item_id"] for i in snap["items"] if t(i["available_at_time"]) > as_of]
    if late:
        raise InputIntegrityError(f"{where}: items available after T={snap['as_of']}: {late}")


def case_ids(dataset: Path, split: str) -> list[str]:
    root = Path(dataset) / "inputs" / split
    return sorted(e.name for e in os.scandir(root) if e.is_dir())


def load_case(dataset: Path, split: str, case_id: str) -> CaseInputs:
    d = Path(dataset) / "inputs" / split / case_id
    names = sorted(e.name for e in os.scandir(d) if e.is_file() and SNAPSHOT.match(e.name))
    snaps: dict[str, dict[str, Any]] = {}
    for name in names:
        dp = SNAPSHOT.match(name).group(1)  # type: ignore[union-attr]
        snap = _read_json(str(d / name))
        if snap.get("case_id") != case_id:
            raise InputIntegrityError(f"{d / name}: case_id {snap.get('case_id')!r} != {case_id!r}")
        check_time_valid(snap, f"{split}/{case_id}/{name}")
        snaps[dp] = snap
    if not snaps:
        raise InputIntegrityError(f"{d}: no snapshot_T*.json")
    refs = {s["patient_ref"] for s in snaps.values()}
    if len(refs) != 1:
        raise InputIntegrityError(f"{d}: snapshots disagree on patient_ref {sorted(refs)}")
    return CaseInputs(case_id=case_id, patient_ref=refs.pop(), snapshots=snaps)


def load_split(dataset: Path, split: str) -> list[CaseInputs]:
    return [load_case(dataset, split, cid) for cid in case_ids(dataset, split)]


def items(snap: dict[str, Any], data_type: str) -> list[dict[str, Any]]:
    return [i for i in snap["items"] if i["data_type"] == data_type]


def transcript(snap: dict[str, Any]) -> dict[str, Any] | None:
    tx = items(snap, "IntakeTranscript")
    if len(tx) > 1:
        raise InputIntegrityError(f"{snap['case_id']}: more than one IntakeTranscript")
    return tx[0] if tx else None


def patient_turn_texts(snap: dict[str, Any]) -> list[str]:
    tx = transcript(snap)
    return [nfc(x["text"]) for x in tx["turns"] if x["speaker"] == "patient"] if tx else []
