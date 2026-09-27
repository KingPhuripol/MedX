"""Table 3.2-style report rendering (slice s8). Research prototype - not for clinical use.

Output is a pure function of results.json: no wall-clock time, no absolute paths.
"""

from __future__ import annotations

import html
from typing import Any

BANNER_NO_REVIEW = "System Evaluation, not clinical efficacy"
BANNER_REVIEW = "System Evaluation with expert review - not a clinical efficacy study"
RESEARCH_PROTOTYPE = "Research prototype - not for clinical use"
SYNTHETIC = "Synthetic data"
TITLE = "Table 3.2 evaluation results"
COLUMNS = ("Evaluated item", "Metric", "Point estimate", "CI", "Comparator", "Difference (CI)",
           "n patients / decision points", "Threshold (predeclared rule)")


def labels_for(m: dict[str, Any]) -> dict[str, Any]:
    return {
        "banner": BANNER_REVIEW if m["expert_review"]["done"] else BANNER_NO_REVIEW,
        "research_prototype": RESEARCH_PROTOTYPE,
        "synthetic_data": m["dataset"]["data_class"] == "synthetic",
    }


def _num(v: Any) -> str:
    return "null" if v is None else f"{v:.4f}"


def _ci(lo: Any, hi: Any, unstable: bool) -> str:
    if lo is None or hi is None:
        return "null"
    return f"[{lo:.4f}, {hi:.4f}]" + (" (unstable)" if unstable else "")


def _metric_label(r: dict[str, Any]) -> str:
    extra = {k: v for k, v in r["params"].items() if k not in ("labels", "fields")}
    ps = ", ".join(f"{k}={v}" for k, v in sorted(extra.items()))
    lab = f"{r['metric']}({ps})" if ps else r["metric"]
    src = r["details"].get("source")
    lab += f" [source: {src}]" if src else ""
    return lab + (" *primary*" if r["primary"] else "")


def _point(r: dict[str, Any]) -> str:
    return _num(r["point"]) if r["point"] is not None else f"null ({r['reason']})"


def _thresholds(r: dict[str, Any]) -> str:
    if not r["thresholds"]:
        return "not declared"
    return "; ".join(f"{t['op']} {t['value']} on {t['rule']}: {t['status']}" for t in r["thresholds"])


def table_rows(results: dict[str, Any]) -> list[list[str]]:
    out = []
    for r in results["rows"]:
        base = [r["item"], _metric_label(r), _point(r), _ci(r["ci_low"], r["ci_high"], r["unstable"])]
        n = f"{r['n_patients']} / {r['n_decision_points']}"
        th = _thresholds(r)
        comps = r["comparisons"] or [None]
        for i, c in enumerate(comps):
            if c is None:
                cmp_cell, diff_cell = "none declared", "-"
            elif c["status"] != "computed":
                cmp_cell, diff_cell = f"{c['comparator']}: {c['status']}", "-"
            else:
                cp = _num(c["comparator_point"]) if c["comparator_point"] is not None else f"null ({c['comparator_reason']})"
                d = c["diff"]
                cmp_cell = f"{c['comparator']}: {cp}"
                diff_cell = (f"{_num(d['point'])} {_ci(d['ci_low'], d['ci_high'], d['unstable'])}"
                             if d["point"] is not None else f"null ({d['reason']})")
            first = base if i == 0 else ["", "", "", ""]
            out.append(first + [cmp_cell, diff_cell, n if i == 0 else "", th if i == 0 else ""])
    return out


COVERAGE_TITLE = "Split coverage"
COVERAGE_COLUMNS = ("Task", "Population", "Arm", "n_listed", "n_predicted", "n_missing", "missing_policy",
                    "n_imputed_abstain_decision_points")
COVERAGE_NOTE = ("Every listed patient must have predictions. A missing patient refuses the run unless all metrics "
                 "of the task are abstention-aware, where it is counted as abstain "
                 "(imputation unit: 1 decision point per missing patient).")


def _n(v: Any) -> str:
    return "null" if v is None else str(v)


def coverage_rows(results: dict[str, Any]) -> list[list[str]]:
    out = []
    for c in results["split_coverage"]:
        for i, a in enumerate(c["arms"]):
            policy = c["missing_policy"] if i == 0 else ""
            if a["status"] != "provided":
                policy = "not provided"
            out.append([c["task"] if i == 0 else "", _n(c["population"]) if i == 0 else "",
                        a["arm"], _n(c["n_listed"]), _n(a["n_predicted"]), _n(a["n_missing"]), policy,
                        _n(a["n_imputed_abstain_decision_points"])])
    return out


def header_lines(results: dict[str, Any]) -> list[str]:
    lab = results["labels"]
    lines = [lab["banner"], lab["research_prototype"]]
    if lab["synthetic_data"]:
        lines.append(SYNTHETIC)
    if results["stamp"]:
        lines.append(results["stamp"])
    return lines


def meta_lines(results: dict[str, Any]) -> list[str]:
    b = results["bootstrap"]
    ds = results["dataset"]
    return [
        f"Evaluation ID: {results['evaluation_id']} (slice {results['slice']})",
        f"Dataset: {ds['name']} v{ds['version']} ({ds['data_class']}); split: {results['split']} "
        f"({results['split_version']}); frozen: {'yes' if results['frozen'] else 'no'}",
        f"Patients: {results['n_patients']}; decision points: {results['n_decision_points']}",
        f"CI: {b['ci_level'] * 100:g}% {b['method']} patient-level cluster bootstrap, n_boot={b['n_boot']}, "
        f"seed={b['seed']}",
        f"Manifest sha256: {results['manifest_sha256']}",
        f"Frozen ledger entry hash: {results['frozen_entry_hash'] or 'none (not frozen)'}",
        f"Predictions sha256: {results['predictions_sha256']}",
        f"Comparator sha256: {results['comparator_sha256'] or 'none'}",
        f"numpy {results['environment']['numpy_version']}; eval {results['environment']['eval_version']}",
    ]


def _cols(results: dict[str, Any]) -> list[str]:
    lvl = f"{results['bootstrap']['ci_level'] * 100:g}% CI"
    return [c.replace("CI", lvl) for c in COLUMNS]


def render_md(results: dict[str, Any]) -> str:
    lines = [f"# {TITLE}", ""]
    lines += [f"> **{h}**" for h in header_lines(results)]
    lines.append("")
    lines += [f"- {x}" for x in meta_lines(results)]
    lines.append("")
    cols = _cols(results)
    lines.append("| " + " | ".join(cols) + " |")
    lines.append("|" + "---|" * len(cols))
    for row in table_rows(results):
        lines.append("| " + " | ".join(c.replace("|", "\\|") for c in row) + " |")
    lines += ["", "Undefined values are shown as null with a reason; they are never reported as 0 or 1. "
              "Differences are system minus comparator with a paired patient-level bootstrap CI.", ""]
    lines += [f"## {COVERAGE_TITLE}", "", COVERAGE_NOTE, ""]
    lines.append("| " + " | ".join(COVERAGE_COLUMNS) + " |")
    lines.append("|" + "---|" * len(COVERAGE_COLUMNS))
    for row in coverage_rows(results):
        lines.append("| " + " | ".join(c.replace("|", "\\|") for c in row) + " |")
    lines.append("")
    return "\n".join(lines)


def render_html(results: dict[str, Any]) -> str:
    e = html.escape
    parts = ["<!DOCTYPE html>", '<html lang="en">', "<head>", '<meta charset="utf-8">', f"<title>{e(TITLE)}</title>",
             "<style>body{font-family:sans-serif;margin:2em}table{border-collapse:collapse}"
             "td,th{border:1px solid #999;padding:4px 8px;text-align:left}"
             ".banner{font-weight:bold;border:2px solid #333;padding:6px;margin:4px 0}</style>",
             "</head>", "<body>", f"<h1>{e(TITLE)}</h1>"]
    parts += [f'<div class="banner">{e(h)}</div>' for h in header_lines(results)]
    parts.append("<ul>" + "".join(f"<li>{e(x)}</li>" for x in meta_lines(results)) + "</ul>")
    parts.append("<table>")
    parts.append("<tr>" + "".join(f"<th>{e(c)}</th>" for c in _cols(results)) + "</tr>")
    for row in table_rows(results):
        parts.append("<tr>" + "".join(f"<td>{e(c)}</td>" for c in row) + "</tr>")
    parts += ["</table>", "<p>Undefined values are shown as null with a reason; they are never reported as 0 or 1. "
              "Differences are system minus comparator with a paired patient-level bootstrap CI.</p>"]
    parts += [f"<h2>{e(COVERAGE_TITLE)}</h2>", f"<p>{e(COVERAGE_NOTE)}</p>", "<table>",
              "<tr>" + "".join(f"<th>{e(c)}</th>" for c in COVERAGE_COLUMNS) + "</tr>"]
    for row in coverage_rows(results):
        parts.append("<tr>" + "".join(f"<td>{e(c)}</td>" for c in row) + "</tr>")
    parts += ["</table>", "</body>", "</html>", ""]
    return "\n".join(parts)
