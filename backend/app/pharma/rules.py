"""Primary checker: pure, versioned reconciliation rules. No I/O, no model calls.

Each rule takes extracted medication items (with formulary ingredients) and returns issue drafts.
Severity order is fixed here and cannot be changed by model output.
"""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Callable, Iterable
from dataclasses import dataclass, field

from .formulary import Formulary, Resolution

RULES_VERSION = "s5-rules-2.1.0"
RULE_VERSIONS: dict[str, str] = {
    "allergy_direct": "1.1.0",
    "allergy_class": "1.1.0",
    "allergy_cross_reactivity": "1.1.0",
    "duplication_ingredient": "1.0.0",
    "duplication_class": "1.0.0",
    # Compares the dose per administration (strength x quantity; stated amount when no quantity).
    "dose_mismatch": "1.2.0",
    "frequency_mismatch": "1.1.0",
    # A dose or frequency not stated in an entry: a discrepancy type of its own (DECISIONS 2026-09-27).
    "missing_field": "2.1.0",
    "omission": "1.0.0",
}
# Fixed by rule; model output never changes it. missing_field shares the dose/frequency tier and is
# ranked after the two mismatch types (TYPE_ORDER) and before omission.
SEVERITY: dict[str, tuple[int, str]] = {
    "allergy_direct": (1, "high"),
    "allergy_class": (1, "high"),
    "allergy_cross_reactivity": (1, "high"),
    "duplication_ingredient": (2, "elevated"),
    "duplication_class": (2, "elevated"),
    "dose_mismatch": (3, "moderate"),
    "frequency_mismatch": (3, "moderate"),
    "missing_field": (3, "moderate"),
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
    quantity: float | None = None
    dose_status: str = "not_stated"
    dose_unverifiable_reason: str | None = None
    frequency_status: str = "not_stated"

    @property
    def active(self) -> bool:
        return not self.discontinue_intent

    @property
    def dose_basis(self) -> str | None:
        if self.dose_value is None or self.dose_unit is None:
            return None
        return "stated_amount" if self.quantity is None else "strength_x_quantity"

    @property
    def dose_per_administration(self) -> float | None:
        """Dose per administration in ``dose_unit``: strength x quantity, or the stated amount itself
        when no quantity is stated (recorded per source as ``dose_basis``)."""
        if self.dose_basis is None:
            return None
        return round(self.dose_value * (self.quantity or 1.0), 6)  # type: ignore[operator]

    def field_status(self, field_name: str) -> str | None:
        """Why a compared field has no value: ``unverifiable`` / ``not_recognised`` / ``not_stated``
        (None when the field is stated)."""
        if field_name == "dose":
            if self.dose_per_administration is not None:
                return None
            return "unverifiable" if self.dose_status == "unverifiable" else "not_stated"
        if self.frequency_code is not None:
            return None
        return "not_recognised" if self.frequency_status == "not_recognised" else "not_stated"

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
            "quantity": self.quantity,
            "dose_per_administration": self.dose_per_administration,
            "dose_basis": self.dose_basis,
            "dose_status": self.dose_status,
            "dose_unverifiable_reason": self.dose_unverifiable_reason,
            "route": self.route,
            "frequency_code": self.frequency_code,
            "frequency_status": self.frequency_status,
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
    field: str | None = None  # missing_field only: "dose" | "frequency"

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
        first = self.sources[0] if self.sources else {}
        return (
            self.severity_rank, TYPE_ORDER.index(self.type), self.ingredients, first.get("evidence_ref", ""),
            first.get("raw_span", ""), self.field or "", len(self.sources),
        )


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
    """Dose per administration in a comparable unit family, or None when not stated / unverifiable."""
    per_admin = item.dose_per_administration
    if per_admin is None:
        return None
    unit = item.dose_unit.lower()  # type: ignore[union-attr]
    if unit in _MASS:
        return ("mass", round(per_admin * _MASS[unit], 6))
    return (unit, per_admin)


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


def _frequency(item: MedItem) -> str | None:
    return item.frequency_code


# Compared fields: (missing_field payload name, canonical value; None means "not stated").
COMPARED_FIELDS: tuple[tuple[str, Callable[[MedItem], object]], ...] = (
    ("dose", _canonical_dose),
    ("frequency", _frequency),
)


def _cross_source_pairs(group: list[MedItem]) -> list[tuple[MedItem, MedItem]]:
    return [(a, b) for n, a in enumerate(group) for b in group[n + 1:] if a.source_type != b.source_type]


def rule_dose_mismatch(items: list[MedItem], form: Formulary) -> list[IssueDraft]:
    """Stated-vs-stated dose comparison only. An entry without a dose never produces or suppresses a
    mismatch: it is skipped here and raised by ``rule_missing_field`` (a missing value is never agreement)."""
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
            continue
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
    """Stated-vs-stated frequency comparison only (see ``rule_dose_mismatch``)."""
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
                    notes=_missing_notes(missing, "frequency"),
                )
            )
    return out


UNCHECKED_REASONS = ("unverifiable", "not_recognised", "not_stated")  # attribution order for a pair


def count_comparisons(items: list[MedItem]) -> dict:
    """Cross-source comparisons (per field, per pair of active entries of the same ingredient set in
    different source types). A pair with a null side is not compared: it is counted in
    ``unchecked_comparisons`` and attributed once, to the first reason (in ``UNCHECKED_REASONS`` order)
    of its null side(s). Each null side is also a ``missing_field`` issue."""
    made = 0
    by_reason = dict.fromkeys(UNCHECKED_REASONS, 0)
    for _, group in sorted(_comparable_groups(items).items()):
        for field_name, _ in COMPARED_FIELDS:
            for a, b in _cross_source_pairs(group):
                reasons = {r for r in (a.field_status(field_name), b.field_status(field_name)) if r}
                if not reasons:
                    made += 1
                else:
                    by_reason[next(r for r in UNCHECKED_REASONS if r in reasons)] += 1
    return {"comparisons_made": made, "unchecked_comparisons": sum(by_reason.values()), "unchecked_by_reason": by_reason}


def count_skipped_comparisons(items: list[MedItem]) -> int:
    return count_comparisons(items)["unchecked_comparisons"]


def rule_missing_field(items: list[MedItem], form: Formulary) -> list[IssueDraft]:
    """One issue per (entry, field) for every recognised *active* entry, in any source, whose dose per
    administration or frequency has no value (not stated, not recognised, or unverifiable; recorded in
    ``detail.field_status``). Entries with ``discontinue_intent`` raise nothing themselves but still appear
    as other sources. ``conflicting_sources`` = the incomplete entry first, then every other snapshot entry
    of the same ingredient set, then other entries sharing an ingredient (e.g. a combination product).
    So there are >= 2 sources whenever the ingredient is in >= 2 source types."""
    recognised = [i for i in items if i.ingredients]
    out = []
    for item in sorted((i for i in recognised if i.active), key=lambda i: (tuple(sorted(i.ingredients)), i.key)):
        ings = tuple(sorted(item.ingredients))
        same = [o for o in recognised if o.key != item.key and tuple(sorted(o.ingredients)) == ings]
        overlap = [o for o in recognised if o.key != item.key and o not in same and set(o.ingredients) & set(ings)]
        for field_name, value_of in COMPARED_FIELDS:
            if value_of(item) is not None:
                continue
            others = same + overlap
            status = item.field_status(field_name)
            detail = {
                "field": field_name,
                "field_status": status,
                "incomplete_source": item.source_type,
                "stated_in": sorted({o.source_type for o in same if value_of(o) is not None}),
            }
            if status == "unverifiable":
                detail["unverifiable_reason"] = item.dose_unverifiable_reason
            out.append(
                IssueDraft(
                    "missing_field",
                    ings,
                    [item.as_source()] + [o.as_source() for o in others],
                    field=field_name,
                    detail=detail,
                )
            )
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
    """Subtype plus its visible basis (``detail.basis``): what the match rests on and which version."""
    if ingredient in res.ingredients:
        rxcui = form.ingredients[ingredient]["rxcui"]
        return "allergy_direct", {
            "basis": f"The allergen maps to the ingredient {ingredient} (RxCUI {rxcui}) in formulary {form.version}.",
            "formulary_version": form.version,
        }
    allergen_classes = form.allergen_class_set(res)
    shared = sorted(allergen_classes & set(form.classes_of(ingredient)))
    if shared:
        cls = form.classes[shared[0]]
        return "allergy_class", {
            "basis": (f"The allergen and {ingredient} share the class {cls['name']} "
                      f"(class source: {cls['source']}; formulary {form.version})."),
            "class_name": cls["name"],
            "class_source": cls["source"],
            "formulary_version": form.version,
        }
    allergen_keys = {("ingredient", i) for i in res.ingredients} | {("class", c) for c in allergen_classes}
    drug_keys = {("ingredient", ingredient)} | {("class", c) for c in form.classes_of(ingredient)}
    pair = form.cross_reactive(allergen_keys, drug_keys)
    if pair:
        return "allergy_cross_reactivity", {
            "basis": (f"Curated cross-reactivity row {pair['id']} ({form.cross_version}); "
                      "pending pharmacist sign-off."),
            "cross_reactivity_id": pair["id"],
            "citation": pair["citation"],
            "clinical_review_status": pair["clinical_review_status"],
        }
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
        + rule_missing_field(items, form)
        + rule_omission(items, form, order_sources)
    )
    return sorted(drafts, key=lambda d: d.sort_key())
