"""S4 Triage adapter: build an S4 ``Case`` per decision point and call ``engine.assess`` (slice e1).

Inputs per decision point T: the snapshot's Vitals and Demographics items plus the S3 output for the case,
mapped with ``e1_mapping_v1.json``. The department call goes through the Model Gateway with the kw-1.0.0 mock
(offline). The always-answer comparator uses ``baseline.rank`` on the same gateway inputs, with no abstain
gate. Product code is used as-is. Research prototype - not for clinical use.
"""

from __future__ import annotations

from typing import Any

from app.db import make_engine
from app.triage import baseline, department, engine
from app.triage.evaluate import mock_invoke  # S4's own in-process gateway wiring (mock provider)
from app.triage.models import Case, IntakeFact, Snapshot

from . import mapping
from .inputs import CaseInputs, InputIntegrityError, items, t

VITALS = ("hr", "rr", "sbp", "dbp", "spo2", "temp_c")
S3_SOURCE = "e1.voice_replay/S3"


def _fact(fid: str, kind: str, value: Any, at: str, source: str, provenance: str, version: str) -> dict[str, Any]:
    return {"fact_id": fid, "kind": kind, "value": value, "available_at_time": at, "source": source[:128],
            "provenance": provenance[:256], "version": version[:32]}


def snapshot_facts(snap: dict[str, Any]) -> tuple[list[dict[str, Any]], dict[str, int]]:
    """S4 facts from Vitals and Demographics items; counts of unmapped / null items for accounting."""
    facts: list[dict[str, Any]] = []
    n = {"vitals_items": 0, "null_values": 0, "on_oxygen_unmappable": 0, "consciousness_C": 0}
    for v in items(snap, "Vitals"):
        n["vitals_items"] += 1
        meta = (v["available_at_time"], v["source"], v["item_id"], v["version"])
        for p in VITALS:
            if v.get(p) is None:
                n["null_values"] += 1
                continue
            facts.append(_fact(f"{v['item_id']}.{p}", f"vital.{p}", v[p], *meta))
        if v.get("consciousness") is None:
            n["null_values"] += 1
        else:
            n["consciousness_C"] += v["consciousness"] == "C"
            for k, val in mapping.consciousness_facts(v["consciousness"]).items():
                facts.append(_fact(f"{v['item_id']}.{k}", f"vital.{k}", val, *meta))
        if v.get("on_oxygen") is not None:
            n["on_oxygen_unmappable"] += 1
    for d in items(snap, "Demographics"):
        meta = (d["available_at_time"], d["source"], d["item_id"], d["version"])
        if d.get("age_years") is not None:
            facts.append(_fact(f"{d['item_id']}.age", "age", d["age_years"], *meta))
        if d.get("sex") is not None:
            facts.append(_fact(f"{d['item_id']}.sex", "sex", d["sex"], *meta))
    return facts, n


def s3_facts(case_id: str, s3: dict[str, Any], tx_item: str | None) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """S4 facts from the S3 output (KNOWN facts only); returns (facts, what was not mapped)."""
    facts: list[dict[str, Any]] = []
    info: dict[str, Any] = {"cc_symptom": None, "cc_symptom_unmappable": False, "no_fact_fields": []}
    prov = f"{case_id}/{tx_item}"
    got = s3.get("facts", {})
    for field in ("chief_complaint", "onset_duration"):
        f = got.get(field)
        if f is None or f["state"] != "KNOWN":
            info["no_fact_fields"].append(f"{field}:{'MISSING' if f is None else f['state']}")
            continue
        at = f["available_at_time"]
        if field == "chief_complaint":
            text = mapping.nfc(f["span_text"]).strip()
            if not 0 < len(text) <= 500:
                raise InputIntegrityError(f"{case_id}: S3 chief complaint span text length {len(text)}")
            facts.append(_fact("s3.chief_complaint", "chief_complaint", text, at, S3_SOURCE, prov, "s3-0.1.0"))
            sym = mapping.s3_symptom(f["value"])
            if sym is None:
                info["cc_symptom_unmappable"] = True
            else:
                info["cc_symptom"] = sym
                facts.append(_fact(f"s3.symptom.{sym}", f"symptom.{sym}", "present", at, S3_SOURCE, prov, "s3-0.1.0"))
        else:
            facts.append(_fact("s3.onset_duration", "onset_duration", f["value"], at, S3_SOURCE, prov, "s3-0.1.0"))
    return facts, info


def build_case(case: CaseInputs, dp: str, s3: dict[str, Any]) -> tuple[Case, dict[str, Any]]:
    snap = case.snapshots[dp]
    vf, counts = snapshot_facts(snap)
    sf, info = s3_facts(case.case_id, s3, s3.get("transcript_item_id"))
    T = t(snap["as_of"])
    late = [f["fact_id"] for f in vf + sf if t(f["available_at_time"]) > T]
    if late:
        raise InputIntegrityError(f"{case.case_id}/{dp}: facts available after T: {late}")
    c = Case(case_ref=case.case_id, data_class="synthetic", facts=[IntakeFact(**f) for f in vf + sf])
    return c, {"counts": counts, **info}


class Assessor:
    """One in-memory SQLite engine and mock gateway for a whole split."""

    def __init__(self) -> None:
        self.engine = make_engine("sqlite://")
        self.invoke = mock_invoke(self.engine)

    def close(self) -> None:
        self.engine.dispose()

    def assess(self, case: CaseInputs, dp: str, s3: dict[str, Any]) -> dict[str, Any]:
        c, info = build_case(case, dp, s3)
        T = t(case.snapshots[dp]["as_of"])
        a = engine.assess(c, T, self.invoke, actor_id=0)
        snap = Snapshot(c, T)
        always = baseline.rank(department.build_request(snap).inputs)
        return {
            "dp": dp,
            "T": case.snapshots[dp]["as_of"],
            "facts": [f.model_dump(mode="json") for f in sorted(c.facts, key=lambda f: f.fact_id)],
            "input_info": info,
            "alerts": [x.rule_id for x in a.alerts],
            "not_evaluable": [x.rule_id for x in a.not_evaluable],
            "escalation_required": a.escalation_required,
            "department": {
                "status": a.department.status,
                "top3": [e.code for e in a.department.top3],
                "reason": a.department.reason,
                "missing_information": a.department.missing_information,
                "uncertainty": a.department.uncertainty,
                "model_version": a.department.model_version,
            },
            "always_answer_ranking": [r["code"] for r in always["ranking"]],
            "ruleset_version": a.ruleset_version,
        }


def run_split(cases: list[CaseInputs], s3_out: dict[str, dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
    a = Assessor()
    try:
        return {c.case_id: [a.assess(c, dp, s3_out[c.case_id]) for dp in sorted(c.snapshots)] for c in cases}
    finally:
        a.close()
