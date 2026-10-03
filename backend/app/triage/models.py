"""Local triage models (slice s4). Not a shared contract; mapped onto casegraph types at integration.

``Case`` is the only engine input. ``Gold`` is a separate model that the engine never receives.
"""

from __future__ import annotations

import json
import re
from datetime import datetime
from typing import Any, Literal

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, model_validator

SymptomState = Literal["present", "absent", "unknown"]
NUMERIC_VITALS = ("hr", "rr", "sbp", "dbp", "spo2", "temp_c", "capillary_glucose_mg_dl")
VITAL_NAMES = (*NUMERIC_VITALS, "avpu", "new_confusion", "on_oxygen")
_KIND = re.compile(
    r"^(age|sex|chief_complaint|onset_duration|pregnancy_status"
    r"|vital\.(hr|rr|sbp|dbp|spo2|temp_c|avpu|new_confusion|on_oxygen|capillary_glucose_mg_dl)"
    r"|symptom\.[a-z][a-z0-9_]{0,47})$"
)
# Required before the department suggestion may answer (spec s4 scope 3). Order is canonical.
REQUIRED_FIELDS: tuple[tuple[str, str], ...] = (
    ("age", "age"),
    ("sex", "sex"),
    ("chief_complaint", "chief_complaint"),
    ("onset_duration", "onset_duration"),
    ("vitals.hr", "vital.hr"),
    ("vitals.rr", "vital.rr"),
    ("vitals.sbp", "vital.sbp"),
    ("vitals.spo2", "vital.spo2"),
    ("vitals.temp_c", "vital.temp_c"),
    ("vitals.avpu", "vital.avpu"),
)


class _Strict(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class IntakeFact(_Strict):
    fact_id: str = Field(pattern=r"^[A-Za-z0-9_.:-]{1,64}$")
    kind: str
    value: Any
    available_at_time: AwareDatetime
    source: str = Field(min_length=1, max_length=128)
    provenance: str = Field(min_length=1, max_length=256)
    version: str = Field(min_length=1, max_length=32)

    @model_validator(mode="after")
    def _check_value(self) -> "IntakeFact":
        kind, value = self.kind, self.value
        if not _KIND.match(kind):
            raise ValueError(f"unknown fact kind: {kind}")
        ok: bool
        if kind.startswith("symptom."):
            ok = value in ("present", "absent", "unknown")
        elif kind == "vital.avpu":
            ok = value in ("A", "V", "P", "U")
        elif kind in ("vital.new_confusion", "vital.on_oxygen"):
            ok = isinstance(value, bool)
        elif kind.startswith("vital.") or kind == "age":
            ok = isinstance(value, (int, float)) and not isinstance(value, bool) and 0 <= value <= 1000
        elif kind == "sex":
            ok = value in ("female", "male")
        elif kind == "pregnancy_status":
            ok = value in ("positive", "negative", "unknown")
        else:  # chief_complaint, onset_duration
            ok = isinstance(value, str) and 0 < len(value.strip()) <= 500
        if not ok:
            raise ValueError(f"invalid value for {kind}")
        return self


class Case(_Strict):
    """Engine input. Has no gold, label, split, or outcome field (extra fields are rejected)."""

    case_ref: str = Field(pattern=r"^[A-Za-z0-9_-]{1,64}$")
    data_class: Literal["synthetic"]
    facts: list[IntakeFact]


class TemporalGold(_Strict):
    early_as_of: AwareDatetime
    red_flag_rules: list[str]


class Gold(_Strict):
    """Evaluation labels. Kept apart from ``Case``; only the evaluator and tests read it."""

    red_flag_rules: list[str]
    department: str | None
    missing_required: list[str]
    near_miss: bool
    temporal: TemporalGold | None


class FixtureEntry(_Strict):
    split: Literal["dev", "holdout"]
    as_of: AwareDatetime
    case: Case
    gold: Gold


class VitalReading(_Strict):
    value: float | str | bool
    available_at_time: datetime
    fact_id: str


class Vitals(_Strict):
    """Latest reading of each vital at the snapshot time. ``None`` means not recorded."""

    hr: VitalReading | None = None
    rr: VitalReading | None = None
    sbp: VitalReading | None = None
    dbp: VitalReading | None = None
    spo2: VitalReading | None = None
    temp_c: VitalReading | None = None
    avpu: VitalReading | None = None
    new_confusion: VitalReading | None = None
    on_oxygen: VitalReading | None = None
    capillary_glucose_mg_dl: VitalReading | None = None


# ---- same-timestamp conflicts (slice i2, S4 MEDIUM condition) ----
# When facts of one kind share the latest available_at_time and disagree:
#  * kinds with a direction resolve to the worst value (min, or an ordinal from least to most severe);
#  * hr/rr/sbp/dbp/temp_c keep every tied value and a rule leaf is true if any tied value hits;
#  * any other kind is flagged: it is treated as unknown and the department suggestion abstains.
# Across different timestamps the latest fact still wins (S4 behaviour; D-I2-3 reports it).
WORST_MIN = frozenset({"vital.spo2", "vital.capillary_glucose_mg_dl"})
WORST_ORDINAL: dict[str, tuple[Any, ...]] = {
    "vital.avpu": ("A", "V", "P", "U"),
    "vital.new_confusion": (False, True),
    "vital.on_oxygen": (False, True),
    "pregnancy_status": ("negative", "unknown", "positive"),
}
SYMPTOM_ORDER = ("absent", "unknown", "present")
ANY_HIT = frozenset({"vital.hr", "vital.rr", "vital.sbp", "vital.dbp", "vital.temp_c"})


class Conflict(_Strict):
    kind: str
    available_at_time: datetime
    values: list[Any]
    fact_ids: list[str]
    resolution: Literal["worst", "any_hit", "flagged"]
    resolved_value: Any = None
    resolved_fact_id: str | None = None


def _resolution(kind: str) -> str:
    if kind in WORST_MIN or kind in WORST_ORDINAL or kind.startswith("symptom."):
        return "worst"
    return "any_hit" if kind in ANY_HIT else "flagged"


def _severity(kind: str, value: Any) -> float:
    """Larger is worse."""
    if kind in WORST_MIN:
        return -float(value)
    order = SYMPTOM_ORDER if kind.startswith("symptom.") else WORST_ORDINAL[kind]
    return float(order.index(value))


def _canon(value: Any) -> str:
    return json.dumps(value, sort_keys=True)


class Snapshot:
    """Facts with ``available_at_time <= as_of``; the latest fact wins per kind.

    Same-timestamp disagreements at the latest time are resolved or flagged (``conflicts``); the result
    does not depend on the order of the facts.
    """

    def __init__(self, case: Case, as_of: datetime) -> None:
        if as_of.tzinfo is None:
            raise ValueError("as_of must be timezone-aware")
        self.case_ref = case.case_ref
        self.as_of = as_of
        visible = sorted(
            (f for f in case.facts if f.available_at_time <= as_of),
            key=lambda f: (f.available_at_time, f.fact_id),
        )
        groups: dict[str, list[IntakeFact]] = {}
        for f in visible:
            groups.setdefault(f.kind, []).append(f)
        self.by_kind: dict[str, IntakeFact] = {}
        self.tied: dict[str, list[IntakeFact]] = {}
        self.flagged: dict[str, Conflict] = {}
        self.superseded: dict[str, list[str]] = {}  # kind -> earlier fact ids with a different value
        conflicts: list[Conflict] = []
        for kind in sorted(groups):
            facts = groups[kind]
            latest_t = facts[-1].available_at_time
            tied = [f for f in facts if f.available_at_time == latest_t]
            chosen = tied[-1]
            earlier = [f.fact_id for f in facts if f.available_at_time < latest_t and _canon(f.value) != _canon(chosen.value)]
            if earlier:
                self.superseded[kind] = earlier
            values = sorted({_canon(f.value) for f in tied})
            if len(values) == 1:
                self.by_kind[kind] = chosen
                continue
            how = _resolution(kind)
            conflict = dict(kind=kind, available_at_time=latest_t, values=[json.loads(v) for v in values],
                            fact_ids=sorted(f.fact_id for f in tied), resolution=how)
            if how == "worst":
                worst = max(tied, key=lambda f: (_severity(kind, f.value), f.fact_id))
                self.by_kind[kind] = worst
                conflicts.append(Conflict(**conflict, resolved_value=worst.value, resolved_fact_id=worst.fact_id))
            elif how == "any_hit":
                self.by_kind[kind] = chosen
                self.tied[kind] = sorted(tied, key=lambda f: f.fact_id)
                conflicts.append(Conflict(**conflict))
            else:
                self.flagged[kind] = Conflict(**conflict)
                conflicts.append(self.flagged[kind])
        self.conflicts: list[Conflict] = conflicts
        self.fact_ids: frozenset[str] = frozenset(f.fact_id for f in visible)

    def get(self, kind: str) -> IntakeFact | None:
        return self.by_kind.get(kind)

    def values(self, kind: str) -> list[IntakeFact]:
        """Every fact a rule leaf must check: all tied values (any-hit kinds) or the single latest one."""
        if kind in self.tied:
            return list(self.tied[kind])
        fact = self.by_kind.get(kind)
        return [fact] if fact is not None else []

    def symptom(self, name: str) -> tuple[SymptomState, str | None]:
        fact = self.by_kind.get(f"symptom.{name}")
        if fact is None:
            return "unknown", None  # never treated as absent
        return fact.value, fact.fact_id

    def vitals(self) -> Vitals:
        readings = {}
        for name in VITAL_NAMES:
            fact = self.by_kind.get(f"vital.{name}")
            if fact is not None:
                readings[name] = VitalReading(
                    value=fact.value, available_at_time=fact.available_at_time, fact_id=fact.fact_id
                )
        return Vitals(**readings)

    def missing_required(self) -> list[str]:
        """Required fields with no fact. A conflicting field is not missing; see ``conflict_required``."""
        return [label for label, kind in REQUIRED_FIELDS if kind not in self.by_kind and kind not in self.flagged]

    def conflict_required(self) -> list[str]:
        return [f"conflict:{kind}" for kind in sorted(self.flagged)]


# ---- outputs ----


class Alert(_Strict):
    rule_id: str
    ruleset_version: str
    name_en: str
    name_th: str
    severity: Literal["escalate"]
    evidence_refs: list[str]
    message_en: str
    message_th: str


class NotEvaluable(_Strict):
    rule_id: str
    name_en: str
    name_th: str
    missing_inputs: list[str]


class DepartmentEntry(_Strict):
    code: str
    label_th: str
    label_en: str
    score: float = Field(ge=0, le=1)
    evidence_refs: list[str]


class DepartmentSuggestion(_Strict):
    status: Literal["suggested", "abstained", "error"]
    top3: list[DepartmentEntry] = Field(max_length=3)
    uncertainty: Literal["low", "medium", "high"] | None
    uncertainty_label: str
    missing_information: list[str]
    reason: str | None
    provider: str | None
    model_version: str | None
    contract_version: str | None
    request_sha256: str | None


class TriageAssessment(_Strict):
    """Serialized in field order: alerts come before the department section."""

    assessment_id: str
    case_ref: str
    as_of: datetime
    ruleset_version: str
    alerts: list[Alert]
    not_evaluable: list[NotEvaluable]
    escalation_required: bool
    department: DepartmentSuggestion
    conflicts: list[Conflict] = Field(default_factory=list)  # i2: same-timestamp conflicts, shown at review
    graph_id: str | None = None  # i2: the executed Case Graph behind this assessment
    screening: dict[str, Any] | None = None  # i2: RedFlagScreening block of that graph
    review_status: Literal["pending_review", "confirmed", "edited", "rejected"] = "pending_review"
    confirmed_department: str | None = None
    output_label: str = "Suggestion for nurse review"
    data_class: Literal["synthetic"] = "synthetic"
    created_at: str
    created_by: int
