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
    assert redflags.RULESET_VERSION == "rf-1.1.0"
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
        # Measured temperature threshold (> 38.0 C, Sepsis-3 SIRS / NEWS2 band edge), fever denied.
        ({"symptom.fever": "absent", "vital.temp_c": 38.1, "symptom.neck_stiffness": "present"}, True),
        ({"symptom.fever": "absent", "vital.temp_c": 38.0, "symptom.neck_stiffness": "present"}, False),
        ({"symptom.fever": "absent", "vital.temp_c": 38.1, "symptom.non_blanching_rash": "present"}, True),
        ({"symptom.fever": "absent", "vital.temp_c": 39.8}, False),
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


# ---- F1: a measured temperature is never overridden by a self-reported "no fever" (rf-1.1.0) ----

def _mening(overrides: dict):
    alerts, ne = redflags.evaluate(snap(overrides))
    alert = next((a for a in alerts if a.rule_id == "RF-MENING"), None)
    listed = next((n for n in ne if n.rule_id == "RF-MENING"), None)
    return alert, listed


def test_mening_fires_on_measured_fever_when_fever_denied():
    # Reproduction 1: temp 39.8, neck stiffness present, fever self-reported absent, AVPU A.
    ov = {"vital.temp_c": 39.8, "symptom.neck_stiffness": "present", "symptom.fever": "absent", "vital.avpu": "A"}
    alert, listed = _mening(ov)
    assert alert is not None and listed is None
    s = snap(ov)
    # The measured temperature is the fever evidence; the denied self-report is not cited as evidence.
    assert s.get("vital.temp_c").fact_id in alert.evidence_refs
    assert s.get("symptom.fever").fact_id not in alert.evidence_refs


def test_mening_fires_on_measured_fever_when_fever_not_recorded():
    # Reproduction 2: same input with symptom.fever not recorded -> fires (not merely not_evaluable).
    for fever in (DROP, "unknown"):
        alert, listed = _mening({"vital.temp_c": 39.8, "symptom.neck_stiffness": "present",
                                 "symptom.fever": fever, "vital.avpu": "A"})
        assert alert is not None and listed is None, fever


def test_mening_denied_fever_without_temperature_is_not_evaluable():
    # Fever denied but no temperature recorded: cannot be read as "no red flag".
    alert, listed = _mening({"vital.temp_c": DROP, "symptom.neck_stiffness": "present", "symptom.fever": "absent"})
    assert alert is None and listed is not None
    assert listed.missing_inputs == ["vital.temp_c"]


def test_mening_fever_unknown_and_normal_temperature_is_not_evaluable():
    alert, listed = _mening({"vital.temp_c": 37.0, "symptom.neck_stiffness": "present", "symptom.fever": DROP})
    assert alert is None and listed is not None and listed.missing_inputs == ["symptom.fever"]


def test_mening_no_fever_normal_temperature_no_meningeal_sign_is_quiet():
    alert, listed = _mening({"vital.temp_c": 39.8, "symptom.fever": "absent"})
    assert alert is None and listed is None


def _leaves(cond):
    if "symptom" in cond or "vital" in cond or "field" in cond:
        yield cond
    for c in cond.get("any") or cond.get("all") or cond.get("of") or []:
        yield from _leaves(c)


# Symptom elements that have an objective vital counterpart in the intake model. Each must be OR-ed with
# that vital inside the same rule, so "absent" self-report can never evaluate the element as False while an
# abnormal measurement is on record. Symptoms without a vital counterpart are listed with the reason.
SYMPTOM_VITAL_COUNTERPART = {"fever": "temp_c"}
NO_VITAL_COUNTERPART = {
    "acute_chest_pain": "no ECG/troponin in intake",
    "sudden_facial_droop": "neuro exam finding, no vital",
    "sudden_limb_weakness": "neuro exam finding, no vital",
    "sudden_speech_disturbance": "neuro exam finding, no vital",
    "sudden_vision_disturbance": "neuro exam finding, no vital",
    "thunderclap_headache": "history only",
    "allergen_exposure": "history only",
    # WAO 2020 gives no numeric SpO2/RR cut-off for respiratory compromise; RF-SPO2 / RF-RR cover severe
    # measured values independently (see test_anaph_breathing_denied_but_hypoxic_still_escalates).
    "airway_breathing_compromise": "no sourced numeric threshold; RF-SPO2/RF-RR escalate independently",
    "suicidal_ideation": "history only",
    "self_harm": "history only",
    "hematemesis": "history only",
    "melena": "history only",
    "neck_stiffness": "exam finding, no vital",
    "non_blanching_rash": "exam finding, no vital",
    "abdominal_pain": "history only",
    "vaginal_bleeding": "history only",
}


def test_symptom_elements_with_vital_counterpart_accept_the_vital():
    for rule in redflags.rules():
        leaves = list(_leaves(rule["condition"]))
        for leaf in leaves:
            if "symptom" not in leaf:
                continue
            name = leaf["symptom"]
            assert name in SYMPTOM_VITAL_COUNTERPART or name in NO_VITAL_COUNTERPART, f"{rule['id']}: {name}"
            if name in SYMPTOM_VITAL_COUNTERPART:
                vital = SYMPTOM_VITAL_COUNTERPART[name]
                assert any(l.get("vital") == vital for l in leaves), f"{rule['id']}: {name} lacks vital.{vital}"


def test_anaph_breathing_denied_but_hypoxic_still_escalates():
    alerts, _ = redflags.evaluate(snap({"symptom.allergen_exposure": "present",
                                        "symptom.airway_breathing_compromise": "absent",
                                        "vital.spo2": 88, "vital.rr": 26}))
    assert {"RF-SPO2", "RF-RR"} <= {a.rule_id for a in alerts}
