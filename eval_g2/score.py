"""Red-flag scoring for the g2 re-test (Arm A / Case Graph only). Research prototype - not for clinical use.

Units and definitions (predeclared). ``rf_case_recall`` mirrors e1 ``eval/adapters/protocol.py`` ``rf_case_recall``
exactly - gold-positive DPs with >=1 alert of ANY rule - even though e1 calls this decision-point statistic "case-level":

* ``rf_case_recall`` (PRIMARY, unit DP): gold has >=1 red flag at the DP; y_pred = the Case Graph fired >=1 alert.
* ``rf_rulematched_dp`` (secondary, unit DP): same population; y_pred = an alert of a rule mapped to one of the DP's
  gold rules (stricter: a wrong-rule alert does not count).
* ``rf_rule_<S1r rule>`` (secondary, unit DP): gold (DP, rule) pairs; y_pred = a mapped S4 rule fired.
* ``rf_case_agg`` / ``rf_case_agg_rulematched`` (secondary, unit CASE): cases with >=1 gold-positive DP; caught if any
  such DP has any alert / a rule-matched alert.
* ``rf_fpr`` (secondary, unit DP): gold-negative DPs; y_pred = >=1 alert of any rule (the value is a false-positive
  rate; y_true is fixed True so the shared accuracy statistic returns the alert share, as in e1).
* ``rf_surfaced`` (secondary safety, unit DP): gold-positive DPs; y_pred = alert fired OR a gold rule's mapped S4
  rules were not_evaluated (insufficient input surfaced). Silent escalation failure = not surfaced = the screen
  evaluated the rule, raised no alert, and said nothing.
"""

from __future__ import annotations

from typing import Any

from eval_i2.arms import ARM_A
from eval_i2.score import gold_dp, s1r_targets

CASE_TASKS = ("rf_case_agg", "rf_case_agg_rulematched")


def _gold_rules(d: dict[str, Any]) -> list[str]:
    return sorted({f["rule_id"] for f in d["red_flags"]})


def dp_flags(rec: dict[str, Any], d: dict[str, Any]) -> dict[str, Any]:
    rf = rec[ARM_A]["red_flag"]
    fired = set(rf["fired"])
    rules = _gold_rules(d)
    t = s1r_targets()
    targets = {s for r in rules for s in (t.get(r) or [])}
    ne = set(rf["not_evaluated"])
    surfaced_ne = any(set(t.get(r) or []) & ne for r in rules)
    return {"rules": rules, "fired": sorted(fired), "any": bool(fired), "matched": bool(fired & targets),
            "surfaced": bool(fired) or surfaced_ne}


def gold_tasks(g: dict[str, Any]) -> list[tuple[str, str]]:
    """(task, unit id) memberships from gold alone; unit id = DP id, or case id for the case-level tasks."""
    out: list[tuple[str, str]] = []
    targets = s1r_targets()
    pos_case = False
    for d in g["decision_times"]:
        dp_id = f"{g['case_id']}/{d['decision_point']}"
        if d["red_flags"]:
            pos_case = True
            out += [("rf_case_recall", dp_id), ("rf_rulematched_dp", dp_id), ("rf_surfaced", dp_id)]
            out += [(f"rf_rule_{r}", dp_id) for r in _gold_rules(d) if targets.get(r) is not None]
        else:
            out.append(("rf_fpr", dp_id))
    if pos_case:
        out += [(t, g["case_id"]) for t in CASE_TASKS]
    return out


def rows_for_case(recs: list[dict[str, Any]], g: dict[str, Any]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    targets = s1r_targets()
    case_any = case_matched = pos = False
    for rec in recs:
        d = gold_dp(g, rec["decision_point"])
        f = dp_flags(rec, d)
        base = {"patient_id": rec["patient_ref"], "decision_point_id": rec["dp_id"], "y_true": True}
        if d["red_flags"]:
            pos = True
            case_any |= f["any"]
            case_matched |= f["matched"]
            rows += [{**base, "task": "rf_case_recall", "y_pred": f["any"]},
                     {**base, "task": "rf_rulematched_dp", "y_pred": f["matched"]},
                     {**base, "task": "rf_surfaced", "y_pred": f["surfaced"]}]
            fired = set(f["fired"])
            for r in f["rules"]:
                if targets.get(r) is not None:
                    rows.append({**base, "task": f"rf_rule_{r}", "y_pred": bool(fired & set(targets[r]))})
        else:
            rows.append({**base, "task": "rf_fpr", "y_pred": f["any"]})
    if pos:
        cb = {"patient_id": recs[0]["patient_ref"], "decision_point_id": g["case_id"], "y_true": True}
        rows += [{**cb, "task": "rf_case_agg", "y_pred": case_any},
                 {**cb, "task": "rf_case_agg_rulematched", "y_pred": case_matched}]
    return rows
