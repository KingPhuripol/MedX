"""Seeded phrase generator and differential harness for the s5r3 dose grammar (spec §F).

Standard library only. Phrases are synthetic unit-test inputs and belong to no evaluation split.
The harness takes any ``text -> (dose_status, dose_value, dose_unit, quantity, reason)`` callable, so the same
check can be run on an older parser (e.g. ``git show 1c1f476:backend/app/pharma/mock_rules.py``):

    from tests.pharma_dose_fuzz import generate, harness, entry_tuple
    report = harness(entry_tuple(old_module.parse_entry), generate())
"""

from __future__ import annotations

import collections
import random
from collections.abc import Callable
from dataclasses import dataclass, field
from fractions import Fraction

from .pharma_dose_reference import reference_closure, reference_parse

SEED = 5303
N_PHRASES = 4000
Parsed = tuple[str, float | None, str | None, float | None, str | None]


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


# Valid tails, including T1 time phrases that are not directly after "INT เม็ด" (quantity unaffected).
TAILS = [Segment(""), Segment("prn"), Segment("pc"), Segment("po"), Segment("หลังอาหารเช้า"), Segment("หลังอาหาร"),
         Segment("ก่อนอาหารครึ่งชั่วโมง", ("T1",)), Segment("ก่อนอาหาร ครึ่ง ชม.", ("T1",)),
         Segment("ก่อนอาหารครึ่ง hr", ("T1",))]

# Adversarial classes: (slot, choices). Each phrase with an adversarial segment has exactly one.
# A choice is a text, or (text, productions) when the segment is also an instance of a production.
ADVERSARIAL: dict[str, tuple[str, list]] = {
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
    # rev 2: "ครึ่ง" + time word. Quantity slot = directly after "INT เม็ด" (conflict: ambiguous_quantity);
    # tail slot = elsewhere (a time only).
    "th_half_time": ("quantity|tail", [
        ("quantity", "1 เม็ดครึ่งชั่วโมง"), ("quantity", "1 เม็ด ครึ่ง ชม."), ("quantity", "2เม็ดครึ่งนาที"),
        ("quantity", "1 แคปซูล ครึ่งชม"), ("quantity", "ครั้งละ 1 เม็ดครึ่งชั่วโมง"), ("quantity", "วันละ 1 เม็ด ครึ่ง ช.ม."),
        ("quantity", "1เม็ด ครึ่ง hr"), ("quantity", "1 เม็ดครึ่ง minutes"),
        ("tail", "ครึ่ง ชม. ก่อนอาหาร"), ("tail", "หลังอาหาร ครึ่งนาที"), ("tail", "ครึ่งชม ก่อนนอน"),
        ("tail", "ก่อนอาหาร ครึ่ง hour"),
    ]),
    # rev 2: UNIT or QW + / ⁄ per ต่อ + a unit of time, weight or dose (R1), plus L1 look-alikes (liquid_volume).
    "per_unit": ("strength|quantity", [
        ("strength", "1000 mg/day"), ("strength", "5 mg/kg"), ("strength", "5mg / kg"), ("strength", "500 mg per day"),
        ("strength", "1000 มก./วัน"), ("strength", "1000 มก.ต่อวัน"), ("strength", "1000 มก. ต่อ วัน"),
        ("strength", "100 units/ml"), ("strength", "2 mg⁄kg"), ("strength", "10 mcg / dose"), ("strength", "1 g/d"),
        ("strength", "500 มก./ครั้ง"), ("strength", "5 มก/กก."), ("strength", "500-1000 mg/day"),
        ("quantity", "2 tabs/day"), ("quantity", "2 เม็ด/วัน"), ("quantity", "1 tab per dose"),
        ("quantity", "1 เม็ด ต่อ ครั้ง"), ("quantity", "½ tab/day"), ("quantity", "1 cap / d"), ("quantity", "2 เม็ดต่อวัน"),
        ("strength", ("250 mg/5 ml", ("L1",))), ("strength", ("50 mcg/ml", ("L1",))),
        ("strength", ("120 มก./5 มล.", ("L1",))), ("strength", ("125 mg / 5 ml 5 ml", ("L1",))),
    ]),
    # rev 2: Q3 / Q4b / Q5 totals in (10, 40] break the QV bound (unparsed_token, never 30.5).
    "qv_over": ("quantity", ["30 1/2 tabs", "11 1/2 tab", "10 1/2 tab", "15 ½ tab", "39 3/4 tabs", "12 เม็ดครึ่ง",
                             "20เม็ดครึ่ง", "11 เม็ด ครึ่ง", "12x2", "15 x 1", "10.5x2", "11 3/4 เม็ด", "40 1/2 tabs"]),
}

# ---- rev 3 classes (s5r3 §F). Written with \uXXXX escapes: no invisible character is stored literally.
# INVISIBLE code points: every listed category (Cc Cf Co Cs Cn) and every explicit range.
INVISIBLE_POINTS = ["\u0007", "\u007f", "\u200b", "\u200c", "\u200d", "\u2060", "\ufeff", "\u00ad", "\u2066",
                    "\u180e", "\U000e0041", "\ue000", "\ud800", "\u0378", "\u0e3b", "\u034f", "\u115f", "\u1160",
                    "\u17b4", "\u180b", "\u180f", "\u2800", "\u3164", "\ufe0f", "\uffa0", "\U000e0100"]
_TW = ["ชั่วโมง", "ชม.", "นาที", "ชม", " hr", " minutes"]
# SLASH-LIKE code points (a fixed list of more than 12, including the ASCII "/").
SLASH_POINTS = ["/", "\\", "\u2044", "\u2215", "\u2216", "\uff0f", "\uff3c", "\u29f8", "\ufe68", "\u29f9", "\u2afd",
                "\u2e4a", "\ua718", "\u0338", "\U0001f67c", "\u2298"]
_SLASH_CONTEXTS = [("strength", "1000 mg{}day"), ("strength", "5 มก. {} กก."), ("quantity", "2 tabs{}day"),  # anchor tail
                   ("quantity", "1{}2 tab"), ("quantity", "1 1{}2 เม็ด"),  # fraction
                   ("tail", "ก่อนอาหาร{}หลังอาหาร"), ("pre", "HCTZ{}plus")]  # between two words
_DOTTED = ["mg.", "mcg.", "g.", "ml."]
_DOTTED_QW = ["tab.", "tabs.", "cap."]
_DOTTED_TAILS = ["/day", "\uff0fday", "\\kg", "\u2215d", " per day", "per dose", " ต่อวัน", "ต่อ กก.", " a day", " aweek",
                 " a month", " (per day)", "| day", "* bid", '" bid', "' bid", "# od", "= day", "_bid", "\u0e48 bid"]
_DOTTED_CONTROLS = [("strength", ("500 mg. bid", ("S1",))), ("strength", ("20 mcg. od", ("S1",))),
                    ("quantity", ("1 tab. od", ("Q1",))), ("quantity", ("2 caps. bid", ("Q1",))),
                    ("dose", ("500 mg (1 tab) bid", ("S1", "Q1"))), ("dose", ("3 mg; 1 tab, od", ("S1", "Q1")))]
# D1 markers: TH (joined and spaced, before and after the strength), "วันละ S1", EN words; controls that resolve.
_D1_AFTER = ["แบ่งวันละ 2 ครั้ง", "แบ่ง วันละ 2 ครั้ง", "แบ่งให้วันละ 2 ครั้ง", "รวมวันละ 2 ครั้ง", "รวม วันละ 3 ครั้ง",
             "ทั้งหมดต่อวัน", "ทั้งหมด ต่อ วัน", "ทั้งวัน", "หลังอาหาร ต่อวัน", "ต่อ สัปดาห์", "ต่ออาทิตย์", "ต่อ เดือน",
             "ต่อ กก.", "ต่อกิโล", "divided bid", "in 2 divided doses", "divide tid", "split bid", "Split BID", "2 doses",
             "DIVIDED q12h", "total"]
_D1_BEFORE = ["รวม", "ทั้งหมด", "แบ่ง", "total", "Total", "ทั้ง วัน"]
_D1_STRENGTH = ["วันละ 1000 มก.", "วันละ1000มก.", "วันละ 500 mg", "วันละ  250 มิลลิกรัม"]
_D1_CONTROLS = [("frequency", ("วันละ 2 ครั้ง", ("F3",))), ("frequency", ("วันละครั้ง", ("F3",))),
                ("quantity", ("ครั้งละ 1 เม็ด", ("Q6",))), ("tail", "กินต่อ วันละ 1 ครั้ง"), ("tail", "ต่อ วันละ 1 ครั้ง")]
# Q4b + QF item (must resolve), and Q4b + anything else (ambiguous_quantity or a higher reason).
_Q4B = ["1 เม็ดครึ่ง", "2เม็ดครึ่ง", "1 แคปซูลครึ่ง", "1 เม็ด ครึ่ง", "3เม็ด ครึ่ง"]
_QF_OK = ["", "ครึ่งชั่วโมงก่อนอาหาร", "ครึ่ง ชม.", "q8h", "ทุก 6 ชั่วโมง", "twice daily", "2 times a day", "วันละ 2 ครั้ง",
          "ก่อนนอน", "หลังอาหาร", "พร้อมอาหาร", "เช้า", "กลางวัน", "เที่ยง", "เย็น", "ค่ำ", "ตอนเช้า", "เวลาปวด", "เมื่อปวด",
          "od", "bd", "bid", "tid", "qid", "qd", "hs", "prn", "po", "ac", "pc", "daily", "once daily", "thrice daily",
          "every 8 hours", "before meals", "after food", "with food", "สัปดาห์ละ 1 ครั้ง"]
_QF_BAD = ["ชัวโมง", "ช.ม ก่อนอาหาร", "mn ac", "(ก่อนอาหาร)", ", วันละ 1 ครั้ง", "30 นาทีก่อนอาหาร", "\u200bชั่วโมง",
           "\uff0fวัน", "\u2060หลังอาหาร", "ยา", "foo", "x2", "tablet", "นาน 5 วัน", "1", "ชั่วโมงก่อนอาหาร", "hr", "min",
           "q", "[od]"]


def _rev3_classes() -> dict[str, tuple[str, list]]:
    inv = [("insert", c) for c in INVISIBLE_POINTS]
    inv += [("quantity", f"{q}{c}{tw}") for c in INVISIBLE_POINTS for q, tw in (("1 เม็ดครึ่ง", _TW[0]), ("2เม็ดครึ่ง", _TW[2]))]
    slash = [(slot, text.format(c)) for c in SLASH_POINTS for slot, text in _SLASH_CONTEXTS]
    dotted = [("strength", f"1000 {_DOTTED[k % len(_DOTTED)]}{t}") for k, t in enumerate(_DOTTED_TAILS)]
    dotted += [("quantity", f"2 {_DOTTED_QW[k % len(_DOTTED_QW)]}{t}") for k, t in enumerate(_DOTTED_TAILS)]
    dotted += _DOTTED_CONTROLS * 2
    daily = ([("tail", (m, ("D1",))) for m in _D1_AFTER] + [("pre", (m, ("D1",))) for m in _D1_BEFORE]
             + [("dose", (m, ("D1", "S1"))) for m in _D1_STRENGTH] + _D1_CONTROLS)
    q4b = [("last", (_Q4B[k % len(_Q4B)] + sep + f, ("Q4",))) for k, f in enumerate(_QF_OK) for sep in ("", " ")]
    q4b += [("last", _Q4B[k % len(_Q4B)] + sep + f) for k, f in enumerate(_QF_BAD) for sep in ("", " ")]
    classes = {"invisible": inv, "slash_like": slash, "dotted_tail": dotted, "daily_total": daily, "q4b_follower": q4b}
    for choices in classes.values():  # fixed order, mixed so every prefix of the cycle holds good and bad forms
        random.Random(SEED).shuffle(choices)
    return {cls: ("*", choices) for cls, choices in classes.items()}


REV3_CLASSES = _rev3_classes()
ADVERSARIAL.update(REV3_CLASSES)
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
    # Round-robin over the classes; each rev-3 class has 4 turns per round, so its whole choice list is cycled.
    classes = list(ADVERSARIAL) + [c for c in REV3_CLASSES for _ in range(3)]
    turns: collections.Counter = collections.Counter()
    out: list[Phrase] = []
    for k in range(n):
        lang = rng.choice(["en", "th"])
        name = rng.choice(NAMES[lang if rng.random() < 0.8 else ("th" if lang == "en" else "en")])
        slots = {"pre": Segment(""), "strength": strength(rng, lang), "quantity": quantity(rng, lang),
                 "frequency": frequency(rng, lang), "tail": rng.choice(TAILS)}
        insert = None
        if k % 2:  # every other phrase carries one adversarial segment (round-robin over the classes)
            cls = classes[(k // 2) % len(classes)]
            slot, choices = ADVERSARIAL[cls]
            if cls in REV3_CLASSES:  # cycle, so every rev-3 sub-form is generated
                choice = choices[turns[cls] % len(choices)]
                turns[cls] += 1
            else:
                choice = rng.choice(choices)
            if "|" in slot or slot == "*":  # per-choice slot
                slot, choice = choice
            text, pids = choice if isinstance(choice, tuple) else (choice, ())
            if cls in ("th_half_time", "per_unit") and not pids:
                pids = ("T1",) if cls == "th_half_time" else ("R1",)
            if slot == "last":  # the segment ends the entry; it carries the only quantity
                slots["quantity"], slot = Segment(""), "tail"
            elif slot == "dose":  # the segment carries the strength and the only quantity
                slots["quantity"], slot = Segment(""), "strength"
            if slot == "insert":
                insert = Segment(text, pids, adversarial=cls)
            else:
                slots[slot] = Segment(text, pids, adversarial=cls, lang=("th" if any("\u0e00" <= c <= "\u0e7f" for c in text)
                                                                           else "en") if slot == "quantity" else None)
        text = name
        for seg in slots.values():
            text = _join(rng, text, seg.text)
        if insert is not None:  # one character at a random position
            at = rng.randrange(len(text) + 1)
            text = text[:at] + insert.text + text[at:]
        segs = list(slots.values()) + ([insert] if insert else [])
        phrase = Phrase(text, [p for s in segs for p in s.productions], [s.adversarial for s in segs if s.adversarial])
        q = slots["quantity"]
        phrase.quantity_lang = q.lang if q.text else None
        if (not phrase.adversarial and q.quantity is not None and not slots["pre"].text
                and slots["strength"].productions in ((), ("S1",), ("S2",))):
            phrase.single_quantity = q.quantity
        out.append(phrase)
    return out


def entry_tuple(parse_entry: Callable[[str], dict]) -> Callable[[str], Parsed]:
    """Adapt a ``parse_entry``-shaped function to the harness tuple."""

    def parse(text: str) -> Parsed:
        e = parse_entry(text)
        return e["dose_status"], e["dose_value"], e["dose_unit"], e["quantity"], e.get("dose_unverifiable_reason")

    return parse


@dataclass
class Report:
    safety: list[str] = field(default_factory=list)  # resolved, but the reference disagrees
    status: list[str] = field(default_factory=list)  # dose_status or reason differs from the reference
    reference: list[str] = field(default_factory=list)  # reference differs from the generator's built value
    over_ten: list[str] = field(default_factory=list)  # resolved with a quantity > 10 (QV bound)
    closure: list[str] = field(default_factory=list)  # §F.5: resolved despite INVISIBLE / SLASH-LIKE / D1
    closure_counts: collections.Counter = field(default_factory=collections.Counter)  # phrases per closure trigger
    safety_classes: collections.Counter = field(default_factory=collections.Counter)  # class/production -> misreads


def harness(parse: Callable[[str], Parsed], phrases: list[Phrase]) -> Report:
    report = Report()
    for ph in phrases:
        ref = reference_parse(ph.text)
        got = tuple(parse(ph.text))
        line = f"{ph.text!r}: implementation={got} reference={ref} built={ph.productions}+{ph.adversarial}"
        if got[0] == "resolved" and (ref[0] != "resolved" or got[1:4] != ref[1:4]):
            report.safety.append(line)
            report.safety_classes.update({*ph.productions, *ph.adversarial})
        if (got[0], got[4]) != (ref[0], ref[4]):
            report.status.append(line)
        if got[0] == "resolved" and got[3] is not None and got[3] > 10:
            report.over_ten.append(line)
        triggers = [k for k, hit in reference_closure(ph.text).items() if hit]
        report.closure_counts.update(triggers)
        if got[0] == "resolved" and triggers:
            report.closure.append(line + f" closure={triggers}")
        if ph.single_quantity is not None and (ref[0] == "unverifiable" or ref[3] != float(ph.single_quantity)):
            report.reference.append(line + f" expected quantity {float(ph.single_quantity)}")
    return report
