"""Offline formulary: drug names -> RxNorm ingredients -> FDA EPC classes. Read-only."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path

DATA_DIR = Path(__file__).resolve().parent / "data"
_STRIP_PREFIXES = ("ยา",)
_STRIP_SUFFIX_WORDS = {"tab", "tabs", "tablet", "tablets", "cap", "caps", "capsule", "capsules", "เม็ด", "แคปซูล"}
_ALLERGY_PREFIX = re.compile(r"^(?:แพ้ยา|แพ้|allergy to|allergic to|allergy:)\s*", re.IGNORECASE)


def _key(text: str) -> str:
    return " ".join(text.casefold().replace("​", "").split()).strip(" .,;:-")


@dataclass(frozen=True)
class Resolution:
    ingredients: tuple[str, ...] = ()
    classes: tuple[str, ...] = ()  # only for allergen groups (class-level allergens)

    @property
    def mapped(self) -> bool:
        return bool(self.ingredients or self.classes)


@dataclass
class Formulary:
    version: str
    metadata: dict
    classes: dict[str, dict]
    ingredients: dict[str, dict]
    alias_index: dict[str, tuple[str, ...]] = field(default_factory=dict)
    allergen_index: dict[str, str] = field(default_factory=dict)
    cross_pairs: list[dict] = field(default_factory=list)
    cross_version: str = ""

    # ---- names
    def resolve_name(self, name: str) -> tuple[str, ...]:
        """Return the ingredient keys for a drug mention, or () if unrecognised."""
        for candidate in self._candidates(name):
            if candidate in self.alias_index:
                return self.alias_index[candidate]
        return ()

    def _candidates(self, name: str) -> list[str]:
        base = _key(name)
        out = [base]
        words = base.split()
        while words and words[-1] in _STRIP_SUFFIX_WORDS:
            words = words[:-1]
            out.append(" ".join(words))
        for prefix in _STRIP_PREFIXES:
            if base.startswith(prefix) and len(base) > len(prefix):
                out.append(base[len(prefix):].strip())
        return out

    def rxcuis(self, ingredients: tuple[str, ...] | list[str]) -> tuple[str, ...]:
        return tuple(self.ingredients[i]["rxcui"] for i in ingredients)

    def classes_of(self, ingredient: str) -> tuple[str, ...]:
        return tuple(self.ingredients[ingredient]["classes"])

    # ---- allergies
    def resolve_allergen(self, text: str) -> Resolution:
        core = re.split(r"[(\[]| - |:|,", _ALLERGY_PREFIX.sub("", " ".join(text.split())), maxsplit=1)[0]
        core = _ALLERGY_PREFIX.sub("", core)
        for candidate in self._candidates(core):
            if candidate in self.allergen_index:
                return Resolution(classes=(self.allergen_index[candidate],))
            if candidate in self.alias_index:
                return Resolution(ingredients=self.alias_index[candidate])
        return Resolution()

    def allergen_class_set(self, res: Resolution) -> set[str]:
        """Explicit class allergens plus allergy-group classes of ingredient allergens."""
        out = set(res.classes)
        for ing in res.ingredients:
            out |= {c for c in self.classes_of(ing) if self.classes[c].get("allergy_group")}
        return out

    def cross_reactive(self, allergen_keys: set[tuple[str, str]], drug_keys: set[tuple[str, str]]) -> dict | None:
        for pair in self.cross_pairs:
            a = (pair["allergen"]["kind"], pair["allergen"]["id"])
            d = (pair["drug"]["kind"], pair["drug"]["id"])
            if (a in allergen_keys and d in drug_keys) or (
                pair.get("symmetric") and d in allergen_keys and a in drug_keys
            ):
                return pair
        return None


@lru_cache(maxsize=1)
def load_formulary() -> Formulary:
    raw = json.loads((DATA_DIR / "formulary.json").read_text(encoding="utf-8"))
    cross = json.loads((DATA_DIR / "cross_reactivity.json").read_text(encoding="utf-8"))
    form = Formulary(
        version=raw["metadata"]["formulary_version"],
        metadata=raw["metadata"],
        classes=raw["classes"],
        ingredients=raw["ingredients"],
        cross_pairs=cross["pairs"],
        cross_version=cross["metadata"]["version"],
    )
    for product in raw["products"]:
        ings = tuple(sorted(product["ingredients"]))
        for alias in product["aliases"]:
            k = _key(alias["text"])
            if k in form.alias_index and form.alias_index[k] != ings:
                raise ValueError(f"ambiguous formulary alias: {alias['text']}")
            form.alias_index[k] = ings
    for group in raw["allergen_groups"]:
        for phrase in group["phrases"]:
            form.allergen_index[_key(phrase)] = group["class_id"]
    return form
