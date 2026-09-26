"""System Evaluation of slice s4 on the synthetic fixtures (not clinical performance).

Run: ``PYTHONPATH=backend python -m app.triage.evaluate`` -> ``slices/s4/eval/metrics_v1.json``.
Department calls go through the Model Gateway service with the default offline mock provider.
The output is deterministic (no timestamps), with patient-level bootstrap 95% CIs.
"""

from __future__ import annotations

import hashlib
import json
import random
from collections.abc import Callable
from pathlib import Path
from typing import Any

from sqlalchemy import Engine

from ..config import Settings
from ..db import create_schema, make_engine
from ..gateway import build_provider
from ..gateway import service as gateway_service
from ..gateway.contract import GatewayRequest, GatewayResponse
from . import baseline, department, redflags
from .departments import DEPARTMENT_LIST_VERSION
from .fixtures import CASES_PATH, load_entries
from .models import FixtureEntry, Snapshot

REPO_ROOT = Path(__file__).resolve().parents[3]
OUT_PATH = REPO_ROOT / "slices" / "s4" / "eval" / "metrics_v1.json"
JUSTIFICATIONS_PATH = REPO_ROOT / "slices" / "s4" / "eval" / "fp_justifications_v1.json"
LABEL = "System Evaluation on synthetic fixtures — not clinical performance"
RESAMPLES = 1000
SEED = 20260926
ALWAYS_ANSWER_FALLBACK = "MED"  # what an "always answer" system outputs when nothing matched


def mock_invoke(engine: Engine | None = None) -> department.InvokeFn:
    engine = engine or make_engine("sqlite://")
    create_schema(engine)
    provider = build_provider("mock", Settings())

    def _invoke(req: GatewayRequest) -> GatewayResponse:
        return gateway_service.invoke(engine, provider, req, None, request_id="triage-evaluate")

    return _invoke


def case_record(entry: FixtureEntry, invoke: department.InvokeFn) -> dict[str, Any]:
    snap = Snapshot(entry.case, entry.as_of)
    alerts, not_evaluable = redflags.evaluate(snap)
    dept = department.suggest(snap, invoke)
    codes = [e.code for e in dept.top3]
    early = None
    if entry.gold.temporal:
        early_alerts, _ = redflags.evaluate(Snapshot(entry.case, entry.gold.temporal.early_as_of))
        early = sorted(a.rule_id for a in early_alerts)
    return {
        "case_ref": entry.case.case_ref,
        "split": entry.split,
        "gold_rules": sorted(entry.gold.red_flag_rules),
        "fired_rules": sorted(a.rule_id for a in alerts),
        "not_evaluable": sorted(n.rule_id for n in not_evaluable),
        "gold_early": entry.gold.temporal.red_flag_rules if entry.gold.temporal else None,
        "fired_early": early,
        "gold_department": entry.gold.department,
        "gold_missing": entry.gold.missing_required,
        "complete": not entry.gold.missing_required,
        "dept_status": dept.status,
        "top3": codes,
        "missing_information": dept.missing_information,
        "always_answer": codes[0] if codes else ALWAYS_ANSWER_FALLBACK,
    }


def run_records(invoke: department.InvokeFn | None = None) -> list[dict[str, Any]]:
    invoke = invoke or mock_invoke()
    return [case_record(e, invoke) for e in load_entries()]


Ratio = Callable[[list[dict[str, Any]]], tuple[int, int]]


def _count(rows, den_if, num_if) -> tuple[int, int]:
    den = [r for r in rows if den_if(r)]
    return sum(1 for r in den if num_if(r)), len(den)


METRICS: dict[str, Ratio] = {
    "redflag_case_recall": lambda rs: _count(rs, lambda r: r["gold_rules"], lambda r: bool(r["fired_rules"])),
    "redflag_rule_recall": lambda rs: (
        sum(len(set(r["gold_rules"]) & set(r["fired_rules"])) for r in rs),
        sum(len(r["gold_rules"]) for r in rs),
    ),
    "redflag_fpr": lambda rs: _count(rs, lambda r: not r["gold_rules"], lambda r: bool(r["fired_rules"])),
    "redflag_temporal_early_exact": lambda rs: _count(
        rs, lambda r: r["gold_early"] is not None, lambda r: r["fired_early"] == r["gold_early"]
    ),
    "dept_top1_accuracy_answered": lambda rs: _count(
        rs, lambda r: r["complete"] and r["dept_status"] == "suggested", lambda r: r["top3"][0] == r["gold_department"]
    ),
    "dept_top3_accuracy_answered": lambda rs: _count(
        rs, lambda r: r["complete"] and r["dept_status"] == "suggested", lambda r: r["gold_department"] in r["top3"]
    ),
    "dept_coverage_complete": lambda rs: _count(rs, lambda r: r["complete"], lambda r: r["dept_status"] == "suggested"),
    "dept_always_answer_top1_accuracy": lambda rs: _count(
        rs, lambda r: r["complete"], lambda r: r["always_answer"] == r["gold_department"]
    ),
    "abstention_on_missing_exact": lambda rs: _count(
        rs,
        lambda r: not r["complete"],
        lambda r: r["dept_status"] == "abstained" and not r["top3"] and r["missing_information"] == r["gold_missing"],
    ),
    "false_abstention_complete": lambda rs: _count(rs, lambda r: r["complete"], lambda r: r["dept_status"] != "suggested"),
}


def _ci(rows: list[dict[str, Any]], fn: Ratio, rng: random.Random) -> tuple[list[float] | None, int]:
    values = []
    for _ in range(RESAMPLES):
        sample = [rows[rng.randrange(len(rows))] for _ in rows]  # patient-level: one case per patient
        num, den = fn(sample)
        if den:
            values.append(num / den)
    if not values:
        return None, 0
    values.sort()
    lo = values[int(0.025 * (len(values) - 1))]
    hi = values[int(round(0.975 * (len(values) - 1)))]
    return [round(lo, 4), round(hi, 4)], len(values)


def summarize(rows: list[dict[str, Any]]) -> dict[str, Any]:
    rng = random.Random(SEED)
    out: dict[str, Any] = {}
    for split in ("dev", "holdout", "overall"):
        subset = rows if split == "overall" else [r for r in rows if r["split"] == split]
        out[split] = {}
        for name, fn in METRICS.items():
            num, den = fn(subset)
            ci, valid = _ci(subset, fn, rng)
            out[split][name] = {
                "value": round(num / den, 4) if den else None,
                "num": num,
                "den": den,
                "ci95": ci,
                "valid_resamples": valid,
            }
    return out


def false_positives(rows: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], dict[str, list[str]]]:
    notes = json.loads(JUSTIFICATIONS_PATH.read_text(encoding="utf-8")) if JUSTIFICATIONS_PATH.exists() else {}
    fps, extra = [], {}
    for r in rows:
        extra_rules = sorted(set(r["fired_rules"]) - set(r["gold_rules"]))
        for rule in extra_rules:
            extra.setdefault(rule, []).append(r["case_ref"])
        if extra_rules:
            fps.append({
                "case_ref": r["case_ref"],
                "gold_negative_case": not r["gold_rules"],
                "extra_rules": extra_rules,
                "justification": notes.get(r["case_ref"], "UNJUSTIFIED — needs review"),
            })
    return fps, extra


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def build_report(rows: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    rows = rows if rows is not None else run_records()
    metrics = summarize(rows)
    fps, extra = false_positives(rows)
    holdout_top3 = metrics["holdout"]["dept_top3_accuracy_answered"]["value"]
    return {
        "label": LABEL,
        "slice": "s4",
        "versions": {
            "ruleset_version": redflags.RULESET_VERSION,
            "ruleset_sha256": redflags.RULESET_SHA256,
            "fixtures_sha256": _sha(CASES_PATH),
            "baseline_version": baseline.BASELINE_VERSION,
            "department_list_version": DEPARTMENT_LIST_VERSION,
            "department_task": department.TASK,
            "provider": "mock (default, offline)",
        },
        "bootstrap": {"resamples": RESAMPLES, "seed": SEED, "unit": "patient (one synthetic case per patient)",
                      "interval": "percentile 2.5-97.5"},
        "definitions": {
            "answered": "complete cases (no gold missing field) where the department status is 'suggested'",
            "always_answer": f"top-1 of the same baseline without abstention; '{ALWAYS_ANSWER_FALLBACK}' if nothing matched",
            "redflag_fpr": "gold-negative cases with at least one alert / gold-negative cases",
        },
        "metrics": metrics,
        "false_positives": fps,
        "extra_alerts_per_rule": extra,
        "flags": {
            "holdout_top3_below_0_70_overfitting_risk": holdout_top3 is not None and holdout_top3 < 0.70,
            "redflag_recall_gate_pass": all(
                metrics[s][m]["value"] == 1.0
                for s in ("dev", "holdout", "overall")
                for m in ("redflag_case_recall", "redflag_rule_recall")
            ),
        },
        "cases": rows,
        "caveats": [
            "Rules and fixtures were written by the same author: 100% recall on 40 cases is a regression gate, "
            "not evidence of clinical sensitivity.",
            "The department baseline is a MOCK keyword table; scores are not calibrated probabilities.",
            "Department list, MIMIC services mapping, and red-flag thresholds are provisional until clinical "
            "expert review.",
        ],
    }


def main() -> None:
    report = build_report()
    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUT_PATH.write_text(json.dumps(report, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    m = report["metrics"]["overall"]
    print(LABEL)
    for name in METRICS:
        print(f"  {name}: {m[name]['value']} ({m[name]['num']}/{m[name]['den']}) CI95 {m[name]['ci95']}")
    print(f"wrote {OUT_PATH.relative_to(REPO_ROOT)}")


if __name__ == "__main__":
    main()
