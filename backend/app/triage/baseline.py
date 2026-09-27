"""Deterministic keyword/rule department baseline, registered as the mock handler for
``triage.department.v1``. It is a MOCK baseline: scores are normalized weights, not probabilities.
"""

from __future__ import annotations

import json
import re
from functools import lru_cache
from pathlib import Path
from typing import Any

from ..gateway import mock_tasks

TASK = "triage.department.v1"
KEYWORDS_PATH = Path(__file__).with_name("baseline_keywords_v1.json")


@lru_cache(maxsize=1)
def _table() -> dict[str, Any]:
    doc = json.loads(KEYWORDS_PATH.read_text(encoding="utf-8"))
    compiled = {}
    for code, entry in doc["departments"].items():
        en = [re.compile(r"(?<![a-z])" + re.escape(k.lower())) for k in entry["en"]]
        compiled[code] = (en, list(entry["th"]), dict(entry["symptoms"]))
    return {"version": doc["version"], "departments": compiled}


BASELINE_VERSION = _table()["version"]


def rank(inputs: dict[str, Any]) -> dict[str, Any]:
    """Pure function of the inputs. Returns ``{"ranking": [{code, score, evidence_refs}]}``."""
    cc = inputs.get("chief_complaint") or None
    text = (cc or {}).get("text", "") or ""
    lowered = text.lower()
    present = {s["name"]: s["fact_id"] for s in inputs.get("symptoms_present", [])}
    raw: dict[str, tuple[float, list[str]]] = {}
    for code, (en, th, symptoms) in _table()["departments"].items():
        hits = sum(1 for pat in en if pat.search(lowered)) + sum(1 for k in th if k in text)
        refs = [cc["fact_id"]] if hits and cc else []
        weight = float(hits)
        for name, w in sorted(symptoms.items()):
            if name in present:
                weight += float(w)
                refs.append(present[name])
        if weight > 0:
            raw[code] = (weight, sorted(set(refs)))
    total = sum(w for w, _ in raw.values())
    ranking = [
        {"code": code, "score": round(w / total, 4), "evidence_refs": refs}
        for code, (w, refs) in raw.items()
    ]
    ranking.sort(key=lambda r: (-r["score"], r["code"]))
    return {"ranking": ranking}


mock_tasks.register(TASK, rank, version=f"baseline-{BASELINE_VERSION}")
