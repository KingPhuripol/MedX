"""Deterministic rule-based mock for ``pharma.extract.v1`` and ``pharma.phrase.v1``.

Registered through the gateway MockProvider task-handler hook. No network, no randomness.
Fields that are not stated in the text stay ``None``; nothing is defaulted.
"""

from __future__ import annotations

import re
from typing import Any

EXTRACT_TASK = "pharma.extract.v1"
PHRASE_TASK = "pharma.phrase.v1"

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
FREQ_PATTERNS: tuple[tuple[re.Pattern[str], str], ...] = (
    (re.compile(r"(?<![A-Za-z])(?:prn|as needed|when needed)(?![A-Za-z])", re.IGNORECASE), "prn"),
    (re.compile(r"เวลาปวด|เมื่อมีอาการ|เมื่อจำเป็น"), "prn"),
    (re.compile(r"(?<![A-Za-z])(?:qid|q\.i\.d\.|four times (?:a )?daily|q6h)(?![A-Za-z])", re.IGNORECASE), "q6h"),
    (re.compile(r"(?<![A-Za-z])(?:tid|t\.i\.d\.|three times (?:a )?daily|q8h)(?![A-Za-z])", re.IGNORECASE), "q8h"),
    (re.compile(r"(?<![A-Za-z])(?:bid|b\.i\.d\.|twice (?:a )?daily|q12h)(?![A-Za-z])", re.IGNORECASE), "q12h"),
    (re.compile(r"(?<![A-Za-z])(?:od|qd|once (?:a )?daily|daily|q24h|hs|qhs|at bedtime)(?![A-Za-z])", re.IGNORECASE), "q24h"),
    (re.compile(r"วันละ\s*4\s*ครั้ง"), "q6h"),
    (re.compile(r"วันละ\s*3\s*ครั้ง"), "q8h"),
    (re.compile(r"วันละ\s*2\s*ครั้ง"), "q12h"),
    (re.compile(r"วันละ\s*(?:1\s*)?ครั้ง|ก่อนนอน"), "q24h"),
)
TIMES_RE = re.compile(r"(?<![\w.])\d+\s*[x×]\s*([1-4])(?!\d)", re.IGNORECASE)
_TIMES_CODE = {"1": "q24h", "2": "q12h", "3": "q8h", "4": "q6h"}


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
        hits = [(m.start(), code) for pat, code in FREQ_PATTERNS if (m := pat.search(raw))]
        if hits:
            freq = min(hits)[1]

    boundary = _first_start(
        raw,
        [DOSE_RE, QTY_RE, TIMES_RE, *(p for p, _ in ROUTE_PATTERNS), *(p for p, _ in FREQ_PATTERNS)],
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
