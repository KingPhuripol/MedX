"""Regression tests for independent-review findings on S3-A02 (missing/uncertain never becomes a negative).

Every phrase here reproduced a false KNOWN negative (or a lost allergy) against commit 089cecc.
"""

import pytest

from app.gateway import build_provider
from app.config import Settings
from app.voice.mock_rules import extract
from app.voice.models import ExtractedFact
from app.voice.service import reconcile_allergy

from .helpers import StubProvider, VoiceAPI, ok


def _facts(text: str, asked: str | None, speaker: str = "patient") -> dict[str, dict]:
    out = extract({"turns": [{"turn_id": "u1", "speaker": speaker, "text": text}], "last_asked_field": asked})
    return {f["field"]: f for f in out["facts"]}


def _is_known_negative(fact: dict | None) -> bool:
    return bool(fact) and fact["state"] == "KNOWN" and fact["value"] in ("none", [])


# (a) hedges, (b) non-answers: never KNOWN none; the asked field becomes UNKNOWN.
HEDGED_OR_NON_ANSWER = {
    "hedge_none_i_think": "ไม่มีมั้งคะ",
    "hedge_probably_not": "น่าจะไม่แพ้ยานะ",
    "no_information": "ไม่มีข้อมูลค่ะ",
    "never_tested": "ไม่เคยตรวจค่ะ",
    "never_noticed": "ไม่เคยสังเกตค่ะ",
    "patient_asks_back": "ไม่แพ้ยาใช่ไหมคะ",
}


@pytest.mark.parametrize("case", list(HEDGED_OR_NON_ANSWER))
def test_allergy_hedge_or_non_answer_is_unknown(case):
    facts = _facts(HEDGED_OR_NON_ANSWER[case], "allergy_status")
    assert not _is_known_negative(facts.get("allergy_status"))
    assert facts["allergy_status"]["state"] == "UNKNOWN"


@pytest.mark.parametrize("field", ["current_medications", "relevant_history"])
@pytest.mark.parametrize("text", ["ไม่มีมั้งคะ", "น่าจะไม่มีค่ะ", "ไม่มีข้อมูลค่ะ", "ไม่เคยสังเกตค่ะ", "ไม่รู้ค่ะ", "ไม่มีใช่ไหม"])
def test_list_field_hedge_or_non_answer_is_not_negative(field, text):
    facts = _facts(text, field)
    assert not _is_known_negative(facts.get(field)), (field, text)


# (c) a nurse's leading question is not an answer.
@pytest.mark.parametrize("text", ["ไม่แพ้ยาใช่ไหมคะ", "ไม่ได้กินยาอะไรใช่มั้ยคะ", "ไม่มีโรคประจำตัวหรือเปล่าคะ", "แพ้ยาไหมคะ"])
def test_nurse_question_yields_no_facts(text):
    for asked in ("allergy_status", "current_medications", "relevant_history"):
        assert _facts(text, asked, speaker="nurse") == {}, (text, asked)


# (d) an answer about something else never fills a list field with "none".
CROSS_FIELD = [
    ("current_medications", "ไม่เคยไปหาหมอ"),
    ("current_medications", "ไม่แพ้ยาค่ะ"),
    ("relevant_history", "ไม่แพ้ยาค่ะ"),
    ("relevant_history", "ไม่ได้กินยาค่ะ"),
    ("current_medications", "ไม่มีโรคประจำตัว"),
    ("allergy_status", "ไม่เคยไปหาหมอ"),
]


@pytest.mark.parametrize("asked,text", CROSS_FIELD)
def test_cross_field_answer_is_not_a_false_none(asked, text):
    facts = _facts(text, asked)
    assert not _is_known_negative(facts.get(asked)), (asked, text)


def test_bare_denial_is_whole_utterance_only():
    assert _facts("ไม่มีค่ะ", "current_medications")["current_medications"]["value"] == []
    assert _facts("ไม่มีครับ", "relevant_history")["relevant_history"]["value"] == []
    assert _facts("ไม่แพ้ค่ะ", "allergy_status")["allergy_status"]["value"] == "none"
    assert "current_medications" not in _facts("ไม่เคยไปหาหมอเลยค่ะ", "current_medications")


# (e) affirmed allergy with unknown agent; "ไม่ได้แพ้ยา".
def test_affirmed_allergy_with_unknown_agent_stays_present():
    facts = _facts("แพ้ยาค่ะ จำไม่ได้ว่ายาอะไร", "allergy_status")
    assert (facts["allergy_status"]["state"], facts["allergy_status"]["value"]) == ("KNOWN", "present")
    assert facts["allergens"]["state"] == "UNKNOWN"


def test_uncertain_whether_allergic_stays_unknown():
    for text in ("จำไม่ได้ว่าแพ้ยาอะไร", "ไม่แน่ใจว่าเคยแพ้ยาไหม"):
        assert _facts(text, "allergy_status")["allergy_status"]["state"] == "UNKNOWN", text


def test_mai_dai_pae_ya_is_known_none():
    facts = _facts("ไม่ได้แพ้ยาค่ะ", "allergy_status")
    assert (facts["allergy_status"]["state"], facts["allergy_status"]["value"]) == ("KNOWN", "none")
    assert "allergens" not in facts


# Exception / "only" phrasing names an allergen: present, never none.
EXCEPTIONS = {
    "except_nok_jak": ("ไม่แพ้ยาอะไรนอกจากเพนิซิลลิน", ["เพนิซิลลิน"]),
    "except_yok_wen": ("ไม่แพ้ยาอะไร ยกเว้นเพนิซิลลิน", ["เพนิซิลลิน"]),
    "only_pae_tae": ("ไม่แพ้ยาตัวอื่น แพ้แต่ยาซัลฟา", ["ซัลฟา"]),
    "other_but": ("ไม่แพ้ยาอื่น แต่แพ้ซัลฟา", ["ซัลฟา"]),
    "present_then_not_other": ("แพ้เพนิซิลลิน ไม่แพ้พารา", ["เพนิซิลลิน"]),
}


@pytest.mark.parametrize("case", list(EXCEPTIONS))
def test_exception_phrasing_keeps_allergy(case):
    text, allergens = EXCEPTIONS[case]
    facts = _facts(text, "allergy_status")
    assert (facts["allergy_status"]["state"], facts["allergy_status"]["value"]) == ("KNOWN", "present")
    assert facts["allergens"]["value"] == allergens


def test_not_allergic_to_other_drugs_is_never_none():
    for asked in ("allergy_status", "current_medications"):
        facts = _facts("ไม่ได้กินยาอะไร ไม่แพ้ยาอื่นด้วย", asked)
        assert not _is_known_negative(facts.get("allergy_status")), asked


# ---- service guard (extractor-independent) ----


def test_cross_turn_none_cannot_replace_present(client, login, app):
    login("nurse1")
    api = VoiceAPI(client, app)
    api.start()
    api.turn("ปวดท้องค่ะ")
    api.turn("สองวันค่ะ")
    api.turn("ประมาณ 5 ค่ะ")
    api.turn("แพ้เพนิซิลลินค่ะ")
    body = api.turn("ไม่ได้กินยาอะไร ไม่แพ้ยาอื่นด้วย").json()
    assert not any(f["field"] == "allergy_status" for f in body["new_facts"])
    done = api.finish().json()
    latest = {f["field"]: f for f in done["facts"]}
    assert (latest["allergy_status"]["state"], latest["allergy_status"]["value"]) == ("KNOWN", "present")
    assert latest["allergens"]["value"] == ["เพนิซิลลิน"]


def _stub_emitting(facts_for_turn):
    def fn(req):
        tid = [t for t in req.inputs["turns"] if t["speaker"] != "agent"][-1]["turn_id"]
        return ok({"label": "x", "extractor": "stub-llm", "facts": facts_for_turn(tid)})
    return fn


def test_llm_downgrade_is_held_and_visible(client, login, app):
    """A (simulated) LLM extractor that emits 'none' after 'present' is held by the service, and flagged."""
    login("nurse1")
    api = VoiceAPI(client, app)
    api.start()
    app.state.provider = StubProvider(_stub_emitting(lambda tid: [
        {"field": "allergy_status", "state": "KNOWN", "value": "present", "value_text": "แพ้", "span_turn_ids": [tid]},
        {"field": "allergens", "state": "KNOWN", "value": ["เพนิซิลลิน"], "value_text": "เพนิซิลลิน",
         "span_turn_ids": [tid]},
    ]))
    api.turn("แพ้เพนิซิลลินค่ะ")
    app.state.provider = StubProvider(_stub_emitting(lambda tid: [
        {"field": "allergy_status", "state": "KNOWN", "value": "none", "value_text": "ไม่แพ้", "span_turn_ids": [tid]},
        {"field": "allergens", "state": "UNKNOWN", "value": None, "value_text": "ไม่แพ้", "span_turn_ids": [tid]},
    ]))
    body = api.turn("ไม่แพ้ยาอื่นค่ะ").json()
    app.state.provider = build_provider("mock", Settings())
    assert body["new_facts"] == []
    assert {h["field"] for h in body["held_facts"]} == {"allergy_status", "allergens"}
    assert body["allergy_conflict"] is True and body["session"]["allergy_conflict"] is True
    assert api.get().json()["session"]["allergy_conflict"] is True
    done = api.finish().json()
    latest = {f["field"]: f for f in done["facts"]}
    assert latest["allergy_status"]["value"] == "present"
    assert done["evidence"][-1]["payload"]["allergy_conflict"] is True


def test_named_allergens_imply_present_status():
    ef = ExtractedFact(field="allergens", state="KNOWN", value=["ซัลฟา"], value_text="ซัลฟา", span_turn_ids=["t1"])
    none = ExtractedFact(field="allergy_status", state="KNOWN", value="none", value_text="ไม่แพ้", span_turn_ids=["t1"])
    kept, held = reconcile_allergy([none, ef], {})
    status = [f for f in kept if f.field == "allergy_status"]
    assert [(f.state, f.value) for f in status] == [("KNOWN", "present")]
    assert [h["field"] for h in held] == ["allergy_status"]


def test_none_is_allowed_when_nothing_recorded():
    none = ExtractedFact(field="allergy_status", state="KNOWN", value="none", value_text="ไม่แพ้", span_turn_ids=["t1"])
    kept, held = reconcile_allergy([none], {})
    assert kept == [none] and held == []
