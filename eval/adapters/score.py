"""Join system outputs with gold into S8r scored records, per task (slice e1). Research prototype.

System outputs are computed from snapshots only; gold is joined here, after the fact. Every population is
accounted for as n_total = n_scored + sum(n_excluded by reason); nothing is dropped silently.
"""

from __future__ import annotations

from collections import Counter
from typing import Any

from . import mapping
from .baselines import TAMTEE, always_answer, occurs

VOICE_FIELDS = ("chief_complaint", "onset_duration", "allergy_status")
ACTIONS = ("suggest", "abstain", "escalate")


def _dp_id(case_id: str, dp: str) -> str:
    return f"{case_id}/{dp}"


def _gold_dp(g: dict[str, Any], dp: str) -> dict[str, Any]:
    return next(d for d in g["decision_times"] if d["decision_point"] == dp)


# ---------------------------------------------------------------- voice


def voice_gold(g: dict[str, Any]) -> dict[str, Any]:
    """Gold voice fields from the T1 gold (values, or absence; CC acceptable set or UNMAPPABLE)."""
    rf = _gold_dp(g, "T1")["required_fields"]
    out: dict[str, Any] = {"cc_code": None, "cc_acceptable": None, "cc_unmappable": False,
                           "onset_duration": None, "allergy": rf.get("allergy_status")}
    cc = rf.get("chief_complaint")
    if isinstance(cc, dict):
        out["cc_code"] = cc["code"]
        acc = mapping.cc_acceptable(cc["code"])
        out["cc_acceptable"], out["cc_unmappable"] = acc, acc is None
    d = rf.get("duration")
    if isinstance(d, dict):
        out["onset_duration"] = mapping.duration_iso(d["value"], d["unit"])
        out["duration_unit"] = d["unit"]
    a = rf.get("allergy_status")
    out["allergy_value"] = a["value"] if isinstance(a, dict) else "MISSING"
    return out


def voice_rows(case_id: str, patient: str, g: dict[str, Any], s3: dict[str, Any]) -> list[dict[str, Any]]:
    vg = voice_gold(g)
    facts = s3.get("facts", {})
    states = {f: (facts[f]["state"] if f in facts else "MISSING") for f in VOICE_FIELDS}
    known = {f: facts[f]["value"] for f in VOICE_FIELDS if f in facts and facts[f]["state"] == "KNOWN"}
    extracted: dict[str, Any] = {}
    gold_f: dict[str, Any] = {}
    if not vg["cc_unmappable"]:
        pred_cc = known.get("chief_complaint")
        if pred_cc is not None:
            extracted["chief_complaint"] = pred_cc
        if vg["cc_acceptable"]:
            acc = vg["cc_acceptable"]
            gold_f["chief_complaint"] = pred_cc if pred_cc in acc else acc[0]
    if "onset_duration" in known:
        extracted["onset_duration"] = mapping.normalize_iso(known["onset_duration"])
    if vg["onset_duration"] is not None:
        gold_f["onset_duration"] = mapping.normalize_iso(vg["onset_duration"])
    if "allergy_status" in known:
        extracted["allergy_status"] = known["allergy_status"]
    ga = mapping.allergy_gold(vg["allergy_value"])
    if ga is not None:
        gold_f["allergy_status"] = ga
    base = {"patient_id": patient, "decision_point_id": case_id, "case_id": case_id}
    rows = [{**base, "task": "voice_intake", "gold_fields": gold_f, "extracted_fields": extracted,
             "gold_cc_code": vg["cc_code"], "cc_acceptable": vg["cc_acceptable"],
             "cc_excluded_unmappable": vg["cc_unmappable"], "s3_states": states,
             "gold_allergy_value": vg["allergy_value"]}]
    if not vg["cc_unmappable"]:  # the CC field is scored on its own population (UNMAPPABLE excluded, counted)
        cc = "chief_complaint"
        rows.append({**base, "task": "voice_cc", "gold_fields": {k: v for k, v in gold_f.items() if k == cc},
                     "extracted_fields": {k: v for k, v in extracted.items() if k == cc},
                     "gold_cc_code": vg["cc_code"], "cc_acceptable": vg["cc_acceptable"],
                     "s3_state": states[cc]})
    if vg["allergy_value"] in ("known", "MISSING"):
        false_none = known.get("allergy_status") == "none"
        rows.append({**base, "task": "voice_allergy_false_none", "y_true": True, "y_pred": false_none,
                     "gold_allergy_value": vg["allergy_value"], "s3_allergy_state": states["allergy_status"]})
    return rows


# ---------------------------------------------------------------- triage


def system_action(out: dict[str, Any]) -> str:
    if out["alerts"]:
        return "escalate"
    return "suggest" if out["department"]["status"] == "suggested" else "abstain"


def triage_rows(case_id: str, patient: str, g: dict[str, Any], outs: list[dict[str, Any]], snaps: dict[str, Any],
                s_star: str, fallback_e: str) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    rows: list[dict[str, Any]] = []
    cmp_rows: list[dict[str, Any]] = []
    mapped = mapping.mapped_s4_rules()
    targets = mapping.s1r_rule_targets()
    for o in outs:
        dp = o["dp"]
        gd = _gold_dp(g, dp)
        if gd["T"] != o["T"]:
            raise ValueError(f"{case_id}/{dp}: gold T {gd['T']} != snapshot T {o['T']}")
        base = {"patient_id": patient, "decision_point_id": _dp_id(case_id, dp), "case_id": case_id, "dp": dp,
                "T": o["T"]}
        gold_rules = sorted({f["rule_id"] for f in gd["red_flags"]})
        fired = list(o["alerts"])
        detected = mapping.detected_s1r_rules(fired)
        rf = {"gold_rules": gold_rules, "fired_s4": fired, "detected_s1r": detected}
        if gold_rules:
            rows.append({**base, **rf, "task": "rf_case_recall", "y_true": True, "y_pred": bool(fired)})
            rows.append({**base, **rf, "task": "rf_rule_recall", "ordered": gold_rules, "suggested": detected})
            mappable = [r for r in gold_rules if targets[r]]
            if mappable:
                rows.append({**base, **rf, "task": "rf_rule_recall_mappable", "ordered": mappable,
                             "suggested": [r for r in detected if r in mappable]})
            for r in mappable:
                rows.append({**base, **rf, "task": f"rf_rule_{r}", "y_true": True, "y_pred": r in detected})
        else:
            rows.append({**base, **rf, "task": "rf_fpr", "y_true": True, "y_pred": bool(fired)})
            rows.append({**base, **rf, "task": "rf_fpr_mapped", "y_true": True,
                         "y_pred": any(x in mapped for x in fired)})
        if dp == "T1":
            text_pos = any(r in mapping.TEXT_RULES_S1R for r in gold_rules)
            task = "rf_text_t1_recall" if text_pos else "rf_text_t1_fpr"
            sys_hit = any(x in mapping.TEXT_RULES_S4 for x in fired)
            rows.append({**base, **rf, "task": task, "y_true": True, "y_pred": sys_hit})
            for name, s in (("shortcut_s_star", s_star), ("shortcut_tamtee", TAMTEE)):
                cmp_rows.append({**base, "task": task, "comparator": name, "y_true": True,
                                 "y_pred": occurs(s, snaps[dp]), "substring": s})
        # department / abstention
        e_gold, route = mapping.gold_department(gd["target_department"], gd["department_evaluable"])
        dept = o["department"]
        sys_e = mapping.s4_to_e(dept["top3"]) if dept["status"] == "suggested" else []
        aa = always_answer(o["always_answer_ranking"], fallback_e)
        dinfo = {"gold_department": gd["target_department"], "gold_e": e_gold, "dept_status": dept["status"],
                 "dept_reason": dept["reason"], "system_top3_s4": dept["top3"]}
        if e_gold is not None:
            rows.append({**base, **dinfo, "task": "dept", "y_true": e_gold, "ranked": sys_e})
            cmp_rows.append({**base, "task": "dept", "comparator": "always_answer", "y_true": e_gold, "ranked": aa})
            rows.append({**base, **dinfo, "task": "false_abstain", "y_true": True,
                         "y_pred": dept["status"] != "suggested"})
        if e_gold is not None or route == "abstention_only":
            y_true = e_gold if e_gold is not None else mapping.NOT_EVALUABLE
            rows.append({**base, **dinfo, "task": "abstention", "y_true": y_true,
                         "y_pred": sys_e[0] if sys_e else None})
            cmp_rows.append({**base, "task": "abstention", "comparator": "always_answer", "y_true": y_true,
                             "y_pred": aa[0]})
        if route == "abstention_only":
            rows.append({**base, **dinfo, "task": "abst_on_not_evaluable", "y_true": True,
                         "y_pred": dept["status"] != "suggested"})
        rows.append({**base, **dinfo, "task": "expected_action", "y_true": gd["expected_action"],
                     "y_pred": system_action(o), "gold_rules": gold_rules, "fired_s4": fired})
    return rows, cmp_rows


def gold_tasks(case_id: str, g: dict[str, Any]) -> list[tuple[str, str]]:
    """(task, decision_point_id) memberships from gold alone. Used to freeze task patient lists without
    running the system; the pipeline asserts that the scored rows have exactly these memberships."""
    out = [("voice_intake", case_id)]
    if not voice_gold(g)["cc_unmappable"]:
        out.append(("voice_cc", case_id))
    if voice_gold(g)["allergy_value"] in ("known", "MISSING"):
        out.append(("voice_allergy_false_none", case_id))
    targets = mapping.s1r_rule_targets()
    for d in g["decision_times"]:
        dp = d["decision_point"]
        did = _dp_id(case_id, dp)
        rules = sorted({f["rule_id"] for f in d["red_flags"]})
        if rules:
            out += [("rf_case_recall", did), ("rf_rule_recall", did)]
            mappable = [r for r in rules if targets[r]]
            if mappable:
                out.append(("rf_rule_recall_mappable", did))
            out += [(f"rf_rule_{r}", did) for r in mappable]
        else:
            out += [("rf_fpr", did), ("rf_fpr_mapped", did)]
        if dp == "T1":
            text_pos = any(r in mapping.TEXT_RULES_S1R for r in rules)
            out.append(("rf_text_t1_recall" if text_pos else "rf_text_t1_fpr", did))
        e, route = mapping.gold_department(d["target_department"], d["department_evaluable"])
        if e is not None:
            out += [("dept", did), ("false_abstain", did)]
        if e is not None or route == "abstention_only":
            out.append(("abstention", did))
        if route == "abstention_only":
            out.append(("abst_on_not_evaluable", did))
        out.append(("expected_action", did))
    return out


# ---------------------------------------------------------------- population accounting


def populations(gold: dict[str, dict[str, Any]]) -> list[dict[str, Any]]:
    """Every population recomputed from gold: n_total = n_scored + sum(excluded by reason)."""
    cases = list(gold.values())
    dps = [(g, d) for g in cases for d in g["decision_times"]]
    pats = lambda sel: len({g["patient_ref"] for g, _ in sel})  # noqa: E731
    out = []

    def add(name: str, definition: str, unit: str, total: int, scored: int, excluded: dict[str, int],
            n_patients: int) -> None:
        if total != scored + sum(excluded.values()):
            raise AssertionError(f"population {name}: {total} != {scored} + {excluded}")
        out.append({"population": name, "definition": definition, "unit": unit, "n_total": total,
                    "n_scored": scored, "n_excluded": dict(sorted(excluded.items())), "n_patients_scored": n_patients})

    vg = [(g, voice_gold(g)) for g in cases]
    cc_un = sum(v["cc_unmappable"] for _, v in vg)
    add("voice_intake", "every case at T1 (onset_duration, allergy_status, micro-average)", "case", len(cases),
        len(cases), {}, len({g["patient_ref"] for g in cases}))
    add("voice_cc", "cases whose gold CC is mappable to S3 or MISSING (chief_complaint field)", "case", len(cases),
        len(cases) - cc_un, {"UNMAPPABLE": cc_un}, len({g["patient_ref"] for g, v in vg if not v["cc_unmappable"]}))
    fn = [(g, v) for g, v in vg if v["allergy_value"] in ("known", "MISSING")]
    add("voice_allergy_false_none", "cases with gold allergy known or MISSING", "case", len(cases), len(fn),
        {"gold_no_known_allergy": len(cases) - len(fn)}, len({g["patient_ref"] for g, _ in fn}))
    pos = [(g, d) for g, d in dps if d["red_flags"]]
    neg = [(g, d) for g, d in dps if not d["red_flags"]]
    add("rf_case_recall", "gold red-flag-positive DPs", "decision point", len(dps), len(pos),
        {"gold_negative (scored by rf_fpr)": len(neg)}, pats(pos))
    add("rf_fpr", "gold red-flag-negative DPs", "decision point", len(dps), len(neg),
        {"gold_positive (scored by rf_case_recall)": len(pos)}, pats(neg))
    pairs = [(g, d, f["rule_id"]) for g, d in pos for f in d["red_flags"]]
    targets = mapping.s1r_rule_targets()
    unm = sum(1 for *_, r in pairs if not targets[r])
    add("rf_rule_recall", "gold (DP, rule) pairs; UNMAPPABLE pairs scored as missed", "(DP, rule) pair",
        len(pairs), len(pairs), {}, pats(pos))
    add("rf_rule_recall_mappable", "gold (DP, rule) pairs with a mapped S4 rule", "(DP, rule) pair",
        len(pairs), len(pairs) - unm, {"UNMAPPABLE": unm},
        len({g["patient_ref"] for g, d, r in pairs if targets[r]}))
    for rule in sorted(targets):
        sel = [(g, d) for g, d, r in pairs if r == rule]
        excl = {"UNMAPPABLE": len(sel)} if not targets[rule] else {}
        add(f"rf_rule:{rule}", f"gold DPs with {rule}", "decision point", len(sel),
            0 if not targets[rule] else len(sel), excl, 0 if not targets[rule] else pats(sel))
    t1 = [(g, d) for g, d in dps if d["decision_point"] == "T1"]
    tpos = [(g, d) for g, d in t1 if any(f["rule_id"] in mapping.TEXT_RULES_S1R for f in d["red_flags"])]
    add("rf_text_t1_recall", "T1 DPs with a gold text red flag", "decision point", len(dps), len(tpos),
        {"T1 text-negative (scored by rf_text_t1_fpr)": len(t1) - len(tpos), "not T1": len(dps) - len(t1)},
        pats(tpos))
    tneg = [(g, d) for g, d in t1 if (g, d) not in tpos]
    add("rf_text_t1_fpr", "T1 DPs without a gold text red flag", "decision point", len(dps), len(tneg),
        {"T1 text-positive (scored by rf_text_t1_recall)": len(tpos), "not T1": len(dps) - len(t1)}, pats(tneg))
    routes = Counter()
    dept = []
    for g, d in dps:
        e, route = mapping.gold_department(d["target_department"], d["department_evaluable"])
        routes[route if e is None else "department"] += 1
        if e is not None:
            dept.append((g, d))
    ex = {"12": routes["red_flag_metrics"], "11": routes["excluded"], "NOT_EVALUABLE": routes["abstention_only"],
          "UNMAPPABLE": 0}
    add("dept", "DPs with department_evaluable and a gold department in E", "decision point", len(dps), len(dept),
        ex, pats(dept))
    add("false_abstain", "department population", "decision point", len(dps), len(dept), ex, pats(dept))
    ne = [(g, d) for g, d in dps if not d["department_evaluable"] or d["target_department"] == "NOT_EVALUABLE"]
    add("abstention", "department population + NOT_EVALUABLE DPs", "decision point", len(dps),
        len(dept) + len(ne), {"12": ex["12"], "11": ex["11"]}, pats(dept + ne))
    add("abst_on_not_evaluable", "NOT_EVALUABLE DPs", "decision point", len(dps), len(ne),
        {"department population": len(dept), "12": ex["12"], "11": ex["11"]}, pats(ne))
    add("expected_action", "every DP (the 3-class label is defined on every DP)", "decision point", len(dps),
        len(dps), {}, pats(dps))
    return out


def unmapped_counts(gold: dict[str, dict[str, Any]], outs: dict[str, list[dict[str, Any]]],
                    s3: dict[str, dict[str, Any]]) -> dict[str, Any]:
    """Unmapped items per mapping section, as met in this split."""
    dps = [d for g in gold.values() for d in g["decision_times"]]
    targets = mapping.s1r_rule_targets()
    vg = [voice_gold(g) for g in gold.values()]
    tri = [o for v in outs.values() for o in v]
    cc_sym = Counter()
    for o in s3.values():
        f = o["facts"].get("chief_complaint")
        if f and f["state"] == "KNOWN" and mapping.s3_symptom(f["value"]) is None:
            cc_sym[f["value"]] += 1
    no_fact = Counter(x for o in tri if o["dp"] == "T1" for x in o["input_info"]["no_fact_fields"])
    return {
        "department_s1r": {"11 (UNMAPPABLE, excluded)": sum(d["target_department"] == "11" for d in dps),
                           "12 (scored by red-flag metrics)": sum(d["target_department"] == "12" for d in dps),
                           "NOT_EVALUABLE (abstention only)": sum(not d["department_evaluable"] for d in dps)},
        "red_flag_s1r": {"RF-NEWS-AGG5 gold pairs (UNMAPPABLE)": sum(
            1 for d in dps for f in d["red_flags"] if not targets[f["rule_id"]])},
        "chief_complaint_s1r_to_s3": {"cases with UNMAPPABLE gold CC": sum(v["cc_unmappable"] for v in vg),
                                      "UNMAPPABLE codes met": dict(sorted(Counter(
                                          v["cc_code"] for v in vg if v["cc_unmappable"]).items()))},
        "vitals_demographics": {
            "on_oxygen values not passed (UNMAPPABLE)": sum(o["input_info"]["counts"]["on_oxygen_unmappable"]
                                                           for o in tri),
            "null vital values (no fact)": sum(o["input_info"]["counts"]["null_values"] for o in tri),
            "pregnancy_status (no S1r item)": len(tri),
            "unit": "per S4 case built (one per DP)"},
        "consciousness": {"C values mapped to avpu A + new_confusion": sum(
            o["input_info"]["counts"]["consciousness_C"] for o in tri)},
        "s3_cc_to_s4_symptom": {"S3 CC codes with no S4 symptom (per case)": dict(sorted(cc_sym.items()))},
        "s3_field_to_s4_fact": {"S3 fields not KNOWN -> no S4 fact (per case, T1)": dict(sorted(no_fact.items()))},
    }
