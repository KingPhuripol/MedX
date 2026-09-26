"""Deterministic generator for the clean synthetic patients (``patients.json``) and the frozen
test-split manifest (``test_manifest.json``). All content is synthetic (``data_class=synthetic``).

Run: ``PYTHONPATH=backend python -m app.pharma.fixtures.build`` (rewrites both files).
"""

from __future__ import annotations

import hashlib
import json
import random
from datetime import datetime, timedelta, timezone
from pathlib import Path

from ..formulary import Formulary, load_formulary

HERE = Path(__file__).resolve().parent
PATIENTS_FILE = HERE / "patients.json"
MANIFEST_FILE = HERE / "test_manifest.json"
DEMO_FILE = HERE / "demo.json"
GENERATOR_VERSION = "s5-fixtures-1.0.0"
SEED = 20260926
N_PATIENTS = 32
PROVENANCE = "synthetic: s5 fixture generator (no real patient data)"

# (ingredient key or product id, {surface kind: name}, dose, unit, frequency_code)
CHRONIC: tuple[tuple[str, dict[str, str], float | None, str | None, str], ...] = (
    ("amlodipine", {"en": "Amlodipine", "brand": "Norvasc", "th": "แอมโลดิพีน"}, 5, "mg", "q24h"),
    ("losartan", {"en": "Losartan", "brand": "Cozaar", "th": "ลอซาร์แทน"}, 50, "mg", "q24h"),
    ("enalapril", {"en": "Enalapril", "brand": "Renitec", "th": "เอนาลาพริล"}, 5, "mg", "q12h"),
    ("hydrochlorothiazide", {"en": "Hydrochlorothiazide", "brand": "HCTZ", "th": "ไฮโดรคลอโรไทอะไซด์"}, 25, "mg", "q24h"),
    ("atenolol", {"en": "Atenolol", "brand": "Tenormin", "th": "อะทีโนลอล"}, 50, "mg", "q24h"),
    ("simvastatin", {"en": "Simvastatin", "brand": "Zocor", "th": "ซิมวาสแตติน"}, 20, "mg", "q24h"),
    ("atorvastatin", {"en": "Atorvastatin", "brand": "Lipitor", "th": "อะทอร์วาสแตติน"}, 40, "mg", "q24h"),
    ("metformin", {"en": "Metformin", "brand": "Glucophage", "th": "เมทฟอร์มิน"}, 500, "mg", "q12h"),
    ("glipizide", {"en": "Glipizide", "brand": "Minidiab", "th": "กลิพิไซด์"}, 5, "mg", "q24h"),
    ("omeprazole", {"en": "Omeprazole", "brand": "Miracid", "th": "โอเมพราโซล"}, 20, "mg", "q24h"),
    ("levothyroxine", {"en": "Levothyroxine", "brand": "Euthyrox", "th": "เลโวไทร็อกซีน"}, 50, "mcg", "q24h"),
    ("warfarin", {"en": "Warfarin", "brand": "Orfarin", "th": "วาร์ฟาริน"}, 3, "mg", "q24h"),
    ("clopidogrel", {"en": "Clopidogrel", "brand": "Plavix", "th": "โคลพิโดเกรล"}, 75, "mg", "q24h"),
    ("allopurinol", {"en": "Allopurinol", "brand": "Zyloric", "th": "อัลโลพูรินอล"}, 100, "mg", "q24h"),
    ("furosemide", {"en": "Furosemide", "brand": "Lasix", "th": "ฟูโรซีไมด์"}, 40, "mg", "q24h"),
    ("acetaminophen", {"en": "Paracetamol", "brand": "Sara", "th": "ซาร่า"}, 500, "mg", "prn"),
    ("gabapentin", {"en": "Gabapentin", "brand": "Berlontin", "th": "Neurontin"}, 300, "mg", "q24h"),
    ("sitagliptin", {"en": "Sitagliptin", "brand": "Januvia", "th": "Januvia"}, 100, "mg", "q24h"),
)
# Chronic slots: at most one ingredient per slot, so a clean list has no same-class pairs.
SLOTS = (
    ("amlodipine",), ("losartan", "enalapril"), ("hydrochlorothiazide", "furosemide"), ("atenolol",),
    ("simvastatin", "atorvastatin"), ("metformin",), ("glipizide", "sitagliptin"), ("omeprazole",),
    ("levothyroxine",), ("warfarin", "clopidogrel"), ("allopurinol",), ("acetaminophen",), ("gabapentin",),
)
ACUTE: tuple[tuple[str, dict[str, str], float | None, str | None, str], ...] = (
    ("ibuprofen", {"en": "Ibuprofen", "brand": "Brufen", "th": "ไอบูโพรเฟน"}, 400, "mg", "q8h"),
    ("naproxen", {"en": "Naproxen", "brand": "Naprosyn", "th": "นาพรอกเซน"}, 250, "mg", "q12h"),
    ("diclofenac", {"en": "Diclofenac", "brand": "Voltaren", "th": "ไดโคลฟีแนค"}, 25, "mg", "q8h"),
    ("cephalexin", {"en": "Cephalexin", "brand": "Keflex", "th": "เซฟาเลกซิน"}, 500, "mg", "q6h"),
    ("cefuroxime", {"en": "Cefuroxime", "brand": "Zinnat", "th": "Zinnat"}, 250, "mg", "q12h"),
    ("amoxicillin", {"en": "Amoxicillin", "brand": "Amoxil", "th": "อะม็อกซีซิลลิน"}, 500, "mg", "q8h"),
    ("amoxicillin_clavulanate", {"en": "Augmentin", "brand": "Augmentin", "th": "ออกเมนติน"}, 1, "g", "q12h"),
    ("dicloxacillin", {"en": "Dicloxacillin", "brand": "Dicloxacillin", "th": "ไดคล็อกซาซิลลิน"}, 250, "mg", "q6h"),
)
# Extra orders the injector may add for same-class duplication (ingredient -> regimen).
EXTRA_REGIMENS: dict[str, tuple[float, str, str]] = {
    "nifedipine": (30, "mg", "q24h"), "lisinopril": (10, "mg", "q24h"), "valsartan": (80, "mg", "q24h"),
    "metoprolol": (100, "mg", "q12h"), "bisoprolol": (5, "mg", "q24h"), "carvedilol": (6.25, "mg", "q12h"),
    "rosuvastatin": (10, "mg", "q24h"), "simvastatin": (20, "mg", "q24h"), "atorvastatin": (40, "mg", "q24h"),
    "gliclazide": (80, "mg", "q12h"), "glipizide": (5, "mg", "q24h"), "pantoprazole": (40, "mg", "q24h"),
    "esomeprazole": (20, "mg", "q24h"), "lansoprazole": (30, "mg", "q24h"), "celecoxib": (200, "mg", "q24h"),
    "naproxen": (250, "mg", "q12h"), "ibuprofen": (400, "mg", "q8h"), "diclofenac": (25, "mg", "q8h"),
    "apixaban": (5, "mg", "q12h"), "rivaroxaban": (20, "mg", "q24h"), "cefuroxime": (250, "mg", "q12h"),
    "cephalexin": (500, "mg", "q6h"), "dicloxacillin": (250, "mg", "q6h"), "amoxicillin": (500, "mg", "q8h"),
    "losartan": (50, "mg", "q24h"), "enalapril": (5, "mg", "q12h"), "hydrochlorothiazide": (25, "mg", "q24h"),
    "furosemide": (40, "mg", "q24h"), "atenolol": (50, "mg", "q24h"),
}
CLEAN_ALLERGIES = (  # (text, would-reach checker handles safety)
    "Sulfa drugs (rash)", "แพ้ยาซัลฟา (ผื่น)", "Penicillin - urticaria", "Aspirin (angioedema)",
    "Ciprofloxacin (rash)", "แพ้ยา เพนิซิลลิน", "Clarithromycin - rash",
)
FREQ_SURFACES = {
    "q24h": {"en": ("once daily", "OD", "daily", "1x1"), "th": ("วันละ 1 ครั้ง", "วันละครั้ง", "1x1 หลังอาหารเช้า")},
    "q12h": {"en": ("bid", "BID", "twice daily", "1x2 pc"), "th": ("วันละ 2 ครั้ง", "1x2 หลังอาหาร")},
    "q8h": {"en": ("tid", "three times daily", "1x3 pc"), "th": ("วันละ 3 ครั้ง", "1x3 หลังอาหาร")},
    "q6h": {"en": ("qid", "four times daily", "q6h"), "th": ("วันละ 4 ครั้ง",)},
    "prn": {"en": ("prn", "as needed"), "th": ("เวลาปวด", "เมื่อมีอาการ")},
}
ROUTE_SURFACES = {"en": ("PO", "oral", None, None), "th": ("รับประทาน", None, None)}
REASONS = (
    "synthetic: held by team plan after low glucose readings",
    "synthetic: replaced per clinic plan; see order note",
    "synthetic: course completed",
    "synthetic: patient preference recorded at visit",
)


def fmt_num(value: float) -> str:
    return f"{value:g}"


def render(name: str, dose: float | None, unit: str | None, route: str | None, freq: str | None, style: str) -> str:
    """Render one free-text medication line. ``route``/``freq`` are surface strings."""
    parts = [name]
    if dose is not None and unit is not None:
        u = {"mg": "มก.", "g": "กรัม", "mcg": "mcg"}.get(unit, unit) if style == "th" else unit
        parts.append(f"{fmt_num(dose)} {u}")
    if route:
        parts.append(route)
    if freq:
        parts.append(freq)
    return " ".join(parts)


def gold_route(surface: str | None) -> str | None:
    return None if surface is None else "oral"


def make_entry(
    form: Formulary, rng: random.Random, product: str, name: str, dose, unit, freq_code, style: str,
    *, keep_dose: bool = True, keep_freq: bool = True,
) -> dict:
    route_s = rng.choice(ROUTE_SURFACES[style])
    freq_s = rng.choice(FREQ_SURFACES[freq_code][style]) if keep_freq and freq_code else None
    d = dose if keep_dose else None
    u = unit if keep_dose else None
    ingredients = list(form.resolve_name(name))
    assert ingredients, f"fixture name not in formulary: {name}"
    return {
        "text": render(name, d, u, route_s, freq_s, style),
        "gold": {
            "drug_name_raw": name,
            "dose_value": float(d) if d is not None else None,
            "dose_unit": u,
            "route": gold_route(route_s),
            "frequency_code": freq_code if freq_s else None,
            "ingredients": ingredients,
            "ingredient_rxcuis": list(form.rxcuis(ingredients)),
            "product": product,
        },
    }


def allergy_reach(form: Formulary, text: str, ingredients: set[str]) -> set[str]:
    """Ingredients an allergen text would touch (direct, class, or curated cross-reactivity)."""
    res = form.resolve_allergen(text)
    classes = form.allergen_class_set(res)
    keys = {("ingredient", i) for i in res.ingredients} | {("class", c) for c in classes}
    hit = set()
    for ing in ingredients:
        drug_keys = {("ingredient", ing)} | {("class", c) for c in form.classes_of(ing)}
        if ing in res.ingredients or classes & set(form.classes_of(ing)) or form.cross_reactive(keys, drug_keys):
            hit.add(ing)
    return hit


def _surface(names: dict[str, str], style: str, rng: random.Random) -> str:
    if style == "th":
        return rng.choice([names["th"], names["brand"], names["th"]])
    return rng.choice([names["en"], names["en"], names["brand"]])


def build_patient(form: Formulary, index: int) -> dict:
    rng = random.Random(f"{SEED}:patient:{index}")
    pid = f"s5-p{index + 1:02d}"
    thai = index % 3 != 1  # about two thirds use Thai surfaces somewhere
    as_of = datetime(2026, 6, 1, 9, 0, tzinfo=timezone(timedelta(hours=7))) + timedelta(days=index)
    slots = rng.sample(SLOTS, k=rng.randint(3, 5))
    chronic_keys = [rng.choice(s) for s in slots]
    chronic = [c for c in CHRONIC if c[0] in chronic_keys]
    acute = [ACUTE[index % len(ACUTE)]]
    discontinue = index % 6 == 0  # >= 5 patients with documented intentional discontinuation

    home_style = "en"
    pr_style = "th" if thai else "en"
    order_style = "th" if (thai and index % 2 == 0) else "en"

    home, reported, orders = [], [], []
    ended_key = chronic[-1][0] if discontinue else None
    for key, names, dose, unit, freq in chronic:
        home.append(make_entry(form, rng, key, _surface(names, home_style, rng), dose, unit, freq, home_style))
        if rng.random() < 0.7:
            reported.append(
                make_entry(form, rng, key, _surface(names, pr_style, rng), dose, unit, freq, pr_style,
                           keep_dose=rng.random() < 0.6, keep_freq=rng.random() < 0.85)
            )
        entry = make_entry(form, rng, key, _surface(names, order_style, rng), dose, unit, freq, order_style)
        if key == ended_key:
            entry["discontinue_intent"] = True
            entry["reason"] = REASONS[index % len(REASONS)]
        orders.append(entry)
    for key, names, dose, unit, freq in acute:
        orders.append(make_entry(form, rng, key, _surface(names, order_style, rng), dose, unit, freq, order_style))

    all_ings = {i for e in home + reported + orders for i in e["gold"]["ingredients"]}
    allergies = []
    if rng.random() < 0.6:
        options = [a for a in CLEAN_ALLERGIES if not allergy_reach(form, a, all_ings)]
        text = rng.choice(options)
        allergies.append({
            "text": text,
            "evidence_ref": f"{pid}/allergy/1",
            "available_at_time": (as_of - timedelta(days=200)).isoformat(),
            "provenance": PROVENANCE,
            "version": "1",
        })

    def src(source_type: str, entries: list[dict], age: timedelta) -> dict:
        out_entries = []
        for e in entries:
            item = {"text": e["text"]}
            if e.get("discontinue_intent"):
                item |= {"discontinue_intent": True, "reason": e["reason"]}
            out_entries.append(item)
        return {
            "source_type": source_type,
            "evidence_ref": f"{pid}/{source_type}/1",
            "available_at_time": (as_of - age).isoformat(),
            "provenance": PROVENANCE,
            "version": "1",
            "entries": out_entries,
        }

    sources = [src("home_list", home, timedelta(days=30))]
    gold = {"home_list": [e["gold"] for e in home]}
    if reported:
        sources.append(src("patient_reported", reported, timedelta(hours=1)))
        gold["patient_reported"] = [e["gold"] for e in reported]
    sources.append(src("new_order", orders, timedelta(minutes=10)))
    gold["new_order"] = [e["gold"] for e in orders]
    uses_thai = any(
        any("฀" <= ch <= "๿" for ch in e["text"]) or e["gold"]["drug_name_raw"] in {"Sara", "Miracid", "Orfarin", "Berlontin"}
        for e in home + reported + orders
    )
    return {
        "patient_ref": pid,
        "split": "test" if index % 3 == 2 else "dev",
        "data_class": "synthetic",
        "snapshot": {
            "patient_ref": pid,
            "as_of": as_of.isoformat(),
            "data_class": "synthetic",
            "sources": sources,
            "allergies": allergies,
        },
        "gold": gold,
        "meta": {
            "uses_thai_mentions": uses_thai,
            "documented_discontinuation": discontinue,
            "generator_version": GENERATOR_VERSION,
        },
    }


def build_all() -> list[dict]:
    form = load_formulary()
    return [build_patient(form, i) for i in range(N_PATIENTS)]


def dumps(data) -> str:
    return json.dumps(data, ensure_ascii=False, indent=1, sort_keys=True) + "\n"


def frozen_split_sha256(patients: list[dict]) -> str:
    test = [p for p in patients if p["split"] == "test"]
    canon = json.dumps(test, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canon.encode("utf-8")).hexdigest()


def manifest(patients: list[dict]) -> dict:
    return {
        "split": "test",
        "frozen_on": "2026-09-26",
        "generator_version": GENERATOR_VERSION,
        "patient_refs": [p["patient_ref"] for p in patients if p["split"] == "test"],
        "sha256": frozen_split_sha256(patients),
        "note": "Frozen test split. Do not tune rules or the mock against these patients.",
    }


def main() -> None:
    patients = build_all()
    PATIENTS_FILE.write_text(dumps({"generator_version": GENERATOR_VERSION, "seed": SEED, "patients": patients}), encoding="utf-8")
    MANIFEST_FILE.write_text(dumps(manifest(patients)), encoding="utf-8")
    print(f"wrote {len(patients)} patients")


if __name__ == "__main__":
    main()
