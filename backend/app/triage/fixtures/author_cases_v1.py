"""Authoring source for ``cases_v1.json`` (slice s4). Hand-written synthetic adult cases.

Every gold label below was assigned by hand from the rule definitions in ``slices/s4/SPEC.md``
before the red-flag engine existed. Nothing here calls the engine. Re-run to regenerate the JSON:

    python3 backend/app/triage/fixtures/author_cases_v1.py

Synthetic data only. No real patient is described.
"""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

OUT = Path(__file__).with_name("cases_v1.json")
TZ = timezone(timedelta(hours=7))
DAY0 = datetime(2026, 9, 1, 9, 0, tzinfo=TZ)

# Red-flag screen recorded on every complete intake unless a case overrides it.
SCREEN = (
    "acute_chest_pain", "sudden_facial_droop", "sudden_limb_weakness", "sudden_speech_disturbance",
    "sudden_vision_disturbance", "thunderclap_headache", "allergen_exposure", "airway_breathing_compromise",
    "suicidal_ideation", "self_harm", "hematemesis", "melena", "fever", "neck_stiffness",
    "non_blanching_rash", "abdominal_pain", "vaginal_bleeding",
)
NORMAL_VITALS = {"hr": 80, "rr": 16, "sbp": 125, "dbp": 78, "spo2": 98, "temp_c": 36.8, "avpu": "A",
                 "new_confusion": False}
DROP = object()  # marks a field that was not recorded

# (ref, split, cc, age, sex, onset, vitals overrides, symptoms present/unknown, extras,
#  gold rules, gold department, near_miss, late facts, early gold rules or None)
CASES: list[dict] = [
    # ---- red-flag cases ----
    dict(ref="SYN-S4-001", split="dev", cc="เจ็บแน่นหน้าอก ร้าวไปแขนซ้าย", age=58, sex="male", onset="1 hour",
         vitals={"hr": 102}, sx={"acute_chest_pain": "present"}, rules=["RF-CHEST"], dept="CARD"),
    dict(ref="SYN-S4-002", split="holdout", cc="Chest pain with sweating", age=64, sex="male", onset="40 minutes",
         vitals={"sbp": 88, "dbp": 55, "hr": 132}, sx={"acute_chest_pain": "present"},
         rules=["RF-CHEST", "RF-HR", "RF-SBP"], dept="CARD"),
    dict(ref="SYN-S4-003", split="dev", cc="หน้าเบี้ยว แขนขวาอ่อนแรง พูดไม่ชัด", age=67, sex="female",
         onset="45 minutes", vitals={"sbp": 182, "dbp": 98},
         sx={"sudden_facial_droop": "present", "sudden_limb_weakness": "present",
             "sudden_speech_disturbance": "present"}, rules=["RF-STROKE"], dept="NEURO"),
    dict(ref="SYN-S4-004", split="holdout", cc="Sudden loss of vision in the right eye", age=71, sex="male",
         onset="2 hours", vitals={}, sx={"sudden_vision_disturbance": "present"}, rules=["RF-STROKE"], dept="EYE"),
    dict(ref="SYN-S4-005", split="dev", cc="ปวดศีรษะรุนแรงที่สุดในชีวิต เกิดขึ้นทันที", age=45, sex="female",
         onset="30 minutes", vitals={"sbp": 160}, sx={"thunderclap_headache": "present"},
         rules=["RF-THUNDER"], dept="NEURO"),
    dict(ref="SYN-S4-006", split="holdout", cc="Worst headache of my life, started suddenly while lifting",
         age=39, sex="male", onset="50 minutes", vitals={},
         sx={"thunderclap_headache": "present", "neck_stiffness": "present"}, rules=["RF-THUNDER"], dept="NEURO"),
    dict(ref="SYN-S4-007", split="dev", cc="ปากบวม คอบวม หลังกินกุ้ง", age=29, sex="female", onset="20 minutes",
         vitals={"spo2": 93, "rr": 24, "hr": 112},
         sx={"allergen_exposure": "present", "airway_breathing_compromise": "present"},
         rules=["RF-ANAPH"], dept="MED"),
    dict(ref="SYN-S4-008", split="holdout", cc="แพ้ยา ผื่นขึ้นทั้งตัว หน้ามืด", age=50, sex="male",
         onset="30 minutes", vitals={"sbp": 82, "dbp": 50, "hr": 124}, sx={"allergen_exposure": "present"},
         rules=["RF-ANAPH", "RF-SBP"], dept="MED"),
    dict(ref="SYN-S4-009", split="dev", cc="รู้สึกเศร้ามาก นอนไม่หลับ", age=34, sex="female", onset="3 weeks",
         vitals={}, sx={"low_mood": "present", "suicidal_ideation": DROP}, rules=["RF-SUICIDE"], dept="PSY",
         late=[("symptom.suicidal_ideation", "present", 35)], early_rules=[]),
    dict(ref="SYN-S4-010", split="holdout", cc="Cut my wrists last night, feeling hopeless", age=22, sex="male",
         onset="1 day", vitals={}, sx={"self_harm": "present", "low_mood": "present"},
         rules=["RF-SUICIDE"], dept="PSY"),
    dict(ref="SYN-S4-011", split="dev", cc="อาเจียนเป็นเลือด", age=55, sex="male", onset="3 hours",
         vitals={"hr": 118, "sbp": 102}, sx={"hematemesis": "present"}, rules=["RF-GIBLEED"], dept="SURG"),
    dict(ref="SYN-S4-012", split="holdout", cc="Black tarry stools for two days, dizzy", age=62, sex="female",
         onset="2 days", vitals={"sbp": 92, "hr": 110}, sx={"melena": "present"}, rules=["RF-GIBLEED"],
         dept="SURG"),
    dict(ref="SYN-S4-013", split="dev", cc="ปวดท้องน้อย มีเลือดออกทางช่องคลอด ประจำเดือนขาด", age=27,
         sex="female", onset="6 hours", vitals={"hr": 104},
         sx={"abdominal_pain": "present", "vaginal_bleeding": "present"}, extra={"pregnancy_status": "positive"},
         rules=["RF-ECTOPIC"], dept="OBGYN"),
    dict(ref="SYN-S4-014", split="holdout", cc="Lower abdominal pain on one side since this morning", age=31,
         sex="female", onset="5 hours", vitals={}, sx={"abdominal_pain": "present"}, rules=["RF-ECTOPIC"],
         dept="OBGYN"),
    dict(ref="SYN-S4-015", split="dev", cc="ไข้สูง คอแข็ง ปวดศีรษะ", age=19, sex="male", onset="1 day",
         vitals={"temp_c": 39.2, "hr": 118}, sx={"fever": "present", "neck_stiffness": "present",
                                                 "headache": "present"}, rules=["RF-MENING"], dept="MED"),
    dict(ref="SYN-S4-016", split="holdout", cc="Fever with purple spots that do not fade", age=21, sex="female",
         onset="12 hours", vitals={"temp_c": 38.9, "rr": 23, "sbp": 98, "hr": 120},
         sx={"fever": "present", "non_blanching_rash": "present", "neck_stiffness": DROP},
         rules=["RF-MENING", "RF-QSOFA"], dept="MED"),
    dict(ref="SYN-S4-017", split="dev", cc="เบาหวาน ใจสั่น เหงื่อออก สับสน", age=68, sex="male", onset="1 hour",
         vitals={"new_confusion": True, "hr": 104}, sx={"diabetes_known": "present"},
         rules=["RF-CONSC", "RF-HYPOGLY"], dept="MED",
         late=[("vital.capillary_glucose_mg_dl", 42, 25)], early_rules=["RF-CONSC"]),
    dict(ref="SYN-S4-018", split="holdout", cc="ซึม เรียกไม่ค่อยตื่น ตัวเย็น", age=80, sex="female", onset="1 day",
         vitals={"avpu": "V", "temp_c": 34.6, "capillary_glucose_mg_dl": 110}, sx={},
         rules=["RF-CONSC", "RF-TEMP"], dept="MED"),
    dict(ref="SYN-S4-019", split="dev", cc="ไข้ ไอ หอบเหนื่อยมาก", age=72, sex="male", onset="3 days",
         vitals={"spo2": 95, "rr": 20, "sbp": 118, "hr": 100, "temp_c": 38.9},
         sx={"fever": "present", "cough": "present", "dyspnea": "present"},
         rules=["RF-QSOFA", "RF-RR", "RF-SPO2"], dept="MED",
         late=[("vital.spo2", 88, 30), ("vital.rr", 28, 30), ("vital.sbp", 96, 30), ("vital.hr", 115, 30)],
         early_rules=[]),
    dict(ref="SYN-S4-020", split="holdout", cc="กินยานอนหลับเกินขนาด ญาติพามา", age=40, sex="male",
         onset="2 hours", vitals={"rr": 7, "avpu": "P", "sbp": 110}, sx={"suicidal_ideation": "present"},
         rules=["RF-CONSC", "RF-RR", "RF-SUICIDE"], dept="PSY"),
    dict(ref="SYN-S4-021", split="dev", cc="ใจสั่น หน้ามืดจะเป็นลม", age=48, sex="female", onset="2 hours",
         vitals={"hr": 38}, sx={"palpitations": "present"}, rules=["RF-HR"], dept="CARD"),
    dict(ref="SYN-S4-022", split="holdout", cc="ปวดบั้นเอวขวา ไข้หนาวสั่น", age=58, sex="male", onset="2 days",
         vitals={"rr": 24, "sbp": 96, "hr": 112, "temp_c": 38.8},
         sx={"fever": "present", "flank_pain": "present"}, rules=["RF-QSOFA"], dept="URO"),
    # ---- required field missing (department must abstain) ----
    dict(ref="SYN-S4-023", split="dev", cc="Knee pain after a fall", age=45, sex="male", onset="1 day",
         vitals={"spo2": DROP}, sx={"joint_pain": "present"}, rules=[], dept="ORTHO",
         missing=["vitals.spo2"]),
    dict(ref="SYN-S4-024", split="holdout", cc="ปวดหลังร้าวลงขา", age=DROP, sex="female", onset="2 weeks",
         vitals={}, sx={"back_pain": "present"}, rules=[], dept="ORTHO", missing=["age"]),
    dict(ref="SYN-S4-025", split="dev", cc="Vomiting blood this morning", age=DROP, sex="male", onset="4 hours",
         vitals={"hr": 112}, sx={"hematemesis": "present"}, rules=["RF-GIBLEED"], dept="SURG",
         missing=["age"]),
    dict(ref="SYN-S4-026", split="holdout", cc="เวียนหัว หน้ามืด", age=70, sex="female", onset="3 hours",
         vitals={"sbp": 84, "dbp": 52, "temp_c": DROP, "avpu": DROP, "rr": 18}, sx={"dizziness": "present"},
         rules=["RF-SBP"], dept="MED", missing=["vitals.temp_c", "vitals.avpu"]),
    dict(ref="SYN-S4-027", split="dev", cc="ปวดหู", age=33, sex="male", onset=DROP, vitals={},
         sx={"ear_pain": "present"}, rules=[], dept="ENT", missing=["onset_duration"]),
    dict(ref="SYN-S4-028", split="holdout", cc="ปัสสาวะแสบขัด", age=40, sex=DROP, onset="3 days", vitals={},
         sx={"dysuria": "present"}, rules=[], dept="URO", missing=["sex"]),
    # ---- near-miss negatives ----
    dict(ref="SYN-S4-029", split="dev", cc="ปวดเข่าขวาหลังเล่นฟุตบอล", age=24, sex="male", onset="1 day",
         vitals={"hr": 125}, sx={"joint_pain": "present"}, rules=[], dept="ORTHO", near_miss=True),
    dict(ref="SYN-S4-030", split="holdout", cc="Low back pain after lifting boxes", age=41, sex="male",
         onset="2 days", vitals={"spo2": 92}, sx={"back_pain": "present"}, rules=[], dept="ORTHO", near_miss=True),
    dict(ref="SYN-S4-031", split="dev", cc="ข้อมือบวม ปวด หลังล้ม", age=58, sex="female", onset="6 hours",
         vitals={"sbp": 91}, sx={"joint_pain": "present"}, rules=[], dept="ORTHO", near_miss=True),
    dict(ref="SYN-S4-032", split="dev", cc="ปัสสาวะแสบขัด ปัสสาวะบ่อย", age=26, sex="female", onset="2 days",
         vitals={"rr": 24, "temp_c": 37.9}, sx={"dysuria": "present"}, rules=[], dept="URO", near_miss=True),
    dict(ref="SYN-S4-033", split="holdout", cc="Blood in urine, no pain", age=66, sex="male", onset="1 week",
         vitals={"sbp": 219, "dbp": 100}, sx={"hematuria": "present"}, rules=[], dept="URO", near_miss=True),
    dict(ref="SYN-S4-034", split="dev", cc="ตามัวลงเรื่อยๆ หลายเดือน", age=70, sex="female", onset="6 months",
         vitals={"temp_c": 35.1}, sx={"blurred_vision_gradual": "present"}, rules=[], dept="EYE", near_miss=True),
    dict(ref="SYN-S4-035", split="holdout", cc="Red painful eye with discharge", age=35, sex="male",
         onset="2 days", vitals={"hr": 41}, sx={"red_eye": "present", "eye_pain": "present"}, rules=[],
         dept="EYE", near_miss=True),
    dict(ref="SYN-S4-036", split="dev", cc="เจ็บคอ กลืนลำบาก มีไข้", age=30, sex="female", onset="2 days",
         vitals={"temp_c": 38.6}, sx={"sore_throat": "present", "fever": "present"}, rules=[], dept="ENT",
         near_miss=True),
    dict(ref="SYN-S4-037", split="holdout", cc="Ear pain and discharge for three days", age=28, sex="male",
         onset="3 days", vitals={"rr": 9}, sx={"ear_pain": "present"}, rules=[], dept="ENT", near_miss=True),
    dict(ref="SYN-S4-038", split="holdout", cc="เลือดกำเดาไหล หยุดแล้ว", age=52, sex="female", onset="2 hours",
         vitals={"sbp": 170, "dbp": 95, "capillary_glucose_mg_dl": 54}, sx={"epistaxis": "present"}, rules=[],
         dept="ENT", near_miss=True),
    dict(ref="SYN-S4-039", split="dev", cc="Lump in the groin that gets bigger when coughing", age=50, sex="male",
         onset="1 month", vitals={"rr": 22, "sbp": 101}, sx={"groin_lump": "present"}, rules=[], dept="SURG",
         near_miss=True),
    dict(ref="SYN-S4-040", split="holdout", cc="ตกขาวผิดปกติ คันช่องคลอด", age=33, sex="female", onset="1 week",
         vitals={}, sx={"vaginal_discharge": "present"}, rules=[], dept="OBGYN", near_miss=True),
]


def _iso(dt: datetime) -> str:
    return dt.isoformat()


def build_case(i: int, spec: dict) -> dict:
    t0 = DAY0 + timedelta(days=i)
    facts: list[dict] = []

    def add(kind: str, value, minutes: int) -> None:
        facts.append({
            "fact_id": f"{spec['ref']}-F{len(facts) + 1:02d}",
            "kind": kind,
            "value": value,
            "available_at_time": _iso(t0 + timedelta(minutes=minutes)),
            "source": "synthetic-intake-form",
            "provenance": "hand-authored synthetic fixture (slice s4)",
            "version": "cases-v1",
        })

    for kind, value in (("age", spec["age"]), ("sex", spec["sex"]), ("chief_complaint", spec["cc"]),
                        ("onset_duration", spec["onset"])):
        if value is not DROP:
            add(kind, value, 0)
    vitals = NORMAL_VITALS | spec.get("vitals", {})
    for name, value in vitals.items():
        if value is not DROP:
            add(f"vital.{name}", value, 5)
    symptoms = {name: "absent" for name in SCREEN} | spec.get("sx", {})
    for name, state in symptoms.items():
        if state is not DROP:
            add(f"symptom.{name}", state, 10)
    for kind, value in spec.get("extra", {}).items():
        add(kind, value, 10)
    for kind, value, minutes in spec.get("late", []):
        add(kind, value, minutes)

    gold = {
        "red_flag_rules": sorted(spec["rules"]),
        "department": spec["dept"],
        "missing_required": spec.get("missing", []),
        "near_miss": spec.get("near_miss", False),
        "temporal": None,
    }
    if "early_rules" in spec:
        gold["temporal"] = {"early_as_of": _iso(t0 + timedelta(minutes=20)),
                            "red_flag_rules": sorted(spec["early_rules"])}
    return {
        "split": spec["split"],
        "as_of": _iso(t0 + timedelta(minutes=40)),
        "case": {"case_ref": spec["ref"], "data_class": "synthetic", "facts": facts},
        "gold": gold,
    }


def _dump(doc: dict) -> str:
    """Stable JSON with one fact per line, so reviews can read the file."""
    one = lambda obj: json.dumps(obj, ensure_ascii=False)  # noqa: E731
    head = {k: v for k, v in doc.items() if k != "cases"}
    lines = ["{"] + [f" {one(k)}: {one(v)}," for k, v in head.items()] + [' "cases": [']
    for i, entry in enumerate(doc["cases"]):
        case = entry["case"]
        lines.append(f'  {{"split": {one(entry["split"])}, "as_of": {one(entry["as_of"])},')
        lines.append(f'   "case": {{"case_ref": {one(case["case_ref"])}, "data_class": {one(case["data_class"])}, "facts": [')
        lines += [f"    {one(f)}{',' if j < len(case['facts']) - 1 else ''}" for j, f in enumerate(case["facts"])]
        lines.append("   ]},")
        lines.append(f'   "gold": {one(entry["gold"])}}}{"," if i < len(doc["cases"]) - 1 else ""}')
    lines += [" ]", "}"]
    return "\n".join(lines) + "\n"


def main() -> None:
    doc = {
        "version": "cases-v1",
        "data_class": "synthetic",
        "note": "Hand-written synthetic adult cases for slice s4. Not real patients. Gold labels are the "
                "author's reading of the s4 rule definitions (System Evaluation only).",
        "cases": [build_case(i, spec) for i, spec in enumerate(CASES)],
    }
    OUT.write_text(_dump(doc), encoding="utf-8")
    print(f"wrote {len(doc['cases'])} cases to {OUT}")


if __name__ == "__main__":
    main()
