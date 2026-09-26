import hashlib
import json
import re
import shutil

import pytest

from app.triage import redflags
from app.triage.fixtures import load_entries
from app.triage.models import Snapshot

from .helpers import DROP, T0, make_case, snap

RULE_IDS = [
    "RF-SPO2", "RF-RR", "RF-SBP", "RF-HR", "RF-CONSC", "RF-TEMP", "RF-QSOFA", "RF-CHEST", "RF-STROKE",
    "RF-THUNDER", "RF-ANAPH", "RF-SUICIDE", "RF-GIBLEED", "RF-ECTOPIC", "RF-MENING", "RF-HYPOGLY",
]


def fired(overrides: dict) -> set[str]:
    alerts, _ = redflags.evaluate(snap(overrides))
    return {a.rule_id for a in alerts}


def test_every_rule_has_source():
    rules = redflags.rules()
    assert [r["id"] for r in rules] == RULE_IDS
    for r in rules:
        assert r["severity"] == "escalate"
        assert r["name_en"] and r["name_th"] and r["rationale"] and r["message_en"] and r["message_th"]
        src = r["source"]
        assert src["citation"].strip()
        assert re.fullmatch(r"\d{7,8}", src.get("pmid", "")) or src.get("url", "").startswith("https://")
        assert re.fullmatch(r"\d{4}-\d{2}-\d{2}", src["accessed"])


def test_ruleset_hash_pinned_to_version(tmp_path):
    assert redflags.RULESET_VERSION == "rf-1.0.0"
    assert redflags.file_sha256() == redflags.RULESET_SHA256
    assert json.loads(redflags.RULES_PATH.read_text())["version"] == redflags.RULESET_VERSION
    tampered = tmp_path / "rules.json"
    shutil.copy(redflags.RULES_PATH, tampered)
    doc = json.loads(tampered.read_text())
    doc["rules"][0]["condition"]["value"] = 92  # threshold change without a version bump
    tampered.write_text(json.dumps(doc))
    with pytest.raises(RuntimeError, match="version bump"):
        redflags.load_rules(tampered)
    # A new hash alone is not enough either: the file's version must match RULESET_VERSION.
    new_sha = hashlib.sha256(tampered.read_bytes()).hexdigest()
    assert redflags.load_rules(tampered, pinned_sha256=new_sha)  # same version string -> loads when re-pinned
    doc["version"] = "rf-9.9.9"
    tampered.write_text(json.dumps(doc))
    with pytest.raises(RuntimeError, match="version"):
        redflags.load_rules(tampered, pinned_sha256=hashlib.sha256(tampered.read_bytes()).hexdigest())


BOUNDARIES = {
    "RF-SPO2": [({"vital.spo2": 91}, True), ({"vital.spo2": 92}, False)],
    "RF-RR": [({"vital.rr": 8}, True), ({"vital.rr": 9}, False), ({"vital.rr": 25}, True), ({"vital.rr": 24}, False)],
    "RF-SBP": [({"vital.sbp": 90}, True), ({"vital.sbp": 91}, False), ({"vital.sbp": 220}, True),
               ({"vital.sbp": 219}, False)],
    "RF-HR": [({"vital.hr": 40}, True), ({"vital.hr": 41}, False), ({"vital.hr": 131}, True),
              ({"vital.hr": 130}, False)],
    "RF-CONSC": [({"vital.avpu": "V"}, True), ({"vital.avpu": "U"}, True), ({"vital.avpu": "A"}, False),
                 ({"vital.new_confusion": True}, True)],
    "RF-TEMP": [({"vital.temp_c": 35.0}, True), ({"vital.temp_c": 35.1}, False)],
    "RF-QSOFA": [({"vital.rr": 22, "vital.sbp": 100}, True), ({"vital.rr": 21, "vital.sbp": 100}, False),
                 ({"vital.rr": 22, "vital.sbp": 101}, False), ({"vital.rr": 22, "vital.new_confusion": True}, True)],
    "RF-CHEST": [({"symptom.acute_chest_pain": "present"}, True), ({"symptom.acute_chest_pain": "absent"}, False)],
    "RF-STROKE": [({"symptom.sudden_facial_droop": "present"}, True), ({"symptom.sudden_limb_weakness": "present"}, True),
                  ({"symptom.sudden_speech_disturbance": "present"}, True),
                  ({"symptom.sudden_vision_disturbance": "present"}, True), ({}, False)],
    "RF-THUNDER": [({"symptom.thunderclap_headache": "present"}, True), ({}, False)],
    "RF-ANAPH": [
        ({"symptom.allergen_exposure": "present", "symptom.airway_breathing_compromise": "present"}, True),
        ({"symptom.allergen_exposure": "present", "vital.sbp": 89}, True),
        ({"symptom.allergen_exposure": "present", "vital.sbp": 90}, False),
        ({"symptom.airway_breathing_compromise": "present"}, False),
    ],
    "RF-SUICIDE": [({"symptom.suicidal_ideation": "present"}, True), ({"symptom.self_harm": "present"}, True),
                   ({}, False)],
    "RF-GIBLEED": [({"symptom.hematemesis": "present"}, True), ({"symptom.melena": "present"}, True), ({}, False)],
    "RF-ECTOPIC": [
        ({"sex": "female", "age": 15, "symptom.abdominal_pain": "present"}, True),
        ({"sex": "female", "age": 14, "symptom.abdominal_pain": "present"}, False),
        ({"sex": "female", "age": 50, "symptom.vaginal_bleeding": "present"}, True),
        ({"sex": "female", "age": 51, "symptom.vaginal_bleeding": "present"}, False),
        ({"sex": "female", "age": 30, "symptom.abdominal_pain": "present", "pregnancy_status": "negative"}, False),
        ({"sex": "female", "age": 30, "symptom.abdominal_pain": "present", "pregnancy_status": "positive"}, True),
        ({"sex": "male", "age": 30, "symptom.abdominal_pain": "present"}, False),
    ],
    "RF-MENING": [
        ({"symptom.fever": "present", "symptom.neck_stiffness": "present"}, True),
        ({"symptom.fever": "present", "symptom.non_blanching_rash": "present"}, True),
        ({"symptom.fever": "absent", "symptom.neck_stiffness": "present"}, False),
        ({"symptom.fever": "present"}, False),
    ],
    "RF-HYPOGLY": [({"vital.capillary_glucose_mg_dl": 53}, True), ({"vital.capillary_glucose_mg_dl": 54}, False)],
}
BOUNDARY_CASES = [(rule, ov, exp) for rule, cases in BOUNDARIES.items() for ov, exp in cases]


def test_boundaries_cover_every_rule():
    assert set(BOUNDARIES) == set(RULE_IDS)
    for rule, cases in BOUNDARIES.items():
        assert {exp for _, exp in cases} == {True, False}, rule


@pytest.mark.parametrize(("rule", "overrides", "expected"), BOUNDARY_CASES,
                         ids=[f"{r}-{i}" for i, (r, _, _) in enumerate(BOUNDARY_CASES)])
def test_rule_boundary(rule, overrides, expected):
    assert (rule in fired(overrides)) is expected


def test_redflag_recall_is_total():
    for split in ("dev", "holdout", None):
        entries = [e for e in load_entries() if split is None or e.split == split]
        gold_cases = [e for e in entries if e.gold.red_flag_rules]
        assert gold_cases
        for e in gold_cases:
            alerts, _ = redflags.evaluate(Snapshot(e.case, e.as_of))
            got = {a.rule_id for a in alerts}
            assert got, f"{e.case.case_ref}: no alert (case-level recall)"
            assert set(e.gold.red_flag_rules) <= got, f"{e.case.case_ref}: missed {set(e.gold.red_flag_rules) - got}"


def test_unknown_not_negative():
    # Missing symptom facts are unknown, never absent: the rule is not evaluable, not "no red flag".
    alerts, ne = redflags.evaluate(snap({"symptom.acute_chest_pain": DROP}))
    assert "RF-CHEST" not in {a.rule_id for a in alerts}
    assert "RF-CHEST" in {n.rule_id for n in ne}
    alerts, ne = redflags.evaluate(snap({"symptom.acute_chest_pain": "unknown"}))
    assert "RF-CHEST" in {n.rule_id for n in ne}
    # Pregnancy status unknown or not recorded -> RF-ECTOPIC fires.
    for status in ("unknown", DROP):
        got = fired({"sex": "female", "age": 28, "symptom.abdominal_pain": "present", "pregnancy_status": status})
        assert "RF-ECTOPIC" in got
    # any(): one unknown input and one present input still fires; all false -> no alert, not listed.
    got = fired({"symptom.fever": "present", "symptom.neck_stiffness": DROP, "symptom.non_blanching_rash": "present"})
    assert "RF-MENING" in got


def test_not_evaluable_listed():
    s = snap({"vital.spo2": DROP, "vital.temp_c": DROP, "vital.avpu": DROP, "vital.capillary_glucose_mg_dl": DROP})
    alerts, ne = redflags.evaluate(s)
    by_rule = {n.rule_id: n.missing_inputs for n in ne}
    assert by_rule["RF-SPO2"] == ["vital.spo2"]
    assert by_rule["RF-TEMP"] == ["vital.temp_c"]
    assert by_rule["RF-CONSC"] == ["vital.avpu"]
    assert by_rule["RF-HYPOGLY"] == ["vital.capillary_glucose_mg_dl"]
    assert not ({a.rule_id for a in alerts} & set(by_rule))
    # A fully recorded normal intake has nothing to list.
    alerts, ne = redflags.evaluate(snap({}))
    assert alerts == [] and ne == []


def test_snapshot_as_of():
    case = make_case({"vital.spo2": 97}, late=[("vital.spo2", 89, 30)])
    early, _ = redflags.evaluate(Snapshot(case, T0.replace(minute=20)))
    late, _ = redflags.evaluate(Snapshot(case, T0.replace(minute=30)))
    assert "RF-SPO2" not in {a.rule_id for a in early}
    assert "RF-SPO2" in {a.rule_id for a in late}
    for e in load_entries():
        if e.gold.temporal:
            early, _ = redflags.evaluate(Snapshot(e.case, e.gold.temporal.early_as_of))
            late, _ = redflags.evaluate(Snapshot(e.case, e.as_of))
            assert sorted(a.rule_id for a in early) == e.gold.temporal.red_flag_rules
            assert sorted(a.rule_id for a in late) == e.gold.red_flag_rules
            assert set(e.gold.red_flag_rules) - set(e.gold.temporal.red_flag_rules)


def test_naive_as_of_rejected():
    with pytest.raises(ValueError):
        Snapshot(make_case({}), T0.replace(tzinfo=None))
