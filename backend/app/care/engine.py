"""Care suggestion pipeline (slice s6): snapshot -> red-flag screening (first, s4 engine, never changed here)
-> required-input check (abstain before any provider call) -> exactly one gateway call -> post-gateway
validation (fail safe) -> ``CareResult``.

The provider can only propose next-information and pathway codes with evidence refs. Alerts, screening and
escalation are computed before the call and copied through unchanged whatever the provider returns.
"""

from __future__ import annotations

import json
from collections.abc import Callable, Sequence
from typing import Any

from casegraph.data import CareSuggestion

from ..gateway.contract import DataClass, GatewayRequest, GatewayResponse
from ..triage.models import IntakeFact
from . import mock_rules  # noqa: F401  (registers the deterministic mock handler for TASK)
from . import redflag_adapter
from .models import (
    MAX_NEXT_INFO,
    MAX_PATHWAYS,
    TASK,
    CareResult,
    EvidenceRef,
    NextInfo,
    PathwayOption,
    ScreeningView,
    SummaryLine,
)
from .ruleset import CARE_RULES_VERSION, rules
from .snapshot import SnapshotError, SnapshotView, missing_required

InvokeFn = Callable[[GatewayRequest], GatewayResponse]
URGENCY_KEYS = frozenset({"alerts", "red_flag_screening", "escalation_required", "red_flags", "screening"})
OUTPUT_KEYS = frozenset({"next_information", "pathway_options", "label"})
SCREENING_UNAVAILABLE = "red_flag_screening"


class _Invalid(Exception):
    pass


def _screening_view(s: redflag_adapter.Screening) -> ScreeningView:
    x = s.screening  # a validated casegraph.data.RedFlagScreening (I2 block)
    return ScreeningView(**x.model_dump(mode="json"), summary=x.summary())


def _optional_missing(view: SnapshotView) -> list[str]:
    """Optional inputs that are absent. Listed so they are never read as negative or normal."""
    out = []
    if not view.of_type("LabSeries"):
        out.append("lab_results")
    demo = view.demographics()
    lo, hi = rules()["intake"]["pregnancy_status_ages"]
    if demo is not None and demo.sex == "female" and (demo.age_years is None or lo <= demo.age_years <= hi):
        out.append("pregnancy_status")
    return out


def _fmt(v: Any) -> str:
    return "not recorded" if v is None else str(v)


def _count(v: float | None) -> str:
    """A count-like vital (BP, HR, RR, SpO2) as recorded: I2 stores it as a float, so an integral value is shown
    without ``.0`` (as S6 showed it) and any other value is shown in full, never rounded (INT2-A18)."""
    return _fmt(int(v) if isinstance(v, float) and v.is_integer() else v)


def summary(view: SnapshotView, fields: dict) -> list[SummaryLine]:
    """Short descriptive lines, each backed by snapshot refs. Unknown is stated as unknown, never as negative."""
    lines: list[tuple[str, list[str]]] = []
    demo = view.demographics()
    if demo:
        lines.append((f"Age {_fmt(demo.age_years)}, sex {_fmt(demo.sex)}", [demo.item_id]))
    for key, label in (("chief_complaint", "Stated complaint"), ("duration", "Stated duration")):
        f = fields[key]
        if f.state == "known":
            lines.append((f"{label}: {f.value}", list(f.refs)))
        elif f.state == "unknown":
            lines.append((f"{label}: not known (stated as unclear; not read as absent)", list(f.refs)))
    v = view.latest("Vitals")
    if v:
        lines.append((
            f"Latest vital signs at {v.observed_at.isoformat()}: RR {_count(v.rr)}/min, SpO2 {_count(v.spo2)}%, "
            f"on oxygen {_fmt(v.on_oxygen)}, temperature {_fmt(v.temp_c)} °C, BP {_count(v.sbp)}/{_count(v.dbp)} mmHg, "
            f"HR {_count(v.hr)}/min, consciousness {_fmt(v.consciousness)}", [v.item_id]))
    latest: dict[str, tuple[Any, str]] = {}
    for lab in view.of_type("LabSeries"):
        for res in lab.results:
            latest[res.test] = (res, lab.item_id)
    for test in sorted(latest):
        res, iid = latest[test]
        if res.ref_low is None or res.ref_high is None:
            flag = "no reference range given"
        elif res.value < res.ref_low:
            flag = f"below reference range {res.ref_low:g}-{res.ref_high:g}"
        elif res.value > res.ref_high:
            flag = f"above reference range {res.ref_low:g}-{res.ref_high:g}"
        else:
            flag = f"within reference range {res.ref_low:g}-{res.ref_high:g}"
        lines.append((f"Lab {test}: {res.value:g} {res.unit} ({flag})", [iid]))
    allergy = fields["allergy_status"]
    if allergy.state == "known":
        text = {"no_known_allergy": "no known allergy recorded", "known": "allergy recorded"}[allergy.value]
        lines.append((f"Allergy status: {text}", list(allergy.refs)))
    elif allergy.state == "unknown":
        lines.append(("Allergy status: not known (not read as no allergy)", list(allergy.refs)))
    for med in view.of_type("MedicationList"):
        lines.append((f"Medication list ({med.list_source.replace('_', ' ')}): {len(med.entries)} entries",
                      [med.item_id]))
    return [SummaryLine(text=t, evidence_refs=[EvidenceRef(**view.ref(i)) for i in refs]) for t, refs in lines]


def build_request(view: SnapshotView, alerts: Sequence) -> GatewayRequest:
    items = [json.loads(m.model_dump_json()) for m in view.items]
    alert_ctx = [{"rule_id": a.rule_id,
                  "item_ids": sorted({redflag_adapter.item_id_of(r) for r in a.evidence_refs})} for a in alerts]
    return GatewayRequest(task=TASK, data_class=DataClass.SYNTHETIC,
                          inputs={"as_of": view.as_of_text, "items": items, "alerts": alert_ctx,
                                  "max_next_information": MAX_NEXT_INFO, "max_pathway_options": MAX_PATHWAYS})


def _refs(view: SnapshotView, raw: Any) -> list[EvidenceRef]:
    if not isinstance(raw, list) or not raw or not all(isinstance(r, str) for r in raw):
        raise _Invalid("evidence_ref_missing")
    out = []
    for iid in dict.fromkeys(raw):
        if iid not in view.by_id:
            raise _Invalid("evidence_ref_not_in_snapshot")
        if view.by_id[iid].available_at_time > view.as_of:
            raise _Invalid("evidence_ref_after_as_of")
        out.append(EvidenceRef(**view.ref(iid)))
    return out


def validate_output(view: SnapshotView, output: Any, alert_codes: set[str]) -> tuple[list[NextInfo], list[PathwayOption]]:
    """Post-gateway validation. Anything unexpected raises ``_Invalid``; nothing is repaired or guessed."""
    r = rules()
    if not isinstance(output, dict):
        raise _Invalid("provider_output_schema_invalid")
    if URGENCY_KEYS & set(output):
        raise _Invalid("provider_attempted_to_set_urgency")
    if set(output) - OUTPUT_KEYS:
        raise _Invalid("provider_output_schema_invalid")
    ni_raw, cp_raw = output.get("next_information"), output.get("pathway_options")
    if not isinstance(ni_raw, list) or not isinstance(cp_raw, list):
        raise _Invalid("provider_output_schema_invalid")
    if len(ni_raw) > MAX_NEXT_INFO or len(cp_raw) > MAX_PATHWAYS:
        raise _Invalid("provider_output_too_many_items")
    vocab_ni, vocab_cp = r["vocabulary"]["next_info"], r["vocabulary"]["pathways"]
    ni: list[NextInfo] = []
    cp: list[PathwayOption] = []
    for raw, vocab, sink in ((ni_raw, vocab_ni, ni), (cp_raw, vocab_cp, cp)):
        codes = []
        for e in raw:
            if not isinstance(e, dict) or set(e) != {"code", "evidence_refs"}:
                raise _Invalid("provider_output_schema_invalid")
            code = e["code"]
            if not isinstance(code, str) or code not in vocab:
                raise _Invalid("code_outside_vocabulary")
            codes.append(code)
            v = vocab[code]
            common = dict(code=code, display=v["display_en"], display_th=v["display_th"],
                          evidence_refs=_refs(view, e["evidence_refs"]), source_refs=list(r["source_refs"][code]))
            sink.append(NextInfo(kind=v["kind"], **common) if vocab is vocab_ni else PathwayOption(**common))
        if len(set(codes)) != len(codes):
            raise _Invalid("duplicate_code")
    # Items driven by an alert rank first (stable): the provider cannot demote them.
    ni.sort(key=lambda x: x.code not in alert_codes)
    return ni, cp


def _alert_codes(alerts: Sequence) -> set[str]:
    ids = {a.rule_id for a in alerts}
    return {c for rule in rules()["alert_rules"] if rule["alert"] in ids for c in rule["next_info"]}


def _result(**kw: Any) -> CareResult:
    base: dict[str, Any] = dict(case_summary=[], next_information=[], pathway_options=[], reason=None,
                                provider=None, model_version=None, contract_version=None, request_sha256=None,
                                casegraph_projection=None, rules_version=CARE_RULES_VERSION)
    return CareResult(**(base | kw))


def assess(doc: dict[str, Any], invoke: InvokeFn, *, decision_point: str, abstain: bool = True,
           extra_facts: Sequence[IntakeFact] = ()) -> CareResult:
    """Assess one snapshot. ``abstain=False`` (always-answer) is for the evaluation comparator only.

    ``extra_facts`` lets tests supply red-flag symptom facts; the API never passes any.
    """
    try:
        view = SnapshotView(doc)
    except SnapshotError as exc:  # rejected as a whole, never silently dropped
        scr = _screening_view(redflag_adapter.unavailable())
        return _result(alerts=[], red_flag_screening=scr, escalation_required=False, status="error",
                       missing_information=[], reason=str(exc), as_of=str(doc.get("as_of", "")),
                       decision_point=decision_point, case_id=str(doc.get("case_id", "")))

    screening = redflag_adapter.screen(view, extra_facts)  # 1. red flags first, independent of the provider
    alerts = list(screening.alerts)
    scr = _screening_view(screening)
    head = dict(alerts=alerts, red_flag_screening=scr, escalation_required=bool(alerts), as_of=view.as_of_text,
                decision_point=decision_point, case_id=view.case_id)

    fields = view.fields()  # 2. required-input check before the provider
    missing = missing_required(fields)
    if scr.status == "unavailable":
        missing.append(SCREENING_UNAVAILABLE)
    if missing and abstain:
        reason = "required_information_missing" if missing != [SCREENING_UNAVAILABLE] else "red_flag_screening_unavailable"
        return _result(**head, status="abstained", missing_information=missing, reason=reason)
    missing_info = missing + _optional_missing(view)

    resp = invoke(build_request(view, alerts))  # 3. exactly one gateway call
    meta = dict(provider=resp.provider, model_version=resp.model_version, contract_version=resp.contract_version,
                request_sha256=resp.request_sha256)
    if resp.status != "ok" or resp.output is None:
        return _result(**head, **meta, status="error", missing_information=missing_info,
                       reason=f"gateway_{resp.status}:{resp.reason or 'unspecified'}")
    try:
        ni, cp = validate_output(view, resp.output, _alert_codes(alerts))
    except _Invalid as exc:
        return _result(**head, **meta, status="error", missing_information=missing_info, reason=str(exc))

    refs = sorted({e.item_id for x in [*ni, *cp] for e in x.evidence_refs})
    projection = CareSuggestion(produced_by=TASK, input_refs=tuple(refs), provider=resp.provider,
                                model_version=resp.model_version,
                                items=tuple(x.code for x in [*ni, *cp]), red_flag_screening=scr.status)
    return _result(**head, **meta, status="suggested", case_summary=summary(view, fields), next_information=ni,
                   pathway_options=cp, missing_information=missing_info,
                   reason=None if ni or cp else "no_rule_matched",
                   casegraph_projection=projection.model_dump(mode="json"))
