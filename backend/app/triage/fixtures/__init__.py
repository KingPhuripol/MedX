"""Synthetic fixture loader. The API sees ``Case`` objects only; gold stays with the evaluator."""

from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path

from ..models import Case, FixtureEntry

CASES_PATH = Path(__file__).with_name("cases_v1.json")


@lru_cache(maxsize=1)
def load_entries() -> tuple[FixtureEntry, ...]:
    doc = json.loads(CASES_PATH.read_text(encoding="utf-8"))
    if doc.get("data_class") != "synthetic":
        raise RuntimeError("triage fixtures must be synthetic")
    return tuple(FixtureEntry.model_validate(e) for e in doc["cases"])


def engine_cases() -> dict[str, Case]:
    """Engine inputs by case_ref. Gold labels are not reachable from here."""
    return {e.case.case_ref: e.case for e in load_entries()}
