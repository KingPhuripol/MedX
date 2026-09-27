"""i2 split summary and ``i2_summary.{json,md}`` (deterministic; wall time lives only in ``timing.json``).

Research prototype - not for clinical use.
"""

from __future__ import annotations

import json
import statistics
from collections import Counter
from pathlib import Path
from typing import Any

from eval.exact import clopper_pearson, wilson

from eval.adapters import mapping
from .arms import ARM_A, ARM_B
from .score import TEXT_S1R, TEXT_S4, gold_dp, is_text_near_miss, miss_reason

BANNER = "System Evaluation on synthetic data — not clinical performance"
CIRCULARITY = ("Circularity note: rules, fixtures, extractor lexicon and gold share authors, so these results are "
               "circular. One deterministic mock model is used in both arms: the comparison measures graph "
               "structure (typed extraction, mandatory red-flag screening, abstention, call count, time), not model "
               "reasoning.")
ARM_B_RED_FLAG = ("null: Arm B runs without a Red-flag node by design, so it emits no screening output; the "
                  "screening is not compared between arms and its absence in Arm B is not a safety result")
NOT_EVALUATED = {"CareSuggestion": "not evaluated: the mock proposes no care items and S1r has no care gold"}
COMPARED = ("dept_top1", "dept_top3", "coverage", "selective_top1", "calls_per_dp")


def _interval(x: int, n: int) -> dict[str, Any]:
    w, cp = wilson(x, n), clopper_pearson(x, n)
    return {"wilson": [round(w[0], 6), round(w[1], 6)], "clopper_pearson": [round(cp[0], 6), round(cp[1], 6)]}


def _row(results: dict[str, Any], mid: str) -> dict[str, Any] | None:
    return next((r for r in results["rows"] if r["metric_id"] == mid), None)


def _boot(r: dict[str, Any]) -> dict[str, Any]:
    return {"point": r["point"], "ci": [r["ci_low"], r["ci_high"]], "n_patients": r["n_patients"],
            "n_decision_points": r["n_decision_points"], "n_degenerate": r["n_degenerate"], "reason": r["reason"]}


def comparison(results: dict[str, Any], rows: list[dict[str, Any]], cmp_rows: list[dict[str, Any]]
               ) -> dict[str, Any]:
    out = {}
    for mid in COMPARED:
        r = _row(results, mid)
        c = r["comparisons"][0]
        entry = {"case_graph": _boot(r),
                 "single_prompt": {"point": c["comparator_point"], "ci": [c["comparator_ci_low"],
                                                                          c["comparator_ci_high"]]},
                 "paired_difference_A_minus_B": c["diff"]}
        task = r["task"]
        if r["metric"] in ("topk_accuracy", "coverage", "selective_accuracy"):
            for arm, rs in (("case_graph", rows), ("single_prompt", cmp_rows)):
                x, n = _counts(r, [q for q in rs if q["task"] == task])
                entry[arm].update({"x": x, "n": n, **(_interval(x, n) if n else {})})
                degenerate = n and (x in (0, n))
                entry[arm]["reported_interval"] = ("clopper_pearson" if degenerate else "bootstrap") if n else None
        out[mid] = entry
    return out


def _counts(r: dict[str, Any], rs: list[dict[str, Any]]) -> tuple[int, int]:
    m = r["metric"]
    if m == "topk_accuracy":
        k = r["params"]["k"]
        return sum(q["y_true"] in q["ranked"][:k] for q in rs), len(rs)
    if m == "coverage":
        return sum(q["y_pred"] is not None for q in rs), len(rs)
    ans = [q for q in rs if q["y_pred"] is not None]
    return sum(q["y_pred"] == q["y_true"] for q in ans), len(ans)


def red_flags(records: list[dict[str, Any]], gold: dict[str, dict[str, Any]], results: dict[str, Any]
              ) -> dict[str, Any]:
    pairs: dict[str, list[tuple[str, str, bool]]] = {r: [] for r in mapping.s1r_rule_targets()}
    missed, fp_neg, fp_nm = [], Counter(), Counter()
    n_neg = n_nm = 0
    text_fired_on_positive: Counter[str] = Counter()
    targets = mapping.s1r_rule_targets()
    for rec in records:
        g = gold[rec["case_id"]]
        d = gold_dp(g, rec["decision_point"])
        fired = set(rec[ARM_A]["red_flag"]["fired"])
        for rf in d["red_flags"]:
            rule = rf["rule_id"]
            tg = targets[rule]
            hit = bool(tg and fired & set(tg))
            pairs[rule].append((rec["patient_ref"], rec["dp_id"], hit))
            if hit and rule in TEXT_S1R:
                text_fired_on_positive[rule] += 1
            if not hit:
                missed.append({"dp_id": rec["dp_id"], "rule": rule, "reason": miss_reason(rule, rec, d)})
        if not d["red_flags"]:
            n_neg += 1
            fp_neg.update(fired)
        if is_text_near_miss(g, d):
            n_nm += 1
            fp_nm.update(fired)
    per_rule = {}
    for rule, ps in sorted(pairs.items()):
        if targets[rule] is None:
            per_rule[rule] = {"point": None, "reason": "unmappable (e1 mapping v1: S4 has no aggregate-NEWS rule)",
                              "n_gold_pairs": len(ps), "n_patients": len({p for p, _, _ in ps})}
            continue
        if not ps:
            per_rule[rule] = {"point": None, "reason": "no gold pairs on this split", "n_gold_pairs": 0}
            continue
        x, n = sum(h for _, _, h in ps), len(ps)
        r = _row(results, f"rf_rule_{rule}")
        degenerate = x in (0, n)
        per_rule[rule] = {"x": x, "n": n, "point": round(x / n, 6), "n_patients": len({p for p, _, _ in ps}),
                          **_interval(x, n), "bootstrap": _boot(r) if r else None,
                          "reported_interval": "clopper_pearson" if degenerate else "bootstrap"}
    text_nm_alerts = sum(v for k, v in fp_nm.items() if k in TEXT_S4)
    text_recall = {r: per_rule[r].get("point") for r in mapping.TEXT_RULES_S1R}
    return {
        "arm": ARM_A,
        "single_prompt": ARM_B_RED_FLAG,
        "per_s1r_rule_recall": per_rule,
        "false_alerts_per_s4_rule": {
            "gold_negative_dps": {"n_dps": n_neg, "alerts": dict(sorted(fp_neg.items()))},
            "text_near_miss_dps": {"n_dps": n_nm, "alerts": dict(sorted(fp_nm.items()))},
        },
        "missed_gold_red_flags": sorted(missed, key=lambda m: (m["dp_id"], m["rule"])),
        "missed_reason_counts": dict(sorted(Counter(m["reason"] for m in missed).items())),
        "text_rule_fired_on_gold_positive_dps": {r: text_fired_on_positive.get(r, 0) for r in mapping.TEXT_RULES_S1R},
        "predeclared_targets_not_gating": {
            "text_rule_recall_equals_1": {r: ("PASS" if v == 1.0 else "FAIL" if v is not None else "NO_DATA")
                                          for r, v in text_recall.items()},
            "zero_text_rule_alerts_on_text_near_miss_dps": "PASS" if text_nm_alerts == 0 else "FAIL",
            "text_rule_alerts_on_text_near_miss_dps": text_nm_alerts,
        },
    }


def arms_matched(records: list[dict[str, Any]], handler_versions: dict[str, str]) -> dict[str, Any]:
    both = [r for r in records if r[ARM_A]["department"]["status"] == "suggested"
            and r[ARM_B]["department"]["status"] == "suggested"]
    same = sum(r[ARM_A]["department"]["top3"] == r[ARM_B]["department"]["top3"] for r in both)
    a_versions = sorted({json.dumps(r[ARM_A]["handler_versions"], sort_keys=True) for r in records
                         if r[ARM_A]["handler_versions"]})
    b_versions = sorted({json.dumps(r[ARM_B]["handler_versions"], sort_keys=True) for r in records})
    a_union: dict[str, str] = {}
    for v in a_versions:
        a_union.update(json.loads(v))
    return {
        "handler_versions_manifest": handler_versions,
        "handler_versions_arm_a": a_union,
        "handler_versions_arm_b": [json.loads(v) for v in b_versions],
        "identical_handler_versions": [a_union] == [json.loads(v) for v in b_versions] == [handler_versions],
        "n_both_answer": len(both),
        "n_identical_top3_where_both_answer": same,
        "only_case_graph_answers": sum(r[ARM_A]["department"]["status"] == "suggested"
                                       and r[ARM_B]["department"]["status"] != "suggested" for r in records),
        "only_single_prompt_answers": sum(r[ARM_B]["department"]["status"] == "suggested"
                                          and r[ARM_A]["department"]["status"] != "suggested" for r in records),
    }


def calls(records: list[dict[str, Any]]) -> dict[str, Any]:
    per_node: Counter[str] = Counter()
    for r in records:
        per_node.update(r[ARM_A]["calls_per_node"])
    n = len(records)
    ta, tb = sum(r[ARM_A]["calls"] for r in records), sum(r[ARM_B]["calls"] for r in records)
    return {"case_graph": {"total": ta, "mean_per_dp": round(ta / n, 6) if n else None,
                           "per_node": dict(sorted(per_node.items()))},
            "single_prompt": {"total": tb, "mean_per_dp": round(tb / n, 6) if n else None,
                              "per_node": {"single_prompt": tb}}}


def split_summary(split: str, manifest: dict[str, Any], results: dict[str, Any], records: list[dict[str, Any]],
                  rows: list[dict[str, Any]], cmp_rows: list[dict[str, Any]], gold: dict[str, dict[str, Any]],
                  handler_versions: dict[str, str]) -> dict[str, Any]:
    routes: Counter[str] = Counter()
    for rec in records:
        d = gold_dp(gold[rec["case_id"]], rec["decision_point"])
        routes[mapping.gold_department(d["target_department"], d["department_evaluable"])[1]] += 1
    return {
        "label": BANNER,
        "circularity_note": CIRCULARITY,
        "split": split,
        "evaluation_id": manifest["evaluation_id"],
        "frozen": results["frozen"],
        "stamp": results["stamp"],
        "manifest_sha256": results["manifest_sha256"],
        "n_dp": len(records),
        "n_patients": len({r["patient_ref"] for r in records}),
        "department_routes": dict(sorted(routes.items())),
        "comparison": comparison(results, rows, cmp_rows),
        "calls": calls(records),
        "time": "see timing.json (median and p95 wall time per DP; not byte-reproducible by nature)",
        "arms_matched": arms_matched(records, handler_versions),
        "red_flags": red_flags(records, gold, results),
        "red_flag_screening_status": dict(sorted(Counter(r[ARM_A]["red_flag"]["status"] for r in records).items())),
        "case_graph_department_status": dict(sorted(Counter(
            f"{r[ARM_A]['department']['status']}:{r[ARM_A]['department']['reason']}" for r in records).items())),
        "graph_shape_histogram": dict(sorted(Counter("+".join(r[ARM_A]["shape"]) for r in records).items())),
        "replay": {"checked": len(records), "identical": sum(r[ARM_A]["replay_ok"] for r in records)},
        "not_evaluated": NOT_EVALUATED,
    }


def timing(split: str, t: dict[str, dict[str, float]]) -> dict[str, Any]:
    out: dict[str, Any] = {"label": BANNER, "split": split,
                           "note": "in-process wall time per DP, arms alternated per DP; orchestration overhead "
                                   "with a mock provider, not model latency"}
    for arm in (ARM_A, ARM_B):
        v = sorted(x[arm] for x in t.values())
        out[arm] = {"median_ms": round(statistics.median(v), 3) if v else None,
                    "p95_ms": round(statistics.quantiles(v, n=20, method="inclusive")[18], 3) if len(v) > 1 else None,
                    "n": len(v)}
    out["per_dp_ms"] = t
    return out


# ---------------------------------------------------------------- i2_summary.{json,md}


def build(splits: dict[str, dict[str, Any] | None], not_run: str) -> dict[str, Any]:
    return {"label": BANNER, "circularity_note": CIRCULARITY,
            "research_question": "With the same mock model, how does the Case Graph compare with one prompt over "
                                 "the whole snapshot? (PROPOSAL Table 3.2, row Case Graph)",
            "predeclared_expectation": "Equal accuracy on DPs where both arms answer; the Case Graph abstains on "
                                       "NOT_EVALUABLE DPs where the single prompt answers; the Case Graph makes more "
                                       "model calls.",
            "splits": {s: (v if v is not None else {"status": "not run", "reason": not_run}) for s, v in splits.items()}}


def _fmt(v: Any) -> str:
    if v is None:
        return "null"
    if isinstance(v, float):
        return f"{v:.4f}"
    if isinstance(v, list):
        return "[" + ", ".join(_fmt(x) for x in v) + "]"
    return str(v)


def _table(header: list[str], rows: list[list[Any]]) -> list[str]:
    return [f"> **{BANNER}**", ">", f"> {CIRCULARITY}", "", "| " + " | ".join(header) + " |",
            "|" + "---|" * len(header)] + ["| " + " | ".join(_fmt(c) for c in r) + " |" for r in rows] + [""]


def render_md(s: dict[str, Any]) -> str:
    out = [f"# i2: Case Graph vs single prompt", "", f"> **{BANNER}**", "", s["circularity_note"], "",
           f"Research question: {s['research_question']}", "", f"Predeclared expectation: {s['predeclared_expectation']}",
           ""]
    for split, v in s["splits"].items():
        out += [f"## {split}", ""]
        if "comparison" not in v:
            out += [f"Not run: {v['reason']}", ""]
            continue
        out += [f"{v['stamp'] or 'FROZEN'}; n_dp={v['n_dp']}, n_patients={v['n_patients']}; manifest "
                f"`{v['manifest_sha256'][:12]}`", ""]
        rows = []
        for mid, e in v["comparison"].items():
            a, b, d = e["case_graph"], e["single_prompt"], e["paired_difference_A_minus_B"] or {}
            rows.append([mid, a["point"], a["ci"], b["point"], b["ci"], d.get("point"), [d.get("ci_low"),
                                                                                          d.get("ci_high")]])
        out += _table(["metric", "Case Graph", "CI", "single prompt", "CI", "A - B", "paired CI (patient bootstrap)"],
                      rows)
        c = v["calls"]
        out += _table(["arm", "calls total", "calls per DP", "per node"],
                      [["Case Graph", c["case_graph"]["total"], c["case_graph"]["mean_per_dp"],
                        ", ".join(f"{k}={n}" for k, n in c["case_graph"]["per_node"].items())],
                       ["single prompt", c["single_prompt"]["total"], c["single_prompt"]["mean_per_dp"],
                        "single_prompt"]])
        m = v["arms_matched"]
        out += [f"Arms matched: identical handler versions = {m['identical_handler_versions']}; identical top-3 on "
                f"{m['n_identical_top3_where_both_answer']} of {m['n_both_answer']} DPs where both answer. "
                f"Wall time: see `timing.json`.", ""]
        rf = v["red_flags"]
        rows = [[r, e.get("x"), e.get("n"), e.get("n_patients"), e.get("point"), e.get("wilson"),
                 e.get("clopper_pearson"), (e.get("bootstrap") or {}).get("ci"), e.get("reported_interval") or
                 e.get("reason")] for r, e in rf["per_s1r_rule_recall"].items()]
        out += [f"Red-flag recall per S1r rule (Case Graph). Single prompt: {rf['single_prompt']}.", ""]
        out += _table(["S1r rule", "x", "n", "n_patients", "recall", "Wilson", "Clopper-Pearson", "bootstrap",
                       "reported"], rows)
        fa = rf["false_alerts_per_s4_rule"]
        out += _table(["population", "n_dps", "alerts per S4 rule"],
                      [[k, x["n_dps"], ", ".join(f"{r}={n}" for r, n in x["alerts"].items()) or "none"]
                       for k, x in fa.items()])
        out += _table(["missed DP", "S1r rule", "reason"],
                      [[x["dp_id"], x["rule"], x["reason"]] for x in rf["missed_gold_red_flags"]] or
                      [["none", "", ""]])
        out += [f"Predeclared targets (reported, not gating): {json.dumps(rf['predeclared_targets_not_gating'])}",
                "", f"Not evaluated: {json.dumps(v['not_evaluated'])}", ""]
    return "\n".join(out) + "\n"


def write(root: Path, s: dict[str, Any]) -> None:
    root.mkdir(parents=True, exist_ok=True)
    (root / "i2_summary.json").write_text(json.dumps(s, sort_keys=True, indent=1, ensure_ascii=False,
                                                     allow_nan=False) + "\n", encoding="utf-8")
    (root / "i2_summary.md").write_text(render_md(s), encoding="utf-8")
