"""Gold join for the i2 comparison (e1-style gold, e1 mapping v1). Research prototype - not for clinical use.

Gold is joined only after both arms have run on snapshot inputs. Tasks (one record per DP and task):

* ``dept``: evaluable DPs whose gold department maps to E (11 and 12 excluded, counted); ``ranked`` = the arm's
  top-3 mapped to E (an abstention is ``[]``, i.e. wrong);
* ``abstention``: the ``dept`` population plus the ``NOT_EVALUABLE`` DPs; ``y_pred`` = top-1 in E or null;
* ``calls``: every DP; ``n_calls`` = gateway calls for that DP;
* ``rf_rule_<S1r rule>``: gold (DP, rule) pairs of mappable S1r rules, Arm A only; ``y_pred`` = a mapped S4 rule
  fired at that DP.
"""

from __future__ import annotations

from typing import Any

from eval.adapters import mapping
from .arms import ARM_A, ARM_B

TEXT_S4 = set(mapping.TEXT_RULES_S4)
TEXT_S1R = set(mapping.TEXT_RULES_S1R)
VITAL_S1R = ("RF-NEWS-SINGLE3", "RF-QSOFA", "RF-NEWS-AGG5")


def gold_dp(g: dict[str, Any], dp: str) -> dict[str, Any]:
    return next(d for d in g["decision_times"] if d["decision_point"] == dp)


def dept_gold(d: dict[str, Any]) -> tuple[str | None, str]:
    """(E code, route): route ``department`` | ``abstention_only`` | ``excluded`` | ``red_flag_metrics``."""
    return mapping.gold_department(d["target_department"], d["department_evaluable"])


def e_ranked(top3: list[str]) -> list[str]:
    return mapping.s4_to_e(top3)


def _base(rec: dict[str, Any], task: str) -> dict[str, Any]:
    return {"patient_id": rec["patient_ref"], "decision_point_id": rec["dp_id"], "task": task}


def rows_for(rec: dict[str, Any], g: dict[str, Any]) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """(system rows = Arm A, comparator rows = Arm B ``single_prompt``) for one DP."""
    d = gold_dp(g, rec["decision_point"])
    e, route = dept_gold(d)
    sys_rows, cmp_rows = [], []
    for arm, out in ((ARM_A, sys_rows), (ARM_B, cmp_rows)):
        ranked = e_ranked(rec[arm]["department"]["top3"])
        extra = {} if arm == ARM_A else {"comparator": ARM_B}
        if route == "department":
            out.append({**_base(rec, "dept"), **extra, "y_true": e, "ranked": ranked})
        if route in ("department", "abstention_only"):
            out.append({**_base(rec, "abstention"), **extra, "y_true": e or mapping.NOT_EVALUABLE,
                        "y_pred": ranked[0] if ranked else None})
        out.append({**_base(rec, "calls"), **extra, "n_calls": rec[arm]["calls"]})
    targets = mapping.s1r_rule_targets()
    fired = set(rec[ARM_A]["red_flag"]["fired"])
    for rf in d["red_flags"]:
        tg = targets[rf["rule_id"]]
        if tg is None:
            continue  # UNMAPPABLE (RF-NEWS-AGG5): reported as null in the summary, never a metric row
        sys_rows.append({**_base(rec, f"rf_rule_{rf['rule_id']}"), "y_true": True, "y_pred": bool(fired & set(tg))})
    return sys_rows, cmp_rows


def gold_tasks(g: dict[str, Any]) -> list[tuple[str, str]]:
    """(task, dp_id) memberships from gold alone (manifest task lists; checked against the scored rows)."""
    out = []
    targets = mapping.s1r_rule_targets()
    for d in g["decision_times"]:
        dp_id = f"{g['case_id']}/{d['decision_point']}"
        _, route = dept_gold(d)
        if route == "department":
            out.append(("dept", dp_id))
        if route in ("department", "abstention_only"):
            out.append(("abstention", dp_id))
        out.append(("calls", dp_id))
        out += [(f"rf_rule_{rf['rule_id']}", dp_id) for rf in d["red_flags"] if targets[rf["rule_id"]] is not None]
    return out


# ---------------------------------------------------------------- red-flag detail (Arm A)


def miss_reason(rule: str, rec: dict[str, Any], d: dict[str, Any]) -> str:
    """Why a gold (DP, S1r rule) pair was not detected by Arm A."""
    tg = mapping.s1r_rule_targets()[rule]
    if tg is None:
        return "unmappable"
    rf = rec[ARM_A]["red_flag"]
    ne = [r for r in tg if r in rf["not_evaluated"]]
    if ne and len(ne) == len(tg):
        missing = [m for r in ne for m in rf["missing_inputs"][r]]
        if any(":stale(" in m for m in missing):
            return "stale"
        if all(m.startswith("symptom.") for m in missing):
            return "unmentioned"
        return "not_evaluated"
    if rule in VITAL_S1R:
        gold_items = {i for x in d["red_flags"] if x["rule_id"] == rule for i in x["item_ids"]}
        read = {i for r in tg for i in rf["evaluated_on"].get(r, [])}
        if gold_items and read and not gold_items & read:
            return "latest_wins"  # the screen read a later reading than the one the gold rule fired on
    return "evaluated_not_fired"


def is_text_near_miss(g: dict[str, Any], d: dict[str, Any]) -> bool:
    return bool(g["scenario"].get("text_near_miss")) and not any(r["rule_id"] in TEXT_S1R for r in d["red_flags"])
