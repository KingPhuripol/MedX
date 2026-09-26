"""Synthetic fixture access for dev/demo (``GET /api/pharma/fixtures``)."""

from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path

from ..models import MedSnapshot

HERE = Path(__file__).resolve().parent


@lru_cache(maxsize=1)
def _load() -> dict[str, dict]:
    patients = json.loads((HERE / "patients.json").read_text(encoding="utf-8"))["patients"]
    demo = json.loads((HERE / "demo.json").read_text(encoding="utf-8"))["cases"]
    out: dict[str, dict] = {}
    for case in demo:
        out[case["fixture_ref"]] = {"label": case["label"], "split": "demo", "snapshot": case["snapshot"]}
    for p in patients:
        out[p["patient_ref"]] = {"label": f"Clean synthetic patient ({p['split']})", "split": p["split"],
                                 "snapshot": p["snapshot"]}
    return out


def list_fixtures() -> list[dict]:
    return [
        {"fixture_ref": ref, "patient_ref": f["snapshot"]["patient_ref"], "split": f["split"], "label": f["label"]}
        for ref, f in _load().items()
    ]


def get_fixture(ref: str) -> MedSnapshot | None:
    f = _load().get(ref)
    return MedSnapshot.model_validate(f["snapshot"]) if f else None
