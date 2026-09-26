"""Strict JSON I/O shared by manifests, predictions and ledgers (slice s8r).

``NaN``, ``Infinity``, ``-Infinity`` and float literals that overflow to +/-inf (e.g. ``1e999``) are
rejected with ``NonFiniteValueError`` naming the file and line. Research prototype - not for clinical use.
"""

from __future__ import annotations

import datetime as _dt
import hashlib
import json
import math
import os
import re
from pathlib import Path
from typing import Any

from .metrics import NonFiniteValueError

# A JSON string literal (skipped) or a non-finite constant or a number literal.
_TOKEN = re.compile(r'"(?:[^"\\]|\\.)*"|(-?(?:Infinity|NaN))|(-?\d+(?:\.\d+)?(?:[eE][+-]?\d+)?)')


def canonical_bytes(obj: Any) -> bytes:
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False).encode("utf-8")


def sha256_bytes(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()


def utc_now() -> str:
    return _dt.datetime.now(_dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


class _NonFinite(Exception):
    pass


def _reject_constant(s: str) -> Any:
    raise _NonFinite(s)


def _finite_float(s: str) -> float:
    v = float(s)
    if not math.isfinite(v):
        raise _NonFinite(s)
    return v


def _locate(text: str) -> tuple[int, str]:
    """(1-based line, literal) of the first non-finite literal outside JSON strings."""
    for m in _TOKEN.finditer(text):
        lit = m.group(1) or m.group(2)
        if lit and (m.group(1) or not math.isfinite(float(lit))):
            return text.count("\n", 0, m.start()) + 1, lit
    return 1, "?"


def loads_strict(text: str, where: str, line: int | None = None) -> Any:
    """``json.loads`` that rejects NaN / +-Infinity / overflowing floats. ``where`` names the file."""
    try:
        return json.loads(text, parse_constant=_reject_constant, parse_float=_finite_float)
    except _NonFinite:
        n, lit = _locate(text)
        ln = line if line is not None else n
        raise NonFiniteValueError(
            f"{where} line {ln}: non-finite number {lit!r}; NaN/Infinity/overflow is rejected, never missing"
        ) from None


def load_json_file(path: str | os.PathLike[str]) -> Any:
    p = Path(path)
    return loads_strict(p.read_text(encoding="utf-8"), p.name)
