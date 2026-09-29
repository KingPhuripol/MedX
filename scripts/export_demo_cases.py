#!/usr/bin/env python3
"""Export 6 synthetic demo cases for the V2 case workspace (slice u7).

Reads ONLY ``data/synthetic/v1/inputs/train/<case>/snapshot_T2.json`` (the decision-point-T2 snapshot; already
temporally filtered) and ``splits.json`` to prove the patient is in the train split. It never reads ``gold/``,
``journey.json`` (holds items after T), or any dev/test/held-out split. Output is deterministic:

    backend/app/demo/fixtures/cases_v1.json

Selection uses the deterministic engines (red-flag rules and pharma reconcile) only to pick *which* train cases
show which path; no label is read. Usage:  python3 scripts/export_demo_cases.py [--data DIR] [--out FILE]
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))
sys.path.insert(0, str(ROOT))

from app.config import Settings  # noqa: E402
from app.db import create_schema  # noqa: E402
from app.demo import case_engines as eng  # noqa: E402

SCRIPT_VERSION = "u7-1"
SPLIT = "train"
DECISION_POINT = "T2"
LABEL = {"home_list": "รายการยาประจำ (ประวัติเดิม)", "patient_reported": "ผู้รับบริการแจ้งจากการสัมภาษณ์",
         "new_order": "คำสั่งยาใหม่"}
TYPE_ORDER = {"home_list": 0, "patient_reported": 1, "new_order": 2}
KEEP_VITAL = ("hr", "rr", "sbp", "dbp", "spo2", "temp_c", "consciousness", "on_oxygen")


def dt(s: str) -> datetime:
    return datetime.fromisoformat(s)


def med_text(e: dict) -> str:
    dose = None if e.get("dose_value") is None else f"{e['dose_value']:g} {e.get('dose_unit') or ''}".strip()
    return " ".join(p for p in (e["generic_name"], dose, e.get("frequency")) if p)


def build_case(snap: dict) -> dict:
    t = dt(snap["as_of"])
    items = [i for i in snap["items"] if dt(i["available_at_time"]) <= t]  # temporal filter: nothing after T
    by = lambda kind: [i for i in items if i["data_type"] == kind]  # noqa: E731
    demo = by("Demographics")[0]
    allergy = by("AllergyList")[0]
    tx = by("IntakeTranscript")[0]
    patient = [x["text"] for x in tx["turns"] if x["speaker"] == "patient"]
    vitals = [{"observed_at": v["observed_at"], "available_at_time": v["available_at_time"], "evidence_id": v["item_id"],
               **{k: v.get(k) for k in KEEP_VITAL}} for v in sorted(by("Vitals"), key=lambda v: v["observed_at"])]
    labs: dict[str, dict] = {}
    for series in sorted(by("LabSeries"), key=lambda i: i["available_at_time"]):
        for r in series["results"]:
            if dt(r["resulted_at"]) <= t:
                labs[r["test"]] = {"test": r["test"], "value": r["value"], "unit": r["unit"], "ref_low": r["ref_low"],
                                   "ref_high": r["ref_high"], "resulted_at": r["resulted_at"],
                                   "available_at_time": series["available_at_time"]}
    status = allergy["status"]
    allergies = None if status == "unknown" else ([{"substance": e["substance"], "reaction": e["reaction"]}
                                                    for e in allergy["entries"]] if status == "known" else [])
    med_sources = [{"source_type": m["list_source"], "evidence_ref": m["item_id"], "list_name": LABEL[m["list_source"]],
                    "available_at_time": m["available_at_time"], "provenance": f"{m['source']} (synthetic)",
                    "version": m["version"], "entries": [med_text(e) for e in m["entries"]]}
                   for m in sorted(by("MedicationList"), key=lambda m: TYPE_ORDER[m["list_source"]])]
    title = {"AllergyList": "บันทึกประวัติแพ้", "Demographics": "ลงทะเบียนรับเข้า", "Vitals": "บันทึกสัญญาณชีพ",
             "IntakeTranscript": "บันทึกข้อมูลรับเข้า", "LabSeries": "ผลแล็บออก", "MedicationList": "บันทึกรายการยา"}
    timeline = []
    for i in sorted(items, key=lambda i: (i["available_at_time"], i["item_id"])):
        kind = i["data_type"]
        detail = {"AllergyList": {"known": "มีประวัติแพ้ที่บันทึกไว้", "no_known_allergy": "บันทึกว่าไม่มีประวัติแพ้",
                                  "unknown": "ไม่ทราบสถานะการแพ้"}[i.get("status", "unknown")] if kind == "AllergyList" else "",
                  "Demographics": "ข้อมูลประชากรจากทะเบียน", "Vitals": "ค่าที่บันทึกที่จุดคัดกรอง",
                  "IntakeTranscript": "บทสนทนาจำลองภาษาไทย", "LabSeries": f"{len(i.get('results', []))} รายการ",
                  "MedicationList": LABEL.get(i.get("list_source", ""), "")}[kind]
        timeline.append({"event_id": f"{snap['case_id']}-{i['item_id']}", "kind": kind.lower(),
                         "title": title[kind] + (f" ({LABEL[i['list_source']]})" if kind == "MedicationList" else ""),
                         "detail": detail, "actor": {"role": "system", "display": "ข้อมูลสังเคราะห์"},
                         "timestamp": i["available_at_time"], "version": 1})
    return {
        "case_id": snap["case_id"], "patient_ref": snap["patient_ref"], "data_class": "synthetic",
        "display_name": f"ผู้รับบริการสังเคราะห์ {snap['case_id']}", "decision_time": snap["as_of"],
        "demographics": {"age": demo["age_years"], "sex": {"female": "หญิง", "male": "ชาย"}[demo["sex"]], "sex_code": demo["sex"],
                         "hn": snap["patient_ref"], "available_at_time": demo["available_at_time"]},
        "intake": {"chief_complaint": patient[0], "onset": patient[1], "source": "บทสนทนาจำลองภาษาไทย (ข้อความที่ผู้รับบริการพูด)",
                   "status": "recorded"},
        "summary": f"ข้อมูลสังเคราะห์ ณ จุดตัดสินใจ T2 · อาการที่ผู้รับบริการแจ้ง: {patient[0]}",
        "vitals": vitals, "allergies": allergies, "allergy_available_at_time": allergy["available_at_time"], "labs": list(labs.values()),
        "med_sources": med_sources, "timeline": timeline,
    }


def features(case: dict, engine) -> dict:
    flags = eng.run_redflags(case)
    issues = eng.run_pharma(case, engine)["issues"] if case["med_sources"] else []
    latest = case["vitals"][-1]
    return {"alerts": len(flags["alerts"]), "issue_types": sorted({i["type"] for i in issues}),
            "allergy": "unknown" if case["allergies"] is None else ("known" if case["allergies"] else "none"),
            "missing_latest": [k for k in KEEP_VITAL if latest.get(k) is None],
            "missing_any": [k for v in case["vitals"] for k in KEEP_VITAL if v.get(k) is None], "has_meds": bool(case["med_sources"])}


def select(cases: dict[str, dict], feats: dict[str, dict]) -> list[tuple[str, str]]:
    """Deterministic: the lowest case id matching each rule, no case used twice."""
    ids, chosen = sorted(cases), []
    rules = [
        ("vitals red flag (RF-* rule raised by recorded vitals)", lambda f: f["alerts"] > 0 and f["has_meds"]),
        ("medication discrepancy (pharma engine issue, no allergy issue, no red flag)",
         lambda f: f["alerts"] == 0 and f["issue_types"] and not any(t.startswith("allergy") for t in f["issue_types"])),
        ("allergy recorded (known substance), no red flag", lambda f: f["alerts"] == 0 and f["allergy"] == "known" and f["has_meds"]),
        ("allergy status unknown (null), no red flag", lambda f: f["alerts"] == 0 and f["allergy"] == "unknown" and f["has_meds"]),
        ("missing vital (a recorded vital is null), no red flag",
         lambda f: f["alerts"] == 0 and f["missing_any"] and f["has_meds"]),
        ("no rule raised, no medication issue, no known allergy (shows the not-evaluated path)",
         lambda f: f["alerts"] == 0 and not f["issue_types"] and f["allergy"] == "none" and f["has_meds"] and not f["missing_any"]),
    ]
    for label, ok in rules:
        pick = next((i for i in ids if i not in {c for c, _ in chosen} and ok(feats[i])), None)
        if pick is None:
            raise SystemExit(f"no train case matches: {label}")
        chosen.append((pick, label))
    return chosen


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--data", default=str(ROOT / "data/synthetic/v1"))
    ap.add_argument("--out", default=str(ROOT / "backend/app/demo/fixtures/cases_v1.json"))
    args = ap.parse_args()
    data = Path(args.data)
    splits = json.loads((data / "splits.json").read_text())
    manifest = json.loads((data / "manifest.json").read_text())
    from sqlalchemy import create_engine
    from sqlalchemy.pool import StaticPool

    engine = create_engine("sqlite://", poolclass=StaticPool, connect_args={"check_same_thread": False})
    create_schema(engine)
    cases: dict[str, dict] = {}
    for d in sorted((data / "inputs" / SPLIT).iterdir()):
        snap = json.loads((d / f"snapshot_{DECISION_POINT}.json").read_text())
        assert splits[snap["patient_ref"]] == SPLIT, f"{snap['case_id']} is not a {SPLIT}-split patient"
        cases[snap["case_id"]] = build_case(snap)
    feats = {cid: features(c, engine) for cid, c in cases.items()}
    chosen = select(cases, feats)
    out = {
        "provenance": {
            "data_class": "synthetic", "generator": "scripts/export_demo_cases.py", "script_version": SCRIPT_VERSION,
            "source_dataset": "data/synthetic/v1", "dataset_output_version": manifest["output_version"],
            "dataset_generator_version": manifest["generator_version"], "dataset_seed": manifest["seed"],
            "split": SPLIT, "decision_point": DECISION_POINT, "temporal_filter": "available_at_time <= decision_time",
            "excluded": ["gold labels", "expected_action", "injected-issue logs", "journey.json", "dev/test/held-out splits"],
            "selection": [{"case_id": c, "reason": r} for c, r in chosen],
        },
        "cases": [cases[c] for c, _ in chosen],
    }
    Path(args.out).write_text(json.dumps(out, ensure_ascii=False, indent=1, sort_keys=True) + "\n", encoding="utf-8")
    for c, r in chosen:
        print(c, r, feats[c])


if __name__ == "__main__":
    main()
