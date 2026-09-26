"""Rule-based Thai intake extraction for the offline mock provider (stdlib ``re`` only).

Registered as the mock handler for ``voice.intake_extract``. A pure, deterministic function of the
request inputs: ``{"turns": [{turn_id, speaker, text, ended_at}, ...], "last_asked_field": str|None}``.
It extracts only from the latest non-agent turn and cites only that turn.

MOCK — not clinical. Symptom codes are categories, not diagnoses. Medication and allergen names are
kept exactly as said (no mapping, no dose inference).
"""

from __future__ import annotations

import re
from typing import Any

EXTRACTOR_VERSION = "voice-mock-rules-0.1.0"

# ---------------------------------------------------------------- numbers
_DIGITS = {"ศูนย์": 0, "หนึ่ง": 1, "นึง": 1, "เอ็ด": 1, "สอง": 2, "สาม": 3, "สี่": 4, "ห้า": 5,
           "หก": 6, "เจ็ด": 7, "แปด": 8, "เก้า": 9}
_UNIT_WORD = "หนึ่ง|นึง|สอง|สาม|สี่|ห้า|หก|เจ็ด|แปด|เก้า"
NUM_WORD = rf"(?:(?:{_UNIT_WORD}|ยี่)?สิบ(?:เอ็ด|{_UNIT_WORD})?|{_UNIT_WORD}|ศูนย์)"
NUM = rf"(?:[0-9๐-๙]{{1,3}}|{NUM_WORD})"
_THAI_DIGITS = str.maketrans("๐๑๒๓๔๕๖๗๘๙", "0123456789")


def thai_number(token: str) -> int | None:
    """Parse arabic/Thai digits or Thai number words up to 99."""
    token = token.strip()
    if not token:
        return None
    if token.translate(_THAI_DIGITS).isdigit():
        return int(token.translate(_THAI_DIGITS))
    m = re.fullmatch(rf"(?:({_UNIT_WORD}|ยี่)?(สิบ))?(เอ็ด|{_UNIT_WORD}|ศูนย์)?", token)
    if not m or not token:
        return None
    tens_word, sib, unit_word = m.groups()
    total = 0
    if sib:
        total += 20 if tens_word == "ยี่" else 10 * (_DIGITS.get(tens_word, 1) if tens_word else 1)
    if unit_word:
        total += _DIGITS[unit_word]
    return total


# ---------------------------------------------------------------- vocabularies
CC_PATTERNS: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("chest_pain", ("เจ็บหน้าอก", "แน่นหน้าอก", "ปวดหน้าอก")),
    ("dyspnea", ("หายใจไม่ออก", "หายใจลำบาก", "หอบเหนื่อย", "เหนื่อยหอบ")),
    ("fever", ("มีไข้", "ไข้", "ตัวร้อน")),
    ("cough", ("ไอ",)),
    ("sore_throat", ("เจ็บคอ",)),
    ("runny_nose", ("น้ำมูก", "คัดจมูก")),
    ("headache", ("ปวดหัว", "ปวดศีรษะ")),
    ("dizziness", ("เวียนหัว", "เวียนศีรษะ", "วิงเวียน", "มึนหัว", "บ้านหมุน")),
    ("abdominal_pain", ("ปวดท้อง", "เจ็บท้อง", "จุกท้อง")),
    ("diarrhea", ("ท้องเสีย", "ถ่ายเหลว")),
    ("nausea_vomiting", ("อาเจียน", "คลื่นไส้", "อ้วก")),
    ("rash", ("ผื่น", "ลมพิษ")),
    ("back_pain", ("ปวดหลัง", "ปวดเอว")),
    ("joint_pain", ("ปวดเข่า", "ปวดข้อ", "ข้อบวม")),
    ("dysuria", ("ฉี่แสบ", "ปัสสาวะแสบ", "ปัสสาวะขัด", "ฉี่ขัด")),
    ("fatigue", ("อ่อนเพลีย", "อ่อนแรง", "เพลีย")),
)

DRUG_LEXICON: tuple[str, ...] = (
    "พาราเซตามอล", "พารา", "ไอบูโพรเฟน", "แอสไพริน", "เพนิซิลลิน", "เพนนิซิลิน", "อะม็อกซีซิลลิน",
    "อะม็อกซี่", "ซัลฟา", "เมทฟอร์มิน", "อินซูลิน", "วาร์ฟาริน", "โลซาร์แทน", "แอมโลดิปีน",
    "ซิมวาสแตติน", "โอเมพราโซล", "วิตามิน",
)
DRUG_DESCRIPTOR = re.compile(
    r"ยา(?:แก้[ก-๙]+|ลด[ก-๙]+|ความดัน|เบาหวาน|ไทรอยด์|หัวใจ|ไขมัน|นอนหลับ|คุมกำเนิด|พ่น|ฆ่าเชื้อ|"
    r"ปฏิชีวนะ|ละลายลิ่มเลือด|กันเลือดแข็ง)[ก-๙]*"
)
CONDITION_LEXICON: tuple[str, ...] = (
    "เบาหวาน", "ความดันโลหิตสูง", "ความดันสูง", "ความดัน", "ไขมันในเลือดสูง", "ไขมันสูง", "ไขมัน",
    "หอบหืด", "โรคหัวใจ", "หัวใจ", "ไทรอยด์", "โรคไต", "ไตวาย", "ข้อเข่าเสื่อม", "ข้อเสื่อม", "เกาต์",
    "เก๊าท์", "มะเร็ง", "หลอดเลือดสมอง", "อัมพฤกษ์", "ภูมิแพ้", "ไมเกรน", "โรคกระเพาะ", "ตับอักเสบ",
    "ไวรัสตับอักเสบ", "ลมชัก", "ซึมเศร้า",
)
SURGERY = re.compile(r"ผ่าตัด[ก-๙]+")
ENGLISH_WORD = re.compile(r"[A-Za-z][A-Za-z\-]{2,}")
_PARTICLES = re.compile(r"(?:ค่ะ|คะ|ครับ|คับ|นะ|จ้ะ|จ้า|ด้วย|เลย|แล้ว|อยู่|ตอนนี้|ประจำ)+$")

UNKNOWN_PHRASES = re.compile(r"จำไม่ได้|ไม่แน่ใจ|ไม่ทราบ|ไม่รู้")
REFUSED_PHRASES = re.compile(r"ไม่ขอตอบ|ขอไม่ตอบ|ไม่อยากบอก|ไม่อยากตอบ|ไม่สะดวกตอบ|ขอไม่บอก")
CORRECTION = re.compile(r"ไม่ใช่|เอ้ย|เอ๊ย|เอ๊ะ|ขอโทษ|นับผิด|แก้เป็น")
BARE_NONE = re.compile(r"^(?:ไม่มี|ไม่เคย|ไม่แพ้|ปฏิเสธ|ไม่ได้ใช้|ไม่ได้กิน|ไม่ได้ทาน)")

DURATION_UNITS: tuple[tuple[str, str, str], ...] = (
    ("นาที", "PT", "M"), ("ชั่วโมง", "PT", "H"), ("ชม.", "PT", "H"), ("วัน", "P", "D"),
    ("สัปดาห์", "P", "W"), ("อาทิตย์", "P", "W"), ("เดือน", "P", "M"), ("ปี", "P", "Y"),
)
_UNIT_ALT = "|".join(re.escape(u) for u, _, _ in DURATION_UNITS)
DURATION_NUM_UNIT = re.compile(rf"({NUM})\s*({_UNIT_ALT})")
DURATION_UNIT_ONE = re.compile(rf"({_UNIT_ALT})(?:นึง|หนึ่ง)")
DURATION_RELATIVE = (("เมื่อวานซืน", "P2D"), ("เมื่อวาน", "P1D"))

SEVERITY_OUT_OF_10 = re.compile(rf"({NUM})\s*(?:เต็ม\s*(?:10|สิบ)|คะแนน|/\s*10)")
SEVERITY_BARE_NUM = re.compile(rf"({NUM})(?!\s*(?:{_UNIT_ALT}|[0-9]))")
SEVERITY_CATEGORIES: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("mild", re.compile(r"นิดหน่อย|เล็กน้อย|ไม่มาก|ไม่ค่อย(?:มาก|ปวด|เจ็บ|รุนแรง)|ไม่ค่อยเท่าไ")),
    ("moderate", re.compile(r"ปานกลาง|พอทน")),
    ("severe", re.compile(r"ทนไม่ไหว|รุนแรง|หนักมาก|มาก|หนัก")),
)


# ---------------------------------------------------------------- helpers
def _fact(field: str, state: str, value: Any, value_text: str, turn_id: str) -> dict[str, Any]:
    return {"field": field, "state": state, "value": value, "value_text": value_text, "span_turn_ids": [turn_id]}


def _lexicon_items(text: str, lexicon: tuple[str, ...], extra: tuple[re.Pattern[str], ...] = ()) -> list[str]:
    """Longest-first, non-overlapping surface matches, returned in text order."""
    spans: list[tuple[int, int, str]] = []
    taken = [False] * len(text)

    def claim(start: int, end: int, item: str) -> None:
        if not any(taken[start:end]):
            for i in range(start, end):
                taken[i] = True
            spans.append((start, end, item))

    for pat in extra:
        for m in pat.finditer(text):
            item = _PARTICLES.sub("", m.group(0))
            if len(item) > 2:
                claim(m.start(), m.start() + len(item), item)
    for term in sorted(lexicon, key=len, reverse=True):
        for m in re.finditer(re.escape(term), text):
            claim(m.start(), m.end(), term)
    return [item for _, _, item in sorted(spans)]


def _english_items(text: str) -> list[tuple[int, str]]:
    return [(m.start(), m.group(0)) for m in ENGLISH_WORD.finditer(text)]


def _merge_items(text: str, thai_items: list[str], english: list[tuple[int, str]]) -> list[str]:
    positioned = [(text.find(i), i) for i in thai_items] + english
    out: list[str] = []
    for _, item in sorted(positioned):
        if item.casefold() not in {o.casefold() for o in out}:
            out.append(item)
    return out


# ---------------------------------------------------------------- field rules
def _chief_complaint(text: str, tid: str, asked: str | None) -> list[dict]:
    if asked not in (None, "chief_complaint"):
        return []
    best: tuple[int, str, str] | None = None
    for code, phrases in CC_PATTERNS:
        for p in phrases:
            idx = text.find(p)
            if idx >= 0 and (best is None or idx < best[0] or (idx == best[0] and len(p) > len(best[2]))):
                best = (idx, code, p)
    return [_fact("chief_complaint", "KNOWN", best[1], best[2], tid)] if best else []


def _duration(text: str, tid: str, asked: str | None) -> list[dict]:
    has_symptom = any(p in text for _, ps in CC_PATTERNS for p in ps)
    if asked not in (None, "chief_complaint", "onset_duration") and not CORRECTION.search(text) and not has_symptom:
        return []
    found: list[tuple[int, str, str]] = []  # (position, iso, surface)
    for m in DURATION_NUM_UNIT.finditer(text):
        n = thai_number(m.group(1))
        unit = next(u for u in DURATION_UNITS if u[0] == m.group(2))
        if n is not None and n > 0:
            found.append((m.start(), f"{unit[1]}{n}{unit[2]}", m.group(0)))
    for m in DURATION_UNIT_ONE.finditer(text):
        unit = next(u for u in DURATION_UNITS if u[0] == m.group(1))
        found.append((m.start(), f"{unit[1]}1{unit[2]}", m.group(0)))
    for phrase, iso in DURATION_RELATIVE:  # longest phrase first; เมื่อวานซืน contains เมื่อวาน
        if (idx := text.find(phrase)) >= 0:
            found.append((idx, iso, phrase))
            break
    if not found:
        return []
    _, iso, surface = max(found)  # last mention wins (in-turn correction)
    return [_fact("onset_duration", "KNOWN", iso, surface, tid)]


def _severity(text: str, tid: str, asked: str | None) -> list[dict]:
    m = SEVERITY_OUT_OF_10.search(text)
    if m and (n := thai_number(m.group(1))) is not None and 0 <= n <= 10:
        return [_fact("severity", "KNOWN", n, m.group(0), tid)]
    if asked != "severity":
        return []
    for m in SEVERITY_BARE_NUM.finditer(text):
        n = thai_number(m.group(1))
        if n is not None and 0 <= n <= 10:
            return [_fact("severity", "KNOWN", n, m.group(1), tid)]
    for category, pat in SEVERITY_CATEGORIES:
        if cm := pat.search(text):
            return [_fact("severity", "KNOWN", category, cm.group(0), tid)]
    return []


ALLERGY_NONE = re.compile(
    r"ปฏิเสธ(?:การ|ประวัติ)?แพ้ยา|ไม่(?:เคย)?แพ้ยา|ไม่มี(?:ประวัติ)?(?:การ)?แพ้ยา|ไม่แพ้อะไร|ไม่เคยแพ้อะไร"
)
ALLERGY_ANY = re.compile(r"(?:เคย)?แพ้ยา")


def _allergy(text: str, tid: str, asked: str | None) -> list[dict]:
    if "แพ้" not in text and asked != "allergy_status":
        return []
    # Allergens: drug names / English words said after an affirmative "แพ้" (not after "ไม่แพ้").
    allergens: list[str] = []
    for m in re.finditer(r"(?<!ไม่)(?<!ไม่เคย)(?<!ปฏิเสธ)(?<!ปฏิเสธการ)แพ้", text):
        tail = re.split(r"แต่|ส่วน", text[m.end():])[0]
        thai = _lexicon_items(tail, DRUG_LEXICON, (DRUG_DESCRIPTOR,))
        english = _english_items(tail)
        for item in _merge_items(tail, thai, english):
            if item.casefold() not in {a.casefold() for a in allergens}:
                allergens.append(item)
    if allergens:
        surface = next(m.group(0) for m in re.finditer(r"แพ้(?:ยา)?", text))
        return [_fact("allergy_status", "KNOWN", "present", surface, tid),
                _fact("allergens", "KNOWN", allergens, allergens[0], tid)]
    if um := UNKNOWN_PHRASES.search(text):
        return [_fact("allergy_status", "UNKNOWN", None, um.group(0), tid)]
    if rm := REFUSED_PHRASES.search(text):
        return [_fact("allergy_status", "REFUSED", None, rm.group(0), tid)]
    if nm := ALLERGY_NONE.search(text):
        return [_fact("allergy_status", "KNOWN", "none", nm.group(0), tid)]
    if asked == "allergy_status" and (bm := BARE_NONE.search(text.strip())):
        return [_fact("allergy_status", "KNOWN", "none", bm.group(0), tid)]
    if am := ALLERGY_ANY.search(text):
        if not re.search(r"(?:ไม่|ปฏิเสธ)(?:เคย|การ)?" + re.escape(am.group(0)), text):
            return [_fact("allergy_status", "KNOWN", "present", am.group(0), tid)]
    return []


MEDS_NONE = re.compile(r"ไม่ได้(?:กิน|ใช้|ทาน)ยา|ไม่(?:กิน|ใช้|ทาน)ยา|ไม่มียา")


def _medications(text: str, tid: str, asked: str | None) -> list[dict]:
    if asked != "current_medications" and (not re.search(r"(?:กิน|ใช้|ทาน)ยา", text) or "แพ้" in text):
        return []
    if nm := MEDS_NONE.search(text):
        return [_fact("current_medications", "KNOWN", [], nm.group(0), tid)]
    items = _merge_items(text, _lexicon_items(text, DRUG_LEXICON, (DRUG_DESCRIPTOR,)), _english_items(text))
    if items:
        return [_fact("current_medications", "KNOWN", items, items[0], tid)]
    if asked == "current_medications" and (bm := BARE_NONE.search(text.strip())):
        return [_fact("current_medications", "KNOWN", [], bm.group(0), tid)]
    return []


HISTORY_NONE = re.compile(r"ไม่มีโรคประจำตัว|ไม่มีโรค|แข็งแรงดี|ไม่เคยป่วย")


def _history(text: str, tid: str, asked: str | None) -> list[dict]:
    if asked != "relevant_history" and not re.search(r"โรคประจำตัว|เป็นโรค", text):
        return []
    items = _lexicon_items(text, CONDITION_LEXICON, (SURGERY,))
    if items:
        return [_fact("relevant_history", "KNOWN", items, items[0], tid)]
    if nm := HISTORY_NONE.search(text):
        return [_fact("relevant_history", "KNOWN", [], nm.group(0), tid)]
    if asked == "relevant_history" and (bm := BARE_NONE.search(text.strip())):
        return [_fact("relevant_history", "KNOWN", [], bm.group(0), tid)]
    return []


def _uncertain_answer(text: str, tid: str, asked: str | None, produced: set[str]) -> list[dict]:
    """"I can't remember" / "I'd rather not say" in reply to the field just asked."""
    if asked is None or asked in produced or asked == "allergy_status":
        return []
    if um := UNKNOWN_PHRASES.search(text):
        return [_fact(asked, "UNKNOWN", None, um.group(0), tid)]
    if rm := REFUSED_PHRASES.search(text):
        return [_fact(asked, "REFUSED", None, rm.group(0), tid)]
    return []


def extract(inputs: dict[str, Any]) -> dict[str, Any]:
    """Mock handler for ``voice.intake_extract``."""
    turns = [t for t in inputs.get("turns", []) if t.get("speaker") != "agent"]
    asked = inputs.get("last_asked_field")
    if not turns:
        return {"extractor": EXTRACTOR_VERSION, "facts": []}
    target = turns[-1]
    text, tid = str(target["text"]), str(target["turn_id"])
    facts: list[dict] = []
    for rule in (_chief_complaint, _duration, _severity, _allergy, _medications, _history):
        facts += rule(text, tid, asked)
    facts += _uncertain_answer(text, tid, asked, {f["field"] for f in facts})
    return {"extractor": EXTRACTOR_VERSION, "facts": facts}
