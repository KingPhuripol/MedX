"""U7: run the existing deterministic engines on the committed synthetic demo fixture cases.

Red flags: ``triage.redflags`` (rule file pinned by SHA-256) on facts built from the snapshot vitals and
demographics. Rules that need symptom facts the snapshot cannot supply come back as *not evaluated* and are
never read as negative. Medications: ``pharma.pipeline.reconcile`` on the case's medication sources, through
the in-process gateway with the **mock** provider only. No model is used for the red-flag decision.
"""

from __future__ import annotations

import json
from datetime import datetime
from functools import lru_cache
from pathlib import Path
from typing import Any

from ..config import Settings
from ..gateway import GatewayRequest, GatewayResponse, build_provider, invoke_gateway
from ..pharma import pipeline as pharma_pipeline
from ..pharma.models import MedSnapshot
from ..triage import redflags
from ..triage.models import Case, Snapshot

FIXTURE_PATH = Path(__file__).with_name("fixtures") / "cases_v1.json"
SYMPTOM_TEXT = "ยังประเมินไม่ได้ — ข้อมูลอาการยังไม่ถูกดึง"
ISSUE_LABEL_TH = {
    "allergy_direct": "ยาตรงกับสิ่งที่แพ้",
    "allergy_class": "ยาอยู่ในกลุ่มเดียวกับสิ่งที่แพ้",
    "allergy_cross_reactivity": "อาจแพ้ข้ามกลุ่ม",
    "duplication_ingredient": "ตัวยาซ้ำกัน",
    "duplication_class": "ยากลุ่มเดียวกันซ้ำกัน",
    "dose_mismatch": "ขนาดยาไม่ตรงกัน",
    "frequency_mismatch": "ความถี่ไม่ตรงกัน",
    "missing_field": "ข้อมูลยาไม่ครบ",
    "omission": "ยาหายจากรายการสั่งใหม่",
}
_VITAL_TH = {"hr": "ชีพจร", "rr": "อัตราหายใจ", "sbp": "ความดันตัวบน", "dbp": "ความดันตัวล่าง", "spo2": "SpO₂",
             "temp_c": "อุณหภูมิ", "avpu": "ระดับความรู้สึกตัว", "new_confusion": "อาการสับสนเฉียบพลัน",
             "capillary_glucose_mg_dl": "น้ำตาลปลายนิ้ว"}


@lru_cache(maxsize=1)
def load_fixture() -> dict[str, Any]:
    return json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))


def fixture_cases() -> dict[str, dict]:
    return {c["case_id"]: c for c in load_fixture()["cases"]}


# ---- red flags ----------------------------------------------------------------------------------


def triage_case(case: dict) -> Case:
    """Facts from the recorded snapshot. A null vital is *not* a fact (missing stays missing)."""
    facts: list[dict] = []

    def add(fact_id: str, kind: str, value: Any, at: str, source: str) -> None:
        facts.append({"fact_id": fact_id, "kind": kind, "value": value, "available_at_time": at,
                      "source": source, "provenance": "synthetic demo fixture", "version": "1"})

    demo_at = case["demographics"]["available_at_time"]
    add("demo-age", "age", case["demographics"]["age"], demo_at, "registration")
    add("demo-sex", "sex", case["demographics"]["sex_code"], demo_at, "registration")
    for n, reading in enumerate(case["vitals"]):
        at, src = reading["available_at_time"], reading.get("evidence_id") or f"vitals-{n}"
        for key in ("hr", "rr", "sbp", "dbp", "spo2", "temp_c"):
            if reading.get(key) is not None:
                add(f"{src}:{key}", f"vital.{key}", reading[key], at, src)
        acvpu = reading.get("consciousness")
        if acvpu is not None:  # ACVPU is one scale: "C" is new confusion, A/V/P/U mean no new confusion
            if acvpu in ("A", "V", "P", "U"):
                add(f"{src}:avpu", "vital.avpu", acvpu, at, src)
            add(f"{src}:new_confusion", "vital.new_confusion", acvpu == "C", at, src)
    return Case.model_validate({"case_ref": case["case_id"], "data_class": "synthetic", "facts": facts})


def _missing_reason(missing: list[str]) -> str:
    symptoms = [m for m in missing if m.startswith("symptom.")]
    others = [m.removeprefix("vital.") for m in missing if not m.startswith("symptom.")]
    parts = []
    if symptoms:
        parts.append(SYMPTOM_TEXT)
    if others:
        parts.append("ไม่มีบันทึก " + ", ".join(_VITAL_TH.get(o, o) for o in others))
    return " · ".join(parts)


def run_redflags(case: dict) -> dict:
    as_of = datetime.fromisoformat(case["decision_time"])
    snap = Snapshot(triage_case(case), as_of)
    alerts, not_evaluable = redflags.evaluate(snap)
    return {
        "engine": "triage.redflags",
        "ruleset_version": redflags.RULESET_VERSION,
        "rules_total": len(redflags.rules()),
        "alerts": [{"rule_id": a.rule_id, "name_th": a.name_th, "message_th": a.message_th,
                    "evidence_refs": a.evidence_refs} for a in alerts],
        "not_evaluated": [{"rule_id": n.rule_id, "name_th": n.name_th, "missing_inputs": n.missing_inputs,
                           "reason_th": _missing_reason(n.missing_inputs)} for n in not_evaluable],
        "not_evaluated_text": SYMPTOM_TEXT,
    }


def safety_block(flags: dict) -> dict:
    """Banner content. No alert never says the case is safe; it says no alert was raised from available data."""
    if flags["alerts"]:
        detail = " · ".join(f"{a['rule_id']} {a['name_th']}" for a in flags["alerts"])
        return {"level": "critical", "label": "พบสัญญาณที่ต้องประเมินเร่งด่วน", "detail": detail, "acknowledged": False}
    n = len(flags["not_evaluated"])
    tail = f" · กฎ {n} ข้อยังประเมินไม่ได้ ({SYMPTOM_TEXT.split(' — ')[1]})" if n else ""
    return {"level": "none", "label": "ไม่พบสัญญาณเตือนจากข้อมูลที่มีอยู่",
            "detail": "ผลนี้มาจากข้อมูลที่ดึงมาแล้วเท่านั้น ไม่ใช่ข้อสรุปว่าไม่มีความเสี่ยง" + tail,
            "acknowledged": False}


# ---- medications --------------------------------------------------------------------------------


def med_snapshot(case: dict) -> MedSnapshot:
    return MedSnapshot.model_validate({
        "patient_ref": case["patient_ref"],
        "as_of": case["decision_time"],
        "data_class": "synthetic",
        "sources": [{k: s[k] for k in ("source_type", "evidence_ref", "available_at_time", "provenance", "version", "entries")}
                    for s in case["med_sources"]],
        "allergies": [{"text": a["substance"], "evidence_ref": f"{case['case_id']}-ALLERGY", "provenance": "synthetic demo fixture",
                       "version": "1", "available_at_time": case["allergy_available_at_time"]}
                      for a in (case["allergies"] or [])],
    })


def run_pharma(case: dict, engine, user=None) -> dict:
    """Mock provider only, whatever the app's configured provider is; gateway calls are audited on ``engine``."""
    provider = build_provider("mock", Settings())

    def invoke(req: GatewayRequest) -> GatewayResponse:
        return invoke_gateway(engine, provider, req, request_id="demo-fixture", actor_id=getattr(user, "id", None), actor_role=user.role.value if user else "system")

    return pharma_pipeline.reconcile(med_snapshot(case), invoke, "rules_only")


def pharma_summary(run: dict) -> dict:
    return {"engine": "pharma.reconcile", "pipeline_version": run["pipeline_version"], "rules_version": run["rules_version"],
            "formulary_version": run["formulary_version"], "issue_count": len(run["issues"]),
            "notice_count": len(run["notices"]), "unchecked_comparisons": run["unchecked_comparisons"]}


def medications_payload(case: dict, run: dict) -> dict:
    sources = [{"source_id": s["evidence_ref"], "label": s["list_name"], "recorded_value": "; ".join(s["entries"]) or "ไม่มีรายการ",
                "captured_at": s["available_at_time"]} for s in case["med_sources"]]
    discrepancies = [{
        "review_id": i["issue_id"], "type": i["type"], "label": ISSUE_LABEL_TH.get(i["type"], i["type"]),
        "detail": i["phrasing"]["text"], "status": "pending",
        "provenance": sorted({s["evidence_ref"] for s in i["conflicting_sources"]}), "version": 1,
    } for i in run["issues"]]
    return {"sources": sources, "discrepancies": discrepancies, "engine": pharma_summary(run)}
