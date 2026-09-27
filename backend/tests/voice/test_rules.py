"""Thai semantics of the mock extraction rules (S3-A02 unit phrases, duration normalisation, corrections)."""

import pytest
from sqlalchemy import select

from app.voice.db import voice_facts
from app.voice.mock_rules import extract, thai_number

from .helpers import VoiceAPI


def _facts(text: str, asked: str | None = "allergy_status") -> dict[str, dict]:
    out = extract({"turns": [{"turn_id": "u1", "speaker": "patient", "text": text}], "last_asked_field": asked})
    return {f["field"]: f for f in out["facts"]}


ALLERGY_CASES = {
    "deny": ("ปฏิเสธแพ้ยา", "KNOWN", "none", None),
    "present": ("แพ้เพนิซิลลิน", "KNOWN", "present", ["เพนิซิลลิน"]),
    "unknown": ("จำไม่ได้", "UNKNOWN", None, None),
    "refused": ("ไม่ขอตอบ", "REFUSED", None, None),
}


@pytest.mark.parametrize("case", list(ALLERGY_CASES))
def test_allergy_semantics(case):
    text, state, value, allergens = ALLERGY_CASES[case]
    facts = _facts(text)
    assert (facts["allergy_status"]["state"], facts["allergy_status"]["value"]) == (state, value)
    assert facts.get("allergens", {}).get("value") == allergens
    # "ปฏิเสธ" in Thai clinical usage means *denies*, never "refused to answer".
    if case == "deny":
        assert facts["allergy_status"]["state"] != "REFUSED"


def test_allergy_uncertainty_never_becomes_none():
    for text in ("ไม่แน่ใจว่าเคยแพ้ยาไหม", "จำไม่ได้ว่าแพ้ยาอะไร", "ไม่อยากบอก", "ไม่แพ้ยาอื่น แต่แพ้ซัลฟา"):
        facts = _facts(text)
        assert facts["allergy_status"]["value"] != "none", text


def test_missing_allergy_stays_missing(client, login, app):
    login("nurse1")
    api = VoiceAPI(client, app)
    api.start()
    api.turn("ปวดท้องค่ะ")
    api.turn("สองวันค่ะ")
    api.turn("ประมาณ 5 ค่ะ")
    assert api.turn("ค่ะ").json()["next_action"]["utterance_id"] == "reask.allergy_status"
    assert api.turn("ค่ะ").json()["next_action"]["field"] == "current_medications"
    api.turn("ไม่มีค่ะ")
    last = api.turn("ไม่มีค่ะ").json()
    assert last["next_action"]["reason"] == "attempts_exhausted"
    assert last["next_action"]["missing_fields"] == ["allergy_status"]
    done = api.finish().json()
    statuses = {s["field"]: s for s in done["field_statuses"]}
    assert statuses["allergy_status"]["status"] == "MISSING"
    assert statuses["allergy_status"]["not_elicited"] is True
    assert "allergy_status" in done["missing_fields"]
    assert all(f["field"] != "allergy_status" for f in done["facts"])
    for item in done["evidence"]:  # i2: facts live in the VoiceIntakeFacts item
        assert all(f["field"] != "allergy_status" for f in item.get("facts", []))


DURATIONS = {
    "digits": ("เป็นมา 3 วันแล้ว", "P3D"),
    "thai_digits": ("เป็นมา ๓ วัน", "P3D"),
    "number_words": ("สามวันแล้วค่ะ", "P3D"),
    "compound_words": ("สิบห้าวัน", "P15D"),
    "yesterday": ("ตั้งแต่เมื่อวาน", "P1D"),
    "day_before_yesterday": ("ตั้งแต่เมื่อวานซืน", "P2D"),
    "weeks": ("สองสัปดาห์", "P2W"),
    "week_colloquial": ("อาทิตย์นึงแล้ว", "P1W"),
    "hours": ("ห้าชั่วโมง", "PT5H"),
    "hours_digits": ("ประมาณ 1 ชั่วโมง", "PT1H"),
    "months": ("หกเดือน", "P6M"),
}


@pytest.mark.parametrize("case", list(DURATIONS))
def test_thai_duration_normalization(case):
    text, iso = DURATIONS[case]
    facts = _facts(text, asked="onset_duration")
    assert facts["onset_duration"]["value"] == iso
    assert facts["onset_duration"]["value_text"] in text


def test_thai_number_words():
    assert [thai_number(w) for w in ("หนึ่ง", "นึง", "สิบ", "สิบเอ็ด", "ยี่สิบ", "ยี่สิบห้า", "สามสิบ", "๗")] == [
        1, 1, 10, 11, 20, 25, 30, 7,
    ]


def test_correction_supersedes(client, login, app):
    login("nurse1")
    api = VoiceAPI(client, app)
    api.start()
    api.turn("ปวดหัวค่ะ")
    first = api.turn("เป็นตั้งแต่เมื่อวานค่ะ").json()["new_facts"]
    assert [(f["field"], f["value"]) for f in first] == [("onset_duration", "P1D")]
    second = api.turn("เมื่อวาน เอ้ย สองวันแล้วค่ะ").json()["new_facts"]
    dur = [f for f in second if f["field"] == "onset_duration"]
    assert len(dur) == 1 and dur[0]["value"] == "P2D"
    assert dur[0]["supersedes_fact_id"] == first[0]["fact_id"]
    # The earlier version is kept and still readable.
    with app.state.engine.connect() as conn:
        rows = conn.execute(select(voice_facts).where(voice_facts.c.field == "onset_duration")).mappings().all()
    assert {r["fact_id"] for r in rows} == {first[0]["fact_id"], dur[0]["fact_id"]}
    old = api.facts(as_of=first[0]["available_at_time"]).json()["facts"]
    assert [f["value"] for f in old if f["field"] == "onset_duration"] == ["P1D"]
    assert [f["value"] for f in api.facts().json()["facts"] if f["field"] == "onset_duration"] == ["P2D"]
