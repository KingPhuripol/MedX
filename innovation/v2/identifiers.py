"""Refuse text that looks like a real person's identifier (DEC-0006, DEC-0022).

The prototype accepts synthetic cases only. A Thai national ID, phone number, e-mail or
hospital number in free text is the most likely sign that someone typed a real patient,
so it is rejected before it is stored or sent to a model provider. A pattern check cannot
prove data is synthetic; it only stops the obvious leak.
"""
import re
from innovation.v2.store import DomainError

PATTERNS = {
    'THAI_NATIONAL_ID': re.compile(r'(?<!\d)\d[\s.-]?\d{4}[\s.-]?\d{5}[\s.-]?\d{2}[\s.-]?\d(?!\d)'),
    'PHONE': re.compile(r'(?<!\d)(?:\+66[\s.-]?|0)[2-9]\d?[\s.-]?\d{3}[\s.-]?\d{4}(?!\d)'),
    'EMAIL': re.compile(r'[\w.+-]+@[\w-]+\.[\w.-]+'),
    'HOSPITAL_NUMBER': re.compile(r'(?<![A-Za-z])(?:HN|AN|MRN)\s*[:#.]?\s*\d{4,}', re.IGNORECASE),
}


def guard(value):
    """Raise 422 if any string inside `value` matches an identifier pattern."""
    if isinstance(value, dict):
        for item in value.values():
            guard(item)
    elif isinstance(value, (list, tuple)):
        for item in value:
            guard(item)
    elif isinstance(value, str):
        found = sorted(name for name, pattern in PATTERNS.items() if pattern.search(value))
        if found:
            raise DomainError(422, 'POSSIBLE_REAL_IDENTIFIER', {'kinds': found})
