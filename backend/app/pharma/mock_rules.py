"""Deterministic rule-based mock for ``pharma.extract.v1`` and ``pharma.phrase.v1``.

Registered through the gateway MockProvider task-handler hook. No network, no randomness.
Fields that are not stated in the text stay ``None``; nothing is defaulted.
"""

from __future__ import annotations

import re
from typing import Any

EXTRACT_TASK = "pharma.extract.v1"
PHRASE_TASK = "pharma.phrase.v1"
# Bumped when the deterministic parsing patterns change (recorded on every run).
MOCK_RULES_VERSION = "s5-mock-rules-1.1.0"

_NUM = r"(\d+(?:\.\d+)?)"
_UNITS = {
    "mg": "mg", "มก": "mg", "มก.": "mg", "มิลลิกรัม": "mg",
    "g": "g", "gm": "g", "กรัม": "g",
    "mcg": "mcg", "µg": "mcg", "ug": "mcg", "ไมโครกรัม": "mcg",
    "unit": "unit", "units": "unit", "u": "unit", "iu": "unit", "ยูนิต": "unit",
    "ml": "ml", "มล": "ml", "มล.": "ml",
}
_UNIT_ALT = "|".join(sorted((re.escape(u) for u in _UNITS), key=len, reverse=True))
# Latin units must end at a word boundary; Thai units are matched as written.
DOSE_RE = re.compile(rf"(?<![\w/]){_NUM}\s*({_UNIT_ALT})(?![A-Za-z])", re.IGNORECASE)
QTY_RE = re.compile(r"(?<!\w)\d+\s*(?:tabs?|tablets?|caps?|capsules?|เม็ด|แคปซูล)(?![A-Za-z])", re.IGNORECASE)
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
    (re.compile(r"วันละ\s*(?:1\s*)?ครั้ง|ก่อนนอน"), "q24h"),
    # Thai meal-time slots: morning-evening, morning-noon-evening, (+ bedtime).
    (re.compile(r"เช้า\s*[-,/]?\s*กลางวัน\s*[-,/]?\s*เย็น\s*[-,/]?\s*ก่อนนอน"), "q6h"),
    (re.compile(r"เช้า\s*[-,/]?\s*กลางวัน\s*[-,/]?\s*เย็น"), "q8h"),
    (re.compile(r"เช้า\s*[-,/]?\s*เย็น"), "q12h"),
)
TIMES_RE = re.compile(r"(?<![\w.])\d+\s*[x×]\s*([1-4])(?!\d)", re.IGNORECASE)
_TIMES_CODE = {"1": "q24h", "2": "q12h", "3": "q8h", "4": "q6h"}
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


def parse_entry(text: str) -> dict[str, Any]:
    """Parse one free-text medication line (EN/TH) into the extract schema."""
    raw = " ".join(text.split())
    dose_m = DOSE_RE.search(raw)
    dose_value = float(dose_m.group(1)) if dose_m else None
    dose_unit = _UNITS[dose_m.group(2).lower()] if dose_m else None

    route = next((code for pat, code in ROUTE_PATTERNS if pat.search(raw)), None)

    freq = None
    times = TIMES_RE.search(raw)
    if times:
        freq = _TIMES_CODE[times.group(1)]
    else:
        # Earliest phrase wins; at the same start the longest phrase wins ("เช้า กลางวัน เย็น" over "เช้า เย็น").
        hits = [(m.start(), -len(m.group(0)), code) for pat, code in FREQ_PATTERNS if (m := pat.search(raw))]
        every = EVERY_RE.search(raw)
        code = _EVERY_CODE.get(next(g for g in every.groups() if g is not None).lstrip("0")) if every else None
        if every and code:
            hits.append((every.start(), -len(every.group(0)), code))
        if hits:
            freq = min(hits, key=lambda h: (h[0], h[1]))[2]

    boundary = _first_start(
        raw,
        [DOSE_RE, QTY_RE, TIMES_RE, EVERY_RE, *(p for p, _ in ROUTE_PATTERNS), *(p for p, _ in FREQ_PATTERNS)],
    )
    name = raw[:boundary].strip(" ,;:-") or raw
    return {
        "drug_name_raw": name,
        "dose_value": dose_value,
        "dose_unit": dose_unit,
        "route": route,
        "frequency_code": freq,
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
