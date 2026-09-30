"""V2A-A04 (classifier part): nurse-question intent classifier on the SPEC section 7 phrases."""

import ast

import pytest

from app.voice import intent_th
from app.voice.intent_th import classify, classify_turn

from ..conftest import REPO_ROOT

QUESTIONS = {  # SPEC 7, plus ASR-style variants (no particle / "?")
    "chief_complaint": ["มาด้วยอาการอะไรคะ", "วันนี้เป็นอะไรมาคะ", "ไม่สบายตรงไหนคะ", "มีอาการอะไรบ้างคะ",
                        "มาด้วยอาการอะไร?"],
    "onset_duration": ["เป็นมากี่วันแล้วคะ", "เริ่มเป็นตั้งแต่เมื่อไหร่คะ", "เป็นมาสามวันแล้วใช่ไหมคะ", "เป็นมากี่วันแล้ว?"],
    "severity": ["ปวดกี่คะแนนคะ", "ถ้าเต็มสิบให้เท่าไหร่คะ", "เจ็บมากไหมคะ", "ปวดกี่คะแนน"],
    "allergy_status": ["แพ้ยาอะไรไหมคะ", "มีประวัติแพ้ยาไหมคะ", "ไม่แพ้ยาใช่ไหมคะ", "แพ้ยาอะไรไหม",
                       "เคยมีอาการผิดปกติหลังใช้ยาไหมคะ"],
    "current_medications": ["ทานยาอะไรประจำไหมคะ", "ตอนนี้กินยาอะไรอยู่บ้างคะ", "ใช้ยาอะไรอยู่ไหม", "กินยาอะไรอยู่?"],
    "relevant_history": ["มีโรคประจำตัวไหมคะ", "เคยป่วยเป็นโรคอะไรมาก่อนไหมคะ", "ไม่มีโรคประจำตัวใช่ไหมคะ",
                         "มีโรคประจำตัวไหม"],
}
LEADING = ["เป็นมาสามวันแล้วใช่ไหมคะ", "ไม่แพ้ยาใช่ไหมคะ", "ไม่มีโรคประจำตัวใช่ไหมคะ"]
ANSWERS = [
    "ไม่แพ้ยาอะไรค่ะ", "ไม่ได้แพ้อะไรเลยครับ", "จำไม่ได้ว่าแพ้ยาอะไร",
    "อันนี้จำไม่ได้ค่ะ ไม่แน่ใจว่าแม่เคยแพ้ยาอะไรหรือเปล่า", "ไม่ได้กินยาอะไรเลยค่ะ", "เป็นมาสามวันแล้วค่ะ",
    "ปวดประมาณเจ็ดคะแนนค่ะ", "มาด้วยอาการไข้ค่ะ", "ไม่มีโรคประจำตัวค่ะ", "กินยาความดันประจำค่ะ",
    "เรื่องนี้ไม่ขอตอบครับ",
    # extra dev answers
    "เจ็บคอ ไอด้วยค่ะ เป็นมาสองวันแล้ว ไม่แพ้ยาอะไรนะคะ", "ไม่มีค่ะ", "เบาหวานค่ะ", "ปฏิเสธแพ้ยาค่ะ",
]
# SPEC rev 2 SP-2: a final บ้าง with no wh-word and no "?" is the quantifier "some/sometimes": an answer.
BANG_ANSWERS = ["ไอบ้างค่ะ", "ไข้ขึ้นบ้างลงบ้างค่ะ", "มีน้ำมูกบ้างค่ะ", "ปวดหัวบ้างครับ", "เป็นเบาหวานกับความดันบ้างค่ะ"]


@pytest.mark.parametrize(("field", "text"), [(f, t) for f, ts in QUESTIONS.items() for t in ts])
def test_question_classified_with_field(field, text):
    assert classify(text) == field
    assert classify_turn(text).remainder == ""  # a pure question: nothing left to extract


def test_every_field_has_three_phrasings_incl_leading_and_asr_variant():
    for field, texts in QUESTIONS.items():
        assert len(texts) >= 3
        assert any(t.endswith("?") or not t.endswith(("คะ", "ค่ะ", "ครับ")) for t in texts), field
    assert {classify(t) for t in LEADING} == {"onset_duration", "allergy_status", "relevant_history"}


@pytest.mark.parametrize("text", ANSWERS + BANG_ANSWERS)
def test_answers_are_not_questions(text):
    assert classify_turn(text) is None  # question:false


@pytest.mark.parametrize(("text", "field"), [
    ("ไอบ้างคะ?", None), ("มีอาการอะไรบ้างคะ", "chief_complaint"), ("ตอนนี้กินยาอะไรอยู่บ้างคะ", "current_medications"),
    ("ไปไหนมาบ้างคะ", None), ("เป็นมากี่วันบ้างคะ", "onset_duration"),
])
def test_bang_is_a_question_after_wh_word_or_before_question_mark(text, field):
    c = classify_turn(text)
    assert c is not None and (c.field, c.remainder) == (field, "")


@pytest.mark.parametrize(("text", "field", "remainder"), [
    ("แพ้ยาอะไรไหมคะ ไม่แพ้ค่ะ", "allergy_status", "ไม่แพ้ค่ะ"),
    ("แพ้ยาอะไรไหมคะไม่แพ้ค่ะ", "allergy_status", "ไม่แพ้ค่ะ"),  # ASR joined without a space
    ("เป็นมากี่วันแล้วคะ สองวันค่ะ", "onset_duration", "สองวันค่ะ"),
    ("มีโรคประจำตัวไหมคะ ค่ะ", "relevant_history", ""),  # only a particle after it: a pure question
])
def test_merged_segment(text, field, remainder):
    c = classify_turn(text)
    assert (c.field, c.remainder) == (field, remainder)


# Symptom / history screening questions with no field intent (reviewer HIGH, dev-only phrasings).
SCREENING = ["มีไข้ไหมคะ", "ไอไหมคะ", "เจ็บหน้าอกไหมคะ", "ปวดท้องด้วยไหมคะ", "มีอาการเจ็บหน้าอกไหมคะ",
             "เจ็บหน้าอก ไหมคะ", "หายใจเหนื่อยหรือเปล่าคะ", "เป็นเบาหวานไหมคะ", "ความดันสูงไหมคะ",
             "ขอไปเข้าห้องน้ำก่อนได้ไหมครับ", "ไอบ้างไหมคะ"]


@pytest.mark.parametrize("text", SCREENING)
def test_fieldless_question_is_removed(text):
    c = classify_turn(text)
    assert (c.field, c.remainder, c.window) == (None, "", None)  # a question; resets the window


@pytest.mark.parametrize(("text", "field", "remainder", "after", "window"), [
    # an answer before the next question (ASR joined the segments): kept for extraction, never dropped
    ("แพ้เพนิซิลลินค่ะ ทานยาอะไรประจำไหมคะ", "current_medications", "แพ้เพนิซิลลินค่ะ", False, None),
    ("อ๋อ จริงๆเคยแพ้ยาซัลฟาค่ะ ทานยาอะไรประจำไหมคะ", "current_medications", "อ๋อ จริงๆเคยแพ้ยาซัลฟาค่ะ", False, None),
    ("ปวดหัวมากค่ะ เป็นมากี่วันแล้วคะ", "onset_duration", "ปวดหัวมากค่ะ", False, None),
    # a patient question after a disclosure
    ("อ้อ แพ้เพนิซิลลินด้วย จะเป็นอะไรไหมคะ", "chief_complaint", "อ้อ แพ้เพนิซิลลินด้วย", False, None),
    # text on both sides of the question
    ("ไม่แพ้ค่ะ ทานยาอะไรไหมคะ ไม่ได้ทานค่ะ", "current_medications", "ไม่แพ้ค่ะ ไม่ได้ทานค่ะ", True, "current_medications"),
    # text after a field-less question belongs to no field (SPEC B2)
    ("มีไข้ไหมคะ ไม่มีค่ะ", None, "ไม่มีค่ะ", True, None),
    # the window after the turn follows its last question clause, field-less included
    ("แพ้ยาอะไรไหมคะ มีไข้ไหมคะ", "allergy_status", "", False, None),
])
def test_answer_around_question_is_kept(text, field, remainder, after, window):
    c = classify_turn(text)
    assert (c.field, c.remainder, c.answer_after, c.answer_field) == (field, remainder, after, window)


def test_last_intent_wins():
    # medication intent ends before the allergy intent: the question is about allergy
    assert classify("กินยาแล้วแพ้ไหมคะ") == "allergy_status"


def test_stdlib_only():
    tree = ast.parse((REPO_ROOT / "backend" / "app" / "voice" / "intent_th.py").read_text(encoding="utf-8"))
    mods = {n.module if isinstance(n, ast.ImportFrom) else a.name
            for n in ast.walk(tree) if isinstance(n, (ast.Import, ast.ImportFrom))
            for a in (n.names if isinstance(n, ast.Import) else [n])}
    assert mods <= {"__future__", "re", "dataclasses", "mock_rules"}, mods
    assert intent_th.QUESTION_FORM.pattern


@pytest.mark.parametrize(("text", "window"), [
    ("แพ้ยาอะไรไหมคะ มีไข้ไหมคะ", None), ("มีไข้ไหมคะ แพ้ยาอะไรไหมคะ", "allergy_status"),
    ("มีโรคประจำตัวไหมคะ เบาหวานค่ะ", "relevant_history"),
])
def test_window_after_turn_is_the_last_question_clause(text, window):
    assert classify_turn(text).window == window
