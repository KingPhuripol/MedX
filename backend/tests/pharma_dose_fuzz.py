"""Seeded phrase generator and differential harness for the s5r3 dose grammar (spec §F).

Standard library only. Phrases are synthetic unit-test inputs and belong to no evaluation split.
The harness takes any ``text -> (dose_status, dose_value, dose_unit, quantity)`` callable, so the same
check can be run on an older parser (e.g. ``git show 1c1f476:backend/app/pharma/mock_rules.py``):

    from tests.pharma_dose_fuzz import generate, harness, entry_tuple
    report = harness(entry_tuple(old_module.parse_entry), generate())
"""

from __future__ import annotations

import random
from collections.abc import Callable
from dataclasses import dataclass, field
from fractions import Fraction

from .pharma_dose_reference import reference_parse

SEED = 5303
N_PHRASES = 3000
Parsed = tuple[str, float | None, str | None, float | None]


@dataclass(frozen=True)
class Segment:
    text: str
    productions: tuple[str, ...] = ()
    adversarial: str | None = None
    quantity: Fraction | None = None  # value the generator built (valid quantity productions only)
    lang: str | None = None


@dataclass
class Phrase:
    text: str
    productions: list[str] = field(default_factory=list)
    adversarial: list[str] = field(default_factory=list)
    quantity_lang: str | None = None
    single_quantity: Fraction | None = None  # set when built from exactly one valid quantity production


def _fmt(v: Fraction) -> str:
    return str(v.numerator) if v.denominator == 1 else f"{float(v):g}"


NAMES = {"en": ["Warfarin", "Metformin", "Paracetamol", "Amlodipine", "Omeprazole"],
         "th": ["วาร์ฟาริน", "เมทฟอร์มิน", "พาราเซตามอล", "แอมโลดิปีน", "แอมลอดิปีน", "โอเมพราโซล"]}
STRENGTH_VALUES = ["1", "2.5", "3", "5", "20", "81", "250", "500", "1000"]
QV_VALUES = [Fraction(1), Fraction(2), Fraction(3), Fraction(1, 2), Fraction(3, 2), Fraction(5, 2), Fraction(10),
             Fraction(1, 4), Fraction(3, 4)]


def strength(rng: random.Random, lang: str) -> Segment:
    roll = rng.random()
    if roll < 0.08:
        return Segment(rng.choice(["875/125 mg", "50/12.5 mg", "500/125 มก."]), ("S2",))
    if roll < 0.16:
        return Segment(rng.choice(["3 mg + 1 mg", "3 mg and 2 mg", "500 มก. และ 250 มก.", "5 mg, 10 mg", "3mg&1mg"]),
                       ("S3",))
    if roll < 0.24:
        return Segment(rng.choice(["250 mg/5 ml 10 ml", "120 มก./5 มล. 5 มล.", "100 mg/ml", "250 mg / 5 ml"]), ("L1",))
    if roll < 0.29:
        return Segment("")
    v = rng.choice(STRENGTH_VALUES)
    units = ["{} mg", "{}mg", "{} mcg", "{} units"] if lang == "en" else ["{} มก.", "{}มก.", "{} มิลลิกรัม", "{} มก", "{}มก"]
    return Segment(rng.choice(units).format(v), ("S1",))


def quantity(rng: random.Random, lang: str) -> Segment:
    options = ["Q1", "Q2", "Q3", "Q5", "none"] if lang == "en" else ["Q1", "Q2", "Q3", "Q4", "Q5", "Q6", "Q7", "none"]
    pid = rng.choice(options)
    if pid == "none":
        return Segment("")
    if pid == "Q1":
        v = rng.choice(QV_VALUES)
        words = ["{} tab", "{} tabs", "{} tablets", "{} cap", "{}tabs"] if lang == "en" else ["{} เม็ด", "{}แคปซูล", "{}เม็ด"]
        return Segment(rng.choice(words).format(_fmt(v)), ("Q1",), quantity=v, lang=lang)
    if pid == "Q2":
        text, v = rng.choice([("1/2 tab", Fraction(1, 2)), ("3/4 tab", Fraction(3, 4)), ("1/4 tabs", Fraction(1, 4)),
                              ("¼ tab", Fraction(1, 4)), ("½ cap", Fraction(1, 2)), ("1 / 2 tab", Fraction(1, 2))]
                             if lang == "en" else
                             [("½ เม็ด", Fraction(1, 2)), ("1/2 เม็ด", Fraction(1, 2)), ("3/4แคปซูล", Fraction(3, 4))])
        return Segment(text, ("Q2",), quantity=v, lang=lang)
    if pid == "Q3":
        text, v = rng.choice([("1 1/2 tab", Fraction(3, 2)), ("1-1/2 tab", Fraction(3, 2)),
                              ("1 and 1/2 tabs", Fraction(3, 2)), ("2½ tab", Fraction(5, 2)),
                              ("2 ½ tabs", Fraction(5, 2)), ("1 - 1/4 tab", Fraction(5, 4)), ("3 3/4 tabs", Fraction(15, 4))]
                             if lang == "en" else
                             [("1และ1/2 เม็ด", Fraction(3, 2)), ("2 1/2 เม็ด", Fraction(5, 2)), ("1½ เม็ด", Fraction(3, 2))])
        return Segment(text, ("Q3",), quantity=v, lang=lang)
    if pid == "Q4":
        text, v = rng.choice([("ครึ่งเม็ด", Fraction(1, 2)), ("ครึ่ง แคปซูล", Fraction(1, 2)),
                              ("1 เม็ดครึ่ง", Fraction(3, 2)), ("2เม็ดครึ่ง", Fraction(5, 2))])
        return Segment(text, ("Q4",), quantity=v, lang=lang)
    if pid == "Q5":
        text, v = rng.choice([("2x2", Fraction(2)), ("1 x 3", Fraction(1)), ("½x1", Fraction(1, 2)),
                              ("1/2x2", Fraction(1, 2)), ("1.5x2", Fraction(3, 2)), ("1×1", Fraction(1)), ("3x4", Fraction(3))])
        return Segment(text, ("Q5",), quantity=v, lang=lang)
    if pid == "Q6":
        text, v = rng.choice([("ครั้งละ2เม็ด", Fraction(2)), ("ครั้งละ ครึ่งเม็ด", Fraction(1, 2)),
                              ("ครั้งละ 1 1/2 เม็ด", Fraction(3, 2)), ("ครั้งละ 1 เม็ดครึ่ง", Fraction(3, 2))])
        return Segment(text, ("Q6",), quantity=v, lang=lang)
    text, v = rng.choice([("วันละ 1 เม็ด", Fraction(1)), ("วันละครึ่งเม็ด", Fraction(1, 2)), ("วันละ ½ เม็ด", Fraction(1, 2))])
    return Segment(text, ("Q7",), quantity=v, lang=lang)


def frequency(rng: random.Random, lang: str) -> Segment:
    pid = rng.choice(["F1", "F2" if lang == "en" else "F3", "plain"])
    if pid == "F1":
        return Segment(rng.choice(["q6h", "q 8 h", "every 8 hours", "q4h", "q12hr", "every 6 h"] if lang == "en"
                                  else ["ทุก 6 ชั่วโมง", "ทุก 12 ชม.", "ทุก8ชั่วโมง"]), ("F1",))
    if pid == "F2":
        return Segment(rng.choice(["twice daily", "four times daily", "3 times a week", "once a day", "2 times per day",
                                   "thrice weekly", "one time daily"]), ("F2",))
    if pid == "F3":
        return Segment(rng.choice(["วันละ 3 ครั้ง", "วันละครั้ง", "สัปดาห์ละ 1 ครั้ง", "วันละ2ครั้ง", "เดือนละ 1 ครั้ง",
                                   "อาทิตย์ละครั้ง"]), ("F3",))
    return Segment(rng.choice(["od", "bid", "prn", "hs", "at bedtime"] if lang == "en" else ["เช้า-เย็น", "ก่อนนอน", "เวลาปวด"]))


TAILS = ["", "prn", "pc", "po", "หลังอาหารเช้า", "หลังอาหาร"]

# Adversarial classes: (slot, choices). Each phrase with an adversarial segment has exactly one.
ADVERSARIAL: dict[str, tuple[str, list[str]]] = {
    "range_hyphen": ("quantity", ["1-2 tabs", "1 - 2 เม็ด"]),
    "range_en_dash": ("quantity", ["1–2 tabs", "1 – 2 เม็ด"]),
    "range_em_dash": ("quantity", ["1—2 tab"]),
    "range_tilde": ("quantity", ["1~2 tabs", "1 ~ 2 เม็ด"]),
    "range_to": ("quantity", ["1 to 2 tabs"]),
    "range_or": ("quantity", ["1 or 2 tabs", "1 tab or 2 tabs"]),
    "range_and": ("quantity", ["1 and 2 tabs"]),
    "range_th_to": ("quantity", ["1 ถึง 2 เม็ด"]),
    "range_th_or": ("quantity", ["1 หรือ 2 เม็ด"]),
    "range_th_and": ("quantity", ["1 และ 2 เม็ด"]),
    "range_fraction": ("quantity", ["1/2-1 tab", "½-1 เม็ด"]),
    "range_strength": ("strength", ["500-1000 mg", "250 - 500 มก."]),
    "bare_number": ("quantity", ["2", "1"]),
    "trailing_digit": ("tail", ["1", "2"]),
    "dot_five": ("quantity", [".5 tab"]),
    "thousands": ("strength", ["1,000 mg", "1,500 มก."]),
    "zero": ("quantity", ["0 tab", "0"]),
    "large_count": ("quantity", ["12 tabs", "30 tabs", "12", "30"]),
    "decimal_1_3": ("quantity", ["1.3 tab"]),
    "fraction_3_2": ("quantity", ["3/2 tab"]),
    "fraction_1_0": ("quantity", ["1/0 tab"]),
    "fraction_2_3": ("quantity", ["2/3 tab"]),
    "fraction_third": ("quantity", ["⅓ tab"]),
    "thai_digit": ("quantity", ["๑ เม็ด", "๒ เม็ด"]),
    "en_number_word": ("quantity", ["one tab", "two tabs", "half tab"]),
    "th_number_word": ("quantity", ["สองเม็ด", "หนึ่ง เม็ด"]),
    "bare_qw": ("quantity", ["tab", "เม็ด", "tabs"]),
    "x_without_n": ("quantity", ["x2"]),
    "n_without_m": ("quantity", ["2x"]),
    "m_out_of_range": ("quantity", ["2x5", "1x6"]),
    "conflicting_quantity": ("quantity", ["2 tabs 1x2", "1 tab 2 tabs", "วันละ 2 เม็ด"]),
    "duplicated_quantity": ("quantity", ["1 tab 1x2", "2 tabs 2 tabs"]),  # equal values: stays resolved
    "frequency_range": ("frequency", ["q4-6h"]),
    "times_range": ("frequency", ["1-2 times daily"]),
    # Thai words that start with (or contain) an undotted unit: "มกราคม" = January, "มลพิษ" = pollution.
    "thai_unit_prefix": ("strength", ["เริ่ม 5 มกราคม", "5มกราคม", "10 มลพิษ", "ตั้งแต่ 3 มกรา"]),
    "variable_regimen": ("tail", ["except Sunday", "alternating", "ยกเว้นวันอาทิตย์", "on Mondays"]),
}
_NO_JOIN = set(".,/-–—~")


def _join(rng: random.Random, left: str, right: str) -> str:
    if not left or not right:
        return left + right
    joiner = rng.choice(["", " ", "  "])
    a, b = left[-1], right[0]
    merges = (a.isdigit() and b.isdigit()) or (a.isascii() and a.isalpha() and b.isascii() and b.isalpha())
    if joiner == "" and (merges or a in _NO_JOIN or b in _NO_JOIN or (a.isdigit() and b in "x×")):
        joiner = " "
    return left + joiner + right


def generate(seed: int = SEED, n: int = N_PHRASES) -> list[Phrase]:
    rng = random.Random(seed)
    classes = list(ADVERSARIAL)
    out: list[Phrase] = []
    for k in range(n):
        lang = rng.choice(["en", "th"])
        name = rng.choice(NAMES[lang if rng.random() < 0.8 else ("th" if lang == "en" else "en")])
        slots = {"strength": strength(rng, lang), "quantity": quantity(rng, lang),
                 "frequency": frequency(rng, lang), "tail": Segment(rng.choice(TAILS))}
        if k % 2:  # every other phrase carries one adversarial segment (round-robin over the classes)
            cls = classes[(k // 2) % len(classes)]
            slot, choices = ADVERSARIAL[cls]
            text = rng.choice(choices)
            slots[slot] = Segment(text, adversarial=cls, lang=("th" if any("฀" <= c <= "๿" for c in text)
                                                                 else "en") if slot == "quantity" else None)
        text = name
        for seg in slots.values():
            text = _join(rng, text, seg.text)
        segs = list(slots.values())
        phrase = Phrase(text, [p for s in segs for p in s.productions], [s.adversarial for s in segs if s.adversarial])
        q = slots["quantity"]
        phrase.quantity_lang = q.lang if q.text else None
        if (not phrase.adversarial and q.quantity is not None
                and slots["strength"].productions in ((), ("S1",), ("S2",))):
            phrase.single_quantity = q.quantity
        out.append(phrase)
    return out


def entry_tuple(parse_entry: Callable[[str], dict]) -> Callable[[str], Parsed]:
    """Adapt a ``parse_entry``-shaped function to the harness tuple."""

    def parse(text: str) -> Parsed:
        e = parse_entry(text)
        return e["dose_status"], e["dose_value"], e["dose_unit"], e["quantity"]

    return parse


@dataclass
class Report:
    safety: list[str] = field(default_factory=list)  # resolved, but the reference disagrees
    status: list[str] = field(default_factory=list)  # dose_status differs from the reference
    reference: list[str] = field(default_factory=list)  # reference differs from the generator's built value


def harness(parse: Callable[[str], Parsed], phrases: list[Phrase]) -> Report:
    report = Report()
    for ph in phrases:
        ref = reference_parse(ph.text)
        got = parse(ph.text)
        line = f"{ph.text!r}: implementation={got} reference={ref} built={ph.productions}+{ph.adversarial}"
        if got[0] == "resolved" and (ref[0] != "resolved" or tuple(got[1:]) != tuple(ref[1:])):
            report.safety.append(line)
        if got[0] != ref[0]:
            report.status.append(line)
        if ph.single_quantity is not None and (ref[0] == "unverifiable" or ref[3] != float(ph.single_quantity)):
            report.reference.append(line + f" expected quantity {float(ph.single_quantity)}")
    return report
