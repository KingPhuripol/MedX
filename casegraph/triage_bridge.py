"""Bridge from Case Graph evidence to the S4 triage engine (slice i2). Research prototype — not for clinical use.

``build_case`` turns snapshot ``Demographics`` and ``Vitals`` items plus Reader:Text ``Findings`` into the S4
``Case`` (the only S4 engine input), following e1 mapping v1 (``eval/adapters/mappings/e1_mapping_v1.json``):

* every Vitals field becomes one S4 fact with the item's own ``available_at_time``; a ``null`` field is no fact;
* consciousness ``C`` is ``vital.avpu=A`` plus ``vital.new_confusion=true`` (ACVPU convention; D1 item);
* ``on_oxygen`` maps to ``vital.on_oxygen`` (rf-1.2.0 aggregate NEWS2); null is no fact;
* Findings symptom facts ``present``/``absent`` become ``symptom.<name>`` facts; ``unknown`` is no fact;
* an S3 chief-complaint code with an equal-meaning S4 symptom adds that symptom (e1 section s3_cc_to_s4_symptom).

With a :class:`Freshness` (Red-flag node only) a vital whose latest reading is older than its window is
dropped: rules that need it are ``not_evaluated`` with ``vital.<k>:stale(read_at=..., age_min=...)``.
The Reasoning node builds the Case without freshness (S4 department behaviour, latest wins).
"""

from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Iterable, Sequence
from dataclasses import dataclass, field
from datetime import datetime
from functools import lru_cache
from pathlib import Path
from typing import Any

from app.triage import department, redflags  # noqa: F401  (department registers triage.department.v1)
from app.triage.models import VITAL_NAMES, Case, IntakeFact
from app.triage.models import Snapshot as S4Snapshot

from .data import (
    RF_120,
    RULE_SET_LABELS,
    RULE_SET_SCOPES,
    Alert,
    Demographics,
    Evidence,
    RuleResult,
    VitalReadingInfo,
    Vitals,
    screening_status,
)

FRESHNESS_PATH = Path(__file__).resolve().parent / "config" / "vital_freshness_v1.json"
_CASE_REF = re.compile(r"[^A-Za-z0-9_-]")
_FACT_ID = re.compile(r"^[A-Za-z0-9_.:-]{1,64}$")
VITAL_FIELDS = ("hr", "rr", "sbp", "dbp", "spo2", "temp_c", "capillary_glucose_mg_dl")
PASS_THROUGH_KINDS = frozenset({"age", "sex", "chief_complaint", "onset_duration", "pregnancy_status"})
# e1 mapping v1, section s3_cc_to_s4_symptom (equal meaning only; acuity-qualified symptoms never come from here).
CC_TO_S4_SYMPTOM: dict[str, str] = {
    "fever": "fever", "cough": "cough", "sore_throat": "sore_throat", "headache": "headache",
    "dizziness": "dizziness", "dyspnea": "dyspnea", "abdominal_pain": "abdominal_pain", "back_pain": "back_pain",
    "joint_pain": "joint_pain", "dysuria": "dysuria",
}


class BridgeError(ValueError):
    """Evidence that cannot become an S4 Case (never silently repaired)."""


# ------------------------------------------------------------------------------------ freshness


@dataclass(frozen=True)
class Freshness:
    version: str
    label: str
    windows_min: dict[str, float]
    sources: dict[str, str]


@lru_cache(maxsize=4)
def load_freshness(path: str = str(FRESHNESS_PATH)) -> Freshness:
    doc = json.loads(Path(path).read_text(encoding="utf-8"))
    windows = {k: float(v["window_min"]) for k, v in doc["windows"].items()}
    missing = [v for v in VITAL_NAMES if v not in windows]
    if missing:
        raise BridgeError(f"freshness config has no window for {missing}")
    return Freshness(doc["version"], doc["label"], windows, {k: v["source"] for k, v in doc["windows"].items()})


def stale_input(kind: str, read_at: datetime, age_min: float) -> str:
    return f"{kind}:stale(read_at={read_at.isoformat()}, age_min={age_min:.2f})"


# ------------------------------------------------------------------------------------ the S4 Case


@dataclass
class Adapted:
    case: Case
    T: datetime
    readings: tuple[VitalReadingInfo, ...] = ()
    stale: dict[str, str] = field(default_factory=dict)  # S4 kind -> missing-input text
    unmappable: tuple[str, ...] = ()
    fact_source: dict[str, str] = field(default_factory=dict)  # S4 fact_id -> evidence item id / upstream ref

    def snapshot(self) -> S4Snapshot:
        return S4Snapshot(self.case, self.T)


def case_ref_for(patient_ref: str) -> str:
    ref = _CASE_REF.sub("-", patient_ref)[:64]
    return ref or "case"


def _fid(raw: str) -> str:
    if _FACT_ID.match(raw):
        return raw
    return "h:" + hashlib.sha256(raw.encode("utf-8")).hexdigest()[:40]


def _meta(item: Evidence) -> dict[str, Any]:
    return {"source": item.source[:128], "provenance": item.provenance[:256], "version": item.version[:32]}


@dataclass(frozen=True)
class _Pending:
    fact: dict[str, Any]
    src: str
    event_time: datetime | None = None  # vitals only: for the freshness age


def _vital_facts(item: Vitals) -> tuple[list[_Pending], list[str]]:
    out: list[_Pending] = []
    unmappable: list[str] = []
    base = {"available_at_time": item.available_at_time, **_meta(item)}
    for k in VITAL_FIELDS:
        v = getattr(item, k)
        if v is not None:
            out.append(_Pending({"fact_id": _fid(f"{item.item_id}.{k}"), "kind": f"vital.{k}", "value": v, **base},
                                item.item_id, item.event_time))
    if item.consciousness is not None:
        avpu = "A" if item.consciousness == "C" else item.consciousness
        out.append(_Pending({"fact_id": _fid(f"{item.item_id}.avpu"), "kind": "vital.avpu", "value": avpu, **base},
                            item.item_id, item.event_time))
    confusion = True if item.consciousness == "C" else item.new_confusion
    if confusion is not None:
        out.append(_Pending({"fact_id": _fid(f"{item.item_id}.new_confusion"), "kind": "vital.new_confusion",
                             "value": confusion, **base}, item.item_id, item.event_time))
    if item.on_oxygen is not None:  # null stays no fact: the NEWS2 oxygen parameter is then missing, never 0
        out.append(_Pending({"fact_id": _fid(f"{item.item_id}.on_oxygen"), "kind": "vital.on_oxygen",
                             "value": item.on_oxygen, **base}, item.item_id, item.event_time))
    return out, unmappable


def _demographic_facts(item: Demographics) -> list[_Pending]:
    base = {"available_at_time": item.available_at_time, **_meta(item)}
    out = []
    if item.age_years is not None:
        out.append(_Pending({"fact_id": _fid(f"{item.item_id}.age"), "kind": "age", "value": item.age_years, **base},
                            item.item_id))
    if item.sex is not None:
        out.append(_Pending({"fact_id": _fid(f"{item.item_id}.sex"), "kind": "sex", "value": item.sex, **base},
                            item.item_id))
    return out


def _findings_facts(n: int, ref: str, findings: dict[str, Any], version: str) -> list[_Pending]:
    """S4 facts from the ``n``-th Reader Findings output dict (``ref`` = ``node_id:output_sha256``).

    Each fact keeps its own ``available_at_time`` (fact ids are positional, so repeated kinds never collide);
    the S4 snapshot then applies latest-wins and the same-timestamp rules.
    """
    out: list[_Pending] = []
    meta = {"source": "casegraph.reader_text", "provenance": ref[:256], "version": version[:32]}
    for j, f in enumerate(findings.get("facts", ())):
        if f["state"] == "unknown":
            continue  # unknown is no fact: S4 reads it as unknown, never as absent
        out.append(_Pending({"fact_id": _fid(f"rt{n}.{j}.symptom.{f['name']}"), "kind": f"symptom.{f['name']}",
                             "value": f["state"], "available_at_time": f["available_at_time"], **meta}, ref))
    for j, v in enumerate(findings.get("intake", ())):
        kind = v["kind"]
        if v["state"] != "KNOWN" or kind not in PASS_THROUGH_KINDS:
            continue
        value = v["value"]
        if kind == "chief_complaint":  # the patient's words (cited turns) are what S4 ranks on
            value = (v.get("span_text") or v["value_text"])[:500]
            symptom = CC_TO_S4_SYMPTOM.get(v["value"]) if isinstance(v["value"], str) else None
            if symptom is not None:
                out.append(_Pending({"fact_id": _fid(f"rt{n}.{j}.cc_symptom.{symptom}"), "kind": f"symptom.{symptom}",
                                     "value": "present", "available_at_time": v["available_at_time"], **meta}, ref))
        out.append(_Pending({"fact_id": _fid(f"rt{n}.{j}.{kind}"), "kind": kind, "value": value,
                             "available_at_time": v["available_at_time"], **meta}, ref))
    return out


def build_case(
    patient_ref: str,
    T: datetime,
    items: Iterable[Evidence],
    findings: Sequence[tuple[str, dict[str, Any], str]] = (),
    *,
    freshness: Freshness | None = None,
    data_class: str = "synthetic",
) -> Adapted:
    """The S4 Case for one decision time. ``findings`` = (upstream ref, Findings dict, version) triples.

    The S4 engine accepts synthetic data only (``Case.data_class``); any other class raises, so the node
    fails safe instead of relabelling data.
    """
    if data_class != "synthetic":
        raise BridgeError(f"the S4 engine accepts synthetic data only, got {data_class!r}")
    pending: list[_Pending] = []
    unmappable: list[str] = []
    for item in sorted(items, key=lambda i: i.item_id):
        if item.available_at_time > T:
            raise BridgeError(f"{item.item_id} is available after T")
        if isinstance(item, Vitals):
            facts, un = _vital_facts(item)
            pending += facts
            unmappable += un
        elif isinstance(item, Demographics):
            pending += _demographic_facts(item)
        # any other evidence type has no S4 fact kind and is not read here
    for n, (ref, f, version) in enumerate(findings):
        pending += _findings_facts(n, ref, f, version)
    readings: list[VitalReadingInfo] = []
    stale: dict[str, str] = {}
    if freshness is not None:
        by_kind: dict[str, list[_Pending]] = {}
        for p in pending:
            if p.event_time is not None:
                by_kind.setdefault(p.fact["kind"], []).append(p)
        drop: set[str] = set()
        for kind in sorted(by_kind):
            latest = max(by_kind[kind], key=lambda p: (p.fact["available_at_time"], p.fact["fact_id"]))
            name = kind.removeprefix("vital.")
            window = freshness.windows_min[name]
            age_s = (T - latest.event_time).total_seconds()  # type: ignore[operator]
            fresh = age_s <= window * 60
            readings.append(VitalReadingInfo(vital=name, value=latest.fact["value"], read_at=latest.event_time,
                                             age_min=age_s / 60, window_min=window, fresh=fresh, item_id=latest.src))
            if not fresh:
                stale[kind] = stale_input(kind, latest.event_time, age_s / 60)  # type: ignore[arg-type]
                drop.add(kind)
        pending = [p for p in pending if p.fact["kind"] not in drop]
    ids = [p.fact["fact_id"] for p in pending]
    if len(ids) != len(set(ids)):
        raise BridgeError("duplicate S4 fact id")
    case = Case(case_ref=case_ref_for(patient_ref), data_class="synthetic",
                facts=[IntakeFact(**p.fact) for p in pending])
    return Adapted(case=case, T=T, readings=tuple(readings), stale=stale, unmappable=tuple(sorted(set(unmappable))),
                   fact_source={p.fact["fact_id"]: p.src for p in pending})


# ---------------------------------------------------------------------------- rf-1.2.0 screening


def _kinds(cond: dict[str, Any]) -> set[str]:
    if "news_aggregate" in cond:
        return {f"vital.{v}" for v in (*redflags.NEWS_VITALS, "avpu", "new_confusion", "on_oxygen")}
    if "any" in cond or "all" in cond or "at_least" in cond:
        return set().union(*(_kinds(c) for c in cond.get("any") or cond.get("all") or cond["of"]))
    if "symptom" in cond:
        return {f"symptom.{cond['symptom']}"}
    return {f"vital.{cond['vital']}" if "vital" in cond else cond["field"]}


def rule_kinds() -> dict[str, set[str]]:
    return {r["id"]: _kinds(r["condition"]) for r in redflags.rules()}


@dataclass(frozen=True)
class Screen:
    rule_results: tuple[RuleResult, ...]
    alerts: tuple[Alert, ...]
    missing_inputs: tuple[str, ...]
    conflicts: tuple[dict[str, Any], ...]


def screen_rf110(adapted: Adapted, extra_missing: Sequence[str] = ()) -> Screen:
    """Run ``redflags.evaluate`` (rf-1.2.0) on the adapted Case; one RuleResult per declared rule."""
    if redflags.RULESET_VERSION != RF_120:
        raise BridgeError(f"S4 engine is {redflags.RULESET_VERSION}, expected {RF_120}")
    snap = adapted.snapshot()
    alerts, not_evaluable = redflags.evaluate(snap)
    missing_by_rule = {n.rule_id: n.missing_inputs for n in not_evaluable}
    fired = {a.rule_id: a for a in alerts}
    kinds = rule_kinds()
    visible = {f.fact_id: f for f in adapted.case.facts if f.fact_id in snap.fact_ids}
    label = RULE_SET_LABELS[RF_120]
    results: list[RuleResult] = []
    for rule in redflags.rules():
        rid = rule["id"]
        # a stale vital is reported with its read time and age instead of the bare kind (C1)
        missing = tuple(sorted({adapted.stale.get(m, m) for m in missing_by_rule.get(rid, ())}))
        read = sorted({adapted.fact_source[fid] for fid, f in visible.items() if f.kind in kinds[rid]})
        if not missing and not read:
            raise BridgeError(f"{rid} evaluated without reading any input")
        results.append(RuleResult(
            rule_id=rid, missing_inputs=missing,
            status=screening_status([not missing], missing, allow_partial=False),
            evaluated_on=tuple(read) if not missing else (), fired=(rid in fired) if not missing else None,
            label=label,
        ))
    out_alerts = tuple(
        Alert(rule_id=a.rule_id, severity="urgent", message=a.message_en, name_en=a.name_en, name_th=a.name_th,
              message_th=a.message_th, evidence_refs=tuple(a.evidence_refs))
        for a in alerts
    )
    missing = tuple(sorted({m for r in results for m in r.missing_inputs} | set(extra_missing)))
    return Screen(tuple(results), out_alerts, missing,
                  tuple(c.model_dump(mode="json") for c in snap.conflicts))


def screen_fields(adapted: Adapted, screen: Screen) -> dict[str, Any]:
    """Alerts constructor fields for an rf-1.2.0 screen (``status`` is set by the caller via the aggregator)."""
    return {
        "alerts": screen.alerts,
        "rule_results": screen.rule_results,
        "rules_evaluated": tuple(sorted(r.rule_id for r in screen.rule_results if r.status == "evaluated")),
        "rules_not_evaluated": tuple(sorted(r.rule_id for r in screen.rule_results if r.status != "evaluated")),
        "missing_inputs": screen.missing_inputs,
        "rule_set_version": RF_120,
        "label": RULE_SET_LABELS[RF_120],
        "scope": RULE_SET_SCOPES[RF_120],
        "readings": adapted.readings,
        "conflicts": screen.conflicts,
        "unmappable": adapted.unmappable,
    }


# ------------------------------------------------------------------------ S4 Case -> evidence (i2 scope 7)

_VITAL_FIELD = {"avpu": "consciousness", "new_confusion": "new_confusion"}


def evidence_from_case(case: Case) -> list[Evidence]:
    """Case Graph evidence for an S4 ``Case`` (the triage API's input), one item per S4 fact.

    Each item keeps the fact's ``available_at_time`` (as ``event_time`` too: S4 facts carry no separate
    measurement time), source, provenance and version; ``item_id`` is the S4 ``fact_id``. The inverse of
    :func:`build_case` for S4 fact kinds:

    * ``age``/``sex`` -> :class:`Demographics`; ``vital.<k>`` -> :class:`Vitals` with that one field
      (``vital.avpu`` -> ``consciousness``);
    * ``symptom.*``, ``chief_complaint``, ``onset_duration``, ``pregnancy_status`` -> one
      :class:`VoiceIntakeFacts` (ClinicalText family; Reader:Text passes it through with 0 calls).

    A value that has no lossless Case Graph form (a non-integer or out-of-range age) raises, never repaired.
    """
    from .data import VoiceFact, VoiceIntakeFacts  # local: keeps the module's import surface unchanged

    items: list[Evidence] = []
    for f in case.facts:
        base = {"item_id": f.fact_id, "patient_ref": case.case_ref, "event_time": f.available_at_time,
                "available_at_time": f.available_at_time, "source": f.source, "provenance": f.provenance,
                "version": f.version, "data_class": case.data_class}
        kind, value = f.kind, f.value
        if kind == "age":
            if isinstance(value, float) and not value.is_integer():
                raise BridgeError(f"{f.fact_id}: age {value!r} has no integer Demographics form")
            items.append(Demographics(**base, age_years=int(value)))
        elif kind == "sex":
            items.append(Demographics(**base, sex=value))
        elif kind.startswith("vital."):
            name = kind.removeprefix("vital.")
            items.append(Vitals(**base, **{_VITAL_FIELD.get(name, name): value}))
        else:  # symptom.*, chief_complaint, onset_duration, pregnancy_status
            fact = VoiceFact(field=kind, state="KNOWN", value=value, value_text=str(value)[:500],
                             event_time=f.available_at_time, available_at_time=f.available_at_time,
                             fact_id=f.fact_id)
            items.append(VoiceIntakeFacts(**base, facts=(fact,)))
    return items
