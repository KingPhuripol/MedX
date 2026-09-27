"""Step 3 helpers: deterministic templates and validation of model phrasing.

Phrasing is supplementary. It is matched to issues by ``issue_id`` only and can never add,
drop, retype, or re-rank issues. Rejected phrasing falls back to the template.
"""

from __future__ import annotations

from typing import Any

from pydantic import ValidationError

from .models import PhraseOutput

TEMPLATE_VERSION = "template-1.1.0"
SOURCE_LABELS = {
    "home_list": "home list",
    "patient_reported": "patient-reported list",
    "new_order": "new order",
    "allergy_record": "allergy record",
}
BANNED_PHRASES = (
    "discontinue",
    "stop",
    "increase",
    "decrease",
    "change the dose to",
    "prescribe",
    "หยุดยา",
    "เพิ่มขนาด",
)
# Reassurance phrasing (C6): model text that reassures instead of describing the issue falls back to the
# template. Generic phrases apply to every type; the others are anchored to the issue type (prefix).
REASSURANCE_GENERIC = ("no concern", "nothing to worry", "no action needed", "safe to", "ไม่มีปัญหา", "ปลอดภัย")
REASSURANCE_BY_TYPE: dict[str, tuple[str, ...]] = {
    "dose_mismatch": ("doses match", "same dose", "dose is consistent", "ขนาดยาตรงกัน"),
    "frequency_mismatch": ("frequencies match", "same frequency", "ความถี่ตรงกัน"),
    "allergy_": ("not allergic", "no allergy", "tolerated", "ไม่แพ้"),
    "duplication_": ("not a duplicate", "no duplication", "ไม่ซ้ำ"),
    "missing_field": ("dose is stated", "frequency is stated", "complete"),
    "omission": ("intentionally omitted", "was stopped on purpose"),
}
UNVERIFIABLE_WORDS = {
    "variable_regimen": "variable regimen",
    "liquid_volume": "liquid volume",
    "multiple_strengths": "more than one strength",
    "ambiguous_quantity": "conflicting quantities",
}
_TYPE_TITLES = {
    "allergy_direct": "direct allergy match",
    "allergy_class": "allergy to the drug class",
    "allergy_cross_reactivity": "possible cross-reactivity with a recorded allergy",
}


def _join(items: list[str]) -> str:
    if len(items) <= 1:
        return "".join(items)
    return ", ".join(items[:-1]) + " and " + items[-1]


def _num(value) -> str:
    return f"{value:g}" if isinstance(value, (int, float)) else str(value)


def _fmt_dose(src: dict) -> str:
    """Dose per administration as compared: ``3 mg × 2 = 6 mg`` or ``3 mg (quantity not stated; ...)``."""
    if src.get("dose_status") == "unverifiable":
        return f"dose could not be verified ({UNVERIFIABLE_WORDS.get(src.get('dose_unverifiable_reason'), 'unverifiable')})"
    if src.get("dose_value") is None:
        return "dose not stated"
    unit = src.get("dose_unit") or ""
    strength = f"{_num(src['dose_value'])} {unit}".strip()
    if src.get("quantity") is None:
        return f"{strength} (quantity not stated; stated amount used)"
    per = src.get("dose_per_administration")
    per = per if per is not None else src["dose_value"] * src["quantity"]
    return f"{strength} × {_num(src['quantity'])} = {_num(per)} {unit}".strip()


def phrase_input(issue: dict) -> dict[str, Any]:
    """The typed, minimal view of an issue that is sent to the phrasing step."""
    labels = []
    for src in issue["conflicting_sources"]:
        label = SOURCE_LABELS[src["source_type"]]
        if label not in labels:
            labels.append(label)
    return {
        "issue_id": issue["issue_id"],
        "type": issue["type"],
        "ingredients": list(issue["ingredients"]),
        "source_labels": labels,
        "sources": [
            {
                "label": SOURCE_LABELS[s["source_type"]],
                "presence": s.get("presence", "present"),
                "dose": _fmt_dose(s),
                "frequency": s.get("frequency_code") or (
                    "frequency not recognised" if s.get("frequency_status") == "not_recognised" else "frequency not stated"
                ),
            }
            for s in issue["conflicting_sources"]
        ],
        "unverifiable": issue.get("unverifiable", False),
        "possible_substitution": issue.get("possible_substitution", False),
        "detail": issue.get("detail", {}),
    }


def template_text(item: dict[str, Any]) -> str:
    drugs = _join(item["ingredients"])
    labels = _join(item["source_labels"])
    kind = item["type"]
    present = [s for s in item["sources"] if s["presence"] == "present"]
    if kind.startswith("allergy_"):
        allergen = item.get("detail", {}).get("allergy_text", "")
        med_labels = _join([lab for lab in item["source_labels"] if lab != "allergy record"])
        text = (
            f"Allergy check ({_TYPE_TITLES[kind]}): the allergy record lists \"{allergen}\", "
            f"and {drugs} appears in the {med_labels}."
        )
    elif kind == "duplication_ingredient":
        text = f"Possible duplicate: {drugs} appears in more than one active entry of the new order."
    elif kind == "duplication_class":
        classes = _join(item.get("detail", {}).get("classes", []))
        text = f"Possible same-class duplication ({classes}): {drugs} are active together in the new order."
    elif kind == "dose_mismatch":
        per = "; ".join(f"{s['label']}: {s['dose']}" for s in present)
        if item.get("unverifiable"):
            text = (f"The dose per administration of {drugs} could not be compared automatically between the "
                    f"{labels} because the units are of different kinds ({per}).")
        else:
            text = f"Dose per administration differs for {drugs} between the {labels} ({per})."
    elif kind == "frequency_mismatch":
        per = "; ".join(f"{s['label']}: {s['frequency']}" for s in present)
        text = f"Frequency differs for {drugs} between the {labels} ({per})."
    elif kind == "missing_field":
        detail = item.get("detail", {})
        field = detail.get("field", "dose or frequency")
        incomplete = item["sources"][0]["label"]
        others = _join([lab for lab in item["source_labels"] if lab != incomplete])
        status = detail.get("field_status", "not_stated")
        if status == "unverifiable":
            why = UNVERIFIABLE_WORDS.get(detail.get("unverifiable_reason"), "unverifiable")
            text = f"The {field} of {drugs} in the {incomplete} could not be verified ({why})"
        elif status == "not_recognised":
            text = f"The {field} of {drugs} in the {incomplete} was not recognised by the fixed pattern set"
        else:
            text = f"The {field} of {drugs} is not stated in the {incomplete}"
        text += f", so it could not be compared with the {others}." if others else "."
        text += " A value that was not read is not counted as a match."
    elif kind == "omission":
        listed = _join([lab for lab in item["source_labels"] if lab != "new order"])
        text = (
            f"{drugs} is listed in the {listed} but is absent from the new order, "
            "and no intent to end it is recorded."
        )
        if item.get("possible_substitution"):
            text += " A medicine of the same class is in the new order (possible substitution)."
    else:  # pragma: no cover - closed set
        raise ValueError(kind)
    return text + " For pharmacist review."


def validate_text(text: str, item: dict[str, Any]) -> str | None:
    """Return None if acceptable, else the rejection reason."""
    folded = text.casefold()
    for phrase in BANNED_PHRASES:
        if phrase.casefold() in folded:
            return "banned_phrase"
    anchored = [p for prefix, ps in REASSURANCE_BY_TYPE.items() if item["type"].startswith(prefix) for p in ps]
    for phrase in REASSURANCE_GENERIC + tuple(anchored):
        if phrase.casefold() in folded:
            return "reassurance_phrase"
    for label in item["source_labels"]:
        if label.casefold() not in folded:
            return "missing_source"
    for drug in item["ingredients"]:
        if drug.casefold() not in folded:
            return "missing_drug"
    return None


def parse_phrase_output(output: dict[str, Any] | None) -> tuple[dict[str, str] | None, str | None]:
    """Validate the phrase-step schema. Returns ({issue_id: text}, None) or (None, reason)."""
    if output is None:
        return None, "no_output"
    try:
        parsed = PhraseOutput.model_validate(output)
    except ValidationError:
        return None, "schema_invalid"
    return {p.issue_id: p.text for p in parsed.phrasings}, None
