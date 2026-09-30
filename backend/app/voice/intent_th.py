"""Deterministic Thai nurse-question intent classifier (slice v2a, stdlib ``re`` only, no model).

Ambient intake has one phone mic and no diarization, so a nurse's question and a patient's answer both
arrive as ``speaker:"unknown"``. A clause is a nurse question for field F iff it ends in a question form
AND matches a field-intent pattern for F. A question form governed by a patient non-answer
("ไม่แน่ใจว่า...หรือเปล่า") or by a leading negation ("ไม่แพ้ยาอะไรค่ะ") is never a question, except a
confirmation tag ("ไม่แพ้ยาใช่ไหมคะ"), which is a leading question.

MOCK-grade rules for a research prototype. A missed question leaves the answer window unset (the field stays
MISSING and the nurse is prompted again); a false question yields no facts. Neither fabricates a negative.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from .mock_rules import REFUSED_PHRASES, UNKNOWN_PHRASES

_POLITE = r"(?:ค่ะ|คะ|ครับ|คับ|จ๊ะ|จ้ะ|จ้า|นะ|น่ะ)"
_QTAIL = r"(?:มา|แล้ว|อยู่|ด้วย|เนี่ย)"  # "เป็นอะไรมาคะ", "เป็นมากี่วันแล้วคะ"
_CONFIRM = r"(?:ใช่ไหม|ใช่มั้ย|ใช่หรือเปล่า|ใช่รึเปล่า|ใช่หรือไม่)"
_QP = (
    rf"(?:{_CONFIRM}|หรือเปล่า|รึเปล่า|หรือไม่|หรือยัง|ไหม(?!้)|มั้ย|ไม๊|บ้าง|เท่าไหร่|เท่าไร|อะไร|ไหน|"
    r"เมื่อไหร่|เมื่อไร|กี่[ก-๙]+?)"
)
QUESTION_FORM = re.compile(rf"({_QP}){_QTAIL}*\s*{_POLITE}*\s*[?？]?\s*$")
_CONFIRM_RE = re.compile(_CONFIRM)
# A clause boundary without a space: "แพ้ยาอะไรไหมคะไม่แพ้ค่ะ" -> "แพ้ยาอะไรไหมคะ" | "ไม่แพ้ค่ะ".
_GLUED_END = re.compile(rf"{_QP}{_QTAIL}*(?:ค่ะ|คะ|ครับ|คับ)+(?=[ก-๙A-Za-z0-9])")
_CLAUSE = re.compile(r"[^\s?？]+(?:\s*[?？])?|[?？]")
_LEADING_NEG = re.compile(r"^(?:แล้ว|ก็|อ๋อ|อ้อ|อืม|คือ)*(?:ไม่(?!สบาย)|ปฏิเสธ)")
_PARTICLES_ONLY = re.compile(rf"^(?:{_POLITE}|[\s?？.,!ๆ])*$")

_DURATION_UNIT = r"(?:นาที|ชั่วโมง|ชม\.|วัน|สัปดาห์|อาทิตย์|เดือน|ปี)"
INTENTS: dict[str, re.Pattern[str]] = {
    "chief_complaint": re.compile(
        r"อาการอะไร|เป็นอะไร|ไม่สบาย(?:ตรงไหน|อะไร|ยังไง)|(?:เจ็บ|ปวด)ตรงไหน|มาด้วย(?:อาการ|เรื่อง)"
        r"|มา(?:หาหมอ|โรงพยาบาล|วันนี้)(?:ด้วย)?(?:เรื่อง|เพราะ)"
    ),
    "onset_duration": re.compile(
        rf"กี่{_DURATION_UNIT}|นาน(?:เท่าไ|แค่ไหน|ไหม|หรือยัง)|ตั้งแต่(?:เมื่อไ|ตอนไหน|วันไหน)"
        rf"|เริ่ม(?:เป็น|มีอาการ|ปวด|เจ็บ)?(?:ตั้งแต่)?(?:เมื่อไ|วันไหน|ตอนไหน)"
        rf"|(?:[0-9๐-๙]+|[ก-๙]*(?:หนึ่ง|นึง|สอง|สาม|สี่|ห้า|หก|เจ็ด|แปด|เก้า|สิบ))\s*{_DURATION_UNIT}"
    ),
    "severity": re.compile(
        r"คะแนน|เต็ม\s*(?:สิบ|10)|0\s*ถึง\s*10|ศูนย์ถึงสิบ|ให้(?:สัก)?เท่าไ|รุนแรง|มากน้อย|อาการหนัก"
        r"|(?<!นาน)(?:แค่ไหน|ขนาดไหน)|(?:ปวด|เจ็บ|แน่น|คัน|เวียนหัว|ไอ|แสบ|ไข้สูง|หนัก|เป็น)มาก(?=ไหม|มั้ย)"
    ),
    # Adverse-reaction wording is an allergy question ("เคยมีอาการผิดปกติหลังใช้ยาไหมคะ"); it ends where the
    # medication intent "ใช้ยา" ends, and a tie goes to the field earlier in this dict.
    "allergy_status": re.compile(r"แพ้|(?:อาการ(?:ผิดปกติ|ข้างเคียง)|ผื่น)(?:หลัง|จาก|เวลา)(?:ใช้|กิน|ทาน)ยา"),
    "current_medications": re.compile(r"(?:กิน|ทาน|ใช้|รับประทาน)ยา|ยา(?:ประจำ|อะไรอยู่|ตัวไหน)|ยาที่(?:กิน|ทาน|ใช้)"),
    "relevant_history": re.compile(
        r"โรคประจำตัว|โรคอะไร|เป็นโรค|โรคเรื้อรัง|เคย(?:ป่วย|เจ็บป่วย|ผ่าตัด|นอนโรงพยาบาล)"
        r"|ประวัติ(?:การ)?(?:ป่วย|เจ็บป่วย|ผ่าตัด)"
    ),
}


@dataclass(frozen=True)
class Classified:
    field: str
    remainder: str  # text after the question clause ("" for a pure question turn)


def _clauses(text: str) -> list[tuple[int, int]]:
    """(start, end) spans of whitespace/``?``-separated clauses, split again after a glued question end."""
    spans: list[tuple[int, int]] = []
    for m in _CLAUSE.finditer(text):
        start = m.start()
        for g in _GLUED_END.finditer(text, m.start(), m.end()):
            spans.append((start, g.end()))
            start = g.end()
        if start < m.end():
            spans.append((start, m.end()))
    return spans


def _question_field(clause: str) -> str | None:
    q = QUESTION_FORM.search(clause)
    if q is None:
        return None
    head = clause[: q.start(1)]
    if UNKNOWN_PHRASES.search(head) or REFUSED_PHRASES.search(head):
        return None  # "ไม่แน่ใจว่าแม่เคยแพ้ยาอะไรหรือเปล่า", "จำไม่ได้ว่าแพ้ยาอะไร"
    if _LEADING_NEG.search(clause) and not _CONFIRM_RE.match(q.group(1)):
        return None  # "ไม่แพ้ยาอะไรค่ะ" is an answer; "ไม่แพ้ยาใช่ไหมคะ" is a leading question
    best: tuple[int, str] | None = None
    for field, pat in INTENTS.items():
        for m in pat.finditer(clause):
            if best is None or m.end() > best[0]:  # the intent ending last wins
                best = (m.end(), field)
    return best[1] if best else None


def classify_turn(text: str) -> Classified | None:
    """The last question clause of the turn and the text after it (a merged question + answer segment)."""
    found: Classified | None = None
    for start, end in _clauses(text):
        field = _question_field(text[start:end])
        if field is not None:
            rest = text[end:].strip()
            found = Classified(field, "" if _PARTICLES_ONLY.match(rest) else rest)
    return found


def classify(text: str) -> str | None:
    """Field F if the turn is (or contains) a nurse question for F, else None."""
    c = classify_turn(text)
    return c.field if c else None
