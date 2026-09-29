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

EXTRACTOR_VERSION = "voice-mock-rules-0.3.0"

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

# Non-answers ("I have no information", "never been tested/noticed") are UNKNOWN, never a negative.
UNKNOWN_PHRASES = re.compile(
    r"จำไม่ได้|จำไม่ค่อยได้|ไม่ค่อยแน่ใจ|ไม่แน่ใจ|ไม่ทราบ|ไม่รู้|ไม่มีข้อมูล|ไม่(?:เคย|ได้)ตรวจ|ไม่(?:เคย|ได้)สังเกต"
    r"|ถ้าจำไม่ผิด|เท่าที่จำได้|เท่าที่ทราบ|เท่าที่รู้"
)
REFUSED_PHRASES = re.compile(r"ไม่ขอตอบ|ขอไม่ตอบ|ไม่อยากบอก|ไม่อยากตอบ|ไม่สะดวกตอบ|ขอไม่บอก")
CORRECTION = re.compile(r"ไม่ใช่|เอ้ย|เอ๊ย|เอ๊ะ|ขอโทษ|นับผิด|แก้เป็น")
# Hedges and questions: a negative said this way is not a KNOWN negative.
HEDGE = re.compile(r"มั้ง|มั๊ง|น่าจะ|คิดว่า|อาจจะ|เหมือนจะ")
_END_PARTICLES = r"(?:ค่ะ|คะ|ครับ|คับ|จ๊ะ|จ้ะ|จ้า|นะ|น่ะ)*"
QUESTION = re.compile(
    rf"(?:ใช่ไหม|ใช่มั้ย|ไหม(?!้)|มั้ย|ไม๊|หรือเปล่า|รึเปล่า|หรือไม่|เหรอ|หรอ|หรือ)\s*{_END_PARTICLES}\s*[?？]?\s*$|[?？]"
)
_BARE_HEAD = r"^(?:น่าจะ|คิดว่า|อาจจะ)?\s*"  # a hedged short denial is matched here, then made UNKNOWN
_BARE_TAIL = rf"(?:มั้ง|มั๊ง)?\s*{_END_PARTICLES}\s*$"
# Whole-utterance short denials only, per field. "ไม่แพ้" never answers medications or history.
BARE_NONE = {
    "allergy_status": re.compile(rf"{_BARE_HEAD}(?:ไม่มี|ไม่เคย|ไม่(?:ได้|เคย)*แพ้|ปฏิเสธ){_BARE_TAIL}"),
    "current_medications": re.compile(rf"{_BARE_HEAD}(?:ไม่มี|ไม่ได้ใช้|ไม่ได้กิน|ไม่ได้ทาน|ไม่ใช้|ไม่กิน|ไม่ทาน){_BARE_TAIL}"),
    "relevant_history": re.compile(rf"{_BARE_HEAD}(?:ไม่มี|ไม่เคย|ปฏิเสธ){_BARE_TAIL}"),
}

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
class _Ctx:
    """Per-turn context shared by the field rules."""

    def __init__(self, text: str, tid: str, asked: str | None) -> None:
        self.text, self.tid, self.asked = text, tid, asked
        self.hedge = HEDGE.search(text)
        self.question = QUESTION.search(text)
        self.uncertain = UNKNOWN_PHRASES.search(text)
        self.refused = REFUSED_PHRASES.search(text)

    @property
    def negative_ok(self) -> bool:
        """A KNOWN negative needs a plain statement: no hedge, question, non-answer or refusal."""
        return not (self.hedge or self.question or self.uncertain or self.refused)

    def negative(self, field: str, empty: Any, surface: str) -> list[dict]:
        """KNOWN negative when stated plainly; UNKNOWN when hedged or asked back; otherwise no fact."""
        if self.negative_ok:
            return [_fact(field, "KNOWN", empty, surface, self.tid)]
        marker = self.hedge or self.question
        if marker and marker.group(0).strip():
            return [_fact(field, "UNKNOWN", None, marker.group(0).strip(), self.tid)]
        return []

    def bare_none(self, field: str) -> re.Match[str] | None:
        return BARE_NONE[field].search(self.text.strip()) if self.asked == field else None


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


# ---- allergy
# Any negated "แพ้" (used to decide the fallback when the utterance is not a plain denial). The infix list
# covers hedges and adverbs ("ไม่น่าจะแพ้", "ไม่คิดว่าแพ้", "ไม่ค่อยแพ้", "ไม่เห็นแพ้"): these are negations,
# never an affirmed allergy.
_NEG_INFIX = (
    r"(?:ได้|เคย|มี|การ|ประวัติ|น่าจะ|น่า|คิดว่า|ค่อย|เห็น|ถึงกับ|ถึง|ใช่ว่า|แน่ใจว่า|รู้ว่า|ทราบว่า|จำได้ว่า|ยาที่)"
)
_NEGATED_BEFORE = re.compile(rf"(?:ไม่|ปฏิเสธ)(?:\s*{_NEG_INFIX})*\s*$")
ALLERGY_DENIAL = re.compile(rf"(?:ไม่|ปฏิเสธ)(?:\s*{_NEG_INFIX})*\s*แพ้(?:ยา)?")
# "not allergic to any drug except X" / "not allergic to other drugs": an allergy exists, so never "none".
ALLERGY_EXCEPT = re.compile(r"นอกจาก|ยกเว้น|เว้นแต่")
ALLERGY_OTHER = re.compile(r"(?:ไม่|ปฏิเสธ)(?:ได้|เคย)*แพ้(?:ยา)?(?:ตัว|ชนิด|อย่าง)?อื่น")
_CLAUSE_END = re.compile(r"แต่(?!ยา)|ส่วน|ไม่")

# ---- plain denials: a KNOWN negative is recorded only when every whitespace-separated chunk of the
# utterance is a recognised plain denial or a neutral chunk (see _neutral_chunk). Anything else said in the
# same turn (drug name, reaction, memory qualifier, third-party subject, hedge) makes the negative UNKNOWN.
_DENIAL_TAIL = r"(?:อะไร|ใดๆ|ทุกชนิด|ทุกตัว|สักตัว|ทั้งนั้น|ทั้งสิ้น|แน่นอน|เลย)*"
PLAIN_DENIAL: dict[str, re.Pattern[str]] = {
    "allergy_status": re.compile(
        r"(?:ปฏิเสธ(?:การ|ประวัติ(?:การ)?)?แพ้ยา|ไม่(?:ได้|เคย)*แพ้(?:ยา|อะไร)|ไม่มี(?:ประวัติ)?(?:การ)?แพ้ยา"
        rf"|ไม่มียาที่แพ้){_DENIAL_TAIL}"
    ),
    "current_medications": re.compile(
        rf"(?:ไม่ได้|ไม่)(?:กิน|ใช้|ทาน)ยา{_DENIAL_TAIL}(?:ประจำ)?|ไม่มียา(?:ประจำ|ที่(?:กิน|ใช้|ทาน)(?:ประจำ)?)?{_DENIAL_TAIL}"
    ),
    "relevant_history": re.compile(
        rf"(?:ไม่มีโรคประจำตัว|ไม่มีโรค|ปฏิเสธโรคประจำตัว|ไม่เคยป่วย|ไม่เคยเป็นโรค|แข็งแรงดี){_DENIAL_TAIL}"
    ),
}
# Allergy-relevant words that must never sit next to a "none": reactions and third-party subjects.
REACTION = re.compile(r"ผื่น|ลมพิษ|บวม|คัน|หายใจไม่ออก|หายใจลำบาก|ตุ่ม|ผิวลอก|ช็อก|หน้ามืด")
_NON_DRUG_ALLERGEN = (
    r"(?:อาหารทะเล|กุ้ง|ปู|หอย|ปลา|ถั่วลิสง|ถั่ว|นมวัว|นม|ไข่|แป้งสาลี|ไรฝุ่น|ฝุ่น|ขนแมว|ขนหมา|ขนสัตว์|"
    r"เกสรดอกไม้|เกสร|อากาศ|แมลง|ผึ้ง)"
)
NON_DRUG_ALLERGY = re.compile(rf"(?:เคย)?แพ้{_NON_DRUG_ALLERGEN}(?:(?:กับ|และ|แล้วก็)?{_NON_DRUG_ALLERGEN})*")
_LEAD = re.compile(r"^(?:แต่|และ|แล้วก็|ส่วน)")
_FILLER = re.compile(r"เป็นมาได้|เป็นมา|มาได้|ประมาณ|ตั้งแต่|มีอาการ|รู้สึก|แล้วก็|อาการ|เป็น|มี|มา|กับ|และ|ก็")
_CC_PHRASES = tuple(sorted((p for _, ps in CC_PATTERNS for p in ps), key=len, reverse=True))
_CHUNK_SPLIT = re.compile(r"[\s,，]+")


def _chunks(text: str) -> list[str]:
    return [ch for ch in _CHUNK_SPLIT.split(text.strip()) if ch]


def _core(chunk: str) -> str:
    return _PARTICLES.sub("", chunk)


def _is_plain_denial(chunk: str) -> bool:
    return any(p.fullmatch(_core(chunk)) for p in PLAIN_DENIAL.values())


def _neutral_chunk(chunk: str) -> bool:
    """A chunk that says nothing about allergy, medicines or history: a symptom or duration, or a non-drug
    allergy ("แต่แพ้กุ้ง"). Anything mentioning ยา, a reaction or an English word is never neutral."""
    if "ยา" in chunk or REACTION.search(chunk) or ENGLISH_WORD.search(chunk):
        return False
    core = _LEAD.sub("", _core(chunk))
    if NON_DRUG_ALLERGY.fullmatch(core):
        return True
    rest = core
    for p in _CC_PHRASES:
        rest = rest.replace(p, "")
    rest = DURATION_UNIT_ONE.sub("", DURATION_NUM_UNIT.sub("", rest))
    for phrase, _ in DURATION_RELATIVE:
        rest = rest.replace(phrase, "")
    return _FILLER.sub("", rest) == ""


def _plain_negative(c: _Ctx, field: str) -> str | None:
    """Surface of a plain denial for ``field`` if the whole utterance is one, else None."""
    if bm := c.bare_none(field):
        return bm.group(0).strip()
    chunks = _chunks(c.text)

    def own(ch: str) -> bool:  # a plain denial of this field; a bare "ไม่มีค่ะ" only when this field was asked
        return bool(PLAIN_DENIAL[field].fullmatch(_core(ch)) or (c.asked == field and BARE_NONE[field].search(ch)))

    hit = next((ch for ch in chunks if own(ch)), None)
    if hit is None or not all(own(ch) or _is_plain_denial(ch) or _neutral_chunk(ch) for ch in chunks):
        return None
    return _core(hit)


def _drug_items(segment: str) -> list[str]:
    return _merge_items(segment, _lexicon_items(segment, DRUG_LEXICON, (DRUG_DESCRIPTOR,)), _english_items(segment))


def _split_negated(text: str, items: list[str], neg_before: re.Pattern[str]) -> tuple[list[str], list[str]]:
    """(affirmed, negated): an item is negated only if every mention sits right after a negation."""
    affirmed, negated = [], []
    for item in items:
        starts = [m.start() for m in re.finditer(re.escape(item), text)] or [text.find(item)]
        (negated if all(neg_before.search(text[:s]) for s in starts) else affirmed).append(item)
    return affirmed, negated


def _allergy(c: _Ctx) -> list[dict]:
    text, tid, asked = c.text, c.tid, c.asked
    if "แพ้" not in text and asked != "allergy_status":
        return []
    allergens: list[str] = []
    affirmed: re.Match[str] | None = None  # first un-negated "แพ้ยา"
    for m in re.finditer(r"แพ้", text):
        if _NEGATED_BEFORE.search(text[: m.start()]):
            continue
        tail = text[m.end():]
        tail = tail[3:] if tail.startswith("แต่") else tail  # "แพ้แต่ยาซัลฟา" = allergic only to sulfa
        tail = _CLAUSE_END.split(tail)[0]
        allergens += [i for i in _drug_items(tail) if i.casefold() not in {a.casefold() for a in allergens}]
        if affirmed is None and tail.startswith("ยา"):
            affirmed = m
    for m in ALLERGY_EXCEPT.finditer(text):  # "ไม่แพ้ยาอะไรนอกจากเพนิซิลลิน"
        if re.search(r"(?:ไม่|ปฏิเสธ)(?:ได้|เคย)*แพ้", text[: m.start()]):
            tail = _CLAUSE_END.split(text[m.end():])[0]
            allergens += [i for i in _drug_items(tail) if i.casefold() not in {a.casefold() for a in allergens}]
    if allergens:
        surface = next(m.group(0) for m in re.finditer(r"แพ้(?:ยา)?", text))
        return [_fact("allergy_status", "KNOWN", "present", surface, tid),
                _fact("allergens", "KNOWN", allergens, allergens[0], tid)]
    # An affirmed drug allergy with an unknown/refused agent is still KNOWN present.
    if affirmed and not c.question and not (c.uncertain and c.uncertain.start() < affirmed.start()):
        facts = [_fact("allergy_status", "KNOWN", "present", affirmed.group(0), tid)]
        if c.uncertain:
            facts.append(_fact("allergens", "UNKNOWN", None, c.uncertain.group(0), tid))
        elif c.refused:
            facts.append(_fact("allergens", "REFUSED", None, c.refused.group(0), tid))
        return facts
    if c.uncertain:
        return [_fact("allergy_status", "UNKNOWN", None, c.uncertain.group(0), tid)]
    if c.refused:
        return [_fact("allergy_status", "REFUSED", None, c.refused.group(0), tid)]
    if ALLERGY_EXCEPT.search(text) or ALLERGY_OTHER.search(text):
        return []  # implies some allergy exists but no agent was named here
    if surface := _plain_negative(c, "allergy_status"):
        return c.negative("allergy_status", "none", surface)
    # A denial qualified by anything else in the turn ("ไม่แพ้ยาเพนิซิลลิน", "แม่ไม่แพ้ยา",
    # "ไม่แพ้ยา ถ้าจำไม่ผิด", "ไม่น่าจะแพ้ยา") is UNKNOWN when answering the allergy question, never "none".
    if asked == "allergy_status" and (dm := ALLERGY_DENIAL.search(text)):
        return [_fact("allergy_status", "UNKNOWN", None, dm.group(0), tid)]
    return []


# ---- medications
MEDS_NONE = re.compile(r"ไม่ได้(?:กิน|ใช้|ทาน)ยา|ไม่(?:กิน|ใช้|ทาน)ยา|ไม่มียา(?!ที่แพ้)")
_NEG_DRUG_BEFORE = re.compile(
    r"(?:ไม่|ปฏิเสธ|เลิก|หยุด)(?:ได้|เคย|ค่อย|น่าจะ|มี)*(?:กิน|ใช้|ทาน|ฉีด|พ่น)?(?:ยา)?\s*$"
)


def _medications(c: _Ctx) -> list[dict]:
    text, tid, asked = c.text, c.tid, c.asked
    if asked != "current_medications" and (not re.search(r"(?:กิน|ใช้|ทาน)ยา", text) or "แพ้" in text):
        return []
    # A drug named in the turn is recorded; a denial next to it never empties the list.
    items, negated = _split_negated(text, _drug_items(text), _NEG_DRUG_BEFORE)
    if items:
        return [_fact("current_medications", "KNOWN", items, items[0], tid)]
    if surface := _plain_negative(c, "current_medications"):
        return c.negative("current_medications", [], surface)
    # "ไม่ได้กินยาความดันแล้ว" (stopped one drug) or a qualified denial: UNKNOWN, never "takes none".
    dm = MEDS_NONE.search(text)
    if asked == "current_medications" and (dm or negated):
        return [_fact("current_medications", "UNKNOWN", None, dm.group(0) if dm else negated[0], tid)]
    return []


# ---- history
HISTORY_NONE = re.compile(r"ไม่มีโรคประจำตัว|ไม่มีโรค|แข็งแรงดี|ไม่เคยป่วย|ไม่เคยเป็นโรค|ปฏิเสธโรคประจำตัว")
_NEG_COND_BEFORE = re.compile(r"(?:ไม่|ปฏิเสธ)(?:ได้|เคย|มี|เป็น|ป่วย|ประวัติ|โรค|ค่อย|น่าจะ)*\s*$")


def _history(c: _Ctx) -> list[dict]:
    text, tid, asked = c.text, c.tid, c.asked
    if asked != "relevant_history" and not re.search(r"โรคประจำตัว|เป็นโรค", text):
        return []
    items, negated = _split_negated(text, _lexicon_items(text, CONDITION_LEXICON, (SURGERY,)), _NEG_COND_BEFORE)
    if items:
        return [_fact("relevant_history", "KNOWN", items, items[0], tid)]
    if surface := _plain_negative(c, "relevant_history"):
        return c.negative("relevant_history", [], surface)
    dm = HISTORY_NONE.search(text)
    if asked == "relevant_history" and (dm or negated):
        return [_fact("relevant_history", "UNKNOWN", None, dm.group(0) if dm else negated[0], tid)]
    return []


def _uncertain_answer(c: _Ctx, produced: set[str]) -> list[dict]:
    """"I can't remember" / "I'd rather not say" in reply to the field just asked."""
    if c.asked is None or c.asked in produced or c.asked == "allergy_status":
        return []
    if c.uncertain:
        return [_fact(c.asked, "UNKNOWN", None, c.uncertain.group(0), c.tid)]
    if c.refused:
        return [_fact(c.asked, "REFUSED", None, c.refused.group(0), c.tid)]
    return []


def extract(inputs: dict[str, Any]) -> dict[str, Any]:
    """Mock handler for ``voice.intake_extract``."""
    turns = [t for t in inputs.get("turns", []) if t.get("speaker") != "agent"]
    asked = inputs.get("last_asked_field")
    if not turns:
        return {"extractor": EXTRACTOR_VERSION, "facts": []}
    target = turns[-1]
    text, tid = str(target["text"]), str(target["turn_id"])
    if target.get("speaker") == "nurse" and QUESTION.search(text):
        # A nurse's (possibly leading) question is not an answer: nothing is extracted from it.
        return {"extractor": EXTRACTOR_VERSION, "facts": []}
    facts: list[dict] = []
    for rule in (_chief_complaint, _duration, _severity):
        facts += rule(text, tid, asked)
    c = _Ctx(text, tid, asked)
    for field_rule in (_allergy, _medications, _history):
        facts += field_rule(c)
    facts += _uncertain_answer(c, {f["field"] for f in facts})
    return {"extractor": EXTRACTOR_VERSION, "facts": facts}
