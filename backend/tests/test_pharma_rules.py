"""S5 rule unit tests (positive and negative per discrepancy type) and allergy cases (A09)."""

import json

import pytest

from app.pharma.formulary import DATA_DIR, load_formulary
from app.pharma.mock_rules import parse_entry

from .pharma_helpers import notices, of_type, run, snapshot


def test_rule_duplication_ingredient():
    pos = run(snapshot(orders=["Tylenol 500 mg prn", "Sara 500 mg prn", "Amlodipine 5 mg daily"]))
    [issue] = of_type(pos, "duplication_ingredient")
    assert issue["ingredients"] == ["acetaminophen"] and len(issue["conflicting_sources"]) == 2
    combo = run(snapshot(orders=["Augmentin 1 g bid", "Amoxicillin 500 mg tid"]))
    assert [i["ingredients"] for i in of_type(combo, "duplication_ingredient")] == [["amoxicillin"]]
    neg = run(snapshot(orders=["Tylenol 500 mg prn", "Amlodipine 5 mg daily"]))
    assert of_type(neg, "duplication_ingredient") == []
    # a discontinued entry is not active
    ended = run(snapshot(orders=["Tylenol 500 mg prn", {"text": "Sara 500 mg prn", "discontinue_intent": True, "reason": "synthetic"}]))
    assert of_type(ended, "duplication_ingredient") == []


def test_rule_duplication_class():
    pos = run(snapshot(orders=["Simvastatin 20 mg daily", "Lipitor 40 mg daily"]))
    [issue] = of_type(pos, "duplication_class")
    assert issue["ingredients"] == ["atorvastatin", "simvastatin"]
    assert "HMG-CoA Reductase Inhibitor" in issue["detail"]["classes"]
    anticoag = run(snapshot(orders=["Warfarin 3 mg daily", "Eliquis 5 mg bid"]))
    assert [i["ingredients"] for i in of_type(anticoag, "duplication_class")] == [["apixaban", "warfarin"]]
    # not duplication-relevant (platelet aggregation inhibitor) and different classes
    assert of_type(run(snapshot(orders=["Aspirin 81 mg daily", "Metformin 500 mg bid"])), "duplication_class") == []
    # same ingredient twice is ingredient duplication, not class duplication
    same = run(snapshot(orders=["Simvastatin 20 mg daily", "Zocor 20 mg daily"]))
    assert of_type(same, "duplication_class") == [] and of_type(same, "duplication_ingredient")


def test_rule_dose_mismatch():
    pos = run(snapshot(home=["Simvastatin 20 mg daily"], orders=["Simvastatin 40 mg daily"]))
    [issue] = of_type(pos, "dose_mismatch")
    assert issue["ingredients"] == ["simvastatin"] and not issue["unverifiable"]
    # unit conversion: 1 g == 1000 mg is a match; 0.5 g vs 1000 mg is a mismatch
    assert of_type(run(snapshot(home=["Metformin 1000 mg bid"], orders=["Metformin 1 g bid"])), "dose_mismatch") == []
    assert of_type(run(snapshot(home=["Levothyroxine 50 mcg daily"], orders=["Levothyroxine 0.05 mg daily"])), "dose_mismatch") == []
    assert of_type(run(snapshot(home=["Metformin 0.5 g bid"], orders=["Metformin 1000 mg bid"])), "dose_mismatch")
    # units that cannot be compared -> mismatch flagged unverifiable
    [unv] = of_type(run(snapshot(home=["Lantus 10 units hs"], orders=["Lantus 10 mg hs"])), "dose_mismatch")
    assert unv["unverifiable"] is True
    # a missing dose is not a match: no dose_mismatch from the null entry, and a missing_field issue (never silence)
    gap = run(snapshot(home=["Simvastatin 20 mg daily"], reported=["Simvastatin daily"], orders=["Simvastatin 20 mg daily"]))
    assert of_type(gap, "dose_mismatch") == [] and notices(gap, "missing_field") == []
    [mf] = of_type(gap, "missing_field")
    first = mf["conflicting_sources"][0]
    assert (mf["field"], first["source_type"], first["evidence_ref"]) == ("dose", "patient_reported", "t/patient_reported/1")
    assert first["dose_value"] is None and first["raw_span"] == "Simvastatin daily"
    assert mf["ingredients"] == ["simvastatin"] and mf["detail"]["stated_in"] == ["home_list", "new_order"]
    assert gap["unchecked_comparisons"] == 2  # reported-vs-home and reported-vs-order
    # stated-vs-stated mismatch is still detected when a third source is null
    noted = run(snapshot(home=["Simvastatin 20 mg daily"], reported=["ซิมวาสแตติน วันละครั้ง"], orders=["Simvastatin 40 mg daily"]))
    [issue] = of_type(noted, "dose_mismatch")
    assert issue["notes"] == [{"kind": "missing_field", "field": "dose", "source_type": "patient_reported", "evidence_ref": "t/patient_reported/1"}]
    assert all(s["source_type"] != "patient_reported" for s in issue["conflicting_sources"])
    assert [(i["field"], i["conflicting_sources"][0]["source_type"]) for i in of_type(noted, "missing_field")] == [("dose", "patient_reported")]


def test_rule_frequency_mismatch():
    for surface in ("bid", "วันละ 2 ครั้ง", "1x2 pc", "q12h", "twice daily"):
        assert parse_entry(f"Metformin 500 mg {surface}")["frequency_code"] == "q12h"
    assert same_meds_clean(run(snapshot(home=["Metformin 500 mg twice a day"], orders=["Metformin 500 mg เช้า-เย็น"])))
    same = run(snapshot(home=["Metformin 500 mg bid"], reported=["เมทฟอร์มิน 500 มก. วันละ 2 ครั้ง"], orders=["Metformin 500 mg 1x2 pc"]))
    assert of_type(same, "frequency_mismatch") == []
    diff = run(snapshot(home=["Metformin 500 mg bid"], orders=["Metformin 500 mg tid"]))
    [issue] = of_type(diff, "frequency_mismatch")
    assert {s["frequency_code"] for s in issue["conflicting_sources"]} == {"q12h", "q8h"}
    # a missing frequency is not a match: no frequency_mismatch from the null entry, and a missing_field issue
    gap = run(snapshot(home=["Metformin 500 mg bid"], orders=["Metformin 500 mg"]))
    assert of_type(gap, "frequency_mismatch") == []
    [mf] = of_type(gap, "missing_field")
    assert (mf["field"], mf["conflicting_sources"][0]["source_type"], mf["detail"]["stated_in"]) == ("frequency", "new_order", ["home_list"])
    assert gap["unchecked_comparisons"] == 1
    # stated-vs-stated mismatch is still detected when a third source is null
    third = run(snapshot(home=["Metformin 500 mg bid"], reported=["เมทฟอร์มิน 500 มก."], orders=["Metformin 500 mg tid"]))
    [issue] = of_type(third, "frequency_mismatch")
    assert {s["source_type"] for s in issue["conflicting_sources"]} == {"home_list", "new_order"}
    assert [i["field"] for i in of_type(third, "missing_field")] == ["frequency"]


def same_meds_clean(result: dict) -> bool:
    return result["issues"] == [] and result["notices"] == [] and result["unchecked_comparisons"] == 0


# Reviewer probe cases (HIGH finding, 144b1fa): each was reported as complete with 0 issues and 0 notices.
MISSING_OR_MISREAD = {
    "en_freq_twice_a_day": ("Metformin 500 mg twice a day", "Metformin 500 mg once daily", "frequency_mismatch", None),
    "th_freq_chao_yen": ("Metformin 500 mg เช้า-เย็น", "Metformin 500 mg daily", "frequency_mismatch", None),
    "en_dose_missing_home": ("Simvastatin daily", "Simvastatin 40 mg daily", None, ("dose", "home_list")),
    "warfarin_tabs_no_dose": ("Warfarin 5 mg 1 tab daily", "Warfarin 2 tab daily", None, ("dose", "new_order")),
    "warfarin_twice_a_day": ("Warfarin 3 mg once daily", "Warfarin 3 mg twice a day", "frequency_mismatch", None),
    "warfarin_th_freq": ("Warfarin 3 mg วันละ 1 ครั้ง", "Warfarin 3 mg เช้า-เย็น", "frequency_mismatch", None),
    "warfarin_order_no_dose": ("Warfarin 3 mg daily", "Warfarin 1 tab daily", None, ("dose", "new_order")),
    "th_dose_missing": ("วาร์ฟาริน วันละ 1 ครั้ง", "Warfarin 3 mg daily", None, ("dose", "home_list")),
    "en_freq_unreadable": ("Metformin 500 mg thrice weekly", "Metformin 500 mg daily", None, ("frequency", "home_list")),
    "th_freq_unreadable": ("เมทฟอร์มิน 500 มก. สัปดาห์ละ 3 ครั้ง", "Metformin 500 mg daily", None, ("frequency", "home_list")),
}


@pytest.mark.parametrize("mode", ["rules_only", "rules_plus_model"])
@pytest.mark.parametrize("case", list(MISSING_OR_MISREAD))
def test_missing_field_is_never_silent(case, mode):
    home, order, issue_type, gap = MISSING_OR_MISREAD[case]
    result = run(snapshot(home=[home], orders=[order]), mode=mode)
    assert not same_meds_clean(result)
    if issue_type:
        assert [i["type"] for i in result["issues"]] == [issue_type]
    if gap:
        [mf] = of_type(result, "missing_field")
        assert (mf["field"], mf["conflicting_sources"][0]["source_type"]) == gap
        assert len(mf["conflicting_sources"]) == 2 and mf["conflicting_sources"][0]["raw_span"]
        assert [i["type"] for i in result["issues"]] == ["missing_field"]
        assert result["unchecked_comparisons"] == 1


def test_rule_missing_field():
    from app.pharma.models import NOTICE_TYPES

    assert "missing_field" not in NOTICE_TYPES
    stated = {"dose": "Metformin bid", "frequency": "Metformin 500 mg"}
    for field, text in stated.items():
        for target in ("home_list", "patient_reported", "new_order"):
            lists = {t: ["Metformin 500 mg bid"] for t in ("home_list", "patient_reported", "new_order")}
            lists[target] = [text]
            result = run(snapshot(home=lists["home_list"], reported=lists["patient_reported"], orders=lists["new_order"]))
            [mf] = result["issues"]
            assert (mf["type"], mf["field"], mf["rule_id"]) == ("missing_field", field, "missing_field@2.0.0")
            assert mf["conflicting_sources"][0]["source_type"] == target
            assert {s["source_type"] for s in mf["conflicting_sources"]} == {"home_list", "patient_reported", "new_order"}
            key = "dose_value" if field == "dose" else "frequency_code"
            assert mf["conflicting_sources"][0][key] is None
            assert mf["severity"] == "moderate" and mf["severity_rank"] == 3
            for src in mf["conflicting_sources"]:
                assert src["evidence_ref"] and src["available_at_time"] and "raw_span" in src
    # negative: fully specified entries raise nothing
    full = run(snapshot(home=["Metformin 500 mg bid"], reported=["เมทฟอร์มิน 500 มก. วันละ 2 ครั้ง"], orders=["Metformin 500 mg bid"]))
    assert same_meds_clean(full)
    # any source, even when the ingredient is in one source only (then 1 conflicting source)
    only = run(snapshot(home=["Metformin"], orders=["Amlodipine 5 mg daily"]))
    mfs = of_type(only, "missing_field")
    assert [(i["field"], len(i["conflicting_sources"])) for i in mfs] == [("dose", 1), ("frequency", 1)]
    # null in every source: one issue per (entry, field)
    both = run(snapshot(home=["Metformin"], orders=["Metformin"]))
    assert len(of_type(both, "missing_field")) == 4 and both["unchecked_comparisons"] == 2
    # a combination product shares an ingredient: the other entry is listed too (>= 2 sources)
    combo = run(snapshot(home=["Amoxicillin 500 mg tid"], orders=["Augmentin 1 g"]))
    [mf] = of_type(combo, "missing_field")
    assert mf["field"] == "frequency" and len(mf["conflicting_sources"]) == 2
    # unrecognised names are notices, never missing_field issues
    unknown = run(snapshot(home=["Qelvadrine"], orders=["Amlodipine 5 mg daily"]))
    assert of_type(unknown, "missing_field") == [] and notices(unknown, "unrecognised_drug")


PAIRS = [(a, b) for a in ("home_list", "patient_reported", "new_order") for b in ("home_list", "patient_reported", "new_order") if a != b]
STATED = "Metformin 500 mg bid"
NULLED = {"dose": "Metformin bid", "frequency": "Metformin 500 mg"}


@pytest.mark.parametrize("nulls", ["first", "second", "both"])
@pytest.mark.parametrize("pair", PAIRS, ids=[f"{a}-{b}" for a, b in PAIRS])
@pytest.mark.parametrize("field", ["dose", "frequency"])
def test_missing_never_agreement(field, pair, nulls):
    """S5R-A08: every comparison rule x ordered source-type pair x null pattern."""
    first, second = pair
    null_in = {"first": [first], "second": [second], "both": [first, second]}[nulls]
    lists = {t: [NULLED[field] if t in null_in else STATED] for t in pair}
    result = run(snapshot(home=lists.get("home_list"), reported=lists.get("patient_reported"), orders=lists.get("new_order")))
    assert not same_meds_clean(result)
    mfs = of_type(result, "missing_field")
    assert sorted((i["field"], i["conflicting_sources"][0]["source_type"]) for i in mfs) == sorted((field, t) for t in null_in)
    for mf in mfs:
        assert len(mf["conflicting_sources"]) == 2  # the ingredient is in 2 source types
    assert of_type(result, "dose_mismatch") == [] and of_type(result, "frequency_mismatch") == []
    assert [i["type"] for i in result["issues"]] == ["missing_field"] * len(null_in)
    assert result["unchecked_comparisons"] == 1
    # the mismatch rule still runs for the other field, stated in both, and never fires from the null entry
    other_differs = {"dose": ("Metformin bid", "Metformin tid"), "frequency": ("Metformin 500 mg", "Metformin 1000 mg")}[field]
    lists = {first: [other_differs[0]], second: [other_differs[1]]}
    diff = run(snapshot(home=lists.get("home_list"), reported=lists.get("patient_reported"), orders=lists.get("new_order")))
    other = "frequency_mismatch" if field == "dose" else "dose_mismatch"
    assert [i["type"] for i in diff["issues"] if i["type"].endswith("_mismatch")] == [other]
    assert len(of_type(diff, "missing_field")) == 2


def test_unchecked_comparisons_count():
    result = run(snapshot(home=["Metformin 500 mg bid"], reported=["Metformin bid"], orders=["Metformin 500 mg"]))
    # dose: home-reported, reported-order skipped; frequency: home-order, reported-order skipped
    assert result["unchecked_comparisons"] == 4
    assert sorted((i["field"], i["conflicting_sources"][0]["source_type"]) for i in of_type(result, "missing_field")) == [
        ("dose", "patient_reported"), ("frequency", "new_order")]
    # two entries in the same source type are not a cross-source comparison; discontinued entries are not compared
    same = run(snapshot(home=["Metformin 500 mg bid", "Metformin bid"], orders=[
        "Amlodipine 5 mg daily", {"text": "Metformin", "discontinue_intent": True, "reason": "synthetic"}]))
    assert same["unchecked_comparisons"] == 0
    assert all(s["unchecked_comparisons"] == 0 for s in [run(snapshot(home=[STATED], orders=[STATED]))])


FREQ_PHRASINGS = {
    "twice a day": "q12h", "every 12 hours": "q12h", "once a day": "q24h", "q.d.": "q24h", "เช้า-เย็น": "q12h",
    "every 8 hours": "q8h", "every 6 hours": "q6h", "every 24 hours": "q24h", "q 12 h": "q12h",
    "เช้า กลางวัน เย็น": "q8h", "เช้า กลางวัน เย็น ก่อนนอน": "q6h", "ทุก 12 ชั่วโมง": "q12h",
    "three times a day": "q8h", "2 times a day": "q12h", "every 4 hours": None, "q4h prn": "prn",
}


@pytest.mark.parametrize("surface", list(FREQ_PHRASINGS))
def test_mock_frequency_phrasings(surface):
    assert parse_entry(f"Metformin 500 mg {surface}")["frequency_code"] == FREQ_PHRASINGS[surface]
    assert parse_entry(f"Metformin 500 mg {surface}")["drug_name_raw"] == "Metformin"


def test_injector_heldout_surfaces_parse():
    from app.pharma.eval.inject import HELDOUT_FREQ_SURFACES
    from app.pharma.fixtures.build import FREQ_SURFACES

    for code, styles in HELDOUT_FREQ_SURFACES.items():
        for style, forms in styles.items():
            for form in forms:
                assert form not in FREQ_SURFACES[code][style], form  # held out from the clean fixtures
                assert parse_entry(f"Metformin 500 mg {form}")["frequency_code"] == code, form


def test_rule_omission():
    pos = run(snapshot(home=["Metformin 500 mg bid", "Amlodipine 5 mg daily"], orders=["Amlodipine 5 mg daily"]))
    [issue] = of_type(pos, "omission")
    assert issue["ingredients"] == ["metformin"] and issue["possible_substitution"] is False
    absent = [s for s in issue["conflicting_sources"] if s["presence"] == "absent"]
    assert [s["source_type"] for s in absent] == ["new_order"]
    ended = run(snapshot(
        home=["Metformin 500 mg bid", "Amlodipine 5 mg daily"],
        orders=["Amlodipine 5 mg daily", {"text": "Metformin 500 mg bid", "discontinue_intent": True, "reason": "synthetic: held"}],
    ))
    assert of_type(ended, "omission") == []
    sub = run(snapshot(home=["Simvastatin 20 mg daily"], orders=["Atorvastatin 40 mg daily"]))
    [issue] = of_type(sub, "omission")
    assert issue["possible_substitution"] is True
    reported_only = run(snapshot(home=[], reported=["ซาร่า 500 มก. เวลาปวด"], orders=["Amlodipine 5 mg daily"]))
    assert [i["ingredients"] for i in of_type(reported_only, "omission")] == [["acetaminophen"]]


ALLERGY_CASES = {
    "penicillin_amoxicillin": ("Penicillin (rash)", ["Amoxicillin 500 mg tid"], "allergy_class", ["amoxicillin"]),
    "penicillin_cephalexin": ("Penicillin (rash)", ["Cephalexin 500 mg qid"], "allergy_cross_reactivity", ["cephalexin"]),
    "sulfa_cotrimoxazole": ("Sulfonamide antibiotic - hives", ["Bactrim DS 1 tab bid"], "allergy_class", ["sulfamethoxazole"]),
    "aspirin_ibuprofen": ("Aspirin (angioedema)", ["Ibuprofen 400 mg tid"], "allergy_cross_reactivity", ["ibuprofen"]),
    "thai_brand_direct": ("แพ้ยา ซาร่า (ผื่น)", ["Paracetamol 500 mg prn"], "allergy_direct", ["acetaminophen"]),
}


@pytest.mark.parametrize("case", list(ALLERGY_CASES))
def test_allergy_cases(case):
    text, orders, subtype, ings = ALLERGY_CASES[case]
    result = run(snapshot(orders=orders, allergies=[text]))
    allergy_issues = [i for i in result["issues"] if i["type"].startswith("allergy_")]
    assert [(i["type"], i["ingredients"]) for i in allergy_issues] == [(subtype, ings)]
    issue = allergy_issues[0]
    assert result["issues"][0] is issue  # allergy issues sort first
    assert {s["source_type"] for s in issue["conflicting_sources"]} == {"allergy_record", "new_order"}
    if subtype == "allergy_cross_reactivity":
        assert issue["detail"]["citation"]


def test_allergy_negative_control_and_unmapped():
    neg = run(snapshot(orders=["Azithromycin 250 mg daily"], allergies=["Penicillin (rash)"]))
    assert [i for i in neg["issues"] if i["type"].startswith("allergy_")] == []
    unmapped = run(snapshot(orders=["Azithromycin 250 mg daily"], allergies=["Seafood (hives)"]))
    assert len(notices(unmapped, "allergy_unmapped")) == 1 and unmapped["issues"] == []
    home_med = run(snapshot(home=["Brufen 400 mg tid"], orders=[], allergies=["ibuprofen"]))
    assert of_type(home_med, "allergy_direct")


def test_cross_reactivity_citations():
    data = json.loads((DATA_DIR / "cross_reactivity.json").read_text(encoding="utf-8"))
    form = load_formulary()
    assert data["pairs"]
    for row in data["pairs"]:
        assert row["citation"].strip() and "doi:" in row["citation"]
        assert row["clinical_review_status"] == "pending_pharmacist"
        for side in ("allergen", "drug"):
            ref = row[side]
            assert ref["id"] in (form.classes if ref["kind"] == "class" else form.ingredients)


def test_severity_order():
    from app.pharma.rules import SEVERITY, TYPE_ORDER

    result = run(snapshot(
        home=["Simvastatin 20 mg daily", "Metformin 500 mg bid", "Amlodipine 5 mg daily"],
        orders=["Simvastatin 40 mg daily", "Tylenol 500 mg prn", "Sara 500 mg prn", "Augmentin 1 g bid", "Amlodipine daily",
                "Qelvadrine 5 mg daily"],
        allergies=["Penicillin"],
    ))
    ranks = [i["severity_rank"] for i in result["issues"]]
    assert ranks == sorted(ranks)
    assert [i["type"] for i in result["issues"]] == [
        "allergy_class", "duplication_ingredient", "dose_mismatch", "missing_field", "omission"]
    assert all(n["severity_rank"] > max(ranks) for n in result["notices"]) and notices(result, "unrecognised_drug")
    order = ["allergy_direct", "allergy_class", "allergy_cross_reactivity", "duplication_ingredient", "duplication_class",
             "dose_mismatch", "frequency_mismatch", "missing_field", "omission"]
    assert list(TYPE_ORDER) == order
    assert SEVERITY["missing_field"] == SEVERITY["dose_mismatch"] == SEVERITY["frequency_mismatch"]
    assert SEVERITY["duplication_class"][0] < SEVERITY["missing_field"][0] < SEVERITY["omission"][0]
