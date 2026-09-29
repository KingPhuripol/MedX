"""Snapshot input for the care engine: ``inputs/<split>/<case_id>/snapshot_T{1,2}.json`` only.

Every item is validated with ``casegraph.EVIDENCE_ADAPTER`` (data_class synthetic). As a defence, an item with any time after
``as_of`` rejects the whole snapshot (an error, never silently dropped). Intake fields are tri-state:
``known``, ``unknown`` (stated as not known) or ``missing`` (not recorded); ``unknown`` never reads as negative.

A Demographics item whose ``age_years`` or ``sex`` is null ("not recorded") is validated field by field (the
null field is checked with a stand-in value that is never used) and is kept out of ``items``: its non-null
fields are exposed only through :meth:`SnapshotView.demographics`, so a stand-in can never reach the red-flag
engine, the summary or the provider.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Literal

from pydantic import ValidationError

from casegraph import EVIDENCE_ADAPTER

from .ruleset import rules

# The care engine serves S1r synthetic snapshots only (models.py, engine.py). S1r items carry no data_class;
# the i2 type system requires one, so it is supplied here and any other declared class is refused.
DATA_CLASS = "synthetic"
TIME_FIELDS = ("event_time", "observed_at", "available_at_time")
VITAL_REQUIRED = ("rr", "spo2", "on_oxygen", "temp_c", "sbp", "hr", "consciousness")
REQUIRED_INPUTS = ("demographics.age", "demographics.sex", "chief_complaint", "duration", "allergy_status",
                   *(f"vitals.{p}" for p in VITAL_REQUIRED))
FieldState = Literal["known", "unknown", "missing"]


_STAND_IN = {"age_years": 18, "sex": "female"}  # schema probe only; never exposed


def _demo_nulls(it: Any) -> frozenset[str]:
    if not isinstance(it, dict) or it.get("data_type") != "Demographics":
        return frozenset()
    return frozenset(k for k in _STAND_IN if it.get(k) is None)


class SnapshotError(ValueError):
    """The snapshot is not a valid model input; nothing may be computed from it."""


@dataclass(frozen=True)
class Demo:
    item_id: str
    age_years: int | None
    sex: str | None
    available_at_time: datetime
    source: str
    provenance: str
    version: str


@dataclass(frozen=True)
class Field_:
    state: FieldState
    value: Any = None
    refs: tuple[str, ...] = ()


class SnapshotView:
    def __init__(self, doc: dict[str, Any]) -> None:
        try:
            self.case_id: str = doc["case_id"]
            self.as_of_text: str = doc["as_of"]
            self.as_of = datetime.fromisoformat(doc["as_of"])
            raw = list(doc["items"])
        except (KeyError, TypeError, ValueError) as exc:
            raise SnapshotError("snapshot_malformed") from exc
        if self.as_of.tzinfo is None:
            raise SnapshotError("snapshot_as_of_not_timezone_aware")
        items, partial = [], []
        for it in raw:
            nulls = _demo_nulls(it)
            probe = {**it, **{k: v for k, v in _STAND_IN.items() if k in nulls}} if nulls else it
            if isinstance(probe, dict):
                if probe.get("data_class", DATA_CLASS) != DATA_CLASS:
                    raise SnapshotError("snapshot_item_not_synthetic")
                probe = {**probe, "data_class": DATA_CLASS}
            try:
                model = EVIDENCE_ADAPTER.validate_python(probe)
            except ValidationError as exc:
                raise SnapshotError("snapshot_item_invalid") from exc
            if any(getattr(model, f) > self.as_of for f in TIME_FIELDS):
                raise SnapshotError("snapshot_item_after_as_of")
            (partial if nulls else items).append((model, nulls))
        ids = [m.item_id for m, _ in items + partial]
        if len(set(ids)) != len(ids):
            raise SnapshotError("snapshot_duplicate_item_id")
        key = lambda mn: (mn[0].available_at_time, mn[0].item_id)  # noqa: E731
        self.items = [m for m, _ in sorted(items, key=key)]
        self._demo = sorted([(m, frozenset()) for m in self.items if m.data_type == "Demographics"] + partial, key=key)
        self.by_id = {m.item_id: m for m, _ in items + partial}

    def demographics(self) -> Demo | None:
        """Latest Demographics record; a field that was not recorded is ``None`` (never a stand-in)."""
        if not self._demo:
            return None
        m, nulls = self._demo[-1]
        return Demo(m.item_id, None if "age_years" in nulls else m.age_years, None if "sex" in nulls else m.sex,
                    m.available_at_time, m.source, m.provenance, m.version)

    def of_type(self, data_type: str) -> list:
        return [m for m in self.items if m.data_type == data_type]

    def latest(self, data_type: str):
        found = self.of_type(data_type)
        return found[-1] if found else None

    def ref(self, item_id: str) -> dict[str, str]:
        m = self.by_id[item_id]
        return {"item_id": item_id, "data_type": m.data_type, "available_at_time": m.available_at_time.isoformat()}

    # ---------------------------------------------------------------- intake fields
    def _answer(self, question: str) -> tuple[str, str] | None:
        """(patient answer text, transcript item id) for the first nurse turn containing ``question``."""
        for tx in self.of_type("IntakeTranscript"):
            turns = list(tx.turns)
            for i, t in enumerate(turns):
                if t.speaker == "nurse" and question in t.text:
                    nxt = next((u for u in turns[i + 1:] if u.speaker == "patient"), None)
                    if nxt is not None:
                        return nxt.text, tx.item_id
        return None

    def latest_vital(self, param: str) -> tuple[Any, str] | None:
        for v in reversed(self.of_type("Vitals")):
            value = getattr(v, param)
            if value is not None:
                return value, v.item_id
        return None

    def fields(self) -> dict[str, Field_]:
        cfg = rules()["intake"]
        out: dict[str, Field_] = {}
        demo = self.demographics()
        for key, value in (("demographics.age", demo and demo.age_years), ("demographics.sex", demo and demo.sex)):
            out[key] = Field_("known", value, (demo.item_id,)) if demo and value is not None else Field_("missing")
        cc = self._answer(cfg["complaint_question"])
        if cc is None:
            out["chief_complaint"] = Field_("missing")
        elif any(p in cc[0] for p in cfg["complaint_unknown_phrases"]):
            out["chief_complaint"] = Field_("unknown", None, (cc[1],))
        else:
            out["chief_complaint"] = Field_("known", cc[0], (cc[1],))
        dur = self._answer(cfg["duration_question"])
        if dur is None:
            out["duration"] = Field_("missing")
        else:
            m = re.search(cfg["duration_known_pattern"], dur[0])
            out["duration"] = Field_("known", m.group(0), (dur[1],)) if m else Field_("unknown", None, (dur[1],))
        allergy = self.latest("AllergyList")
        if allergy is None:
            out["allergy_status"] = Field_("missing")
        elif allergy.status == "unknown":
            out["allergy_status"] = Field_("unknown", None, (allergy.item_id,))
        else:
            out["allergy_status"] = Field_("known", allergy.status, (allergy.item_id,))
        for p in VITAL_REQUIRED:
            got = self.latest_vital(p)
            out[f"vitals.{p}"] = Field_("known", got[0], (got[1],)) if got else Field_("missing")
        return out


def missing_required(fields: dict[str, Field_]) -> list[str]:
    """Canonical order; ``unknown`` counts as missing."""
    return [f for f in REQUIRED_INPUTS if fields[f].state != "known"]
