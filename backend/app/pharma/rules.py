"""Primary checker: pure, versioned reconciliation rules. No I/O, no model calls.

Each rule takes extracted medication items (with formulary ingredients) and returns issue drafts.
Severity order is fixed here and cannot be changed by model output.
"""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Iterable
from dataclasses import dataclass, field

from .formulary import Formulary, Resolution

RULES_VERSION = "s5-rules-1.1.0"
# Not a discrepancy type: a cross-source comparison that could not be made (a notice, never silence).
MISSING_FIELD_RULE = "missing_field@1.0.0"
RULE_VERSIONS: dict[str, str] = {
    "allergy_direct": "1.0.0",
    "allergy_class": "1.0.0",
    "allergy_cross_reactivity": "1.0.0",
    "duplication_ingredient": "1.0.0",
    "duplication_class": "1.0.0",
    "dose_mismatch": "1.0.0",
    "frequency_mismatch": "1.0.0",
    "omission": "1.0.0",
}
SEVERITY: dict[str, tuple[int, str]] = {
    "allergy_direct": (1, "high"),
    "allergy_class": (1, "high"),
    "allergy_cross_reactivity": (1, "high"),
    "duplication_ingredient": (2, "elevated"),
    "duplication_class": (2, "elevated"),
    "dose_mismatch": (3, "moderate"),
    "frequency_mismatch": (3, "moderate"),
    "omission": (4, "review"),
}
TYPE_ORDER = tuple(RULE_VERSIONS)
NOTICE_RANK = 5
_MASS = {"mg": 1.0, "g": 1000.0, "mcg": 0.001}


@dataclass(frozen=True)
class MedItem:
    """One readable, recognised-or-not medication entry from one source."""

    key: str  # "<source_index>:<entry_index>"
    source_type: str
    evidence_ref: str
    available_at_time: str
    raw_span: str
    drug_name_raw: str
    dose_value: float | None
    dose_unit: str | None
    route: str | None
    frequency_code: str | None
    ingredients: tuple[str, ...]
    discontinue_intent: bool = False

    @property
    def active(self) -> bool:
        return not self.discontinue_intent

    def as_source(self) -> dict:
        return {
            "source_type": self.source_type,
            "evidence_ref": self.evidence_ref,
            "available_at_time": self.available_at_time,
            "raw_span": self.raw_span,
            "presence": "present",
            "drug_name_raw": self.drug_name_raw,
            "dose_value": self.dose_value,
            "dose_unit": self.dose_unit,
            "route": self.route,
            "frequency_code": self.frequency_code,
        }


@dataclass(frozen=True)
class AllergyItem:
    index: int
    text: str
    evidence_ref: str
    available_at_time: str
    resolution: Resolution

    def as_source(self) -> dict:
        return {
            "source_type": "allergy_record",
            "evidence_ref": self.evidence_ref,
            "available_at_time": self.available_at_time,
            "raw_span": self.text,
            "presence": "present",
        }


@dataclass
class IssueDraft:
    type: str
    ingredients: tuple[str, ...]
    sources: list[dict]
    unverifiable: bool = False
    possible_substitution: bool = False
    notes: list[dict] = field(default_factory=list)
    detail: dict = field(default_factory=dict)

    @property
    def rule_id(self) -> str:
        return f"{self.type}@{RULE_VERSIONS[self.type]}"

    @property
    def severity_rank(self) -> int:
        return SEVERITY[self.type][0]

    @property
    def severity(self) -> str:
        return SEVERITY[self.type][1]

    def sort_key(self) -> tuple:
        first = self.sources[0]["evidence_ref"] if self.sources else ""
        return (self.severity_rank, TYPE_ORDER.index(self.type), self.ingredients, first, len(self.sources))


def _group_by_items(ing_to_items: dict[str, list[MedItem]]) -> list[tuple[tuple[str, ...], list[MedItem]]]:
    """Merge ingredients that are carried by exactly the same set of items (e.g. combinations)."""
    groups: dict[tuple[str, ...], list[str]] = defaultdict(list)
    item_by_key: dict[str, MedItem] = {}
    for ing, items in ing_to_items.items():
        keys = tuple(sorted({i.key for i in items}))
        groups[keys].append(ing)
        item_by_key.update({i.key: i for i in items})
    return [
        (tuple(sorted(ings)), [item_by_key[k] for k in keys])
        for keys, ings in sorted(groups.items(), key=lambda kv: sorted(kv[1]))
    ]


def _active_orders(items: Iterable[MedItem]) -> list[MedItem]:
    return [i for i in items if i.source_type == "new_order" and i.active and i.ingredients]


# --------------------------------------------------------------------------- duplication


def rule_duplication_ingredient(items: list[MedItem], form: Formulary) -> list[IssueDraft]:
    by_ing: dict[str, list[MedItem]] = defaultdict(list)
    for item in _active_orders(items):
        for ing in item.ingredients:
            by_ing[ing].append(item)
    dupes = {ing: its for ing, its in by_ing.items() if len({i.key for i in its}) >= 2}
    return [
        IssueDraft("duplication_ingredient", ings, [i.as_source() for i in its])
        for ings, its in _group_by_items(dupes)
    ]


def rule_duplication_class(items: list[MedItem], form: Formulary) -> list[IssueDraft]:
    orders = _active_orders(items)
    found: dict[tuple[str, ...], list[str]] = defaultdict(list)
    for class_id, meta in sorted(form.classes.items()):
        if not meta.get("duplication_relevant"):
            continue
        ings = sorted({ing for it in orders for ing in it.ingredients if class_id in form.classes_of(ing)})
        carriers = {it.key for it in orders if set(it.ingredients) & set(ings)}
        if len(ings) >= 2 and len(carriers) >= 2:
            found[tuple(ings)].append(class_id)
    out = []
    for ings, class_ids in sorted(found.items()):
        its = [it for it in orders if set(it.ingredients) & set(ings)]
        out.append(
            IssueDraft(
                "duplication_class",
                ings,
                [i.as_source() for i in its],
                detail={"classes": [form.classes[c]["name"] for c in class_ids]},
            )
        )
    return out


# --------------------------------------------------------------------------- mismatches


def _canonical_dose(item: MedItem) -> tuple[str, float] | None:
    if item.dose_value is None or item.dose_unit is None:
        return None
    unit = item.dose_unit.lower()
    if unit in _MASS:
        return ("mass", round(item.dose_value * _MASS[unit], 6))
    return (unit, round(item.dose_value, 6))


def _comparable_groups(items: list[MedItem]) -> dict[tuple[str, ...], list[MedItem]]:
    """Active entries grouped by identical ingredient set (a combination is compared only with itself)."""
    groups: dict[tuple[str, ...], list[MedItem]] = defaultdict(list)
    for item in items:
        if item.ingredients and item.active:
            groups[tuple(sorted(item.ingredients))].append(item)
    return groups


def _missing_notes(items: list[MedItem], field_name: str) -> list[dict]:
    return [
        {"kind": "missing_field", "field": field_name, "source_type": i.source_type, "evidence_ref": i.evidence_ref}
        for i in items
    ]


def rule_dose_mismatch(items: list[MedItem], form: Formulary) -> list[IssueDraft]:
    out = []
    for ings, group in sorted(_comparable_groups(items).items()):
        dosed = [(i, d) for i in group if (d := _canonical_dose(i)) is not None]
        missing = [i for i in group if _canonical_dose(i) is None]
        pairs = [
            (a, b)
            for n, (a, da) in enumerate(dosed)
            for (b, db) in dosed[n + 1:]
            if a.source_type != b.source_type and da != db
        ]
        if not pairs:
            continue  # a missing dose is not a match either: find_unchecked_comparisons() raises a notice
        families = {d[0] for _, d in dosed}
        out.append(
            IssueDraft(
                "dose_mismatch",
                ings,
                [i.as_source() for i, _ in dosed],
                unverifiable=len(families) > 1,
                notes=_missing_notes(missing, "dose"),
            )
        )
    return out


def rule_frequency_mismatch(items: list[MedItem], form: Formulary) -> list[IssueDraft]:
    out = []
    for ings, group in sorted(_comparable_groups(items).items()):
        known = [i for i in group if i.frequency_code is not None]
        missing = [i for i in group if i.frequency_code is None]
        differs = any(
            a.source_type != b.source_type and a.frequency_code != b.frequency_code
            for n, a in enumerate(known)
            for b in known[n + 1:]
        )
        if differs:
            out.append(
                IssueDraft(
                    "frequency_mismatch",
                    ings,
                    [i.as_source() for i in known],
                    notes=_missing_notes(missing, "frequency_code"),
                )
            )
    return out


_COMPARED_FIELDS = (("dose", _canonical_dose), ("frequency_code", lambda i: i.frequency_code))


def find_unchecked_comparisons(items: list[MedItem]) -> list[dict]:
    """Cross-source comparisons that could not be made because a field is not stated.

    For every active ingredient set present in 2 or more source types, each entry whose dose (value
    and unit) or frequency is null yields one record. A missing value is never read as agreement;
    the pipeline turns every record into a visible, audited ``missing_field`` notice.
    """
    out = []
    for ings, group in sorted(_comparable_groups(items).items()):
        if len({i.source_type for i in group}) < 2:
            continue
        for field_name, value_of in _COMPARED_FIELDS:
            known_in = sorted({i.source_type for i in group if value_of(i) is not None})
            for item in group:
                if value_of(item) is not None:
                    continue
                others = sorted({i.source_type for i in group if i.source_type != item.source_type})
                out.append({
                    "rule_id": MISSING_FIELD_RULE,
                    "field": field_name,
                    "ingredients": list(ings),
                    "source_type": item.source_type,
                    "evidence_ref": item.evidence_ref,
                    "raw_span": item.raw_span,
                    "compared_with": others,
                    "stated_in": [s for s in known_in if s != item.source_type],
                })
    return out


# --------------------------------------------------------------------------- omission


def rule_omission(items: list[MedItem], form: Formulary, order_sources: list[dict]) -> list[IssueDraft]:
    """``order_sources``: readable new_order sources. Without one, omission is not evaluated."""
    if not order_sources:
        return []
    active = {ing for it in _active_orders(items) for ing in it.ingredients}
    ended = {
        ing for it in items if it.source_type == "new_order" and it.discontinue_intent for ing in it.ingredients
    }
    by_ing: dict[str, list[MedItem]] = defaultdict(list)
    for it in items:
        if it.source_type in ("home_list", "patient_reported"):
            for ing in it.ingredients:
                if ing not in active and ing not in ended:
                    by_ing[ing].append(it)
    active_classes = {c for ing in active for c in form.classes_of(ing)}
    absent = [
        {
            "source_type": "new_order",
            "evidence_ref": s["evidence_ref"],
            "available_at_time": s["available_at_time"],
            "raw_span": "",
            "presence": "absent",
        }
        for s in order_sources
    ]
    out = []
    for ings, its in _group_by_items(by_ing):
        substitution = any(set(form.classes_of(ing)) & active_classes for ing in ings)
        out.append(
            IssueDraft("omission", ings, [i.as_source() for i in its] + absent, possible_substitution=substitution)
        )
    return out


# --------------------------------------------------------------------------- allergy


def _allergy_subtype(form: Formulary, res: Resolution, ingredient: str) -> tuple[str, dict] | None:
    if ingredient in res.ingredients:
        return "allergy_direct", {}
    allergen_classes = form.allergen_class_set(res)
    if allergen_classes & set(form.classes_of(ingredient)):
        return "allergy_class", {}
    allergen_keys = {("ingredient", i) for i in res.ingredients} | {("class", c) for c in allergen_classes}
    drug_keys = {("ingredient", ingredient)} | {("class", c) for c in form.classes_of(ingredient)}
    pair = form.cross_reactive(allergen_keys, drug_keys)
    if pair:
        return "allergy_cross_reactivity", {"cross_reactivity_id": pair["id"], "citation": pair["citation"]}
    return None


def rule_allergy(items: list[MedItem], allergies: list[AllergyItem], form: Formulary) -> list[IssueDraft]:
    meds = [i for i in items if i.active and i.ingredients]
    out = []
    for allergy in allergies:
        if not allergy.resolution.mapped:
            continue  # reported as an allergy_unmapped notice by the pipeline
        hits: dict[str, dict[str, list[MedItem]]] = defaultdict(lambda: defaultdict(list))
        extra: dict[str, dict] = {}
        for med in meds:
            for ing in med.ingredients:
                found = _allergy_subtype(form, allergy.resolution, ing)
                if found:
                    subtype, info = found
                    hits[subtype][ing].append(med)
                    extra.setdefault(subtype, info)
        for subtype in ("allergy_direct", "allergy_class", "allergy_cross_reactivity"):
            if subtype not in hits:
                continue
            ings = tuple(sorted(hits[subtype]))
            seen: dict[str, MedItem] = {}
            for ing in ings:
                for med in hits[subtype][ing]:
                    seen.setdefault(med.key, med)
            sources = [allergy.as_source()] + [m.as_source() for m in seen.values()]
            detail = {"allergy_text": allergy.text, **extra.get(subtype, {})}
            out.append(IssueDraft(subtype, ings, sources, detail=detail))
    return out


def run_rules(
    items: list[MedItem], allergies: list[AllergyItem], form: Formulary, order_sources: list[dict]
) -> list[IssueDraft]:
    drafts = (
        rule_allergy(items, allergies, form)
        + rule_duplication_ingredient(items, form)
        + rule_duplication_class(items, form)
        + rule_dose_mismatch(items, form)
        + rule_frequency_mismatch(items, form)
        + rule_omission(items, form, order_sources)
    )
    return sorted(drafts, key=lambda d: d.sort_key())
