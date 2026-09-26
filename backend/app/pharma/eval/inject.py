"""Seeded synthetic error injection. One case = one clean patient x one of the 9 discrepancy types,
with exactly one injected discrepancy; at most one case per (patient, type). Every patient (and so
every frozen test patient) is injectable for all 9 types; the injector may add an entry (an allergy
record or a new order) to make a type applicable. It uses formulary ground truth, never the rule engine.

Log line: case_id, patient_ref, split, type, source, before, after, expected{type, ingredients, sources}
(+ ``field`` at top level and in ``expected`` for ``missing_field``).
"""

from __future__ import annotations

import copy
import json
import random
from functools import lru_cache

from ..fixtures.build import (
    EXTRA_REGIMENS,
    FREQ_SURFACES,
    PATIENTS_FILE,
    allergy_reach,
    render,
)
from ..formulary import DATA_DIR, Formulary, load_formulary
from ..models import ISSUE_TYPES

INJECT_SEED = 7
_FREQ_SHIFT = {"q24h": "q12h", "q12h": "q24h", "q8h": "q12h", "q6h": "q8h", "prn": "q6h"}
_ALLERGY_FORMS = ("{x} (rash)", "แพ้ยา {x}", "{x} - urticaria", "{x}")
# Held-out frequency surface forms: never used by the clean fixture generator (FREQ_SURFACES), only
# by injected edits, so recall is also measured on phrasings the clean lists do not contain.
HELDOUT_FREQ_SURFACES: dict[str, dict[str, tuple[str, ...]]] = {
    "q24h": {"en": ("once a day", "q.d.", "every 24 hours", "every morning"), "th": ("ทุก 24 ชั่วโมง",)},
    "q12h": {"en": ("twice a day", "every 12 hours", "q 12 h", "2 times a day"), "th": ("เช้า-เย็น", "เช้า เย็น", "ทุก 12 ชั่วโมง")},
    "q8h": {"en": ("three times a day", "every 8 hours", "t.i.d."), "th": ("เช้า กลางวัน เย็น", "ทุก 8 ชั่วโมง")},
    "q6h": {"en": ("four times a day", "every 6 hours", "q.i.d."), "th": ("เช้า กลางวัน เย็น ก่อนนอน", "ทุก 6 ชั่วโมง")},
    "prn": {"en": ("p.r.n.", "when needed"), "th": ("เมื่อจำเป็น",)},
}


# missing_field: (blanked field, source type), rotated by patient index so every split covers both
# fields and all three source types (patient index // 3 walks each split in order).
MISSING_FIELD_PLAN: tuple[tuple[str, str], ...] = (
    ("dose", "home_list"), ("frequency", "patient_reported"), ("dose", "new_order"),
    ("frequency", "home_list"), ("dose", "patient_reported"), ("frequency", "new_order"),
)


def missing_field_plan(patient_ref: str) -> tuple[str, str]:
    index = int(patient_ref.rsplit("p", 1)[1]) - 1
    return MISSING_FIELD_PLAN[(index // 3) % len(MISSING_FIELD_PLAN)]


class InjectionError(RuntimeError):
    pass


def load_patients() -> list[dict]:
    return json.loads(PATIENTS_FILE.read_text(encoding="utf-8"))["patients"]


def _entries(snap: dict, source_type: str) -> list[dict]:
    for s in snap["sources"]:
        if s["source_type"] == source_type:
            return s["entries"]
    return []


def _gold(p: dict, source_type: str) -> list[dict]:
    return p["gold"].get(source_type, [])


def _active_orders(p: dict) -> list[tuple[int, dict]]:
    entries = _entries(p["snapshot"], "new_order")
    return [(i, g) for i, g in enumerate(_gold(p, "new_order")) if not entries[i].get("discontinue_intent")]


def _patient_ings(p: dict) -> set[str]:
    return {i for gl in p["gold"].values() for g in gl for i in g["ingredients"]}


@lru_cache(maxsize=1)
def _raw_formulary() -> dict:
    return json.loads((DATA_DIR / "formulary.json").read_text(encoding="utf-8"))


def _single_aliases(form: Formulary, ingredient: str) -> list[str]:
    for prod in _raw_formulary()["products"]:
        if prod["ingredients"] == [ingredient]:
            return [a["text"] for a in prod["aliases"] if not any(ch.isdigit() for ch in a["text"])]
    return []


def _style(text: str) -> str:
    return "th" if any("฀" <= ch <= "๿" for ch in text) else "en"


def _route_surface(g: dict, style: str) -> str | None:
    if g["route"] is None:
        return None
    return "รับประทาน" if style == "th" else "PO"


def _rerender(g: dict, *, name: str | None = None, dose=None, unit=None, freq_code=None, style="en",
              rng: random.Random) -> str:
    fc = freq_code if freq_code is not None else g["frequency_code"]
    freq_s = rng.choice(FREQ_SURFACES[fc][style] + HELDOUT_FREQ_SURFACES[fc][style]) if fc else None
    return render(
        name or g["drug_name_raw"],
        dose if dose is not None else g["dose_value"],
        unit if unit is not None else g["dose_unit"],
        _route_surface(g, style),
        freq_s,
        style,
    )


def _allergy_record(p: dict, text: str) -> dict:
    snap = p["snapshot"]
    return {
        "text": text,
        "evidence_ref": f"{p['patient_ref']}/allergy/injected",
        "available_at_time": snap["sources"][0]["available_at_time"],
        "provenance": "synthetic: s5 error injection",
        "version": "1",
    }


def _existing_allergy_reach(form: Formulary, p: dict, ings: set[str]) -> set[str]:
    hit: set[str] = set()
    for a in p["snapshot"]["allergies"]:
        hit |= allergy_reach(form, a["text"], ings)
    return hit


def inject(form: Formulary, p: dict, kind: str, rng: random.Random) -> tuple[dict, dict]:
    """Return (mutated snapshot, log fields) for one discrepancy of ``kind``."""
    snap = copy.deepcopy(p["snapshot"])
    ings = _patient_ings(p)
    orders = _active_orders(p)
    order_entries = _entries(snap, "new_order")

    if kind == "duplication_ingredient":
        cands = [(i, g) for i, g in orders if len(g["ingredients"]) == 1 and _single_aliases(form, g["ingredients"][0])]
        i, g = rng.choice(cands)
        ing = g["ingredients"][0]
        alts = [a for a in _single_aliases(form, ing) if a.casefold() != g["drug_name_raw"].casefold()]
        name = rng.choice(alts)
        text = _rerender(g, name=name, style=_style(name), rng=rng)
        order_entries.append({"text": text})
        return snap, {"source": "new_order", "before": None, "after": text,
                      "expected": {"type": kind, "ingredients": [ing], "sources": ["new_order"]}}

    if kind == "duplication_class":
        options = []
        order_ings = {x for _, g in orders for x in g["ingredients"]}
        for _, g in orders:
            for ing in g["ingredients"]:
                for c in form.classes_of(ing):
                    if not form.classes[c]["duplication_relevant"]:
                        continue
                    for x in sorted(EXTRA_REGIMENS):
                        if x in ings or c not in form.classes_of(x):
                            continue
                        same = {y for y in order_ings for cc in form.classes_of(x)
                                if form.classes[cc]["duplication_relevant"] and cc in form.classes_of(y)}
                        if same != {ing}:
                            continue  # adding x must pair with exactly one existing order
                        if _existing_allergy_reach(form, p, {x}):
                            continue
                        options.append((ing, x))
        if not options:
            raise InjectionError(f"{p['patient_ref']}: no duplication_class option")
        ing, x = rng.choice(sorted(set(options)))
        dose, unit, freq = EXTRA_REGIMENS[x]
        style = rng.choice(("en", "th"))
        text = render(x.capitalize(), dose, unit, "PO", rng.choice(FREQ_SURFACES[freq][style]), style)
        order_entries.append({"text": text})
        return snap, {"source": "new_order", "before": None, "after": text,
                      "expected": {"type": kind, "ingredients": sorted([ing, x]), "sources": ["new_order"]}}

    if kind == "missing_field":
        field, source_type = missing_field_plan(p["patient_ref"])
        target = _entries(snap, source_type)
        gold = _gold(p, source_type)
        cands = [i for i, g in enumerate(gold) if g["ingredients"] and not target[i].get("discontinue_intent")]
        if not cands:
            raise InjectionError(f"{p['patient_ref']}: no {source_type} entry to blank")
        i = rng.choice(cands)
        g = gold[i]
        before = target[i]["text"]
        style = _style(before)
        if field == "dose":
            fc = g["frequency_code"]
            freq_s = rng.choice(FREQ_SURFACES[fc][style] + HELDOUT_FREQ_SURFACES[fc][style])
            after = render(g["drug_name_raw"], None, None, _route_surface(g, style), freq_s, style)
        else:
            after = render(g["drug_name_raw"], g["dose_value"], g["dose_unit"], _route_surface(g, style), None, style)
        target[i] = {**target[i], "text": after}
        return snap, {"source": source_type, "before": before, "after": after, "field": field,
                      "expected": {"type": kind, "ingredients": g["ingredients"], "sources": [source_type],
                                   "field": field}}

    if kind in ("dose_mismatch", "frequency_mismatch", "omission"):
        home = _gold(p, "home_list")
        by_ings = {tuple(g["ingredients"]): (i, g) for i, g in orders}
        field = {"dose_mismatch": "dose_value", "frequency_mismatch": "frequency_code", "omission": "drug_name_raw"}[kind]
        cands = [
            (hi, hg) for hi, hg in enumerate(home)
            if tuple(hg["ingredients"]) in by_ings and hg[field] is not None
            and by_ings[tuple(hg["ingredients"])][1][field] is not None
        ]
        hi, hg = rng.choice(cands)
        oi, og = by_ings[tuple(hg["ingredients"])]
        if kind == "omission":
            before = order_entries[oi]["text"]
            del order_entries[oi]
            return snap, {"source": "new_order", "before": before, "after": None,
                          "expected": {"type": kind, "ingredients": hg["ingredients"], "sources": ["new_order"]}}
        target_type = rng.choice(("new_order", "new_order", "home_list"))
        target_entries = order_entries if target_type == "new_order" else _entries(snap, "home_list")
        idx, g = (oi, og) if target_type == "new_order" else (hi, hg)
        before = target_entries[idx]["text"]
        style = _style(before)
        if kind == "dose_mismatch":
            value, unit = g["dose_value"] * 2, g["dose_unit"]
            if unit == "mg" and value >= 1000 and rng.random() < 0.5:
                value, unit = value / 1000, "g"
            after = _rerender(g, dose=value, unit=unit, style=style, rng=rng)
        else:
            after = _rerender(g, freq_code=_FREQ_SHIFT[g["frequency_code"]], style=style, rng=rng)
        target_entries[idx] = {**target_entries[idx], "text": after}
        return snap, {"source": target_type, "before": before, "after": after,
                      "expected": {"type": kind, "ingredients": g["ingredients"], "sources": [target_type]}}

    # ---- allergy types: add one allergy record targeting existing active medicines
    meds = {x for _, g in orders for x in g["ingredients"]} | {
        x for st in ("home_list", "patient_reported") for g in _gold(p, st) for x in g["ingredients"]
    }
    if kind == "allergy_direct":
        options = []
        for ing in sorted(meds):
            for alias in _single_aliases(form, ing):
                text_opts = [f.format(x=alias) for f in _ALLERGY_FORMS]
                for t in text_opts:
                    if allergy_reach(form, t, meds) == {ing}:
                        options.append((ing, t))
        ing, text = rng.choice(options)
        expected_ings = [ing]
    elif kind == "allergy_class":
        options = []
        for group in _raw_formulary()["allergen_groups"]:
            hit = {x for x in meds if group["class_id"] in form.classes_of(x)}
            for phrase in group["phrases"]:
                t = rng.choice(_ALLERGY_FORMS).format(x=phrase)
                if hit and allergy_reach(form, t, meds) == hit:
                    options.append((tuple(sorted(hit)), t))
        if not options:
            raise InjectionError(f"{p['patient_ref']}: no allergy_class option")
        hit_t, text = rng.choice(options)
        expected_ings = list(hit_t)
    elif kind == "allergy_cross_reactivity":
        options = []
        for phrase in ("penicillin", "เพนิซิลลิน", "cephalosporins", "aspirin", "แอสไพริน", "ASA"):
            t = rng.choice(_ALLERGY_FORMS).format(x=phrase)
            res = form.resolve_allergen(t)
            reach = allergy_reach(form, t, meds)
            classes = form.allergen_class_set(res)
            direct_or_class = {x for x in meds if x in res.ingredients or classes & set(form.classes_of(x))}
            if reach and not direct_or_class:
                options.append((tuple(sorted(reach)), t))
        if not options:
            raise InjectionError(f"{p['patient_ref']}: no allergy_cross_reactivity option")
        hit_t, text = rng.choice(options)
        expected_ings = list(hit_t)
    else:  # pragma: no cover
        raise ValueError(kind)
    snap["allergies"] = list(snap["allergies"]) + [_allergy_record(p, text)]
    return snap, {"source": "allergy_record", "before": None, "after": text,
                  "expected": {"type": kind, "ingredients": expected_ings, "sources": ["allergy_record"]}}


def build_cases(patients: list[dict] | None = None, seed: int = INJECT_SEED) -> list[dict]:
    form = load_formulary()
    patients = patients if patients is not None else load_patients()
    cases = []
    for p in patients:
        for kind in ISSUE_TYPES:
            rng = random.Random(f"{seed}:{p['patient_ref']}:{kind}")
            snap, log = inject(form, p, kind, rng)
            cases.append({
                "case_id": f"{p['patient_ref']}-{kind}",
                "patient_ref": p["patient_ref"],
                "split": p["split"],
                "type": kind,
                **log,
                "snapshot": snap,
            })
    return cases


LOG_KEYS = ("case_id", "patient_ref", "split", "type", "source", "before", "after", "expected")


def log_lines(cases: list[dict]) -> str:
    return "".join(
        json.dumps({k: c[k] for k in LOG_KEYS + (("field",) if "field" in c else ())}, ensure_ascii=False, sort_keys=True)
        + "\n"
        for c in cases
    )
