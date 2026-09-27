"""Deterministic rule-based MOCK for ``care.suggest.v1`` (the offline default provider path).

Registered in ``app.gateway.mock_tasks``; only the mock provider calls it. Pure function of the gateway
inputs: the snapshot items and the red-flag alert ids computed before the call (read-only context). It
matches patient-turn text and structured items against ``rules/care_rules_v1.json`` (written from the dev
split only). It never returns alerts, screening or escalation. Not calibrated; not expert-reviewed (D1).
"""

from __future__ import annotations

import operator
from typing import Any

from ..gateway import mock_tasks
from .models import TASK
from .ruleset import CARE_RULES_VERSION, rules

_OPS = {">=": operator.ge, "<=": operator.le, ">": operator.gt, "<": operator.lt}


def _match_text(rule: dict[str, Any], text: str) -> bool:
    return all(any(k in text for k in group) for group in rule["all_of"]) and not any(
        k in text for k in rule.get("none_of", ()))


def _vitals_hit(rule: dict[str, Any], v: dict[str, Any]) -> bool:
    hits = sum(1 for p, op, x in rule["conditions"] if v.get(p) is not None and _OPS[op](v[p], x))
    return hits >= rule["min_count"]


def suggest(inputs: dict[str, Any]) -> dict[str, Any]:
    r = rules()
    items = sorted(inputs["items"], key=lambda it: (it["available_at_time"], it["item_id"]))
    candidates: list[tuple[dict[str, Any], list[str]]] = []  # (rule, evidence item ids), in rank order
    for alert in inputs.get("alerts", []):  # alert-driven items rank first
        for rule in r["alert_rules"]:
            if rule["alert"] == alert["rule_id"] and alert["item_ids"]:
                candidates.append((rule, list(alert["item_ids"])))
    vitals = [it for it in items if it["data_type"] == "Vitals"]
    if vitals:
        for rule in r["vitals_rules"]:
            if _vitals_hit(rule, vitals[-1]):
                candidates.append((rule, [vitals[-1]["item_id"]]))
    for tx in (it for it in items if it["data_type"] == "IntakeTranscript"):
        text = " ".join(t["text"] for t in tx["turns"] if t["speaker"] == "patient")
        for rule in r["text_rules"]:
            if _match_text(rule, text):
                candidates.append((rule, [tx["item_id"]]))

    resulted = {r["lab_names"][res["test"]] for it in items if it["data_type"] == "LabSeries"
                for res in it["results"] if res["test"] in r["lab_names"]}
    if len(vitals) >= 2:
        resulted.add(r["repeat_vitals_code"])

    next_info: dict[str, list[str]] = {}
    pathways: dict[str, list[str]] = {}
    for rule, refs in candidates:
        for code in rule["next_info"]:
            if code not in resulted:
                next_info.setdefault(code, [])
                next_info[code] = sorted(set(next_info[code]) | set(refs))
        pathways.setdefault(rule["pathway"], [])
        pathways[rule["pathway"]] = sorted(set(pathways[rule["pathway"]]) | set(refs))
    return {
        "next_information": [{"code": c, "evidence_refs": refs} for c, refs in list(next_info.items())[:5]],
        "pathway_options": [{"code": c, "evidence_refs": refs} for c, refs in list(pathways.items())[:3]],
    }


mock_tasks.register(TASK, suggest, version=CARE_RULES_VERSION)
