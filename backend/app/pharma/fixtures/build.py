"""Deterministic generator for the clean synthetic patients (``patients.json``) and the frozen
test-split manifest (``test_manifest.json``). All content is synthetic (``data_class=synthetic``).

Run: ``PYTHONPATH=backend python -m app.pharma.fixtures.build`` (rewrites both files).
"""

from __future__ import annotations

import hashlib
import json
import random
import re
from datetime import datetime, timedelta, timezone
from pathlib import Path

from ..formulary import Formulary, load_formulary

HERE = Path(__file__).resolve().parent
PATIENTS_FILE = HERE / "patients.json"
MANIFEST_FILE = HERE / "test_manifest.json"
DEMO_FILE = HERE / "demo.json"
GENERATOR_VERSION = "s5-fixtures-3.0.0"
SEED = 20260926
FROZEN_ON = "2026-09-27"  # manifest v3 frozen before any v1.2 test-split evaluation
MANIFEST_VERSION = 3
# The v2 test split this manifest keeps unchanged (same 32 refs, no patient changes split).
SUPERSEDES = {"manifest_version": 2, "generator_version": "s5-fixtures-2.0.0",
              "sha256": "313e44b314097bf8980d353b3d28f739223fb848c5fe8f9cabdf9b307771dad9"}
# Seeded surface-form suite (eval/inject.py), frozen together with the split.
SURFACE_SEED = 11
SURFACE_GENERATOR_VERSION = "s5-surface-forms-1.0.0"
N_PATIENTS = 96  # >= 60 dev and >= 30 test (s5r); refs s5-p01..s5-p96
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


NXM_SURFACE = re.compile(r"^(\d+)x\d")  # "1x2 pc": N units per administration


def gold_quantity(freq_surface: str | None) -> float | None:
    m = NXM_SURFACE.match(freq_surface or "")
    return float(m.group(1)) if m else None


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
            "quantity": gold_quantity(freq_s) if d is not None else None,
            "dose_status": "resolved" if d is not None else "not_stated",
            "route": gold_route(route_s),
            "frequency_code": freq_code if freq_s else None,
            "frequency_status": "recognised" if freq_s else "not_stated",
            "ingredients": ingredients,
            "ingredient_rxcuis": list(form.rxcuis(ingredients)),
            "product": product,
        },
    }


TIMES_PER_DAY = {"q24h": 1, "q12h": 2, "q8h": 3, "q6h": 4}
TH_UNITS = {"mg": "มก.", "g": "กรัม", "mcg": "mcg"}


def quantity_form_entry(entry: dict, rng: random.Random, style: str) -> tuple[dict, str]:
    """Rewrite a clean entry in a quantity form with the *same dose per administration*, e.g.
    ``Metformin 500 mg bid`` -> ``Metformin 250 mg 2 tabs bid`` (v3: >= 30 patients carry one)."""
    g = entry["gold"]
    dose, unit, code = g["dose_value"], g["dose_unit"], g["frequency_code"]
    u = TH_UNITS.get(unit, unit) if style == "th" else unit
    # Count forms never share a line with an "NxM" surface (two quantity statements = ambiguous).
    freq_s = rng.choice([f for f in FREQ_SURFACES[code][style] if not NXM_SURFACE.match(f)])
    options = [("half_strength_x2", f"{fmt_num(dose / 2)} {u} 2 {'เม็ด' if style == 'th' else 'tabs'} {freq_s}", dose / 2, 2.0),
               ("double_strength_half", f"{fmt_num(dose * 2)} {u} {'ครึ่งเม็ด' if style == 'th' else '1/2 tab'} {freq_s}", dose * 2, 0.5)]
    if code in TIMES_PER_DAY:
        suffix = "หลังอาหาร" if style == "th" else "pc"
        options.append(("nxm", f"{fmt_num(dose / 2)} {u} 2x{TIMES_PER_DAY[code]} {suffix}", dose / 2, 2.0))
    kind, tail, strength, qty = rng.choice(options)
    text = f"{g['drug_name_raw']} {tail}"
    gold = g | {"dose_value": float(strength), "quantity": qty, "route": None}
    return {**{k: v for k, v in entry.items() if k != "text"}, "text": text, "gold": gold}, kind


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
    # >= 15 patients with documented intentional discontinuation, >= 5 of them in test (index % 3 == 2).
    discontinue = index % 6 == 0 or index % 12 == 5

    home_style = "en"
    pr_style = "th" if thai else "en"
    order_style = "th" if (thai and index % 2 == 0) else "en"

    home, reported, orders = [], [], []
    ended_key = chronic[-1][0] if discontinue else None
    for key, names, dose, unit, freq in chronic:
        home.append(make_entry(form, rng, key, _surface(names, home_style, rng), dose, unit, freq, home_style))
        # Clean lists are fully specified in every source (DECISIONS 2026-09-27): incompleteness exists
        # only as an injected missing_field case.
        if rng.random() < 0.7 or (key == chronic[-1][0] and not reported):
            reported.append(make_entry(form, rng, key, _surface(names, pr_style, rng), dose, unit, freq, pr_style))
        entry = make_entry(form, rng, key, _surface(names, order_style, rng), dose, unit, freq, order_style)
        if key == ended_key:
            entry["discontinue_intent"] = True
            entry["reason"] = REASONS[index % len(REASONS)]
        orders.append(entry)
    for key, names, dose, unit, freq in acute:
        orders.append(make_entry(form, rng, key, _surface(names, order_style, rng), dose, unit, freq, order_style))

    # v3: every other patient carries one active chronic entry written in a quantity form whose dose per
    # administration equals the other sources' dose. A separate RNG keeps every other v2 choice unchanged.
    quantity_form = None
    if index % 2 == 0:
        qrng = random.Random(f"{SEED}:quantity-form:{index}")
        by_source = {"home_list": (home, home_style), "patient_reported": (reported, pr_style), "new_order": (orders, order_style)}
        chronic_keys_active = {c[0] for c in chronic} - {ended_key}
        cands_by_source = {
            st: [n for n, e in enumerate(entries) if e["gold"]["product"] in chronic_keys_active]
            for st, (entries, _) in by_source.items()
        }
        source_type = qrng.choice(sorted(st for st, c in cands_by_source.items() if c))
        entries, style = by_source[source_type]
        n = qrng.choice(cands_by_source[source_type])
        entries[n], kind = quantity_form_entry(entries[n], qrng, style)
        quantity_form = {"source_type": source_type, "entry_index": n, "form": kind}

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

    sources = [src("home_list", home, timedelta(days=30)), src("patient_reported", reported, timedelta(hours=1))]
    gold = {"home_list": [e["gold"] for e in home], "patient_reported": [e["gold"] for e in reported]}
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
            "quantity_form": quantity_form,
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


def fixtures_file_sha256() -> str:
    return hashlib.sha256(PATIENTS_FILE.read_bytes()).hexdigest()


def manifest(patients: list[dict], fixtures_sha256: str | None = None) -> dict:
    return {
        "manifest_version": MANIFEST_VERSION,
        "split": "test",
        "frozen_on": FROZEN_ON,
        "decision": "docs/DECISIONS.md 2026-09-27 — S5 Pharma evaluation definitions; slices/s5r2/SPEC.md §11",
        "generator_version": GENERATOR_VERSION,
        "patient_refs": [p["patient_ref"] for p in patients if p["split"] == "test"],
        "sha256": frozen_split_sha256(patients),
        "fixtures_file_sha256": fixtures_sha256 if fixtures_sha256 is not None else fixtures_file_sha256(),
        "surface_suite": {"seed": SURFACE_SEED, "generator_version": SURFACE_GENERATOR_VERSION},
        "supersedes": SUPERSEDES,
        "note": "Frozen test split (same patients as v2). Do not tune rules or the mock against these patients.",
    }


def main() -> None:
    patients = build_all()
    PATIENTS_FILE.write_text(dumps({"generator_version": GENERATOR_VERSION, "seed": SEED, "patients": patients}), encoding="utf-8")
    MANIFEST_FILE.write_text(dumps(manifest(patients, fixtures_file_sha256())), encoding="utf-8")
    print(f"wrote {len(patients)} patients")


if __name__ == "__main__":
    main()
