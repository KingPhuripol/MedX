"""Independent reference reader for the s5r3 dose grammar (spec §G1-§G2), used only by the fuzz test.

Written from the spec, not from ``app.pharma.mock_rules``: it imports nothing from ``app`` and uses no
regular expressions. Technique: a character scanner builds (kind, text) pairs, then one hand-written
priority cascade walks them left to right (longer forms are tried before their prefixes).

``reference_parse(text) -> (dose_status, dose_value, dose_unit, quantity)``.
"""

from __future__ import annotations

import unicodedata
from fractions import Fraction

UNIT_OF = {
    "mg": "mg", "มก.": "mg", "มก": "mg", "มิลลิกรัม": "mg", "g": "g", "gm": "g", "กรัม": "g",
    "mcg": "mcg", "µg": "mcg", "ug": "mcg", "ไมโครกรัม": "mcg",
    "unit": "unit", "units": "unit", "u": "unit", "iu": "unit", "ยูนิต": "unit", "ml": "ml", "มล.": "ml", "มล": "ml",
}
MASS = ("mg", "g", "gm", "mcg", "µg", "ug", "มก.", "มก", "มิลลิกรัม", "กรัม", "ไมโครกรัม")
VOLUME = ("ml", "มล.", "มล")
TH_QW = ("เม็ด", "แคปซูล")
QW = ("tab", "tabs", "tablet", "tablets", "cap", "caps", "capsule", "capsules") + TH_QW
EN_WORDS = ("one", "two", "three", "four", "five", "six", "seven", "eight", "nine", "ten", "half", "once", "twice",
            "thrice")
TH_WORDS = ("หนึ่ง", "สอง", "สาม", "สี่", "ห้า", "หก", "เจ็ด", "แปด", "เก้า", "สิบ", "ครึ่ง")
THAI_LEXEMES = ("เม็ด", "แคปซูล", "ครั้งละ", "วันละ", "สัปดาห์ละ", "อาทิตย์ละ", "เดือนละ", "ครั้ง", "ทุก", "ชั่วโมง",
                "ชม.", "มก.", "มก", "มิลลิกรัม", "กรัม", "ไมโครกรัม", "ยูนิต", "มล.", "มล", "และ", "หรือ", "ถึง") + TH_WORDS
BARE_UNITS = ("มก", "มล")
SYMBOL_CHARS = "/⁄.,-–—~x+&"
LINKS = ("to", "or", "and", "ถึง", "หรือ", "และ")
RANGE_LINKS = ("-", "–", "—", "~") + LINKS
S3_JOINERS = ("+", ",", "&", "and", "และ")
TIMES_OF_DAY = {"1": 1, "2": 2, "3": 3, "4": 4}
EXCEPT_WORDS = ("except",)
WEEKDAY_STEMS = ("mon", "tue", "tues", "wed", "wednes", "thu", "thur", "thurs", "fri", "sat", "satur", "sun")
THAI_VARIABLE = ("ยกเว้น", "สลับ", "วันจันทร์", "วันอังคาร", "วันพุธ", "วันพฤหัส", "วันศุกร์", "วันเสาร์", "วันอาทิตย์")


def _thai(ch: str) -> bool:
    return 0x0E00 <= ord(ch) <= 0x0E7F


def scan(text: str) -> list[tuple[str, str]]:
    s = " ".join(unicodedata.normalize("NFC", text).split()).lower().replace("×", "x")
    lexemes = sorted(THAI_LEXEMES, key=len, reverse=True)
    out: list[tuple[str, str]] = []
    pos = 0
    thai_other = False  # previous pair is unmatched Thai text that may be extended
    while pos < len(s):
        ch = s[pos]
        if ch == " ":
            pos += 1
            thai_other = False
            continue
        if ch in "0123456789":
            end = pos
            while end < len(s) and s[end] in "0123456789":
                end += 1
            if end + 1 < len(s) and s[end] == "." and s[end + 1] in "0123456789":
                end += 1
                while end < len(s) and s[end] in "0123456789":
                    end += 1
            out.append(("N", s[pos:end]))
            pos, thai_other = end, False
            continue
        if unicodedata.numeric(ch, None) is not None:
            out.append(("U", ch))
            pos, thai_other = pos + 1, False
            continue
        if _thai(ch):
            hit = ""
            for lex in lexemes:
                if s[pos:pos + len(lex)] != lex:
                    continue
                if lex in BARE_UNITS:  # undotted "มก"/"มล" is a unit only as a word of its own (not "มกราคม")
                    before = s[pos - 1] if pos else " "
                    after = s[pos + len(lex)] if pos + len(lex) < len(s) else " "
                    if _thai(before) or _thai(after):
                        continue
                hit = lex
                break
            if hit:
                out.append(("T", hit))
                pos, thai_other = pos + len(hit), False
            elif thai_other:
                out[-1] = ("O", out[-1][1] + ch)
                pos += 1
            else:
                out.append(("O", ch))
                pos, thai_other = pos + 1, True
            continue
        thai_other = False
        if ch.isalpha():
            end = pos
            while end < len(s) and s[end].isalpha() and not _thai(s[end]):
                end += 1
            word = s[pos:end]
            out.append(("S" if word == "x" else "W", word))
            pos = end
            continue
        out.append(("S" if ch in SYMBOL_CHARS else "O", ch))
        pos += 1
    return out


class _Walk:
    """One left-to-right pass over the scanned pairs."""

    def __init__(self, pairs: list[tuple[str, str]]):
        self.p = pairs
        self.used = [False] * len(pairs)
        self.strengths: set[tuple[Fraction, str]] = set()
        self.quantities: set[Fraction] = set()
        self.liquid = False
        self.daily_total = False

    # -- primitives
    def t(self, i: int) -> str:
        return self.p[i][1] if 0 <= i < len(self.p) else ""

    def k(self, i: int) -> str:
        return self.p[i][0] if 0 <= i < len(self.p) else ""

    def whole(self, i: int) -> Fraction | None:
        v = self.t(i)
        if self.k(i) == "N" and "." not in v and v[:1] != "0":
            return Fraction(int(v))
        return None

    def amount(self, i: int) -> Fraction | None:
        """INT or decimal within 0 < v <= 10, 4v whole; no leading zero except 0.x."""
        v = self.t(i)
        if self.k(i) != "N":
            return None
        head = v.split(".")[0]
        if len(head) > 1 and head[0] == "0" or head == "0" and "." not in v:
            return None
        f = Fraction(v)
        return f if Fraction(0) < f <= 10 and (f * 4).denominator == 1 else None

    def fraction(self, i: int) -> tuple[Fraction, int] | None:
        if self.t(i) == "½":
            return Fraction(1, 2), 1
        if self.t(i) == "¼":
            return Fraction(1, 4), 1
        if self.t(i) == "¾":
            return Fraction(3, 4), 1
        if self.k(i) == "N" and self.t(i + 1) == "/" and self.k(i + 2) == "N":
            pair = self.t(i) + "/" + self.t(i + 2)
            if pair in ("1/2", "1/4", "3/4"):
                return Fraction(int(self.t(i)), int(self.t(i + 2))), 3
        return None

    def strength_at(self, i: int) -> tuple[Fraction, str] | None:
        if self.k(i) != "N" or self.t(i - 1) == "/" or self.t(i + 1) not in UNIT_OF:
            return None
        v = Fraction(self.t(i))
        return (v, UNIT_OF[self.t(i + 1)]) if v > 0 else None

    def take(self, i: int, n: int) -> int:
        for j in range(i, i + n):
            self.used[j] = True
        return i + n

    # -- quantity forms usable after ครั้งละ / วันละ: returns (value, length)
    def small_quantity(self, i: int) -> tuple[Fraction, int] | None:
        w = self.whole(i)
        # N เม็ดครึ่ง
        if w is not None and self.t(i + 1) in TH_QW and self.t(i + 2) == "ครึ่ง":
            return w + Fraction(1, 2), 3
        # mixed number
        if w is not None:
            gap = 1 if self.t(i + 1) in ("-", "and", "และ") else 0
            fr = self.fraction(i + 1 + gap)
            if fr and self.t(i + 1 + gap + fr[1]) in QW:
                return w + fr[0], 1 + gap + fr[1] + 1
        if self.t(i) == "ครึ่ง" and self.t(i + 1) in TH_QW:
            return Fraction(1, 2), 2
        a = self.amount(i)
        if a is not None and self.t(i + 1) in QW:
            return a, 2
        fr = self.fraction(i)
        if fr and self.t(i + fr[1]) in QW:
            return fr[0], fr[1] + 1
        return None

    # -- the cascade
    def step(self, i: int) -> int:
        t, k = self.t(i), self.k(i)
        if k == "N":
            # L1: NUM MASS / NUM? VOL (NUM VOL)?
            if self.t(i + 1) in MASS and self.t(i + 2) == "/":
                j = i + 3 + (1 if self.k(i + 3) == "N" else 0)
                if self.t(j) in VOLUME:
                    j += 1
                    if self.k(j) == "N" and self.t(j + 1) in VOLUME:
                        j += 2
                    self.liquid = True
                    return self.take(i, j - i)
            # S3 chain, else S1
            first = self.strength_at(i)
            if first:
                chain, j = [first], i + 2
                while True:
                    nxt = j + 1 if self.t(j) in S3_JOINERS else j
                    more = self.strength_at(nxt)
                    if not more:
                        break
                    chain.append(more)
                    j = nxt + 2
                if len(set(chain)) >= 2:
                    self.strengths.update(chain)
                    return self.take(i, j - i)
                self.strengths.add(first)
                return self.take(i, 2)
            # S2 combination
            if self.t(i + 1) == "/" and self.k(i + 2) == "N" and self.t(i + 3) in UNIT_OF:
                return self.take(i, 4)
        # Q5: N x M
        n = self.fraction(i)
        if n is None and self.amount(i) is not None:
            n = (self.amount(i), 1)
        if n and self.t(i + n[1]) == "x" and self.k(i + n[1] + 1) == "N" and self.t(i + n[1] + 1) in TIMES_OF_DAY:
            if self.t(i + n[1] + 2) not in QW:
                self.quantities.add(n[0])
                return self.take(i, n[1] + 2)
        # Q1-Q4 at this position
        q = self.small_quantity(i)
        if q:
            self.quantities.add(q[0])
            return self.take(i, q[1])
        # Q6 / Q7 / F3
        if t == "ครั้งละ":
            q = self.small_quantity(i + 1)
            if q:
                self.quantities.add(q[0])
                return self.take(i, 1 + q[1])
        if t == "วันละ":
            q = self.small_quantity(i + 1)
            if q:
                if q[0] > 1:
                    self.daily_total = True
                else:
                    self.quantities.add(q[0])
                return self.take(i, 1 + q[1])
        if t in ("วันละ", "สัปดาห์ละ", "อาทิตย์ละ", "เดือนละ"):
            j = i + 1 + (1 if self.whole(i + 1) is not None else 0)
            if self.t(j) == "ครั้ง":
                return self.take(i, j - i + 1)
        # F1
        hours = ("h", "hr", "hrs", "hour", "hours")
        if t in ("q", "every") and self.whole(i + 1) is not None and self.t(i + 2) in hours:
            return self.take(i, 3)
        if t == "ทุก" and self.whole(i + 1) is not None and self.t(i + 2) in ("ชั่วโมง", "ชม."):
            return self.take(i, 3)
        # F2
        periods = ("day", "daily", "week", "weekly", "month", "monthly")
        j = None
        if t in ("once", "twice", "thrice"):
            j = i + 1
        elif (self.whole(i) is not None or t in ("one", "two", "three", "four")) and self.t(i + 1) in ("time", "times"):
            j = i + 2
        if j is not None:
            if self.t(j) in ("a", "per"):
                j += 1
            if self.t(j) in periods:
                return self.take(i, j - i + 1)
        return i + 1

    def numberlike(self, i: int) -> bool:
        return self.k(i) in ("N", "U") or self.t(i) in EN_WORDS or (self.k(i) == "T" and self.t(i) in TH_WORDS)

    def numericish(self, i: int) -> bool:
        if self.k(i) == "S" or self.t(i) in LINKS:
            return self.numberlike(i - 1) or self.numberlike(i + 1)
        return self.numberlike(i) or self.t(i) in UNIT_OF or self.t(i) in QW


def _variable(text: str, pairs: list[tuple[str, str]]) -> bool:
    for kind, word in pairs:
        if kind != "W":
            continue
        if word in EXCEPT_WORDS or word.startswith("alternat"):
            return True
        for stem in WEEKDAY_STEMS:
            if word in (stem, stem + "s", stem + "day", stem + "days"):
                return True
    return any(w in text for w in THAI_VARIABLE)


def reference_parse(text: str) -> tuple[str, float | None, str | None, float | None]:
    pairs = scan(text)
    walk = _Walk(pairs)
    i = 0
    while i < len(pairs):
        i = walk.step(i)
    leftover = [j for j in range(len(pairs)) if walk.numericish(j) and not walk.used[j]]
    if (_variable(text, pairs) or walk.liquid or len(walk.strengths) > 1 or leftover
            or len(walk.quantities) > 1 or walk.daily_total):
        return "unverifiable", None, None, None
    quantity = float(next(iter(walk.quantities))) if walk.quantities else None
    if not walk.strengths:
        return "not_stated", None, None, quantity
    ((value, unit),) = walk.strengths
    return "resolved", float(value), unit, quantity


def reference_reason_hint(text: str) -> str:
    """Diagnostic only (printed on failure): which unverifiable condition the reference saw."""
    pairs = scan(text)
    walk = _Walk(pairs)
    i = 0
    while i < len(pairs):
        i = walk.step(i)
    left = [pairs[j][1] for j in range(len(pairs)) if walk.numericish(j) and not walk.used[j]]
    return (f"variable={_variable(text, pairs)} liquid={walk.liquid} strengths={sorted(walk.strengths)} "
            f"quantities={sorted(walk.quantities)} daily_total={walk.daily_total} leftover={left}")
