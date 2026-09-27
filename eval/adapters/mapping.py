"""Loader and lookups for the e1 mapping table (slice e1). Research prototype - not for clinical use.

The table is ``mappings/e1_mapping_v1.json``; ``render_md`` writes the committed ``.md`` view of it.
"""

from __future__ import annotations

import json
import re
import unicodedata
from functools import lru_cache
from pathlib import Path
from typing import Any

MAPPING_DIR = Path(__file__).resolve().parent / "mappings"
MAPPING_PATH = MAPPING_DIR / "e1_mapping_v1.json"
MAPPING_MD_PATH = MAPPING_DIR / "e1_mapping_v1.md"
UNMAPPABLE = "UNMAPPABLE"
NOT_EVALUABLE = "NOT_EVALUABLE"
BANNER = "System Evaluation on synthetic data - not clinical performance"
TEXT_RULES_S1R = ("RF-FAST", "RF-ACUTE-CHEST-PAIN", "RF-THUNDERCLAP", "RF-ANAPHYLAXIS")
TEXT_RULES_S4 = ("RF-CHEST", "RF-STROKE", "RF-THUNDER", "RF-ANAPH")


def nfc(s: str) -> str:
    return unicodedata.normalize("NFC", s)


@lru_cache(maxsize=4)
def load(path: str = str(MAPPING_PATH)) -> dict[str, Any]:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def rows(section: str, m: dict[str, Any] | None = None) -> list[dict[str, Any]]:
    return (m or load())["sections"][section]["rows"]


def table(section: str, m: dict[str, Any] | None = None) -> dict[str, Any]:
    return {r["source"]: r["target"] for r in rows(section, m)}


# ---------------------------------------------------------------- departments


def gold_department(target: str, evaluable: bool, m: dict[str, Any] | None = None) -> tuple[str | None, str]:
    """(E code or None, route) for an S1r gold department."""
    if not evaluable or target == NOT_EVALUABLE:
        return None, "abstention_only"
    row = next(r for r in rows("department_s1r", m) if r["source"] == target)
    return (None, row["route"]) if row["target"] == UNMAPPABLE else (row["target"], row["route"])


def s4_to_e(codes: list[str], m: dict[str, Any] | None = None) -> list[str]:
    """Map an ordered S4 department list to E, de-duplicated, keeping the first occurrence."""
    t = table("department_s4", m)
    out: list[str] = []
    for c in codes:
        e = t[c]
        if e not in out:
            out.append(e)
    return out


# ---------------------------------------------------------------- red flags


def s1r_rule_targets(m: dict[str, Any] | None = None) -> dict[str, list[str] | None]:
    """S1r rule -> S4 rules that detect it, or None if unmappable."""
    return {k: (None if v == UNMAPPABLE else list(v)) for k, v in table("red_flag_s1r", m).items()}


def detected_s1r_rules(fired_s4: list[str], m: dict[str, Any] | None = None) -> list[str]:
    """S1r rules detected by the fired S4 rules (sorted)."""
    fired = set(fired_s4)
    return sorted(r for r, tg in s1r_rule_targets(m).items() if tg and fired & set(tg))


def mapped_s4_rules(m: dict[str, Any] | None = None) -> set[str]:
    return {k for k, v in table("red_flag_s4", m).items() if v != UNMAPPABLE}


def outside_registry_s4_rules(m: dict[str, Any] | None = None) -> list[str]:
    return sorted(k for k, v in table("red_flag_s4", m).items() if v == UNMAPPABLE)


# ---------------------------------------------------------------- voice gold

_ISO = re.compile(r"^P(T)?(\d+)([HMDWY])$")


def duration_iso(value: int, unit: str, m: dict[str, Any] | None = None) -> str:
    fmt = table("duration_unit", m)[unit]
    n = 7 * int(value) if "{7n}" in fmt else int(value)
    return fmt.replace("{7n}", str(n)).replace("{n}", str(n))


def normalize_iso(v: str) -> str:
    """PnW -> P(7n)D; everything else unchanged (months and years are not converted)."""
    mm = _ISO.match(v)
    if mm and not mm.group(1) and mm.group(3) == "W":
        return f"P{7 * int(mm.group(2))}D"
    return v


def cc_acceptable(code: str, m: dict[str, Any] | None = None) -> list[str] | None:
    """Acceptable S3 codes for an S1r CC code, or None when UNMAPPABLE."""
    t = table("chief_complaint_s1r_to_s3", m)[code]
    return None if t == UNMAPPABLE else list(t)


def allergy_gold(value: str, m: dict[str, Any] | None = None) -> str | None:
    t = table("allergy_value", m)[value]
    return None if t.startswith("(") else t


def s3_symptom(code: str, m: dict[str, Any] | None = None) -> str | None:
    t = table("s3_cc_to_s4_symptom", m)[code]
    return None if t == UNMAPPABLE else t.removeprefix("symptom.")


def consciousness_facts(value: str) -> dict[str, Any]:
    """ACVPU -> S4 vital facts (C = avpu A + new_confusion true)."""
    if value == "C":
        return {"avpu": "A", "new_confusion": True}
    if value in ("A", "V", "P", "U"):
        return {"avpu": value}
    raise ValueError(f"unknown consciousness value {value!r}")


# ---------------------------------------------------------------- rendering


def _cell(v: Any) -> str:
    if isinstance(v, list):
        v = ", ".join(v)
    return str(v).replace("|", "\\|").replace("\n", " ")


def render_md(m: dict[str, Any] | None = None) -> str:
    m = m or load()
    out = [f"# e1 mapping table ({m['mapping_version']})", "", f"> **{BANNER}**", "",
           "Generated from `e1_mapping_v1.json` by `python -m eval.adapters render-mapping`; do not edit by hand.", "",
           m["status"], ""]
    out += ["## Target conventions", ""] + [f"- `{k}`: {v}" for k, v in m["target_conventions"].items()] + [""]
    for key, sec in m["sections"].items():
        cols = ["source", "target"] + [c for c in ("icd10cm", "route") if any(c in r for r in sec["rows"])]
        cols += ["rationale", "source_ref"]
        out += [f"## {sec['title']} (`{key}`, {len(sec['rows'])} rows)", "", f"Scoring: {sec['scoring']}", "",
                f"> **{BANNER}**", "", "| " + " | ".join(cols) + " |", "|" + "---|" * len(cols)]
        for r in sec["rows"]:
            out.append("| " + " | ".join(_cell(r.get(c, "")) for c in cols) + " |")
        out.append("")
    out += ["## Known disagreements (reported as-is, flagged for D1)", ""] + [f"- {x}" for x in m["known_disagreements"]]
    out += ["", "## Replay deviations from live use", ""] + [f"- {x}" for x in m["replay_deviations"]]
    out += ["", "## Changelog (changes after the first dev run, with reason)", ""]
    out += [f"- {c['date']}: {c['change']} Reason: {c['reason']}" for c in m["changelog"]] or ["- none"]
    return "\n".join(out) + "\n"
