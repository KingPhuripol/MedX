"""Typed evidence and derived data for the Case Graph (PROPOSAL 3.2.1, 2.1.4, 1.3.4).

Evidence items carry time-validity (``event_time``/``available_at_time``), provenance, version and a
required ``data_class``. Derived values record who produced them and from which inputs. No model
here holds pixel arrays or a free-text reasoning/thought field.
"""

from __future__ import annotations

import hashlib
import json
from datetime import datetime
from collections.abc import Sequence
from typing import Annotated, Any, Literal, Union

from pydantic import AwareDatetime, Field, TypeAdapter, model_validator

from .types import EvidenceItem, TypedData

DataClassName = Literal["synthetic", "mimic", "hospital", "real", "unknown"]
# Least to most restrictive. ``unknown`` is treated as the most restrictive class.
DATA_CLASS_ORDER: tuple[str, ...] = ("synthetic", "mimic", "hospital", "real", "unknown")
PLACEHOLDER_LABEL = "PLACEHOLDER — not clinical"
SHA256_HEX = r"^[0-9a-f]{64}$"


def canonical_json(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def sha256_json(value: Any) -> str:
    return hashlib.sha256(canonical_json(value).encode("utf-8")).hexdigest()


def most_restrictive(classes: list[str] | tuple[str, ...] | set[str]) -> str:
    """Most restrictive data class; an empty input set is ``synthetic`` (nothing to protect)."""
    return max(classes, key=DATA_CLASS_ORDER.index, default="synthetic")


# --------------------------------------------------------------------------------------- evidence
#
# Slice i2: this module is the ONLY evidence hierarchy. The s1 concrete types (IntakeTranscript,
# Demographics, Vitals, LabSeries, MedicationList, AllergyList) live here; ``casegraph/evidence.py`` and
# the s3 ``IntakeEvidence`` are retired. ``encounter_ref``/``observed_at`` are kept when a source has them
# (the S1r loader requires both), so an S1r item round-trips losslessly with only ``data_class`` added.


class Evidence(EvidenceItem):
    """Base of all concrete evidence types. ``data_class`` has no default (1.3.4)."""

    item_id: str = Field(min_length=1)
    data_class: DataClassName
    encounter_ref: str | None = Field(default=None, min_length=1)
    observed_at: AwareDatetime | None = None

    @model_validator(mode="after")
    def _available_not_before_event(self) -> "Evidence":
        if self.available_at_time < self.event_time:
            raise ValueError("available_at_time must not be earlier than event_time")
        if self.observed_at is not None and not (self.event_time <= self.observed_at <= self.available_at_time):
            raise ValueError("require event_time <= observed_at <= available_at_time")
        return self

    def content_sha256(self) -> str:
        return sha256_json(self.model_dump(mode="json"))


class _ClinicalTextFamily(Evidence):
    """Free-text evidence family (PROPOSAL 3.1: transcripts and extracted facts enter as ClinicalText)."""


class ClinicalText(_ClinicalTextFamily):
    """A free-text clinical note."""

    data_type: Literal["ClinicalText"] = "ClinicalText"
    text: str = Field(min_length=1)


class Turn(TypedData):
    """One dialogue turn. ``spoken_at`` is when it started; ``ended_at``/``turn_id`` when the source has them."""

    turn_index: int = Field(ge=0)
    speaker: Literal["nurse", "patient", "relative", "agent", "unknown"]  # unknown: ambient, no diarization
    text: str = Field(min_length=1)
    spoken_at: AwareDatetime
    ended_at: AwareDatetime | None = None
    turn_id: str | None = Field(default=None, min_length=1)


class IntakeTranscript(_ClinicalTextFamily):
    """A Voice Agent / front-door intake transcript (ClinicalText family)."""

    data_type: Literal["IntakeTranscript"] = "IntakeTranscript"
    language: str = Field(default="th", min_length=2)
    turns: tuple[Turn, ...] = Field(min_length=1)

    @model_validator(mode="after")
    def _turns_in_window(self) -> "IntakeTranscript":
        for t in self.turns:
            end = t.ended_at or t.spoken_at
            if t.spoken_at < self.event_time or end > self.available_at_time or end < t.spoken_at:
                raise ValueError(f"turn {t.turn_index} lies outside [event_time, available_at_time]")
        return self


class VoiceFact(TypedData):
    """One extracted intake fact. ``field`` is an S3 field name, or an S4 fact kind for hand-authored fixtures."""

    field: str = Field(min_length=1, max_length=64)
    state: Literal["KNOWN", "UNKNOWN", "REFUSED"]
    value: Any
    value_text: str = Field(min_length=1, max_length=500)
    span_turn_ids: tuple[str, ...] = ()
    event_time: AwareDatetime
    available_at_time: AwareDatetime
    fact_id: str | None = None
    session_id: str | None = None
    extractor: str | None = None
    provider: str | None = None
    model_version: str | None = None
    request_sha256: str | None = None
    supersedes_fact_id: str | None = None
    label: str | None = None


class VoiceIntakeFacts(_ClinicalTextFamily):
    """Session-level extracted facts from a Voice Agent session (ClinicalText family)."""

    data_type: Literal["VoiceIntakeFacts"] = "VoiceIntakeFacts"
    facts: tuple[VoiceFact, ...]
    missing_fields: tuple[str, ...] = ()
    handoff_reason: str | None = None
    allergy_conflict: bool = False

    @model_validator(mode="after")
    def _facts_available(self) -> "VoiceIntakeFacts":
        if any(f.available_at_time > self.available_at_time for f in self.facts):
            raise ValueError("a fact is available after its VoiceIntakeFacts item")
        return self


CLINICAL_TEXT_TYPES: tuple[str, ...] = ("ClinicalText", "IntakeTranscript", "VoiceIntakeFacts")


class Demographics(Evidence):
    data_type: Literal["Demographics"] = "Demographics"
    age_years: int | None = Field(default=None, ge=0, le=130)
    sex: Literal["female", "male"] | None = None


class _ImagingRef(Evidence):
    """Reference plus metadata only. Pixel data never enters the graph."""

    uri: str = Field(min_length=1)
    shape: tuple[int, ...] = Field(min_length=2, max_length=4)
    sha256: str = Field(pattern=SHA256_HEX)


class CTVolume(_ImagingRef):
    data_type: Literal["CTVolume"] = "CTVolume"


class MRIVolume(_ImagingRef):
    data_type: Literal["MRIVolume"] = "MRIVolume"


class CXRImage(_ImagingRef):
    data_type: Literal["CXRImage"] = "CXRImage"


# NaN / +-inf are rejected at validation (s2r): every comparison against NaN is False, so a corrupted
# reading would otherwise pass every threshold rule as "normal".
FiniteFloat = Annotated[float, Field(allow_inf_nan=False)]
NUMERIC_VITALS: tuple[str, ...] = ("sbp", "dbp", "hr", "rr", "temp_c", "spo2", "capillary_glucose_mg_dl")


class Vitals(Evidence):
    """Named, nullable, finite vital signs. A missing measurement is ``None``, never 0 (data rule 6).

    ``consciousness`` is ACVPU. ``new_confusion`` is only set when a source records it explicitly
    (``C`` already means new confusion); ``on_oxygen`` is kept but has no S4 counterpart.
    """

    data_type: Literal["Vitals"] = "Vitals"
    sbp: FiniteFloat | None = None
    dbp: FiniteFloat | None = None
    hr: FiniteFloat | None = None
    rr: FiniteFloat | None = None
    temp_c: FiniteFloat | None = None
    spo2: FiniteFloat | None = None
    consciousness: Literal["A", "C", "V", "P", "U"] | None = None
    new_confusion: bool | None = None
    on_oxygen: bool | None = None
    capillary_glucose_mg_dl: FiniteFloat | None = None

    @model_validator(mode="after")
    def _consistent_confusion(self) -> "Vitals":
        if self.consciousness == "C" and self.new_confusion is False:
            raise ValueError("consciousness C means new confusion; new_confusion=false contradicts it")
        return self

    def readings(self) -> dict[str, Any]:
        """Recorded (non-null) values by name."""
        names = (*NUMERIC_VITALS, "consciousness", "new_confusion", "on_oxygen")
        return {k: getattr(self, k) for k in names if getattr(self, k) is not None}


class LabResult(TypedData):
    test: str = Field(min_length=1)
    value: FiniteFloat
    unit: str = Field(min_length=1)
    ref_low: FiniteFloat | None = None
    ref_high: FiniteFloat | None = None
    collected_at: AwareDatetime | None = None
    resulted_at: AwareDatetime | None = None


class LabSeries(Evidence):
    data_type: Literal["LabSeries"] = "LabSeries"
    results: tuple[LabResult, ...] = Field(min_length=1)


class MedicationEntry(TypedData):
    generic_name: str = Field(min_length=1)
    atc_code: str | None = Field(default=None, pattern=r"^[A-Z]\d{2}[A-Z]{2}\d{2}$")
    dose_value: FiniteFloat | None = Field(default=None, gt=0)
    dose_unit: str | None = Field(default=None, min_length=1)
    frequency: str | None = Field(default=None, min_length=1)
    route: str | None = Field(default=None, min_length=1)

    @property
    def dose(self) -> str | None:
        """Dose as one string for the placeholder Pharma rules; None when value or unit is missing."""
        if self.dose_value is None or self.dose_unit is None:
            return None
        return f"{self.dose_value:g} {self.dose_unit}"


class MedicationList(Evidence):
    data_type: Literal["MedicationList"] = "MedicationList"
    list_source: str = Field(min_length=1)  # e.g. home_list, patient_reported, new_order
    entries: tuple[MedicationEntry, ...]
    derived_from: str | None = None


class AllergyEntry(TypedData):
    substance: str = Field(min_length=1)
    atc_class: str | None = Field(default=None, min_length=1)
    reaction: str | None = Field(default=None, min_length=1)


class AllergyList(Evidence):
    data_type: Literal["AllergyList"] = "AllergyList"
    status: Literal["known", "no_known_allergy", "unknown"]
    entries: tuple[AllergyEntry, ...]

    @model_validator(mode="after")
    def _entries(self) -> "AllergyList":
        if (self.status == "known") != bool(self.entries):
            raise ValueError("entries must be non-empty iff status == 'known'")
        return self


EVIDENCE_TYPES: tuple[type[Evidence], ...] = (
    ClinicalText, IntakeTranscript, VoiceIntakeFacts, Demographics, CTVolume, MRIVolume, CXRImage, Vitals,
    LabSeries, MedicationList, AllergyList,
)


# ---------------------------------------------------------------------------------------- derived


class Derived(TypedData):
    """Every derived value records the producing node and its inputs (evidence ids / output hashes)."""

    produced_by: str = Field(min_length=1)
    input_refs: tuple[str, ...]
    provider: str = Field(min_length=1)
    model_version: str = Field(min_length=1)


class TurnRef(TypedData):
    """A cited transcript turn (slice i2): which item, which turn, and when it was spoken."""

    item_id: str = Field(min_length=1)
    turn_index: int = Field(ge=0)
    spoken_at: AwareDatetime


class SymptomFact(TypedData):
    """A typed symptom fact from Reader:Text (slice i2). ``name`` is an rf-1.1.0 ``symptom.*`` name.

    ``present``/``absent`` always cite the turn(s) or the source item that support them; an unmentioned
    symptom has no fact at all (unknown), never ``absent``.
    """

    name: str = Field(pattern=r"^[a-z][a-z0-9_]{0,47}$")
    state: Literal["present", "absent", "unknown"]
    onset: Literal["sudden", "gradual", "unknown"] = "unknown"
    duration: str | None = None
    evidence_turns: tuple[TurnRef, ...] = ()
    source_item: str | None = None  # pass-through facts (VoiceIntakeFacts) cite their item instead of turns
    source_refs: tuple[str, ...] = ()  # lexicon rule citations of the matched terms
    available_at_time: AwareDatetime

    @model_validator(mode="after")
    def _cited(self) -> "SymptomFact":
        if self.state != "unknown" and not (self.evidence_turns or self.source_item):
            raise ValueError(f"{self.name}: a {self.state} fact must cite a turn or a source item")
        if self.evidence_turns and not self.source_refs:
            raise ValueError(f"{self.name}: a transcript fact must carry the lexicon source_refs")
        return self


class IntakeValue(TypedData):
    """A non-symptom intake fact (S3 field or S4 fact kind) carried by Reader:Text Findings."""

    kind: str = Field(min_length=1, max_length=64)  # e.g. chief_complaint, onset_duration, allergy_status
    state: Literal["KNOWN", "UNKNOWN", "REFUSED"]
    value: Any
    value_text: str = Field(min_length=1, max_length=500)
    evidence_turns: tuple[TurnRef, ...] = ()
    source_item: str | None = None
    span_text: str | None = Field(default=None, max_length=2000)  # NFC text of the cited turns
    available_at_time: AwareDatetime


class Findings(Derived):
    source_data_types: tuple[str, ...] = Field(min_length=1)
    statements: tuple[str, ...]
    facts: tuple[SymptomFact, ...] = ()
    intake: tuple[IntakeValue, ...] = ()


class ImageTokens(Derived):
    modality: str = Field(min_length=1)
    encoder_provider: Literal["encoder_2d", "encoder_3d"]
    token_ref: str = Field(min_length=1)
    token_sha256: str = Field(pattern=SHA256_HEX)


class Alert(TypedData):
    rule_id: str = Field(min_length=1)
    severity: Literal["urgent", "warning"]
    message: str = Field(min_length=1)
    # rf-1.1.0 (slice i2): the S4 rule names/messages and the fact ids that made the rule fire
    name_en: str | None = None
    name_th: str | None = None
    message_th: str | None = None
    evidence_refs: tuple[str, ...] = ()


# ------------------------------------------------------------------ screening status (s2r, v1.1)

ScreeningStatus = Literal["evaluated", "partially_evaluated", "not_evaluated"]
CheckStatus = Literal["evaluated", "not_evaluated"]
RedFlagScreeningStatus = Literal["evaluated", "partially_evaluated", "not_evaluated", "unavailable"]
BANNER_NOT_PERFORMED = "RED-FLAG SCREENING NOT PERFORMED"
BANNER_INCOMPLETE = "RED-FLAG SCREENING INCOMPLETE"


def screening_status(
    parts: Sequence[Any], missing_inputs: Sequence[str] = (), *, allow_partial: bool = True
) -> ScreeningStatus:
    """The single status aggregator. The only place a status value of ``evaluated`` is produced.

    ``parts`` are per-rule/per-check results (objects with ``.status``) or, for one rule, one bool per
    declared input (True = present, finite, inside the snapshot). ``evaluated`` requires at least one
    part, every part evaluated and no missing input. An empty rule set is ``not_evaluated``. With
    ``allow_partial=False`` (a single rule) anything short of ``evaluated`` is ``not_evaluated``.
    """
    done = [p if isinstance(p, bool) else p.status == "evaluated" for p in parts]
    if done and all(done) and not missing_inputs:
        return "evaluated"
    if allow_partial and any(done):
        return "partially_evaluated"
    return "not_evaluated"


class _CheckResult(TypedData):
    """One rule/check outcome. ``fired`` is None exactly when the check was not evaluated."""

    status: CheckStatus
    missing_inputs: tuple[str, ...]
    evaluated_on: tuple[str, ...]  # evidence item_ids actually read
    fired: bool | None
    label: str = PLACEHOLDER_LABEL

    @model_validator(mode="after")
    def _consistent(self):
        if self.status != screening_status([not self.missing_inputs], self.missing_inputs, allow_partial=False):
            raise ValueError("status must be not_evaluated iff missing_inputs is non-empty")
        if self.status == "not_evaluated" and self.fired is not None:
            raise ValueError("a not_evaluated check cannot have fired=True/False")
        if self.status != "not_evaluated" and (self.fired is None or not self.evaluated_on):
            raise ValueError("an evaluated check needs fired and evaluated_on")
        return self


class RuleResult(_CheckResult):
    rule_id: str = Field(min_length=1)


def _check_aggregate(status: str, results: Sequence[_CheckResult], missing: tuple[str, ...]) -> None:
    if status != screening_status(results, missing):
        raise ValueError(f"status {status!r} != aggregate {screening_status(results, missing)!r} of the results")
    if list(missing) != sorted(set(missing)):
        raise ValueError("missing_inputs must be sorted and unique")
    if not {m for r in results for m in r.missing_inputs} <= set(missing):
        raise ValueError("missing_inputs must include every result's missing inputs")


# Declared rule sets (slice i2, S2r MEDIUM): an Alerts output lists exactly these rule ids, once each.
# rf-1.1.0 is the S4 engine (``app/triage/rules/redflag_rules_v1.json``; equality is tested there).
RF_110 = "rf-1.1.0"
PLACEHOLDER_RULE_SET = "placeholder-redflag-0.2"
DECLARED_RULES: dict[str, tuple[str, ...]] = {
    PLACEHOLDER_RULE_SET: ("RF-PH-001", "RF-PH-002", "RF-PH-003", "RF-PH-004"),
    RF_110: ("RF-SPO2", "RF-RR", "RF-SBP", "RF-HR", "RF-CONSC", "RF-TEMP", "RF-QSOFA", "RF-CHEST", "RF-STROKE",
             "RF-THUNDER", "RF-ANAPH", "RF-SUICIDE", "RF-GIBLEED", "RF-ECTOPIC", "RF-MENING", "RF-HYPOGLY"),
}
RULE_SET_LABELS: dict[str, str] = {
    PLACEHOLDER_RULE_SET: PLACEHOLDER_LABEL,
    RF_110: "provisional research prototype; thresholds copied from the cited source, pending clinical expert review",
}
RULE_SET_SCOPES: dict[str, str] = {
    PLACEHOLDER_RULE_SET: "placeholder-redflag-0.2: 4 placeholder vitals thresholds only; PLACEHOLDER — not clinical",
    RF_110: ("rf-1.1.0: 16 declared rules over vitals within their freshness windows and symptoms mentioned in "
             "the intake transcript; an unmentioned symptom is unknown, not absent"),
}


class VitalReadingInfo(TypedData):
    """One vital as the Red-flag node saw it: value, when it was read, its age at T and freshness (C1)."""

    vital: str = Field(min_length=1)
    value: Any
    read_at: AwareDatetime
    age_min: float = Field(ge=0)
    window_min: float = Field(gt=0)
    fresh: bool
    item_id: str = Field(min_length=1)

    @model_validator(mode="after")
    def _fresh(self) -> "VitalReadingInfo":
        if self.fresh != (self.age_min <= self.window_min):
            raise ValueError(f"{self.vital}: fresh must equal age_min <= window_min")
        return self


class Alerts(Derived):
    """Red-flag output v1.2. Cannot be constructed as ``evaluated`` unless every rule was evaluated.

    Slice i2: ``rule_results`` must list exactly the declared rules of ``rule_set_version`` (no missing,
    extra or duplicate id). ``readings``/``conflicts``/``unmappable`` record what the screen actually read.
    """

    status: ScreeningStatus
    alerts: tuple[Alert, ...]
    rule_results: tuple[RuleResult, ...]
    rules_evaluated: tuple[str, ...]
    rules_not_evaluated: tuple[str, ...]
    missing_inputs: tuple[str, ...]
    rule_set_version: str
    label: str = PLACEHOLDER_LABEL
    scope: str | None = None
    readings: tuple[VitalReadingInfo, ...] = ()
    conflicts: tuple[dict[str, Any], ...] = ()
    unmappable: tuple[str, ...] = ()

    @model_validator(mode="after")
    def _invariant(self) -> "Alerts":
        declared = DECLARED_RULES.get(self.rule_set_version)
        if declared is None:
            raise ValueError(f"undeclared rule set {self.rule_set_version!r}")
        ids = [r.rule_id for r in self.rule_results]
        if len(ids) != len(set(ids)):
            raise ValueError("rule_results has a duplicate rule id")
        if set(ids) != set(declared):
            raise ValueError(f"rule_results must equal the declared rules of {self.rule_set_version}: "
                             f"missing={sorted(set(declared) - set(ids))} extra={sorted(set(ids) - set(declared))}")
        _check_aggregate(self.status, self.rule_results, self.missing_inputs)
        done = sorted(r.rule_id for r in self.rule_results if r.status == "evaluated")
        if list(self.rules_evaluated) != done:
            raise ValueError("rules_evaluated must list the evaluated rule ids, sorted")
        if list(self.rules_not_evaluated) != sorted(r.rule_id for r in self.rule_results if r.rule_id not in done):
            raise ValueError("rules_not_evaluated must list the not_evaluated rule ids, sorted")
        fired = {r.rule_id for r in self.rule_results if r.fired}
        if not {a.rule_id for a in self.alerts} <= fired:
            raise ValueError("every alert must come from an evaluated rule that fired")
        return self

    @property
    def has_urgent(self) -> bool:
        return any(a.severity == "urgent" for a in self.alerts)


def banner_for(status: str) -> str | None:
    if status == "evaluated":
        return None
    return BANNER_INCOMPLETE if status == "partially_evaluated" else BANNER_NOT_PERFORMED


class RedFlagScreening(TypedData):
    """Red-flag screening block carried by the Human Checkpoint payload and the graph export (v1.2, slice i2).

    It states which rule set ran, its label and scope, and counts; it is never a "no red flags" statement.
    An evaluated screen with 0 alerts reads "0 of <n_declared> declared rules fired" (:meth:`summary`).
    """

    status: RedFlagScreeningStatus
    performed: bool
    banner: str | None
    rules_evaluated: tuple[str, ...]
    rules_not_evaluated: tuple[str, ...]
    missing_inputs: tuple[str, ...]
    rule_set_version: str = Field(min_length=1)
    label: str = Field(min_length=1)
    scope: str = Field(min_length=1)
    n_declared: int = Field(ge=0)
    n_evaluated: int = Field(ge=0)
    n_not_evaluated: int = Field(ge=0)
    n_fired: int = Field(ge=0)
    readings: tuple[VitalReadingInfo, ...] = ()
    conflicts: tuple[dict[str, Any], ...] = ()

    @model_validator(mode="after")
    def _consistent(self) -> "RedFlagScreening":
        if self.performed != (self.status == "evaluated") or self.banner != banner_for(self.status):
            raise ValueError("performed/banner inconsistent with status")
        if (self.n_evaluated, self.n_not_evaluated) != (len(self.rules_evaluated), len(self.rules_not_evaluated)):
            raise ValueError("counts must match the rule lists")
        if self.n_evaluated + self.n_not_evaluated != self.n_declared or self.n_fired > self.n_evaluated:
            raise ValueError("n_evaluated + n_not_evaluated must equal n_declared, and n_fired <= n_evaluated")
        return self

    def summary(self) -> str:
        """One line for any render. Never "no red flags": it states what fired out of what was declared."""
        text = (f"{self.n_fired} of {self.n_declared} declared rules fired ({self.n_evaluated} evaluated, "
                f"{self.n_not_evaluated} not evaluated); {self.rule_set_version}; {self.scope}")
        return f"{self.banner}: {text}" if self.banner else text

    @classmethod
    def from_alerts(cls, alerts: dict[str, Any] | None, rule_set_version: str) -> "RedFlagScreening":
        """From an Alerts output dict; ``None`` (Red-flag absent or errored) is ``unavailable``."""
        if alerts is None:
            declared = DECLARED_RULES.get(rule_set_version, ())
            return cls(status="unavailable", performed=False, banner=banner_for("unavailable"), rules_evaluated=(),
                       rules_not_evaluated=tuple(sorted(declared)), missing_inputs=("Alerts",),
                       rule_set_version=rule_set_version,
                       label=RULE_SET_LABELS.get(rule_set_version, PLACEHOLDER_LABEL),
                       scope=RULE_SET_SCOPES.get(rule_set_version, rule_set_version),
                       n_declared=len(declared), n_evaluated=0, n_not_evaluated=len(declared), n_fired=0)
        checked = Alerts.model_validate(alerts)  # re-validates the construction invariant
        v = checked.rule_set_version
        return cls(status=checked.status, performed=checked.status == "evaluated", banner=banner_for(checked.status),
                   rules_evaluated=checked.rules_evaluated, rules_not_evaluated=checked.rules_not_evaluated,
                   missing_inputs=checked.missing_inputs, rule_set_version=v, label=checked.label,
                   scope=checked.scope or RULE_SET_SCOPES.get(v, v), n_declared=len(checked.rule_results),
                   n_evaluated=len(checked.rules_evaluated), n_not_evaluated=len(checked.rules_not_evaluated),
                   n_fired=sum(1 for r in checked.rule_results if r.fired), readings=checked.readings,
                   conflicts=checked.conflicts)


class CaseSummary(Derived):
    text: str
    red_flag_screening: RedFlagScreeningStatus  # required (s2r): never shown as if screening passed


class DepartmentEntry(TypedData):
    code: str = Field(min_length=1)
    label_th: str
    label_en: str
    score: float = Field(ge=0, le=1)
    evidence_refs: tuple[str, ...]


class DepartmentSuggestion(Derived):
    """The S4 ``department.suggest`` result (slice i2): status, top3, uncertainty, missing_information.

    ``gateway_*``/``request_sha256`` describe the one department call (None when it abstained with no call).
    """

    status: Literal["suggested", "abstained", "error"]
    top3: tuple[DepartmentEntry, ...] = Field(max_length=3)
    uncertainty: Literal["low", "medium", "high"] | None
    uncertainty_label: str
    missing_information: tuple[str, ...]
    reason: str | None
    gateway_provider: str | None
    gateway_model_version: str | None
    contract_version: str | None
    request_sha256: str | None
    red_flag_screening: RedFlagScreeningStatus

    @model_validator(mode="after")
    def _status(self) -> "DepartmentSuggestion":
        if (self.status == "suggested") != bool(self.top3):
            raise ValueError("top3 is non-empty iff status == 'suggested'")
        return self


class CareSuggestion(Derived):
    items: tuple[str, ...]
    red_flag_screening: RedFlagScreeningStatus


class MedicationIssue(TypedData):
    kind: str = Field(min_length=1)
    medication: str = Field(min_length=1)
    message: str = Field(min_length=1)


class MedicationCheck(_CheckResult):
    medication: str = Field(min_length=1)
    check: str = Field(min_length=1)  # e.g. duplicate, dose_mismatch


class MedicationIssues(Derived):
    """Pharma output v1.1: same construction invariant as :class:`Alerts`."""

    status: ScreeningStatus
    issues: tuple[MedicationIssue, ...]
    check_results: tuple[MedicationCheck, ...]
    checks_not_evaluated: tuple[MedicationCheck, ...]
    missing_inputs: tuple[str, ...]
    summary: str | None = None
    rule_set_version: str | None = None
    label: str = PLACEHOLDER_LABEL

    @model_validator(mode="after")
    def _invariant(self) -> "MedicationIssues":
        _check_aggregate(self.status, self.check_results, self.missing_inputs)
        if self.checks_not_evaluated != tuple(r for r in self.check_results if r.status == "not_evaluated"):
            raise ValueError("checks_not_evaluated must be the not_evaluated check results")
        return self


class ConfirmedResult(Derived):
    action: Literal["confirm", "edit", "reject"]
    graph_id: str = Field(min_length=1)
    reviewer_id: str = Field(min_length=1)
    reviewer_role: Literal["nurse", "physician", "pharmacist"]
    confirmed_at: AwareDatetime
    checkpoint_input_hash: str = Field(pattern=SHA256_HEX)
    payload: dict[str, Any] | None  # reviewed content (confirm), edited content (edit), None (reject)


DERIVED_TYPES: tuple[type[Derived], ...] = (
    Findings, ImageTokens, Alerts, CaseSummary, DepartmentSuggestion, CareSuggestion,
    MedicationIssues, ConfirmedResult,
)


class ConfirmedEvidence(Evidence):
    """A confirmed/edited Human Checkpoint result re-entering the record as new evidence."""

    data_type: Literal["ConfirmedResult"] = "ConfirmedResult"
    result: ConfirmedResult


AnyEvidence = Annotated[
    Union[ClinicalText, IntakeTranscript, VoiceIntakeFacts, Demographics, CTVolume, MRIVolume, CXRImage,  # noqa: UP007
          Vitals, LabSeries, MedicationList, AllergyList, ConfirmedEvidence],
    Field(discriminator="data_type"),
]
EVIDENCE_LIST = TypeAdapter(list[AnyEvidence])
EVIDENCE_ADAPTER = TypeAdapter(AnyEvidence)


def dump_evidence(items: list[Evidence] | tuple[Evidence, ...]) -> list[dict[str, Any]]:
    return [i.model_dump(mode="json") for i in items]


def load_evidence(data: list[dict[str, Any]]) -> list[Evidence]:
    return list(EVIDENCE_LIST.validate_python(data))


def utc_iso(dt: datetime) -> str:
    return dt.isoformat(timespec="microseconds")
