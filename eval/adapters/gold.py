"""Gold loader for scoring (slice e1). Research prototype - not for clinical use.

Reads ``gold/<split>/<case_id>.json`` and ``splits.json``. Nothing here is passed to S3 or S4: the system
outputs are built from snapshots only (``inputs.py``) before gold is joined for scoring.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any


def load_gold(dataset: Path, split: str, case_id: str) -> dict[str, Any]:
    g = json.loads((Path(dataset) / "gold" / split / f"{case_id}.json").read_text(encoding="utf-8"))
    if g["case_id"] != case_id or g["split"] != split:
        raise ValueError(f"gold/{split}/{case_id}.json: case_id/split mismatch")
    return g


def load_split_gold(dataset: Path, split: str) -> dict[str, dict[str, Any]]:
    root = Path(dataset) / "gold" / split
    return {p.stem: load_gold(dataset, split, p.stem) for p in sorted(root.glob("SYNE-*.json"))}


def load_splits(dataset: Path) -> dict[str, str]:
    return json.loads((Path(dataset) / "splits.json").read_text(encoding="utf-8"))


def split_patients(dataset: Path, split: str) -> list[str]:
    return sorted(p for p, s in load_splits(dataset).items() if s == split)


def missing(v: Any) -> bool:
    return v is None or v == "MISSING"


def dps(g: dict[str, Any]) -> list[dict[str, Any]]:
    return g["decision_times"]
