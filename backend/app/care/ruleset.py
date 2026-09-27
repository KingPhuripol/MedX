"""Care rule set loader. The file is pinned by SHA-256 to ``CARE_RULES_VERSION``; a changed file without a
version bump fails to load (fail closed)."""

from __future__ import annotations

import hashlib
import json
from functools import lru_cache
from pathlib import Path
from typing import Any

RULES_PATH = Path(__file__).with_name("rules") / "care_rules_v1.json"
CARE_RULES_VERSION = "care-rules-1.0.0"
CARE_RULES_SHA256 = "8f04f66fbc901f13f63fb866b8add38506df5f99f5782f679d6caf397082a10c"


def file_sha256(path: Path = RULES_PATH) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load(path: Path = RULES_PATH, pinned_sha256: str = CARE_RULES_SHA256) -> dict[str, Any]:
    if file_sha256(path) != pinned_sha256:
        raise RuntimeError("care rules file changed without a CARE_RULES_VERSION bump")
    doc = json.loads(path.read_text(encoding="utf-8"))
    if doc.get("version") != CARE_RULES_VERSION:
        raise RuntimeError("care rules file version does not match CARE_RULES_VERSION")
    return doc


@lru_cache(maxsize=1)
def rules() -> dict[str, Any]:
    return load()
