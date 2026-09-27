"""Adapter behaviour: vitals mapping, hand-built voice/triage cases, population accounting (E1-A02)."""

from __future__ import annotations

import json
from collections import Counter

import pytest

from eval.adapters import mapping, triage, voice
from eval.adapters.score import populations

from .conftest import hand_case


def _kinds(facts):
    return {f["kind"]: f["value"] for f in facts}


def test_vitals_mapping():
    assert mapping.consciousness_facts("C") == {"avpu": "A", "new_confusion": True}
    for v in "AVPU":
        assert mapping.consciousness_facts(v) == {"avpu": v}
    with pytest.raises(ValueError):
        mapping.consciousness_facts("X")
    c = hand_case("VIT", ["ปวดหัวค่ะ"], vitals={"consciousness": "C", "rr": None, "spo2": None, "hr": 131})
    snap = c.snapshots["T1"]
    facts, n = triage.snapshot_facts(snap)
    k = _kinds(facts)
    assert k["vital.avpu"] == "A" and k["vital.new_confusion"] is True
    assert "vital.rr" not in k and "vital.spo2" not in k  # null -> no fact, never a normal value
    assert k["vital.hr"] == 131 and k["age"] == 40 and k["sex"] == "male"
    assert not any(x.startswith("vital.on_oxygen") or x == "pregnancy_status" for x in k)
    assert n == {"vitals_items": 1, "null_values": 2, "on_oxygen_unmappable": 1, "consciousness_C": 1}
    vit = next(i for i in snap["items"] if i["data_type"] == "Vitals")
    for f in facts:  # every vitals fact keeps its own item's available_at_time
        if f["kind"].startswith("vital."):
            assert f["available_at_time"] == vit["available_at_time"] and f["provenance"] == vit["item_id"]
    # consciousness null -> no avpu fact
    facts2, n2 = triage.snapshot_facts(hand_case("VIT2", ["x"], vitals={"consciousness": None}).snapshots["T1"])
    assert "vital.avpu" not in _kinds(facts2) and n2["null_values"] == 1


H1 = ["ปวดหัวค่ะ", "เป็นมา 3 วันแล้วค่ะ", "ไม่แพ้ยาค่ะ"]
H2 = ["เจ็บหน้าอกค่ะ", "เป็นมา 2 ชั่วโมงค่ะ", "แพ้เพนิซิลลินค่ะ"]
H3 = ["ไข้ค่ะ", "เป็นมา 1 สัปดาห์ค่ะ", "ไม่แน่ใจค่ะ"]


@pytest.fixture(scope="module")
def hand_outputs():
    cases = [hand_case("H1", H1, vitals={}),
             hand_case("H2", H2, vitals={"spo2": 88, "consciousness": "C", "rr": None}),
             hand_case("H3", H3, vitals={"sbp": 95, "rr": 24, "consciousness": "C"})]
    ctx, eng = voice.make_context()
    s3 = {c.case_id: voice.replay(ctx, c) for c in cases}
    eng.dispose()
    s4 = triage.run_split(cases, s3)
    return cases, s3, s4


def test_voice_replay_hand_case(hand_outputs):
    cases, s3, _ = hand_outputs
    st = {cid: {f: (v["state"], v["value"]) for f, v in o["facts"].items()} for cid, o in s3.items()}
    assert st["H1"]["chief_complaint"] == ("KNOWN", "headache")
    assert st["H1"]["onset_duration"] == ("KNOWN", "P3D")
    assert st["H1"]["allergy_status"] == ("KNOWN", "none")
    assert st["H2"]["chief_complaint"] == ("KNOWN", "chest_pain")
    assert st["H2"]["onset_duration"] == ("KNOWN", "PT2H")
    assert st["H2"]["allergy_status"] == ("KNOWN", "present")
    assert st["H3"]["chief_complaint"] == ("KNOWN", "fever")
    assert st["H3"]["onset_duration"] == ("KNOWN", "P1W") and mapping.normalize_iso("P1W") == "P7D"
    assert "allergy_status" not in st["H3"]  # "not sure" is never recorded as none
    for c in cases:
        o = s3[c.case_id]
        assert o["status"] == "replayed" and o["n_turns"] == 6
        # speakers keep their role; the CC span is the patient's own turn
        assert o["facts"]["chief_complaint"]["span_turn_indexes"] == [1]
        assert o["facts"]["chief_complaint"]["span_text"] == {"H1": H1, "H2": H2, "H3": H3}[c.case_id][0]
        windows = voice.turn_windows(c.snapshots["T1"]["items"][0])
        assert [w[0] for w in windows] == ["nurse", "patient"] * 3
        assert all(windows[i][3] == windows[i + 1][2] for i in range(len(windows) - 1))
        assert windows[-1][3].isoformat() == c.snapshots["T1"]["items"][0]["observed_at"]
    # the replay is deterministic (no generated IDs or wall-clock time in the output)
    ctx, eng = voice.make_context()
    again = voice.replay(ctx, cases[0])
    eng.dispose()
    assert json.dumps(again, sort_keys=True, ensure_ascii=False) == json.dumps(s3["H1"], sort_keys=True,
                                                                               ensure_ascii=False)


def test_triage_hand_case(hand_outputs):
    _, _, s4 = hand_outputs
    h1, h2, h3 = (s4[c][0] for c in ("H1", "H2", "H3"))
    # H1: normal vitals, headache -> no alert, department suggested (NEURO -> E-MED)
    assert h1["alerts"] == [] and h1["department"]["status"] == "suggested"
    assert h1["department"]["top3"] == ["NEURO"] and mapping.s4_to_e(h1["department"]["top3"]) == ["E-MED"]
    assert _kinds(h1["facts"])["symptom.headache"] == "present"
    assert _kinds(h1["facts"])["chief_complaint"] == H1[0] and _kinds(h1["facts"])["onset_duration"] == "P3D"
    # H2: SpO2 88 and ACVPU C -> RF-SPO2 + RF-CONSC; escalation, no department; chest_pain has no S4 symptom
    assert sorted(h2["alerts"]) == ["RF-CONSC", "RF-SPO2"] and h2["escalation_required"] is True
    assert h2["department"]["status"] != "suggested" and h2["always_answer_ranking"] == ["CARD"]
    assert h2["input_info"]["cc_symptom_unmappable"] is True
    assert not any(k.startswith("symptom.") for k in _kinds(h2["facts"]))
    assert "vital.rr" not in _kinds(h2["facts"])
    assert mapping.detected_s1r_rules(h2["alerts"]) == ["RF-NEWS-SINGLE3"]
    # H3: SBP 95, RR 24, new confusion -> qSOFA 3 -> RF-QSOFA (and RF-CONSC); fever -> MED
    assert sorted(h3["alerts"]) == ["RF-CONSC", "RF-QSOFA"]
    assert mapping.detected_s1r_rules(h3["alerts"]) == ["RF-NEWS-SINGLE3", "RF-QSOFA"]
    assert h3["department"]["top3"] == ["MED"] and h3["always_answer_ranking"] == ["MED"]
    # no S4 text rule can fire: S3 records no acuity/exposure, so its symptoms are never acuity-qualified
    for o in (h1, h2, h3):
        assert not set(o["alerts"]) & set(mapping.TEXT_RULES_S4)


def test_population_accounting(ds, e1_run):
    s = json.loads((e1_run["out"] / "e1_summary.json").read_text(encoding="utf-8"))
    for split in ("dev", "test"):
        v = s["splits"][split]
        assert v["status"] == "run"
        gold = {p.stem: json.loads(p.read_text(encoding="utf-8")) for p in sorted((ds / "gold" / split).glob("*.json"))}
        n_cases = len(gold)
        n_dps = sum(len(g["decision_times"]) for g in gold.values())
        n_pairs = sum(len(d["red_flags"]) for g in gold.values() for d in g["decision_times"])
        pops = {p["population"]: p for p in v["populations"]}
        assert pops == {p["population"]: p for p in populations(gold)}
        for p in v["populations"]:
            assert p["n_total"] == p["n_scored"] + sum(p["n_excluded"].values()), p
            unit_total = {"case": n_cases, "decision point": n_dps, "(DP, rule) pair": n_pairs}[p["unit"]]
            if not p["population"].startswith("rf_rule:"):
                assert p["n_total"] == unit_total, p
        by_rule = Counter(f["rule_id"] for g in gold.values() for d in g["decision_times"] for f in d["red_flags"])
        assert sum(pops[f"rf_rule:{r}"]["n_total"] for r in by_rule) == n_pairs
        # n_scored equals the scored prediction records per task (nothing dropped silently)
        preds = [json.loads(x) for k in ("voice", "triage")
                 for x in (e1_run["out"] / split / k / "predictions.jsonl").read_text(encoding="utf-8").splitlines()]
        tasks = Counter(r["task"] for r in preds)
        for task in ("voice_intake", "voice_cc", "voice_allergy_false_none", "rf_case_recall", "rf_fpr",
                     "rf_text_t1_recall", "rf_text_t1_fpr", "dept", "false_abstain", "abstention",
                     "abst_on_not_evaluable", "expected_action"):
            assert tasks[task] == pops[task]["n_scored"], (split, task)
        assert sum(len(r["ordered"]) for r in preds if r["task"] == "rf_rule_recall") == pops["rf_rule_recall"][
            "n_scored"]
        # the excluded departments are counted from gold
        dts = [d for g in gold.values() for d in g["decision_times"]]
        ex = pops["dept"]["n_excluded"]
        assert ex["12"] == sum(d["department_evaluable"] and d["target_department"] == "12" for d in dts)
        assert ex["11"] == sum(d["department_evaluable"] and d["target_department"] == "11" for d in dts)
        assert ex["NOT_EVALUABLE"] == sum(not d["department_evaluable"] or d["target_department"] == "NOT_EVALUABLE"
                                          for d in dts)
        # unmapped counts per mapping section are in the summary (json and md)
        assert set(v["unmapped_counts"]) >= {"department_s1r", "red_flag_s1r", "chief_complaint_s1r_to_s3",
                                             "vitals_demographics", "consciousness", "s3_cc_to_s4_symptom",
                                             "s3_field_to_s4_fact"}
    md = (e1_run["out"] / "e1_summary.md").read_text(encoding="utf-8")
    assert md.count("### Unmapped items per mapping section") == 2
    assert md.count("### Populations (n_total = n_scored + excluded)") == 2
