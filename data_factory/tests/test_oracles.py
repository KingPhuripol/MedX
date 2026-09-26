"""Independent reference checkers. They re-implement the rules from the cited sources and must NOT import
the generator's label functions (``data_factory.generate``)."""

import json
from datetime import datetime

from .conftest import REPO_ROOT

# Thresholds copied from the sources, independently of red_flags.json.
QSOFA = {"rr_ge": 22, "sbp_le": 100}                   # Seymour 2016, PMID 26903335
NEWS3 = {"rr_le": 8, "rr_ge": 25, "spo2_le": 91, "temp_le": 35.0, "sbp_le": 90, "sbp_ge": 220,
         "hr_le": 40, "hr_ge": 131}                     # Smith 2013, PMID 23295778
ANAPH_SBP_LT = 90                                       # Sampson 2006, PMID 16461139


def t(s):
    return datetime.fromisoformat(s)


def patient_text(tx):
    return " ".join(turn["text"] for turn in tx["turns"] if turn["speaker"] == "patient")


def oracle_red_flags(items) -> dict[str, list[str]]:
    flags: dict[str, set] = {}
    vitals = [i for i in items if i["data_type"] == "Vitals"]
    for v in vitals:
        rr, sbp, hr, spo2, temp, avpu = v["rr"], v["sbp"], v["hr"], v["spo2"], v["temp_c"], v["consciousness"]
        q = sum([rr is not None and rr >= QSOFA["rr_ge"], sbp is not None and sbp <= QSOFA["sbp_le"],
                 avpu is not None and avpu != "A"])
        if q >= 2:
            flags.setdefault("RF-QSOFA", set()).add(v["item_id"])
        news = [rr is not None and (rr <= NEWS3["rr_le"] or rr >= NEWS3["rr_ge"]),
                spo2 is not None and spo2 <= NEWS3["spo2_le"],
                temp is not None and temp <= NEWS3["temp_le"],
                sbp is not None and (sbp <= NEWS3["sbp_le"] or sbp >= NEWS3["sbp_ge"]),
                hr is not None and (hr <= NEWS3["hr_le"] or hr >= NEWS3["hr_ge"]),
                avpu in ("V", "P", "U")]
        if any(news):
            flags.setdefault("RF-NEWS-SINGLE3", set()).add(v["item_id"])
    low_bp = {v["item_id"] for v in vitals if v["sbp"] is not None and v["sbp"] < ANAPH_SBP_LT}
    for tx in (i for i in items if i["data_type"] == "IntakeTranscript"):
        s = patient_text(tx)
        sudden = "ทันที" in s
        if sudden and ("หน้าเบี้ยว" in s or "แขนขาอ่อนแรงซีกเดียว" in s or "พูดไม่ชัด" in s):
            flags.setdefault("RF-FAST", set()).add(tx["item_id"])
        if sudden and ("เจ็บแน่นหน้าอก" in s or "เจ็บหน้าอก" in s):
            flags.setdefault("RF-ACUTE-CHEST-PAIN", set()).add(tx["item_id"])
        if sudden and "ปวดศีรษะรุนแรง" in s:
            flags.setdefault("RF-THUNDERCLAP", set()).add(tx["item_id"])
        skin = "ผื่นลมพิษ" in s or "ปากบวม" in s
        resp = "หายใจลำบาก" in s or "หายใจมีเสียงหวีด" in s
        if skin and (resp or low_bp):
            flags.setdefault("RF-ANAPHYLAXIS", set()).update({tx["item_id"], *low_bp})
    return {k: sorted(v) for k, v in sorted(flags.items())}


def oracle_med_issues(items) -> set[tuple[str, tuple[str, ...]]]:
    lists = {i["list_source"]: i["entries"] for i in items if i["data_type"] == "MedicationList"}
    home, new = lists.get("home_list", []), lists.get("new_order")
    if new is None:
        return set()
    issues = set()
    by_drug: dict[str, list[dict]] = {}
    for entries in lists.values():
        for e in entries:
            by_drug.setdefault(e["generic_name"], []).append(e)
    for drug, es in by_drug.items():
        if len(es) >= 2 and len({(e["dose_value"], e["dose_unit"]) for e in es}) > 1:
            issues.add(("dose_mismatch", (drug,)))
        if len(es) >= 2 and len({e["frequency"] for e in es}) > 1:
            issues.add(("frequency_mismatch", (drug,)))
    new_names = {e["generic_name"] for e in new}
    issues |= {("omission", (e["generic_name"],)) for e in home if e["generic_name"] not in new_names}
    for a in new:
        for b in new:
            if a["generic_name"] < b["generic_name"] and a["atc_code"][:5] == b["atc_code"][:5]:
                issues.add(("duplicate_therapy", (a["generic_name"], b["generic_name"])))
    classes = [e["atc_class"] for i in items if i["data_type"] == "AllergyList" and i["status"] == "known"
               for e in i["entries"]]
    issues |= {("allergy_conflict", (e["generic_name"],)) for e in new for c in classes if e["atc_code"].startswith(c)}
    return issues


def test_oracle_thresholds_match_registry():
    rules = {r["rule_id"]: r for r in json.loads((REPO_ROOT / "data_factory/templates/red_flags.json").read_text("utf-8"))}
    q = {(c["param"], c["op"]): c["value"] for c in rules["RF-QSOFA"]["criterion"]["conditions"]}
    assert q[("rr", ">=")] == QSOFA["rr_ge"] and q[("sbp", "<=")] == QSOFA["sbp_le"]
    n = {(c["param"], c["op"]): c["value"] for c in rules["RF-NEWS-SINGLE3"]["criterion"]["conditions"]}
    assert n == {("rr", "<="): 8, ("rr", ">="): 25, ("spo2", "<="): 91, ("temp_c", "<="): 35.0, ("sbp", "<="): 90,
                 ("sbp", ">="): 220, ("hr", "<="): 40, ("hr", ">="): 131, ("consciousness", "in"): ["V", "P", "U"]}


def test_red_flag_oracle_agrees(dataset):
    pairs = 0
    for cid, c in dataset.cases.items():
        for row in c["gold"]["decision_times"]:
            snap = c["snapshots"][row["decision_point"]]
            gold = {f["rule_id"]: f["item_ids"] for f in row["red_flags"]}
            assert oracle_red_flags(snap["items"]) == gold, (cid, row["decision_point"])
            pairs += 1
    assert pairs >= 400


def test_near_miss_negatives(dataset):
    near = {"rr": {21, 24}, "sbp": {101, 91}, "hr": {130, 41}, "spo2": {92}, "temp_c": {35.1}}
    hits = []
    for cid, c in dataset.cases.items():
        vit = [i for i in c["journey"]["items"] if i["data_type"] == "Vitals"]
        if any(v[k] in vals for v in vit for k, vals in near.items()):
            if not any(oracle_red_flags(s["items"]) for s in c["snapshots"].values()):
                assert all(not r["red_flags"] for r in c["gold"]["decision_times"]), cid
                hits.append(cid)
    assert len(hits) >= 20


def test_medication_oracle_agrees(dataset):
    logged: dict[str, set] = {}
    for r in dataset.injections:
        logged.setdefault(r["case_id"], set()).add((r["issue_type"], tuple(sorted(r["drugs"]))))
    for cid, c in dataset.cases.items():
        found = oracle_med_issues(c["snapshots"]["T2"]["items"])
        assert found == logged.get(cid, set()), cid
        assert oracle_med_issues(c["snapshots"]["T1"]["items"]) == set(), cid
