"""Deterministic rule-based mock for ``pharma.extract.v2`` and ``pharma.phrase.v1``.

Registered through the gateway MockProvider task-handler hook. No network, no randomness.
Fields that are not stated in the text stay ``None``; nothing is defaulted (a quantity is never
assumed to be 1).

Strength and quantity are read by one closed grammar (s5r3 §G1-§G2): the whole line is tokenised and
every numeric-ish token must be consumed by exactly one production in ``DOSE_GRAMMAR``. Anything the
grammar does not consume makes the dose ``unverifiable`` with a reason, never a guessed value.
Frequency-like text that the frequency mapping cannot read is ``not_recognised``.
"""

from __future__ import annotations

import re
import unicodedata
from collections.abc import Callable
from dataclasses import dataclass
from fractions import Fraction
from typing import Any

EXTRACT_TASK = "pharma.extract.v2"
PHRASE_TASK = "pharma.phrase.v1"
# Bumped when the deterministic parsing changes (recorded on every run).
MOCK_RULES_VERSION = "s5-mock-rules-2.3.0"
# Bumped when a lexeme, production or value constraint of DOSE_GRAMMAR changes (recorded on every run).
DOSE_GRAMMAR_VERSION = "s5-dose-grammar-1.3.0"

# ================================================================ G1: lexicon and tokeniser

# Strength units -> canonical unit.
_UNITS = {
    "mg": "mg", "มก": "mg", "มก.": "mg", "มิลลิกรัม": "mg",
    "g": "g", "gm": "g", "กรัม": "g",
    "mcg": "mcg", "µg": "mcg", "ug": "mcg", "ไมโครกรัม": "mcg",
    "unit": "unit", "units": "unit", "u": "unit", "iu": "unit", "ยูนิต": "unit",
    "ml": "ml", "มล": "ml", "มล.": "ml",
}
_MASS = frozenset({"mg", "g", "gm", "mcg", "µg", "ug", "มก.", "มก", "มิลลิกรัม", "กรัม", "ไมโครกรัม"})
_VOLUME = frozenset({"ml", "มล.", "มล"})
_QW_TH = frozenset({"เม็ด", "แคปซูล"})
QUANTITY_WORDS = frozenset({"tab", "tabs", "tablet", "tablets", "cap", "caps", "capsule", "capsules"}) | _QW_TH
_EN_NUMBER_WORDS = frozenset(
    {"one", "two", "three", "four", "five", "six", "seven", "eight", "nine", "ten", "half", "once", "twice", "thrice"}
)
_TH_NUMBER_WORDS = frozenset({"หนึ่ง", "สอง", "สาม", "สี่", "ห้า", "หก", "เจ็ด", "แปด", "เก้า", "สิบ", "ครึ่ง"})
# Closed Thai lexicon, matched longest-first. "มก"/"มล" (no dot) are listed because S1 accepts them as units, but
# only as a standalone word (see _WORD_ONLY): Thai has no spaces, so they are also the start of "มกราคม" (January),
# "มลพิษ" and the middle of "แอมลอดิปีน". The dotted forms carry their own boundary.
_TH_LEXICON = tuple(sorted(
    {"เม็ด", "แคปซูล", "ครั้งละ", "วันละ", "สัปดาห์ละ", "อาทิตย์ละ", "เดือนละ", "ครั้ง", "ทุก", "ชั่วโมง", "ชม.",
     "นาที", "ต่อ", "มก.", "มก", "มิลลิกรัม", "กรัม", "ไมโครกรัม", "ยูนิต", "มล.", "มล", "และ", "หรือ", "ถึง"}
    | _TH_NUMBER_WORDS,
    key=len, reverse=True,
))
_WORD_ONLY = frozenset({"มก", "มล"})  # lexemes that must not touch a Thai character on either side
_SYMBOLS = frozenset("/⁄.,-–—~x+&")
_CONNECTORS = frozenset({"to", "or", "and", "ถึง", "หรือ", "และ"})
_RANGE_CONNECTORS = frozenset({"-", "–", "—", "~"}) | _CONNECTORS
# R1 (rev 3): an anchor's TAIL may hold only these characters; anything else breaks the anchor (unparsed_token).
NEUTRAL = frozenset(" .,;:()[]+&")
# P1 (rev 4): R1 (b) fires when the key after an anchor's TAIL (w1 = the Latin letters there, + w2 = the next Latin
# letters if only " -._" lies between) starts with an "en" prefix, or the Thai text there starts with a "th" prefix.
P1_KEYS = {
    "en": ("per", "aday", "aweek", "amonth", "kg", "tdd", "dailydose", "dailytotal"),
    "th": ("ต่อ", "กก", "กิโล"),
}
_WORD_JOINERS = frozenset(" -._")  # what may separate w1/w2 (P1) and "daily"/"dose" (P2)
# T1: text directly after "ครึ่ง" that starts with one of these is a time ("half an hour"), never a half tablet.
_TW_TH_PREFIXES = ("ชั่วโมง", "ชม", "ช.ม.", "นาที")
_TW_EN = frozenset({"h", "hr", "hrs", "hour", "hours", "min", "mins", "minute", "minutes"})
# QF (rev 3, closed): after a Q4b "ครึ่ง" (+ ␣?) the next thing must be the end of the entry, a T1 or F1-F3 start,
# Thai text beginning with one of "th", or one of the Latin words "en". Anything else is ambiguous_quantity.
QF = {
    "th": ("ก่อน", "หลัง", "พร้อม", "เช้า", "กลางวัน", "เที่ยง", "เย็น", "ค่ำ", "ตอน", "เวลา", "เมื่อ", "วันละ", "ทุก"),
    "en": frozenset({"od", "bd", "bid", "tid", "qid", "qd", "hs", "prn", "po", "ac", "pc", "daily", "once", "twice",
                     "thrice", "every", "before", "after", "with"}),
}
# D1 (rev 3): daily-total or divided-dose markers give per_unit_amount (the amount is a total to be split).
# TH markers are searched with all whitespace removed. "ต่อ" + a period word + "ละ" ("กินต่อ วันละ 1 เม็ด" =
# continue, once daily) is not a marker. "วันละ ␣? S1" is a marker too. EN markers are whole Latin words.
D1_LEXICON = {
    "th": ("แบ่ง", "รวม", "ทั้งหมด", "ทั้งวัน"),
    "th_per": "ต่อ",
    "th_per_objects": ("วัน", "สัปดาห์", "อาทิตย์", "เดือน", "กก", "กิโล"),
    "th_per_periods": ("วัน", "สัปดาห์", "อาทิตย์", "เดือน"),
    "th_period_follower": "ละ",
    "th_before_strength": "วันละ",
    "en": frozenset({"divided", "divide", "split", "total", "doses"}),
    # rev 4 P2: anywhere in the entry, the whole word "tdd", or "daily" joined to / separated by _WORD_JOINERS from
    # one of "daily_followers".
    "en_p2": frozenset({"tdd"}),
    "daily": "daily",
    "daily_followers": frozenset({"dose", "doses", "total"}),
}
# P3 (rev 5, narrowed): in the drug-name region (before the first numeric-ish token), a Latin whole word equal to one of
# these. A word that only starts with "per" (Perindopril, Perphenazine) does not fire.
P3_WORDS = frozenset({"per", "perday", "perdiem", "perdose", "perweek", "permonth", "perkg", "daily", "day", "days",
                      "aday", "dose"})
# P4 (rev 5): D1 fires when the dose region holds >= 1 DAILY statement and >= 1 MULTI statement, anywhere in it.
# DAILY: d1 = a whole word in "words", a V_EN_PHRASES match equal to "phrase", or the substring "th", in the C1 free
# text (so a word consumed by a production, e.g. the "daily" of F2 "twice daily", is not one); d2 = F1 with interval
# "f1_hours"; d3 = F2 with count "count" per "day"/"daily"; d4 = F3 "วันละ ␣? 1? ␣? ครั้ง".
P4_DAILY = {
    "words": frozenset({"daily", "everyday", "od", "qd"}),
    "phrase": ("every", "day"),
    "th": "ทุกวัน",
    "f1_hours": 24,
    "count": 1,
}
# MULTI m1 (the rev-4 list): one of "words" (whole words, after dot compaction), F1 with an interval in "f1_hours", F2
# with a count >= "min_count" per one of "f2_periods", or F3 "วันละ INT ครั้ง" with INT >= "min_count".
P4_MULTI_DOSE = {
    "words": frozenset({"bd", "bid", "tid", "qid", "twice", "thrice"}),
    "f1_hours": range(1, 24),
    "f2_periods": frozenset({"day", "daily"}),
    "count_words": {"once": 1, "twice": 2, "thrice": 3, "one": 1, "two": 2, "three": 3, "four": 4},
    "min_count": 2,
}
# MULTI m2: >= 2 distinct slots in the dose region. Slot -> (EN whole words, casefolded; TH substrings).
TIME_SLOTS = {
    "AM": (frozenset({"morning", "breakfast"}), ("เช้า",)),
    "MID": (frozenset({"noon", "midday", "lunch"}), ("กลางวัน", "เที่ยง")),
    "PM": (frozenset({"evening", "dinner", "supper"}), ("เย็น", "ค่ำ")),
    "HS": (frozenset({"night", "bedtime", "hs"}), ("นอน",)),
}
_UFRACTIONS = {"½": Fraction(1, 2), "¼": Fraction(1, 4), "¾": Fraction(3, 4)}
_SLASH_FRACTIONS = {("1", "2"): Fraction(1, 2), ("1", "4"): Fraction(1, 4), ("3", "4"): Fraction(3, 4)}
_NUM_TOKEN = re.compile(r"[0-9]+(?:\.[0-9]+)?")


def _is_thai(ch: str) -> bool:
    return "\u0e00" <= ch <= "\u0e7f"


# G1 INVISIBLE (rev 3): a character in one of these general categories, or on the explicit list. Each one is its
# own OTHER token, numeric-ish wherever it appears, and never consumed, so the dose can never be ``resolved``.
INVISIBLE_CATEGORIES = frozenset({"Cc", "Cf", "Co", "Cs", "Cn"})
INVISIBLE_EXTRA = frozenset({
    0x034F, 0x115F, 0x1160, 0x17B4, 0x17B5, 0x180B, 0x180C, 0x180D, 0x180F, 0x2800, 0x3164, 0xFFA0,
    *range(0xFE00, 0xFE0F + 1), *range(0xE0100, 0xE01EF + 1),
})


def is_invisible(ch: str) -> bool:
    return unicodedata.category(ch) in INVISIBLE_CATEGORIES or ord(ch) in INVISIBLE_EXTRA


def is_slash_like(ch: str) -> bool:
    """G1 SLASH-LIKE (rev 3): Unicode name contains SOLIDUS or SLASH, or U+2216 SET MINUS. Numeric-ish everywhere;
    only an ASCII "/" inside FRAC, S2 or L1 is ever consumed."""
    name = unicodedata.name(ch, "")
    return "SOLIDUS" in name or "SLASH" in name or ch == "\u2216"


def _never_consumed(t: "Token") -> bool:
    """A single INVISIBLE or SLASH-LIKE character token (an ASCII "/" only counts as consumed inside FRAC/S2/L1)."""
    return len(t.text) == 1 and (is_invisible(t.text) or is_slash_like(t.text))


@dataclass(frozen=True)
class Token:
    kind: str  # NUM | UFRAC | WORD | TH | SYM | OTHER
    text: str  # normalised lexeme
    start: int  # offsets into the normalised line (aligned 1:1 with ``normalise(text)``)
    end: int


def normalise(text: str) -> str:
    """NFC (not NFKC, so "½" survives) with whitespace collapsed (§N N1 + N5). This is also the ``raw_span``."""
    return " ".join(unicodedata.normalize("NFC", text).split())


# §N (rev 4, closed): Thai spelling steps applied between N1 (NFC) and N5 (whitespace), in this order. They change
# only the text the grammar reads (dose, D1, R1, C1, frequency); ``raw_span`` stays N1 + N5. Nothing else is
# rewritten: no character is removed, and homoglyphs, duplicated tone marks and misspellings are not corrected.
NORMALISE_STEPS: tuple[tuple[str, re.Pattern[str], str], ...] = (
    ("N2", re.compile("\u0e4d([\u0e48-\u0e4b]?)\u0e32"), "\\1\u0e33"),  # decomposed sara am -> tone? + U+0E33
    ("N3", re.compile("([\u0e48-\u0e4b])([\u0e31\u0e34-\u0e37])"), "\\2\\1"),  # tone before upper vowel -> after
    ("N4", re.compile("\u0e40\u0e40"), "\u0e41"),  # doubled sara e -> sara ae
)


def normalise_grammar(text: str) -> str:
    """§N N1-N5: the text every grammar check reads."""
    s = unicodedata.normalize("NFC", text)
    for _, pattern, repl in NORMALISE_STEPS:
        s = pattern.sub(repl, s)
    return " ".join(s.split())


def _fold(raw: str) -> str:
    # Case-fold per character so offsets stay aligned with ``raw``; "×" is the letter x.
    return "".join("x" if c == "×" else (c.lower() if len(c.lower()) == 1 else c) for c in raw)


def tokenise(raw: str) -> list[Token]:
    s = _fold(raw)
    toks: list[Token] = []
    i = 0
    while i < len(s):
        c = s[i]
        if c.isspace():
            i += 1
        elif is_invisible(c):  # before every other class: Thai unassigned code points and Hangul fillers included
            toks.append(Token("OTHER", c, i, i + 1))
            i += 1
        elif is_slash_like(c):
            toks.append(Token("SYM", c, i, i + 1))
            i += 1
        elif "0" <= c <= "9":
            m = _NUM_TOKEN.match(s, i)
            toks.append(Token("NUM", m.group(), i, m.end()))
            i = m.end()
        elif unicodedata.numeric(c, None) is not None:  # ½ ⅓ Thai digits, full-width digits, superscripts, ...
            toks.append(Token("UFRAC", c, i, i + 1))
            i += 1
        elif _is_thai(c):
            lexeme = next((w for w in _TH_LEXICON if s.startswith(w, i) and not (w in _WORD_ONLY and (
                (i > 0 and _is_thai(s[i - 1])) or (i + len(w) < len(s) and _is_thai(s[i + len(w)]))))), None)
            if lexeme:
                toks.append(Token("TH", lexeme, i, i + len(lexeme)))
                i += len(lexeme)
            elif toks and toks[-1].kind == "OTHER" and toks[-1].end == i and _is_thai(toks[-1].text[0]):
                toks[-1] = Token("OTHER", toks[-1].text + c, toks[-1].start, i + 1)
                i += 1
            else:
                toks.append(Token("OTHER", c, i, i + 1))
                i += 1
        elif c.isalpha():
            j = i
            while j < len(s) and s[j].isalpha() and not _is_thai(s[j]) and not is_invisible(s[j]) and not is_slash_like(s[j]):
                j += 1
            toks.append(Token("SYM" if s[i:j] == "x" else "WORD", s[i:j], i, j))
            i = j
        else:
            toks.append(Token("SYM" if c in _SYMBOLS else "OTHER", c, i, i + 1))
            i += 1
    return toks


def _is_number(t: Token) -> bool:
    return t.kind in ("NUM", "UFRAC") or t.text in _EN_NUMBER_WORDS or (t.kind == "TH" and t.text in _TH_NUMBER_WORDS)


def numeric_ish(toks: list[Token]) -> list[bool]:
    """G1: numbers, number words, strength units and quantity words; every INVISIBLE and SLASH-LIKE character;
    any other symbol or connector next to a number."""
    out = [_is_number(t) or t.text in _UNITS or t.text in QUANTITY_WORDS or _never_consumed(t) for t in toks]
    for i, t in enumerate(toks):
        if (t.kind == "SYM" or t.text in _CONNECTORS) and not _never_consumed(t):
            out[i] = any(0 <= j < len(toks) and _is_number(toks[j]) for j in (i - 1, i + 1))
    return out


# ================================================================ G2: productions


@dataclass(frozen=True)
class Match:
    pid: str
    start: int  # token index
    end: int  # token index, exclusive
    strengths: tuple[tuple[Fraction, str], ...] = ()
    quantity: Fraction | None = None
    anchor: int | None = None  # token index where dose text starts (drug-name boundary)
    last: int | None = None  # R1 anchor: last token of S1/Q1-Q5 (UNIT, QW, closing ครึ่ง of Q4b, M of Q5)
    broken: bool = False  # R1 (c): a non-NEUTRAL character in the anchor's TAIL
    freq_code: str | None = None  # Q5 only
    daily_total: bool = False  # Q7 with a value > 1


def _text(toks: list[Token], i: int) -> str | None:
    return toks[i].text if 0 <= i < len(toks) else None


def _num(toks: list[Token], i: int) -> str | None:
    return toks[i].text if 0 <= i < len(toks) and toks[i].kind == "NUM" else None


def _int(toks: list[Token], i: int) -> Fraction | None:
    t = _num(toks, i)
    return Fraction(t) if t and t.isdigit() and t[0] != "0" else None


def _qv(toks: list[Token], i: int) -> tuple[Fraction, int] | None:
    """QV: an INT or decimal (no leading zero except "0.x") with 0 < v <= 10 and 4v whole."""
    t = _num(toks, i)
    if not t:
        return None
    whole = t.split(".")[0]
    if whole[0] == "0" and not (whole == "0" and "." in t):
        return None
    return _bounded(Fraction(t), i + 1)


def _bounded(v: Fraction, end: int) -> tuple[Fraction, int] | None:
    return (v, end) if 0 < v <= 10 and (4 * v).denominator == 1 else None


def _frac(toks: list[Token], i: int) -> tuple[Fraction, int] | None:
    t = _text(toks, i)
    if t in _UFRACTIONS:
        return _UFRACTIONS[t], i + 1
    if _num(toks, i) and _text(toks, i + 1) == "/" and (t, _num(toks, i + 2)) in _SLASH_FRACTIONS:
        return _SLASH_FRACTIONS[(t, _num(toks, i + 2))], i + 3
    return None


def _s1(toks: list[Token], i: int) -> Match | None:
    t = _num(toks, i)
    if not t or _text(toks, i - 1) == "/" or _text(toks, i + 1) not in _UNITS or Fraction(t) <= 0:
        return None
    return Match("S1", i, i + 2, strengths=((Fraction(t), _UNITS[toks[i + 1].text]),), anchor=i, last=i + 1)


def _s2(toks: list[Token], i: int) -> Match | None:
    ok = _num(toks, i) and _text(toks, i + 1) == "/" and _num(toks, i + 2) and _text(toks, i + 3) in _UNITS
    return Match("S2", i, i + 4) if ok else None  # combination product: consumed, no dose read


def _s3(toks: list[Token], i: int) -> Match | None:
    first = _s1(toks, i)
    if first is None:
        return None
    strengths, end = list(first.strengths), first.end
    while True:
        j = end + 1 if _text(toks, end) in ("+", ",", "&", "and", "และ") else end
        nxt = _s1(toks, j)
        if nxt is None:
            break
        strengths += nxt.strengths
        end = nxt.end
    return Match("S3", i, end, strengths=tuple(strengths), anchor=i) if len(set(strengths)) >= 2 else None


def _l1(toks: list[Token], i: int) -> Match | None:
    if not (_num(toks, i) and _text(toks, i + 1) in _MASS and _text(toks, i + 2) == "/"):
        return None
    j = i + 4 if _num(toks, i + 3) else i + 3
    if _text(toks, j) not in _VOLUME:
        return None
    j += 3 if _num(toks, j + 1) and _text(toks, j + 2) in _VOLUME else 1
    return Match("L1", i, j, anchor=i)


def _quantity(pid: str, got: tuple[Fraction, int] | None, toks: list[Token], i: int) -> Match | None:
    if got and _text(toks, got[1]) in QUANTITY_WORDS:
        return Match(pid, i, got[1] + 1, quantity=got[0], anchor=i, last=got[1])
    return None


def _q1(toks: list[Token], i: int) -> Match | None:
    return _quantity("Q1", _qv(toks, i), toks, i)


def _q2(toks: list[Token], i: int) -> Match | None:
    return _quantity("Q2", _frac(toks, i), toks, i)


def _q3(toks: list[Token], i: int) -> Match | None:
    whole = _int(toks, i)
    if whole is None:
        return None
    got = _frac(toks, i + 2 if _text(toks, i + 1) in ("-", "and", "และ") else i + 1)
    return _quantity("Q3", _bounded(whole + got[0], got[1]) if got else None, toks, i)


def _q4(toks: list[Token], i: int) -> Match | None:
    if _text(toks, i) == "ครึ่ง" and _text(toks, i + 1) in _QW_TH:
        return Match("Q4", i, i + 2, quantity=Fraction(1, 2), anchor=i, last=i + 1)
    whole = _int(toks, i)
    if not _half_shape(toks, i) or not _qf(toks, i + 3):
        return None
    got = _bounded(whole + Fraction(1, 2), i + 3)
    return Match("Q4", i, got[1], quantity=got[0], anchor=i, last=i + 2) if got else None


def _half_shape(toks: list[Token], i: int) -> bool:
    """The Q4b shape "INT ␣? (เม็ด|แคปซูล) ␣? ครึ่ง" at token ``i`` (standalone or inside Q6/Q7, any total)."""
    return _int(toks, i) is not None and _text(toks, i + 1) in _QW_TH and _text(toks, i + 2) == "ครึ่ง"


def _qf(toks: list[Token], j: int) -> bool:
    """QF: the token ``j`` right after a Q4b "ครึ่ง" (whitespace ignored) is an allowed follower."""
    if j >= len(toks) or any(fn(toks, j) for fn in (_t1, _f1, _f2, _f3)):
        return True
    if toks[j].kind == "WORD":
        return toks[j].text in QF["en"]
    return _surface(toks).startswith(QF["th"], toks[j].start)


def _is_tw(toks: list[Token], i: int) -> bool:
    """TW: the text at token ``i`` (directly after "ครึ่ง", whitespace ignored) starts a time word."""
    if not 0 <= i < len(toks):
        return False
    if toks[i].kind == "WORD":
        return toks[i].text in _TW_EN
    # Contiguous (unspaced) text from token i onwards, enough to test the longest prefix.
    text, end = "", toks[i].start
    for t in toks[i:i + 4]:
        if t.start != end:
            break
        text, end = text + t.text, t.end
    return text.startswith(_TW_TH_PREFIXES)


_TIMES_CODE = {"1": "q24h", "2": "q12h", "3": "q8h", "4": "q6h"}


def _q5(toks: list[Token], i: int) -> Match | None:
    got = _frac(toks, i) or _qv(toks, i)
    if got is None or _text(toks, got[1]) != "x":
        return None
    m = _num(toks, got[1] + 1)
    if m not in _TIMES_CODE or _text(toks, got[1] + 2) in QUANTITY_WORDS:
        return None
    return Match("Q5", i, got[1] + 2, quantity=got[0], anchor=i, last=got[1] + 1, freq_code=_TIMES_CODE[m])


def _prefixed(pid: str, toks: list[Token], i: int) -> Match | None:
    inner = [m for fn in (_q1, _q2, _q3, _q4) if (m := fn(toks, i + 1))]
    if not inner:
        return None
    best = max(inner, key=lambda m: m.end)
    return Match(pid, i, best.end, quantity=best.quantity, anchor=best.anchor, last=best.last)


def _q6(toks: list[Token], i: int) -> Match | None:
    return _prefixed("Q6", toks, i) if _text(toks, i) == "ครั้งละ" else None


def _q7(toks: list[Token], i: int) -> Match | None:
    m = _prefixed("Q7", toks, i) if _text(toks, i) == "วันละ" else None
    if m is not None and m.quantity > 1:  # a daily total, not a per-dose amount
        return Match("Q7", m.start, m.end, anchor=m.anchor, last=m.last, daily_total=True)
    return m


def _surface(toks: list[Token]) -> str:
    """The normalised, case-folded line rebuilt from the tokens (whitespace is always one space)."""
    chars = [" "] * (toks[-1].end if toks else 0)
    for t in toks:
        chars[t.start:t.end] = t.text
    return "".join(chars)


def _latin_run(s: str, k: int) -> str:
    end = k
    while end < len(s) and "a" <= s[end] <= "z":  # the surface is already case-folded
        end += 1
    return s[k:end]


def _after_tail(toks: list[Token], i: int) -> tuple[str, int, str]:
    """(TAIL, offset right after it, P1 key) for the anchor at token ``i``."""
    s = _surface(toks)
    j = toks[i].end
    while j < len(s) and unicodedata.category(s[j])[0] not in "LN":
        j += 1
    w1 = _latin_run(s, j)
    k = j + len(w1)
    while k < len(s) and s[k] in _WORD_JOINERS:
        k += 1
    w2 = _latin_run(s, k) if w1 and k > j + len(w1) else ""
    return s[toks[i].end:j], j, (w1 + w2).casefold()


def _r1(toks: list[Token], i: int) -> Match | None:
    """R1 (rev 3) on the anchor at token ``i``, unless the anchor's UNIT and a "/" begin an L1 liquid.

    TAIL = the run of characters right after the anchor whose category is not L* or N*. (a) a SLASH-LIKE
    character in TAIL, or (b) a P1 key or Thai prefix right after TAIL (rev 4): per_unit_amount.
    Otherwise (c) any TAIL character outside NEUTRAL breaks the anchor (unparsed_token). Consumes nothing.
    """
    if toks[i].text in _MASS and _l1(toks, i - 1):
        return None
    tail, j, key = _after_tail(toks, i)
    if key.startswith(P1_KEYS["en"]) or _surface(toks).startswith(P1_KEYS["th"], j) or any(map(is_slash_like, tail)):
        return Match("R1", i, i)
    if set(tail) - NEUTRAL:
        return Match("R1", i, i, broken=True)
    return None


def _d1_th_at(compact: str) -> bool:
    """A TH D1 marker at the start of ``compact`` (whitespace already removed)."""
    if compact.startswith(D1_LEXICON["th"]):
        return True
    if not compact.startswith(D1_LEXICON["th_per"]):
        return False
    obj = compact[len(D1_LEXICON["th_per"]):]
    period = next((w for w in D1_LEXICON["th_per_periods"] if obj.startswith(w)), None)
    if period and obj[len(period):].startswith(D1_LEXICON["th_period_follower"]):
        return False
    return obj.startswith(D1_LEXICON["th_per_objects"])


def _daily_total_word(toks: list[Token], i: int) -> bool:
    """P2: "daily" + dose/doses/total, joined or separated only by _WORD_JOINERS."""
    t, daily = toks[i], D1_LEXICON["daily"]
    if t.text.startswith(daily) and t.text[len(daily):] in D1_LEXICON["daily_followers"]:
        return True
    if t.text != daily:
        return False
    s, k = _surface(toks), t.end
    while k < len(s) and s[k] in _WORD_JOINERS:
        k += 1
    nxt = next((u for u in toks[i + 1:] if u.start == k), None)
    return k > t.end and nxt is not None and nxt.kind == "WORD" and nxt.text in D1_LEXICON["daily_followers"]


def _name_region_word(toks: list[Token], i: int) -> bool:
    """P3: a per-day word before the first numeric-ish token (only when the entry has one)."""
    if toks[i].text not in P3_WORDS:
        return False
    numeric = numeric_ish(toks)
    return True in numeric and i < numeric.index(True)


def _f_count(t: Token) -> int:
    return int(t.text) if t.kind == "NUM" else P4_MULTI_DOSE["count_words"].get(t.text, 0)


def _p4(toks: list[Token], numeric: list[bool], spans: list[tuple[int, int]]) -> list[Match]:
    """P4 (rev 5): one D1 at the dose region's start if it holds a DAILY and a MULTI statement (see P4_DAILY).

    The dose region starts at the first numeric-ish token; an F1-F3 match counts when it overlaps it ("q24h 1000 mg"
    included). m1 is read over the whole entry, as in rev 4, so no rev-4 per_unit_amount becomes resolved."""
    if True not in numeric:
        return []
    fi = numeric.index(True)
    daily_c, multi_c = P4_DAILY, P4_MULTI_DOSE
    free = _free_text(toks, fi, spans)
    daily = (bool(daily_c["words"] & set(_latin_words(free))) or daily_c["th"] in free
             or any(tuple(_latin_words(m.group())) == daily_c["phrase"] for m in _phrases(free)))
    region = _compact_dots(_surface(toks)[toks[fi].start:].casefold())
    words = set(_latin_words(region))
    multi = sum(bool(en & words) or any(th in region for th in ths) for en, ths in TIME_SLOTS.values()) >= 2  # m2
    multi = multi or any(w in multi_c["words"] for w in _LETTER_RUN.findall(_compact_dots(_surface(toks))))
    for k in range(len(toks)):
        in_region = k >= fi - 1
        if _f1(toks, k):
            hours = int(toks[k + 1].text)
            daily = daily or (in_region and hours == daily_c["f1_hours"])
            multi = multi or hours in multi_c["f1_hours"]
        f2 = _f2(toks, k)
        if f2 and toks[f2.end - 1].text in multi_c["f2_periods"]:
            count = _f_count(toks[k])
            daily = daily or (in_region and count == daily_c["count"])
            multi = multi or count >= multi_c["min_count"]
        if _f3(toks, k) and toks[k].text == "วันละ":
            count = _int(toks, k + 1) or 1
            daily = daily or (in_region and count == daily_c["count"])
            multi = multi or count >= multi_c["min_count"]
    return [Match("D1", fi, fi)] if daily and multi else []


def _d1(toks: list[Token], i: int) -> Match | None:
    """D1 (rev 3): a daily-total or divided-dose marker that starts inside token ``i``. Consumes nothing."""
    t = toks[i]
    if (t.kind == "WORD" and (t.text in D1_LEXICON["en"] or t.text in D1_LEXICON["en_p2"] or _daily_total_word(toks, i)
                              or _name_region_word(toks, i))) or (
            t.text == D1_LEXICON["th_before_strength"] and _s1(toks, i + 1)):
        return Match("D1", i, i)
    compact = "".join(x.text for x in toks[i:])  # tokens hold every non-whitespace character
    return Match("D1", i, i) if any(_d1_th_at(compact[k:]) for k in range(len(t.text))) else None


# C1 (rev 4, amended in rev 5): closed free-text vocabulary for the dose region. Units, quantity words, number words,
# ครั้ง, ครั้งละ, วันละ, time words, x, a, per, to, or and and are deliberately absent: they pass only when a production
# consumes them. Rev 5: the bare period words day/days/week/month and วัน are absent too; they pass only inside a
# V_EN_PHRASES match or a listed Thai compound (ทุกวัน, วันเว้นวัน, ทั้งวัน, กลางวัน).
V_EN_FREE = frozenset("""
od bd bid tid qid qd qod hs prn po ac pc daily nightly weekly monthly once twice thrice every other
morning evening night bedtime noon before after with without meal meals food breakfast lunch dinner
supper as needed when required for pain fever oral orally by mouth at in the take sc sl im iv
""".split())
V_TH_FREE = frozenset("""
รับประทาน กิน ทาน อาหาร นอน มี อาการ ปวด ไข้ เว้น ให้ ก่อน หลัง พร้อม เช้า กลางวัน เที่ยง เย็น ค่ำ ตอน เวลา
เมื่อ ทุก ทันที ต่อ แบ่ง รวม ทั้งหมด ทั้งวัน ทุกวัน วันเว้นวัน
""".split())
# Rev 5: frequency phrases blanked (whole words; each space stands for a run of _WORD_JOINERS) before the word check.
V_EN_PHRASES = ("every day", "every other day", "every week", "every other week", "every month")
_V_TH_LONGEST = tuple(sorted(V_TH_FREE, key=len, reverse=True))
_DOTTED_ABBR = re.compile(r"(?<![^\W\d_])[^\W\d_](?:\.[^\W\d_])+\.?(?![^\W\d_])")  # p.r.n. -> prn
_TH_RUN = re.compile("[\u0e01-\u0e3a\u0e40-\u0e4e]+")
_LETTER_RUN = re.compile(r"[^\W\d_]+")
_JOINER_RUN = "[" + re.escape("".join(sorted(_WORD_JOINERS))) + "]+"
_PHRASE_RE = re.compile("|".join(_JOINER_RUN.join(map(re.escape, p.split())) for p in sorted(V_EN_PHRASES, key=len, reverse=True)))


def _is_latin_letter(c: str) -> bool:
    """A letter of a C1 Latin word: category L*, not Thai."""
    return unicodedata.category(c)[0] == "L" and not _is_thai(c)


def _latin_words(text: str) -> list[str]:
    """The whole Latin words of ``text`` (maximal runs of _is_latin_letter characters)."""
    return "".join(c if _is_latin_letter(c) else " " for c in text).split()


def _phrases(free: str) -> list[re.Match[str]]:
    """Whole-word V_EN_PHRASES matches in ``free`` (casefolded), left to right, non-overlapping."""
    return [m for m in _PHRASE_RE.finditer(free)
            if not (m.start() and _is_latin_letter(free[m.start() - 1]))
            and not (m.end() < len(free) and _is_latin_letter(free[m.end()]))]


def _compact_dots(text: str) -> str:
    return _DOTTED_ABBR.sub(lambda m: m.group().replace(".", ""), text)


def _consumed_spans(toks: list[Token], matches: list[Match]) -> list[tuple[int, int]]:
    """Character spans of every token a consuming production took. T1 takes "ครึ่ง" and exactly its time word."""
    spans = []
    for m in matches:
        if m.pid == "T1":
            tw = toks[m.start + 1]
            end = tw.end if tw.kind == "WORD" else tw.start + len(
                next(p for p in _TW_TH_PREFIXES if _surface(toks).startswith(p, tw.start)))
            spans.append((toks[m.start].start, end))
        elif m.pid not in _FLAG_PIDS:
            spans += [(toks[k].start, toks[k].end) for k in range(m.start, m.end)]
    return spans


def _th_segmented(run: str) -> bool:
    """One greedy, longest-first, left-to-right pass over V_TH_FREE covers the whole run."""
    k = 0
    while k < len(run):
        word = next((w for w in _V_TH_LONGEST if run.startswith(w, k)), None)
        if word is None:
            return False
        k += len(word)
    return True


def _free_text(toks: list[Token], i: int, spans: list[tuple[int, int]]) -> str:
    """The dose region (token ``i`` to the end) with every consumed character blanked, casefolded, dots compacted."""
    chars = list(_surface(toks))
    for a, b in spans:
        chars[a:b] = " " * (b - a)
    return _compact_dots("".join(chars[toks[i].start:]).casefold())


def _c1(toks: list[Token], i: int, spans: list[tuple[int, int]] = ()) -> Match | None:
    """C1 (rev 4, rev 5): the free text of the dose region (token ``i`` = the first numeric-ish token, to the end;
    every consumed character blanked) must be closed-vocabulary words or V_EN_PHRASES only. Consumes nothing."""
    if i >= len(toks):
        return None
    free = _free_text(toks, i, spans)
    if not all(_th_segmented(run) for run in _TH_RUN.findall(free)):
        return Match("C1", i, i)
    for m in _phrases(free):  # rev 5: a listed frequency phrase is the only place a bare period word may stand
        free = free[:m.start()] + " " * (m.end() - m.start()) + free[m.end():]
    word = ""
    for c in free + " ":
        if _is_latin_letter(c):
            word += c
        elif word:
            if word not in V_EN_FREE:
                return Match("C1", i, i)
            word = ""
    return None


def _t1(toks: list[Token], i: int) -> Match | None:
    """T1: "ครึ่ง" + TW is a time, never a quantity (right after "INT เม็ด" the QF rule makes it ambiguous)."""
    if _text(toks, i) != "ครึ่ง" or not _is_tw(toks, i + 1):
        return None
    return Match("T1", i, i + 2, anchor=i)


_HOURS = ("h", "hr", "hrs", "hour", "hours")
_F1_UNITS = {"q": _HOURS, "every": _HOURS, "ทุก": ("ชั่วโมง", "ชม.")}


def _f1(toks: list[Token], i: int) -> Match | None:
    units = _F1_UNITS.get(_text(toks, i) or "")
    return Match("F1", i, i + 3) if units and _int(toks, i + 1) and _text(toks, i + 2) in units else None


_PERIODS = ("day", "daily", "week", "weekly", "month", "monthly")


def _f2(toks: list[Token], i: int) -> Match | None:
    head = _text(toks, i)
    if head in ("once", "twice", "thrice"):
        j = i + 1
    elif (_int(toks, i) or head in ("one", "two", "three", "four")) and _text(toks, i + 1) in ("time", "times"):
        j = i + 2
    else:
        return None
    j += 1 if _text(toks, j) in ("a", "per") else 0
    return Match("F2", i, j + 1) if _text(toks, j) in _PERIODS else None


def _f3(toks: list[Token], i: int) -> Match | None:
    if _text(toks, i) not in ("วันละ", "สัปดาห์ละ", "อาทิตย์ละ", "เดือนละ"):
        return None
    j = i + 2 if _int(toks, i + 1) else i + 1
    return Match("F3", i, j + 1) if _text(toks, j) == "ครั้ง" else None


# The complete, closed production table (§G2). Nothing else reads a numeric-ish token.
DOSE_GRAMMAR: dict[str, Callable[[list[Token], int], Match | None]] = {
    "S1": _s1, "S2": _s2, "S3": _s3, "L1": _l1, "R1": _r1, "D1": _d1, "C1": _c1,
    "Q1": _q1, "Q2": _q2, "Q3": _q3, "Q4": _q4, "Q5": _q5, "Q6": _q6, "Q7": _q7,
    "T1": _t1, "F1": _f1, "F2": _f2, "F3": _f3,
}
_QUANTITY_PIDS = frozenset({"Q1", "Q2", "Q3", "Q4", "Q5", "Q6", "Q7"})
# Checked separately (R1 on anchors, D1 at every token, C1 once on the dose region); they consume nothing.
_FLAG_PIDS = frozenset({"R1", "D1", "C1"})

# Variable regimen: an exception, alternation, or a weekday-specific dose. Checked before all productions.
_WEEKDAYS = r"mon|tue|tues|wed|wednes|thu|thur|thurs|fri|sat|satur|sun"
VARIABLE_RE = re.compile(
    rf"(?<![A-Za-z])(?:except|alternat\w*|(?:{_WEEKDAYS})(?:day)?s?)(?![A-Za-z])"
    r"|ยกเว้น|สลับ|วัน(?:จันทร์|อังคาร|พุธ|พฤหัส(?:บดี)?|ศุกร์|เสาร์|อาทิตย์)",
    re.IGNORECASE,
)


@dataclass(frozen=True)
class DoseParse:
    """Parse trace of one line: the §N text read, its tokens, the productions that fired, and the dose read."""

    text: str
    tokens: tuple[Token, ...]
    matches: tuple[Match, ...]
    consumed: frozenset[int]
    numeric: tuple[bool, ...]
    dose_status: str
    reason: str | None
    dose_value: float | None
    dose_unit: str | None
    quantity: float | None

    @property
    def unconsumed_numeric(self) -> list[Token]:
        return [t for i, t in enumerate(self.tokens) if self.numeric[i] and i not in self.consumed]

    @property
    def times_code(self) -> str | None:
        return next((m.freq_code for m in self.matches if m.freq_code), None)


def read_dose(raw: str) -> DoseParse:
    """Apply §N, tokenise the whole line and apply ``DOSE_GRAMMAR`` left to right, longest match first."""
    line = normalise_grammar(raw)
    toks = tokenise(line)
    matches: list[Match] = []
    i = 0
    while i < len(toks):
        found = [m for pid, fn in DOSE_GRAMMAR.items() if pid not in _FLAG_PIDS and (m := fn(toks, i))]
        if found:
            best = max(found, key=lambda m: m.end)  # a tie keeps table order
            matches.append(best)
            i = best.end
        else:
            i += 1
    consumed = frozenset(k for m in matches for k in range(m.start, m.end))
    # R1 is checked on every anchor of the productions that fired; it flags and consumes nothing.
    tails = [r for m in matches if m.last is not None and (r := _r1(toks, m.last))]
    per_unit = [r for r in tails if not r.broken]
    numeric = numeric_ish(toks)
    spans = _consumed_spans(toks, matches)
    daily = [m for k in range(len(toks)) if (m := _d1(toks, k))]
    daily += _p4(toks, numeric, spans)
    # Q4b shape whose "ครึ่ง" is not followed by a QF item: half a tablet or not, so no value is chosen.
    half_unfollowed = any(_half_shape(toks, k) and not _qf(toks, k + 3) for k in range(len(toks)))
    left = [k for k in range(len(toks)) if numeric[k] and k not in consumed]
    free = [m for m in [_c1(toks, numeric.index(True), spans)] if m] if any(numeric) else []
    strengths = {s for m in matches for s in m.strengths}
    quantities = {m.quantity for m in matches if m.pid in _QUANTITY_PIDS and m.quantity is not None}

    # The first reason that applies is reported (§2 order). When unsure, never guess a value.
    if VARIABLE_RE.search(line):
        reason = "variable_regimen"
    elif any(m.pid == "L1" for m in matches):
        reason = "liquid_volume"
    elif len(strengths) > 1:
        reason = "multiple_strengths"
    elif per_unit or daily:
        reason = "per_unit_amount"
    elif any(toks[k].text in _RANGE_CONNECTORS and 0 < k < len(toks) - 1 and numeric[k - 1] and numeric[k + 1]
             for k in left):
        reason = "range"
    elif len(quantities) > 1 or half_unfollowed or any(m.daily_total for m in matches):
        reason = "ambiguous_quantity"
    elif left or tails or free:  # an unconsumed numeric-ish token, a broken anchor (R1 c) or a C1 word
        reason = "unparsed_token"
    else:
        reason = None

    status, value, unit, quantity = "unverifiable", None, None, None
    if reason is None:
        quantity = float(next(iter(quantities))) if quantities else None
        if strengths:
            ((v, unit),) = strengths
            status, value = "resolved", float(v)
        else:
            status = "not_stated"
    return DoseParse(line, tuple(toks), tuple(matches + tails + daily + free), consumed, tuple(numeric), status, reason, value, unit, quantity)


# ================================================================ frequency mapping (unchanged since s5r2)

# Frequency-like text. When no code is read, such text makes the frequency "not_recognised" rather than
# "not_stated". Non-daily schedules can never be expressed by a daily code, so they win over any code.
FREQ_LIKE_RE = re.compile(
    r"(?<![A-Za-z])(?:q\s*\d+\s*(?:h|hr|hrs|hours?|d)|every|times?|thrice|twice|weekly|monthly|qod|qwk|tiw|biw"
    r"|daily|nightly)(?![A-Za-z])|วันละ|ครั้ง|ทุก\s*\d+|วันเว้นวัน|สัปดาห์|อาทิตย์ละ|เดือนละ",
    re.IGNORECASE,
)
NON_DAILY_RE = re.compile(
    r"(?<![A-Za-z])(?:weeks?|weekly|monthly|months?|other day|alternate days?|qod|qwk|tiw|biw)(?![A-Za-z])"
    r"|วันเว้นวัน|สัปดาห์|อาทิตย์ละ|เดือนละ",
    re.IGNORECASE,
)
ROUTE_PATTERNS: tuple[tuple[re.Pattern[str], str], ...] = (
    (re.compile(r"(?<![A-Za-z])(?:po|oral|orally|by mouth)(?![A-Za-z])", re.IGNORECASE), "oral"),
    (re.compile(r"รับประทาน|ทางปาก"), "oral"),
    (re.compile(r"(?<![A-Za-z])(?:sc|subcut|subcutaneous|sq)(?![A-Za-z])|ฉีดใต้ผิวหนัง", re.IGNORECASE), "subcutaneous"),
    (re.compile(r"(?<![A-Za-z])(?:iv|intravenous)(?![A-Za-z])", re.IGNORECASE), "intravenous"),
)
_A_DAY = r"(?:a |per )?(?:day|daily)"
FREQ_PATTERNS: tuple[tuple[re.Pattern[str], str], ...] = (
    (re.compile(r"(?<![A-Za-z])(?:prn|p\.r\.n\.?|as needed|when needed)(?![A-Za-z])", re.IGNORECASE), "prn"),
    (re.compile(r"เวลาปวด|เมื่อมีอาการ|เมื่อจำเป็น"), "prn"),
    (re.compile(rf"(?<![A-Za-z])(?:qid|q\.i\.d\.?|(?:four|4) times {_A_DAY}|q6h)(?![A-Za-z])", re.IGNORECASE), "q6h"),
    (re.compile(rf"(?<![A-Za-z])(?:tid|t\.i\.d\.?|(?:three|3) times {_A_DAY}|q8h)(?![A-Za-z])", re.IGNORECASE), "q8h"),
    (re.compile(rf"(?<![A-Za-z])(?:bid|b\.i\.d\.?|(?:twice|two times|2 times) {_A_DAY}|q12h)(?![A-Za-z])", re.IGNORECASE), "q12h"),
    (re.compile(
        rf"(?<![A-Za-z])(?:od|qd|o\.d\.?|q\.d\.?|(?:once|one time|1 time) {_A_DAY}|daily|every day|q24h"
        r"|hs|qhs|q\.?h\.?s\.?|at bedtime|nightly|every (?:morning|night))(?![A-Za-z])",
        re.IGNORECASE,
    ), "q24h"),
    (re.compile(r"วันละ\s*4\s*ครั้ง"), "q6h"),
    (re.compile(r"วันละ\s*3\s*ครั้ง"), "q8h"),
    (re.compile(r"วันละ\s*2\s*ครั้ง"), "q12h"),
    (re.compile(r"วันละ\s*(?:1\s*)?ครั้ง|วันละ\s*1\s*(?:เม็ด|แคปซูล)|ก่อนนอน"), "q24h"),
    # Thai meal-time slots: morning-evening, morning-noon-evening, (+ bedtime).
    (re.compile(r"เช้า\s*[-,/]?\s*กลางวัน\s*[-,/]?\s*เย็น\s*[-,/]?\s*ก่อนนอน"), "q6h"),
    (re.compile(r"เช้า\s*[-,/]?\s*กลางวัน\s*[-,/]?\s*เย็น"), "q8h"),
    (re.compile(r"เช้า\s*[-,/]?\s*เย็น"), "q12h"),
)
# "every N hours" / "q N h" / "ทุก N ชั่วโมง". Only intervals with a schema code are mapped; any other
# interval (e.g. q4h) gives no code, so the field stays null unless another phrase (e.g. prn) is present.
EVERY_RE = re.compile(
    r"(?<![A-Za-z])(?:every\s*(\d+)\s*(?:hours?|hrs?|h)(?![A-Za-z])|q\s*(\d+)\s*(?:hours?|hrs?|h)(?![A-Za-z]))"
    r"|ทุก\s*(\d+)\s*(?:ชั่วโมง|ชม\.?)",
    re.IGNORECASE,
)
_EVERY_CODE = {"6": "q6h", "8": "q8h", "12": "q12h", "24": "q24h"}


def _first_start(text: str, patterns: list[re.Pattern[str]]) -> int:
    starts = [m.start() for p in patterns if (m := p.search(text))]
    return min(starts) if starts else len(text)


def _frequency(raw: str, times_code: str | None) -> str | None:
    if times_code:  # "NxM" (production Q5): M times a day
        return times_code
    # Earliest phrase wins; at the same start the longest phrase wins ("เช้า กลางวัน เย็น" over "เช้า เย็น").
    hits = [(m.start(), -len(m.group(0)), code) for pat, code in FREQ_PATTERNS if (m := pat.search(raw))]
    every = EVERY_RE.search(raw)
    code = _EVERY_CODE.get(next(g for g in every.groups() if g is not None).lstrip("0")) if every else None
    if every and code:
        hits.append((every.start(), -len(every.group(0)), code))
    return min(hits, key=lambda h: (h[0], h[1]))[2] if hits else None


def parse_entry(text: str) -> dict[str, Any]:
    """Parse one free-text medication line (EN/TH) into the ``pharma.extract.v2`` schema."""
    raw = normalise(text)  # shown on the page and in the audit (N1 + N5)
    dose = read_dose(raw)
    line = dose.text  # §N: what the grammar, route and frequency mapping read

    route = next((code for pat, code in ROUTE_PATTERNS if pat.search(line)), None)

    freq = None if NON_DAILY_RE.search(line) else _frequency(line, dose.times_code)
    if freq is not None:
        frequency_status = "recognised"
    elif FREQ_LIKE_RE.search(line):
        frequency_status = "not_recognised"
    else:
        frequency_status = "not_stated"

    # The name ends where dose text (a strength, liquid or quantity production, or any numeric-ish token the
    # grammar did not consume), a route or a frequency starts.
    starts = [dose.tokens[m.anchor].start for m in dose.matches if m.anchor is not None]
    starts += [t.start for t in dose.unconsumed_numeric[:1]]
    starts.append(_first_start(line, [EVERY_RE, *(p for p, _ in ROUTE_PATTERNS), *(p for p, _ in FREQ_PATTERNS)]))
    name = line[: min(starts)].strip(" ,;:-") or line
    return {
        "drug_name_raw": name,
        "dose_value": dose.dose_value,
        "dose_unit": dose.dose_unit,
        "quantity": dose.quantity,
        "dose_status": dose.dose_status,
        "dose_unverifiable_reason": dose.reason,
        "route": route,
        "frequency_code": freq,
        "frequency_status": frequency_status,
        "raw_span": raw,
    }


def extract_handler(inputs: dict[str, Any]) -> dict[str, Any]:
    entries = inputs.get("entries") or []
    return {"entries": [parse_entry(str(e)) for e in entries]}


def phrase_handler(inputs: dict[str, Any]) -> dict[str, Any]:
    from .phrasing import template_text  # local import: phrasing imports nothing from here

    return {
        "phrasings": [
            {"issue_id": item["issue_id"], "text": "Mock phrasing. " + template_text(item)}
            for item in inputs.get("issues") or []
        ]
    }


def register() -> None:
    from ..gateway import register_mock_task_handler

    register_mock_task_handler(EXTRACT_TASK, extract_handler)
    register_mock_task_handler(PHRASE_TASK, phrase_handler)
