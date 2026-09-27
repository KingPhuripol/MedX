"""Independent reference reader for the s5r3 dose grammar (spec §G1-§G2), used only by the fuzz test.

Written from the spec, not from ``app.pharma.mock_rules``: it imports nothing from ``app`` and uses no
regular expressions. Technique: a character scanner builds (kind, text) pairs, then one hand-written
priority cascade walks them left to right (longer forms are tried before their prefixes).

``reference_parse(text) -> (dose_status, dose_value, dose_unit, quantity, reason)``.
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
                "ชม.", "นาที", "ต่อ", "มก.", "มก", "มิลลิกรัม", "กรัม", "ไมโครกรัม", "ยูนิต", "มล.", "มล", "และ", "หรือ", "ถึง") + TH_WORDS
BARE_UNITS = ("มก", "มล")
SYMBOL_CHARS = "/⁄.,-–—~x+&"
LINKS = ("to", "or", "and", "ถึง", "หรือ", "และ")
RANGE_LINKS = ("-", "–", "—", "~") + LINKS
S3_JOINERS = ("+", ",", "&", "and", "และ")
TIMES_OF_DAY = {"1": 1, "2": 2, "3": 3, "4": 4}
# rev 3 QF: what may follow a Q4b "ครึ่ง" (besides the end, a T1 start and an F1-F3 start).
AFTER_HALF_THAI = ("ก่อน", "หลัง", "พร้อม", "เช้า", "กลางวัน", "เที่ยง", "เย็น", "ค่ำ", "ตอน", "เวลา", "เมื่อ", "วันละ", "ทุก")
AFTER_HALF_LATIN = ("od", "bd", "bid", "tid", "qid", "qd", "hs", "prn", "po", "ac", "pc", "daily", "once", "twice", "thrice",
                    "every", "before", "after", "with")
TAIL_OK = " .,;:()[]+&"  # rev 3 R1 (c): the only characters an anchor's tail may hold
PERIODS_AFTER_A = ("day", "week", "month")  # rev 3 R1 (b): "a day", "a week", "a month"
HALF = "ครึ่ง"
TIME_TH = ("ชั่วโมง", "ชม", "ช.ม.", "นาที")  # T1: text right after ครึ่ง starting with one of these is a time
TIME_EN = ("h", "hr", "hrs", "hour", "hours", "min", "mins", "minute", "minutes")
EXCEPT_WORDS = ("except",)
WEEKDAY_STEMS = ("mon", "tue", "tues", "wed", "wednes", "thu", "thur", "thurs", "fri", "sat", "satur", "sun")
THAI_VARIABLE = ("ยกเว้น", "สลับ", "วันจันทร์", "วันอังคาร", "วันพุธ", "วันพฤหัส", "วันศุกร์", "วันเสาร์", "วันอาทิตย์")


def _thai(ch: str) -> bool:
    return 0x0E00 <= ord(ch) <= 0x0E7F


# rev 3 G1: hidden characters. General category Cc/Cf/Co/Cs/Cn, or one of these code points / inclusive ranges.
HIDDEN_KINDS = ("Cc", "Cf", "Co", "Cs", "Cn")
HIDDEN_RANGES = ((0x034F, 0x034F), (0x115F, 0x1160), (0x17B4, 0x17B5), (0x180B, 0x180D), (0x180F, 0x180F),
                 (0x2800, 0x2800), (0x3164, 0x3164), (0xFE00, 0xFE0F), (0xFFA0, 0xFFA0), (0xE0100, 0xE01EF))


def hidden(ch: str) -> bool:
    if unicodedata.category(ch) in HIDDEN_KINDS:
        return True
    cp = ord(ch)
    return any(lo <= cp <= hi for lo, hi in HIDDEN_RANGES)


def slashy(ch: str) -> bool:
    """rev 3 G1: any character named ...SOLIDUS... or ...SLASH..., plus SET MINUS."""
    if ord(ch) == 0x2216:
        return True
    words = unicodedata.name(ch, "").split()
    return any("SOLIDUS" in w or "SLASH" in w for w in words)


def _latin_letter(ch: str) -> bool:
    return ch.isalpha() and not _thai(ch) and not hidden(ch) and not slashy(ch)


def _time_follows(s: str, pos: int) -> bool:
    """Is the text at ``pos`` (one optional space skipped) a Thai time word, or an EN time word?"""
    rest = s[pos + 1:] if s[pos:pos + 1] == " " else s[pos:]
    for prefix in TIME_TH:
        if rest[:len(prefix)] == prefix:
            return True
    end = 0
    while end < len(rest) and _latin_letter(rest[end]):
        end += 1
    return rest[:end] in TIME_EN


def scan(text: str) -> list[tuple[str, str]]:
    return _scan(text)[1]


def _scan(text: str) -> tuple[str, list[tuple[str, str]], list[int]]:
    """Returns the normalised line, its (kind, text) pairs and the end offset of each pair."""
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
        if hidden(ch):  # its own pair, never consumed
            out.append(("I", ch))
            pos, thai_other = pos + 1, False
            continue
        if slashy(ch):  # its own pair; only an ASCII "/" inside FRAC, S2 or L1 is consumed
            out.append(("L", ch))
            pos, thai_other = pos + 1, False
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
                pos, thai_other = pos + len(hit), False
                out.append(("H" if hit == HALF and _time_follows(s, pos) else "T", hit))
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
            while end < len(s) and _latin_letter(s[end]):
                end += 1
            word = s[pos:end]
            out.append(("S" if word == "x" else "W", word))
            pos = end
            continue
        out.append(("S" if ch in SYMBOL_CHARS else "O", ch))
        pos += 1
    ends, at = [], 0
    for _, txt in out:  # pairs appear in order and hold every non-space character of s
        while s[at] == " ":
            at += 1
        at += len(txt)
        ends.append(at)
    return s, out, ends


def _latin_run(s: str, pos: int) -> str:
    end = pos
    while end < len(s) and _latin_letter(s[end]):
        end += 1
    return s[pos:end]


def _per_follows(s: str, pos: int) -> bool:
    """rev 3 R1 (b): Latin "per", Thai text beginning with "ต่อ", or Latin "a" then an optional space and a period."""
    if s[pos:pos + 3] == "ต่อ":
        return True
    word = _latin_run(s, pos)
    if word == "per":
        return True
    if word[:1] == "a" and word[1:] in PERIODS_AFTER_A:
        return True
    if word == "a":
        nxt = pos + 1 + (1 if s[pos + 1:pos + 2] == " " else 0)
        return _latin_run(s, nxt) in PERIODS_AFTER_A
    return False


class _Walk:
    """One left-to-right pass over the scanned pairs."""

    def __init__(self, pairs: list[tuple[str, str]], s: str = "", ends: list[int] | None = None):
        self.p = pairs
        self.s = s
        self.ends = ends or []
        self.anchors: list[int] = []  # last pair of each S1 / Q1-Q5 (inner of Q6/Q7)
        self.broken_tail = False
        self.used = [False] * len(pairs)
        self.strengths: set[tuple[Fraction, str]] = set()
        self.quantities: set[Fraction] = set()
        self.liquid = False
        self.daily_total = False
        self.half_conflict = False  # "INT เม็ด ครึ่ง<time>": half a tablet or half an hour
        self.per_unit = False

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

    @staticmethod
    def within(v: Fraction) -> bool:
        return Fraction(0) < v <= 10 and (v * 4).denominator == 1

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
        # N เม็ดครึ่ง, only when the ครึ่ง has an allowed follower (rev 3 QF)
        if w is not None and self.t(i + 1) in TH_QW and self.t(i + 2) == HALF and self.half_followed(i + 2):
            return (w + Fraction(1, 2), 3) if self.within(w + Fraction(1, 2)) else None
        # mixed number
        if w is not None:
            gap = 1 if self.t(i + 1) in ("-", "and", "และ") else 0
            fr = self.fraction(i + 1 + gap)
            if fr and self.t(i + 1 + gap + fr[1]) in QW and self.within(w + fr[0]):
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

    def half_followed(self, h: int) -> bool:
        """rev 3 QF, on the characters after the ครึ่ง at pair ``h`` (one optional space skipped)."""
        pos = self.ends[h]
        if self.s[pos:pos + 1] == " ":
            pos += 1
        rest = self.s[pos:]
        if not rest:
            return True
        if rest.startswith(HALF) and _time_follows(self.s, pos + len(HALF)):
            return True
        if any(rest.startswith(w) for w in AFTER_HALF_THAI):
            return True
        if _latin_run(self.s, pos) in AFTER_HALF_LATIN:
            return True
        return self.freq_len(h + 1) > 0  # the next pair starts at ``pos``

    def freq_len(self, i: int) -> int:
        """F1 / F2 / F3 starting at pair ``i``: its length, else 0."""
        t = self.t(i)
        if t in ("วันละ", "สัปดาห์ละ", "อาทิตย์ละ", "เดือนละ"):
            j = i + 1 + (1 if self.whole(i + 1) is not None else 0)
            if self.t(j) == "ครั้ง":
                return j - i + 1
        hours = ("h", "hr", "hrs", "hour", "hours")
        if t in ("q", "every") and self.whole(i + 1) is not None and self.t(i + 2) in hours:
            return 3
        if t == "ทุก" and self.whole(i + 1) is not None and self.t(i + 2) in ("ชั่วโมง", "ชม."):
            return 3
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
                return j - i + 1
        return 0

    def check_half_followers(self) -> None:
        for j in range(len(self.p)):
            if self.whole(j) is not None and self.t(j + 1) in TH_QW and self.t(j + 2) == HALF:
                if not self.half_followed(j + 2):
                    self.half_conflict = True

    def liquid_len(self, i: int) -> int:
        """L1: NUM MASS / NUM? VOL (NUM VOL)?; returns its length or 0."""
        if self.k(i) != "N" or self.t(i + 1) not in MASS or self.t(i + 2) != "/":
            return 0
        j = i + 3 + (1 if self.k(i + 3) == "N" else 0)
        if self.t(j) not in VOLUME:
            return 0
        j += 1
        if self.k(j) == "N" and self.t(j + 1) in VOLUME:
            j += 2
        return j - i

    def check_tails(self) -> None:
        """rev 3 R1 on every anchor: the tail is the run after it with no letter and no number."""
        for a in self.anchors:
            if self.t(a) in MASS and self.liquid_len(a - 1):
                continue
            start = stop = self.ends[a]
            while stop < len(self.s) and unicodedata.category(self.s[stop])[:1] not in ("L", "N"):
                stop += 1
            tail = self.s[start:stop]
            if any(slashy(c) for c in tail) or _per_follows(self.s, stop):
                self.per_unit = True
            elif any(c not in TAIL_OK for c in tail):
                self.broken_tail = True

    # -- the cascade
    def step(self, i: int) -> int:
        t, k = self.t(i), self.k(i)
        if k == "H":  # T1: half an hour / half a minute is a time, never a quantity
            return self.take(i, 1)
        if k == "N":
            n_liquid = self.liquid_len(i)
            if n_liquid:
                self.liquid = True
                return self.take(i, n_liquid)
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
                self.anchors.append(i + 1)
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
                self.anchors.append(i + n[1] + 1)
                return self.take(i, n[1] + 2)
        # Q1-Q4 at this position
        q = self.small_quantity(i)
        if q:
            self.quantities.add(q[0])
            self.anchors.append(i + q[1] - 1)
            return self.take(i, q[1])
        # Q6 / Q7 / F3
        if t == "ครั้งละ":
            q = self.small_quantity(i + 1)
            if q:
                self.quantities.add(q[0])
                self.anchors.append(i + q[1])
                return self.take(i, 1 + q[1])
        if t == "วันละ":
            q = self.small_quantity(i + 1)
            if q:
                if q[0] > 1:
                    self.daily_total = True
                else:
                    self.quantities.add(q[0])
                self.anchors.append(i + q[1])
                return self.take(i, 1 + q[1])
        n_freq = self.freq_len(i)  # F3, F1, F2
        if n_freq:
            return self.take(i, n_freq)
        return i + 1

    def numberlike(self, i: int) -> bool:
        return self.k(i) in ("N", "U", "H") or self.t(i) in EN_WORDS or (self.k(i) == "T" and self.t(i) in TH_WORDS)

    def numericish(self, i: int) -> bool:
        if self.k(i) in ("I", "L"):  # hidden and slash-like characters: numeric-ish wherever they appear
            return True
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


def _walk(text: str) -> tuple[list[tuple[str, str]], _Walk]:
    s, pairs, ends = _scan(text)
    walk = _Walk(pairs, s, ends)
    i = 0
    while i < len(pairs):
        i = walk.step(i)
    walk.check_tails()
    walk.check_half_followers()
    return pairs, walk


def reference_parse(text: str) -> tuple[str, float | None, str | None, float | None, str | None]:
    pairs, walk = _walk(text)
    leftover = [j for j in range(len(pairs)) if walk.numericish(j) and not walk.used[j]]
    if _variable(text, pairs):
        reason = "variable_regimen"
    elif walk.liquid:
        reason = "liquid_volume"
    elif len(walk.strengths) > 1:
        reason = "multiple_strengths"
    elif walk.per_unit:
        reason = "per_unit_amount"
    elif any(walk.t(j) in RANGE_LINKS and walk.numericish(j - 1) and walk.numericish(j + 1) for j in leftover):
        reason = "range"
    elif len(walk.quantities) > 1 or walk.daily_total or walk.half_conflict:
        reason = "ambiguous_quantity"
    elif leftover or walk.broken_tail:
        reason = "unparsed_token"
    else:
        reason = None
    if reason:
        return "unverifiable", None, None, None, reason
    quantity = float(next(iter(walk.quantities))) if walk.quantities else None
    if not walk.strengths:
        return "not_stated", None, None, quantity, None
    ((value, unit),) = walk.strengths
    return "resolved", float(value), unit, quantity, None


def reference_reason_hint(text: str) -> str:
    """Diagnostic only (printed on failure): which unverifiable condition the reference saw."""
    pairs, walk = _walk(text)
    left = [pairs[j][1] for j in range(len(pairs)) if walk.numericish(j) and not walk.used[j]]
    return (f"variable={_variable(text, pairs)} liquid={walk.liquid} strengths={sorted(walk.strengths)} "
            f"per_unit={walk.per_unit} quantities={sorted(walk.quantities)} daily_total={walk.daily_total} "
            f"half_conflict={walk.half_conflict} broken_tail={walk.broken_tail} leftover={left}")
