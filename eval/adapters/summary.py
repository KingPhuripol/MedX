"""e1 summary: every metric row with bootstrap CI and exact intervals, verdicts, exclusions and safety lists.

Research prototype - not for clinical use. Output is canonical (sorted keys, no wall-clock time) and is a pure
function of the committed per-split outputs.
"""

from __future__ import annotations

import json
from collections import Counter
from pathlib import Path
from typing import Any

from eval.bootstrap import RatioStat, cluster_bootstrap
from eval.exact import clopper_pearson, wilson
from eval.registry import prepare

from . import mapping

BANNER = mapping.BANNER
RESEARCH = "Research prototype - not for clinical use"
PROPORTION_METRICS = {"accuracy", "topk_accuracy", "coverage", "selective_accuracy"}
EXACT_NOTE = ("Wilson and Clopper-Pearson intervals assume independent decision points; decision points of one "
              "patient are not independent, so they ignore patient clustering. They are shown next to the "
              "patient-level bootstrap CI and n_patients.")
DEGENERATE_RULE = ("A bootstrap CI is degenerate when the S8r flag 'unstable' is set, ci_low == ci_high, or "
                   "x is 0 or n; the reported interval is then Clopper-Pearson (interval_method='clopper_pearson'). "
                   "Otherwise the patient-level bootstrap percentile interval is reported.")
NOT_EVALUATED = [
    {"row": "Voice Agent: comparison with form filling", "reason": "needs a human-factors study with users; S3 out "
     "of scope (no form-filling comparator can be simulated honestly)"},
    {"row": "Voice Agent: response latency and total time", "reason": "in-process mock timing is not representative "
     "of a deployed system, and recording wall-clock time would break byte reproducibility"},
]
TOL = 1e-12


def _key(r: dict[str, Any]) -> tuple[str, str]:
    return (r["patient_id"], r["decision_point_id"])


def _is_proportion(spec: dict[str, Any]) -> bool:
    if spec["name"] in PROPORTION_METRICS:
        return True
    return spec["name"] in ("set_prf", "field_prf") and spec["params"].get("component") in ("precision", "recall")


def interval_fields(point: float | None, x: int | None, n: int | None, ci_low: float | None, ci_high: float | None,
                    unstable: bool, proportion: bool) -> dict[str, Any]:
    """Exact intervals and the degenerate rule for one arm of one metric."""
    out: dict[str, Any] = {"x": x, "n": n, "proportion": proportion, "wilson": None, "clopper_pearson": None,
                           "degenerate": False, "degenerate_reasons": [], "interval": None,
                           "interval_method": None}
    if point is None:
        out["exact_reason"] = "undefined point estimate (empty denominator)"
        return out
    reasons = []
    if unstable:
        reasons.append("bootstrap flagged unstable")
    if ci_low is None or ci_high is None:
        reasons.append("no bootstrap CI")
    elif ci_low == ci_high:
        reasons.append("ci_low == ci_high")
    if proportion and x is not None and n and x in (0, n):
        reasons.append("x in {0, n}")
    out["degenerate"], out["degenerate_reasons"] = bool(reasons), reasons
    if proportion and n:
        out["wilson"] = list(wilson(x, n))
        out["clopper_pearson"] = list(clopper_pearson(x, n))
        if reasons:
            out["interval"], out["interval_method"] = out["clopper_pearson"], "clopper_pearson"
        else:
            out["interval"], out["interval_method"] = [ci_low, ci_high], "bootstrap_percentile"
    else:
        out["exact_reason"] = "not a binomial proportion (F1 = 2TP / (2TP + FP + FN)); no exact interval"
        out["interval"] = None if ci_low is None else [ci_low, ci_high]
        out["interval_method"] = None if ci_low is None else "bootstrap_percentile"
    return out


def _counts(stat: Any) -> tuple[int | None, int | None]:
    if isinstance(stat, RatioStat):
        x, n = float(stat.num.sum()), float(stat.den.sum())
        if x.is_integer() and n.is_integer():
            return int(x), int(n)
    return None, None


def _same(a: float | None, b: float | None) -> bool:
    return (a is None and b is None) or (a is not None and b is not None and abs(a - b) <= TOL)


def metric_rows(manifest: dict[str, Any], results: dict[str, Any], rows: list[dict[str, Any]],
                cmp_rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """One row per (metric, arm), recomputed with the runner's own adapters and checked against results.json."""
    b = manifest["bootstrap"]
    bkw = dict(n_boot=b["n_boot"], seed=b["seed"], ci_level=b["ci_level"], method=b["method"])
    out = []
    for spec, res in zip(manifest["metrics"], results["rows"], strict=True):
        if spec["id"] != res["metric_id"]:
            raise AssertionError("results rows are not in manifest order")
        trs = sorted((r for r in rows if r["task"] == spec["task"]), key=_key)
        prep = prepare(spec["name"], trs, spec["params"])
        x, n = _counts(prep.stat)
        prop = _is_proportion(spec)
        if res["point"] is not None and x is not None and n and abs(x / n - res["point"]) > TOL and spec[
                "params"].get("component") != "f1":
            raise AssertionError(f"{spec['id']}: x/n != point")
        common = {"metric_id": spec["id"], "item": spec["item"], "task": spec["task"], "metric": spec["name"],
                  "params": spec["params"], "primary": spec["primary"]}
        sys_row = {**common, "arm": "system", "point": res["point"], "reason": res["reason"],
                   "bootstrap": {"ci_low": res["ci_low"], "ci_high": res["ci_high"], "unstable": res["unstable"],
                                 "n_degenerate": res["n_degenerate"]},
                   "n_patients": res["n_patients"], "n_decision_points": res["n_decision_points"],
                   "thresholds": [{**t, "verdict": {"met": "PASS", "not met": "FAIL"}.get(t["status"], "UNDEFINED")}
                                  for t in res["thresholds"]],
                   **interval_fields(res["point"], x, n, res["ci_low"], res["ci_high"], res["unstable"], prop)}
        out.append(sys_row)
        for comp in res["comparisons"]:
            name = comp["comparator"]
            crs = sorted((r for r in cmp_rows if r["task"] == spec["task"] and r["comparator"] == name), key=_key)
            cprep = prepare(spec["name"], crs, spec["params"])
            boot = cluster_bootstrap([r["patient_id"] for r in crs], cprep.stat, **bkw)
            if not (_same(boot.point, comp["comparator_point"]) and _same(boot.ci_low, comp["comparator_ci_low"])
                    and _same(boot.ci_high, comp["comparator_ci_high"])):
                raise AssertionError(f"{spec['id']} {name}: recomputed comparator differs from results.json")
            cx, cn = _counts(cprep.stat)
            out.append({**common, "arm": f"comparator:{name}", "point": boot.point, "reason": boot.reason,
                        "bootstrap": {"ci_low": boot.ci_low, "ci_high": boot.ci_high, "unstable": boot.unstable,
                                      "n_degenerate": boot.n_degenerate},
                        "n_patients": boot.n_patients, "n_decision_points": boot.n_decision_points,
                        "paired_difference_system_minus_comparator": comp["diff"],
                        **interval_fields(boot.point, cx, cn, boot.ci_low, boot.ci_high, boot.unstable, prop)})
    return out


# ---------------------------------------------------------------- safety lists and tables


def safety_lists(rows: list[dict[str, Any]]) -> dict[str, Any]:
    case_misses = [{"case_id": r["case_id"], "dp": r["dp"], "T": r["T"], "rule": rule}
                   for r in rows if r["task"] == "rf_case_recall" and not r["y_pred"] for rule in r["gold_rules"]]
    rule_misses = [{"case_id": r["case_id"], "dp": r["dp"], "T": r["T"], "rule": rule,
                    "reason": "UNMAPPABLE (no S4 counterpart)" if not mapping.s1r_rule_targets()[rule]
                    else ("no alert at this DP" if not r["fired_s4"] else "other alert(s) only: "
                          + ", ".join(r["fired_s4"]))}
                   for r in rows if r["task"] == "rf_rule_recall" for rule in r["ordered"]
                   if rule not in r["suggested"]]
    fp: dict[str, list[str]] = {}
    for r in rows:
        if r["task"] == "rf_fpr":
            for a in r["fired_s4"]:
                fp.setdefault(a, []).append(r["decision_point_id"])
    outside = mapping.outside_registry_s4_rules()
    out_reg: dict[str, list[str]] = {k: [] for k in outside}
    for r in rows:
        if r["task"] == "expected_action":
            for a in r["fired_s4"]:
                if a in out_reg:
                    out_reg[a].append(r["decision_point_id"])
    key = lambda d: (d["case_id"], d["dp"], d["rule"])  # noqa: E731
    return {
        "missed_gold_red_flag_dps": sorted(case_misses, key=key),
        "missed_gold_red_flag_pairs": sorted(rule_misses, key=key),
        "false_positive_dps_by_s4_rule": {k: sorted(v) for k, v in sorted(fp.items())},
        "alerts_outside_s1r_registry": {k: {"n_alerts": len(v), "dps": sorted(v)} for k, v in out_reg.items()},
    }


def confusion(rows: list[dict[str, Any]]) -> dict[str, dict[str, int]]:
    acts = ("suggest", "abstain", "escalate")
    c = Counter((r["y_true"], r["y_pred"]) for r in rows if r["task"] == "expected_action")
    return {g: {p: c[(g, p)] for p in acts} for g in acts}


def voice_states(rows: list[dict[str, Any]]) -> dict[str, dict[str, int]]:
    out: dict[str, Counter[str]] = {}
    for r in rows:
        if r["task"] == "voice_intake":
            for f, s in r["s3_states"].items():
                out.setdefault(f, Counter())[s] += 1
    return {f: dict(sorted(c.items())) for f, c in sorted(out.items())}


def null_rows(split_info: dict[str, Any], manifests: dict[str, dict[str, Any]]) -> list[dict[str, Any]]:
    """Scope-4 metrics with no runner row in this split: null with a reason and n."""
    ids = {m["id"] for man in manifests.values() for m in man["metrics"]}
    out = []
    targets = mapping.s1r_rule_targets()
    pops = {p["population"]: p for p in split_info["populations"]}
    for rule in sorted(targets):
        p = pops[f"rf_rule:{rule}"]
        if not targets[rule]:
            out.append({"metric_id": f"rf_rule_{rule}", "point": None, "n_decision_points": p["n_total"],
                        "reason": "UNMAPPABLE: S4 has no counterpart rule; its gold pairs count as missed in "
                                  "rf_rule_recall"})
        elif f"rf_rule_{rule}" not in ids:
            out.append({"metric_id": f"rf_rule_{rule}", "point": None, "n_decision_points": 0,
                        "reason": "no gold DPs with this rule in this split"})
    for mid, pop in (("abst_rate_not_evaluable", "abst_on_not_evaluable"), ("rf_text_t1_recall", "rf_text_t1_recall"),
                     ("rf_text_t1_fpr", "rf_text_t1_fpr"), ("rf_fpr", "rf_fpr"), ("rf_case_recall", "rf_case_recall")):
        if mid not in ids:
            out.append({"metric_id": mid, "point": None, "n_decision_points": pops[pop]["n_scored"],
                        "reason": "empty population in this split"})
    return out


def split_summary(split: str, manifests: dict[str, dict[str, Any]], results: dict[str, dict[str, Any]],
                  rows: dict[str, list[dict[str, Any]]], cmp_rows: dict[str, list[dict[str, Any]]],
                  split_info: dict[str, Any]) -> dict[str, Any]:
    mrows = []
    for kind in ("voice", "triage"):
        mrows += metric_rows(manifests[kind], results[kind], rows[kind], cmp_rows[kind])
    verdicts = [{"metric_id": r["metric_id"], "rule": f"{t['op']} {t['value']} on {t['rule']}",
                 "compared_value": t["compared_value"], "verdict": t["verdict"]}
                for r in mrows if r["arm"] == "system" for t in r["thresholds"]]
    return {
        "split": split,
        "status": "run",
        "frozen": all(results[k]["frozen"] for k in results),
        "stamp": results["triage"]["stamp"],
        "evaluation_ids": {k: results[k]["evaluation_id"] for k in results},
        "manifest_sha256": {k: results[k]["manifest_sha256"] for k in results},
        "frozen_entry_hash": {k: results[k]["frozen_entry_hash"] for k in results},
        "n_patients_in_split": results["triage"]["n_patients_in_split_list"],
        "metric_rows": mrows,
        "null_rows": null_rows(split_info, manifests),
        "threshold_verdicts": verdicts,
        "populations": split_info["populations"],
        "unmapped_counts": split_info["unmapped_counts"],
        "comparators": split_info["comparators"],
        "safety": safety_lists(rows["triage"]),
        "expected_action_confusion": {"rows": "gold", "columns": "system", "matrix": confusion(rows["triage"])},
        "voice_s3_states": voice_states(rows["voice"]),
    }


# ---------------------------------------------------------------- overall summary + markdown


def build(splits: dict[str, dict[str, Any] | None], not_run_reason: str) -> dict[str, Any]:
    body = {s: (v if v is not None else {"split": s, "status": "not_run", "reason": not_run_reason})
            for s, v in splits.items()}
    headline = []
    for s, v in body.items():
        for mid in ("rf_case_recall", "rf_rule_recall"):
            if v["status"] != "run":
                headline.append({"split": s, "metric_id": mid, "verdict": "NOT RUN", "point": None})
                continue
            r = next(x for x in v["metric_rows"] if x["metric_id"] == mid and x["arm"] == "system")
            headline.append({"split": s, "metric_id": mid, "point": r["point"], "x": r["x"], "n": r["n"],
                             "interval": r["interval"], "interval_method": r["interval_method"],
                             "verdict": r["thresholds"][0]["verdict"] if r["thresholds"] else "UNDEFINED"})
    return {
        "banner": BANNER,
        "research_prototype": RESEARCH,
        "slice": "e1",
        "claim_boundary": "System Evaluation of the as-built S3 and S4 on synthetic S1r data; not clinical "
                          "performance; not expert-reviewed. Outcome thresholds are reported as PASS/FAIL and do "
                          "not gate the slice.",
        "red_flag_recall_verdicts": headline,
        "exact_interval_note": EXACT_NOTE,
        "degenerate_rule": DEGENERATE_RULE,
        "not_evaluated": NOT_EVALUATED,
        "splits": body,
    }


def _f(v: Any) -> str:
    if v is None:
        return "null"
    if isinstance(v, float):
        return f"{v:.4f}"
    return str(v)


def _iv(v: list[float] | None) -> str:
    return "null" if v is None else f"[{v[0]:.4f}, {v[1]:.4f}]"


def _table(cols: list[str], body: list[list[Any]]) -> list[str]:
    out = [f"> **{BANNER}**", "", "| " + " | ".join(cols) + " |", "|" + "---|" * len(cols)]
    body = body or [["(none)"] + [""] * (len(cols) - 1)]
    out += ["| " + " | ".join(str(c).replace("|", "\\|") for c in row) + " |" for row in body]
    return out + [""]


def render_md(s: dict[str, Any]) -> str:
    L = ["# e1 System Evaluation: Voice (S3) and Triage (S4) on S1r", "", f"> **{BANNER}**", f"> **{RESEARCH}**",
         "", s["claim_boundary"], "", "## Red-flag recall verdicts (predeclared: point >= 1.00)", ""]
    L += _table(["Split", "Metric", "x / n", "Point", "Interval (method)", "Verdict"],
                [[h["split"], h["metric_id"], f"{_f(h.get('x'))} / {_f(h.get('n'))}", _f(h["point"]),
                  f"{_iv(h.get('interval'))} ({h.get('interval_method')})", h["verdict"]]
                 for h in s["red_flag_recall_verdicts"]])
    L += [s["exact_interval_note"], "", s["degenerate_rule"], ""]
    for split, v in s["splits"].items():
        L += [f"## Split: {split}", ""]
        if v["status"] != "run":
            L += [f"Not run: {v['reason']}", ""]
            continue
        L += [f"- Evaluation IDs: {', '.join(sorted(v['evaluation_ids'].values()))}; frozen: "
              f"{'yes' if v['frozen'] else 'no'}{'; ' + v['stamp'] if v['stamp'] else ''}",
              f"- Patients in split: {v['n_patients_in_split']}", ""]
        L += ["### Threshold verdicts (predeclared rule only)", ""]
        L += _table(["Metric", "Rule", "Compared value", "Verdict"],
                    [[t["metric_id"], t["rule"], _f(t["compared_value"]), t["verdict"]]
                     for t in v["threshold_verdicts"]])
        L += ["### Metric rows", ""]
        body = []
        for r in v["metric_rows"]:
            est = r["params"].get("estimand") or ", ".join(f"{k}={x}" for k, x in sorted(r["params"].items())
                                                           if k not in ("fields",))
            d = r.get("paired_difference_system_minus_comparator")
            body.append([r["metric_id"], r["arm"], est, f"{_f(r['x'])} / {_f(r['n'])}",
                         _f(r["point"]) if r["point"] is not None else f"null ({r['reason']})",
                         _iv(None if r["bootstrap"]["ci_low"] is None else
                             [r["bootstrap"]["ci_low"], r["bootstrap"]["ci_high"]]),
                         _iv(r["wilson"]), _iv(r["clopper_pearson"]), f"{_iv(r['interval'])} ({r['interval_method']})",
                         f"{r['n_patients']} / {r['n_decision_points']}",
                         "-" if d is None else (f"{_f(d['point'])} {_iv(None if d['ci_low'] is None else [d['ci_low'], d['ci_high']])}"
                                                if d["point"] is not None else f"null ({d['reason']})")])
        L += _table(["Metric", "Arm", "Estimand", "x / n", "Point", "Bootstrap 95% CI", "Wilson", "Clopper-Pearson",
                     "Reported interval (method)", "n patients / n units", "Paired diff (sys - comp)"], body)
        L += ["### Null rows", ""]
        L += _table(["Metric", "Point", "n", "Reason"],
                    [[x["metric_id"], "null", x["n_decision_points"], x["reason"]] for x in v["null_rows"]])
        L += ["### Populations (n_total = n_scored + excluded)", ""]
        L += _table(["Population", "Definition", "Unit", "n_total", "n_scored", "Excluded by reason", "n patients"],
                    [[p["population"], p["definition"], p["unit"], p["n_total"], p["n_scored"],
                      "; ".join(f"{k}: {x}" for k, x in p["n_excluded"].items()) or "none", p["n_patients_scored"]]
                     for p in v["populations"]])
        saf = v["safety"]
        L += ["### Missed gold red flags: DPs with no alert at all", ""]
        L += _table(["Case", "DP", "T", "Gold rule"],
                    [[m["case_id"], m["dp"], m["T"], m["rule"]] for m in saf["missed_gold_red_flag_dps"]])
        L += ["### Missed gold (DP, rule) pairs", ""]
        L += _table(["Case", "DP", "T", "Gold rule", "Reason"],
                    [[m["case_id"], m["dp"], m["T"], m["rule"], m["reason"]] for m in saf["missed_gold_red_flag_pairs"]])
        L += ["### Alerts on gold-negative DPs, by S4 rule", ""]
        L += _table(["S4 rule", "n", "DPs"], [[k, len(x), ", ".join(x)]
                                             for k, x in saf["false_positive_dps_by_s4_rule"].items()])
        L += ["### Alerts from S4 rules outside the S1r registry (all DPs)", ""]
        L += _table(["S4 rule", "n alerts", "DPs"], [[k, x["n_alerts"], ", ".join(x["dps"]) or "-"]
                                                    for k, x in saf["alerts_outside_s1r_registry"].items()])
        L += ["### expected_action confusion (rows gold, columns system)", ""]
        mat = v["expected_action_confusion"]["matrix"]
        L += _table(["gold \\ system", *mat], [[g, *row.values()] for g, row in mat.items()])
        L += ["### Unmapped items per mapping section", ""]
        L += _table(["Section", "Item", "Count"],
                    [[sec, k, json.dumps(x, ensure_ascii=False) if isinstance(x, dict) else x]
                     for sec, d in v["unmapped_counts"].items() for k, x in d.items()])
        L += ["### Comparators", ""]
        c = v["comparators"]
        L += _table(["Comparator", "Definition", "Train-split selection evidence"],
                    [["shortcut_s_star", f"contains({c['s_star']['s_star']!r})", json.dumps(c["s_star"]["train"])],
                     ["shortcut_tamtee", "contains('ทันที')", json.dumps(c["s_star"]["tamtee_train"])],
                     ["always_answer", f"S4 baseline.rank, fallback {c['always_answer_fallback']['code']}",
                      json.dumps(c["always_answer_fallback"]["counts"])]])
        L += ["### S3 final field states (per case)", ""]
        L += _table(["Field", "States"], [[f, json.dumps(x)] for f, x in v["voice_s3_states"].items()])
    L += ["## Not evaluated", ""]
    L += _table(["Row", "Reason"], [[x["row"], x["reason"]] for x in s["not_evaluated"]])
    return "\n".join(L)


def write(out_root: Path, s: dict[str, Any]) -> None:
    (out_root / "e1_summary.json").write_text(
        json.dumps(s, sort_keys=True, indent=1, ensure_ascii=False, allow_nan=False) + "\n", encoding="utf-8")
    (out_root / "e1_summary.md").write_text(render_md(s), encoding="utf-8")
