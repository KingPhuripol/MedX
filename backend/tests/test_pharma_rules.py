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
    # a missing dose is not a match: no dose_mismatch issue, but a visible missing_field notice (never silence)
    gap = run(snapshot(home=["Simvastatin 20 mg daily"], reported=["Simvastatin daily"], orders=["Simvastatin 20 mg daily"]))
    assert of_type(gap, "dose_mismatch") == []
    [notice] = notices(gap, "missing_field")
    assert (notice["field"], notice["source_type"], notice["evidence_ref"]) == ("dose", "patient_reported", "t/patient_reported/1")
    assert notice["ingredients"] == ["simvastatin"] and notice["stated_in"] == ["home_list", "new_order"]
    assert notice["raw_span"] == "Simvastatin daily" and gap["unchecked_comparisons"] == 1
    noted = run(snapshot(home=["Simvastatin 20 mg daily"], reported=["ซิมวาสแตติน วันละครั้ง"], orders=["Simvastatin 40 mg daily"]))
    [issue] = of_type(noted, "dose_mismatch")
    assert issue["notes"] == [{"kind": "missing_field", "field": "dose", "source_type": "patient_reported", "evidence_ref": "t/patient_reported/1"}]
    assert all(s["source_type"] != "patient_reported" for s in issue["conflicting_sources"])


def test_rule_frequency_mismatch():
    for surface in ("bid", "วันละ 2 ครั้ง", "1x2 pc", "q12h", "twice daily"):
        assert parse_entry(f"Metformin 500 mg {surface}")["frequency_code"] == "q12h"
    assert same_meds_clean(run(snapshot(home=["Metformin 500 mg twice a day"], orders=["Metformin 500 mg เช้า-เย็น"])))
    same = run(snapshot(home=["Metformin 500 mg bid"], reported=["เมทฟอร์มิน 500 มก. วันละ 2 ครั้ง"], orders=["Metformin 500 mg 1x2 pc"]))
    assert of_type(same, "frequency_mismatch") == []
    diff = run(snapshot(home=["Metformin 500 mg bid"], orders=["Metformin 500 mg tid"]))
    [issue] = of_type(diff, "frequency_mismatch")
    assert {s["frequency_code"] for s in issue["conflicting_sources"]} == {"q12h", "q8h"}
    # a missing frequency is not a match: no frequency_mismatch issue, but a visible missing_field notice
    gap = run(snapshot(home=["Metformin 500 mg bid"], orders=["Metformin 500 mg"]))
    assert of_type(gap, "frequency_mismatch") == []
    [notice] = notices(gap, "missing_field")
    assert (notice["field"], notice["source_type"], notice["stated_in"]) == ("frequency_code", "new_order", ["home_list"])
    assert gap["unchecked_comparisons"] == 1


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
    "en_freq_unreadable": ("Metformin 500 mg thrice weekly", "Metformin 500 mg daily", None, ("frequency_code", "home_list")),
    "th_freq_unreadable": ("เมทฟอร์มิน 500 มก. สัปดาห์ละ 3 ครั้ง", "Metformin 500 mg daily", None, ("frequency_code", "home_list")),
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
        [notice] = notices(result, "missing_field")
        assert (notice["field"], notice["source_type"]) == gap
        assert notice["evidence_ref"] and notice["raw_span"] and notice["compared_with"]
        assert result["unchecked_comparisons"] == 1


def test_missing_field_scope():
    # an order line with neither dose nor frequency: one notice per field
    bare = run(snapshot(home=["Metformin 500 mg twice a day"], orders=["Metformin"]))
    assert [(n["field"], n["source_type"]) for n in notices(bare, "missing_field")] == [
        ("dose", "new_order"), ("frequency_code", "new_order")]
    # ingredient in one source only: nothing to compare, so no missing_field notice (omission covers it)
    only_home = run(snapshot(home=["Metformin"], orders=["Amlodipine 5 mg daily"]))
    assert notices(only_home, "missing_field") == []
    # null in every source is still unchecked (one notice per source and field)
    both = run(snapshot(home=["Metformin"], orders=["Metformin"]))
    assert len(notices(both, "missing_field")) == 4 and both["unchecked_comparisons"] == 4
    # a discontinued order entry is not compared
    ended = run(snapshot(home=["Metformin 500 mg bid"], orders=[{"text": "Metformin", "discontinue_intent": True, "reason": "synthetic"}]))
    assert notices(ended, "missing_field") == []
    # the missing_field note on a mismatch issue is kept, and the notice is also raised
    both_ways = run(snapshot(home=["Simvastatin 20 mg daily"], reported=["ซิมวาสแตติน วันละครั้ง"], orders=["Simvastatin 40 mg daily"]))
    assert of_type(both_ways, "dose_mismatch") and len(notices(both_ways, "missing_field")) == 1


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


def test_severity_order_is_fixed():
    result = run(snapshot(
        home=["Simvastatin 20 mg daily", "Metformin 500 mg bid"],
        orders=["Simvastatin 40 mg daily", "Tylenol 500 mg prn", "Sara 500 mg prn", "Augmentin 1 g bid"],
        allergies=["Penicillin"],
    ))
    ranks = [i["severity_rank"] for i in result["issues"]]
    assert ranks == sorted(ranks)
    assert [i["type"] for i in result["issues"]] == ["allergy_class", "duplication_ingredient", "dose_mismatch", "omission"]
