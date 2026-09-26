"""Evaluate both modes on clean and injected synthetic cases. Offline; mock provider only.

Run: ``make pharma-eval`` -> ``slices/s5/eval/{results.json,injection_log.jsonl}``.
Results are a System Evaluation on synthetic data, not clinical performance.
"""

from __future__ import annotations

import argparse
import json
import math
import random
from collections.abc import Callable
from pathlib import Path

from sqlalchemy import create_engine
from sqlalchemy.pool import StaticPool

from ...config import Settings
from ...db import create_schema
from ...gateway import GatewayRequest, build_provider, invoke_gateway
from ..fixtures.build import MANIFEST_FILE
from ..formulary import load_formulary
from ..mock_rules import parse_entry
from ..models import ISSUE_TYPES, MedSnapshot
from ..pipeline import PIPELINE_VERSION, issue_signature, reconcile
from ..rules import RULES_VERSION
from .inject import INJECT_SEED, build_cases, load_patients, log_lines

BOOT_SEED = 20260926
RESAMPLES = 1000
MODES = ("rules_only", "rules_plus_model")
PRIMARY_MODE = "rules_plus_model"
FIELDS = ("drug_name_raw", "dose_value", "dose_unit", "route", "frequency_code")
THRESHOLDS = {
    "recall_min_per_type": 0.95,
    "min_cases_per_type": 30,
    "clean_false_alerts_max": 0.10,
    "extra_issues_per_case_max": 0.10,
    "extraction_accuracy_min": 0.98,
    "mode_equality": 1.0,
}
DEFAULT_OUT = Path(__file__).resolve().parents[4] / "slices" / "s5" / "eval"


def make_invoke() -> Callable[[GatewayRequest], object]:
    """In-process audited gateway on a throwaway in-memory DB with the offline mock provider."""
    engine = create_engine("sqlite://", poolclass=StaticPool, connect_args={"check_same_thread": False})
    create_schema(engine)
    provider = build_provider("mock", Settings())

    def invoke(req: GatewayRequest):
        return invoke_gateway(engine, provider, req, request_id="pharma-eval", actor_id=None, actor_role="eval")

    return invoke


def matches(issue: dict, expected: dict) -> bool:
    """Same type, same ingredient set, injected source among ``conflicting_sources``; for
    ``missing_field`` also the same field, with the injected source as the incomplete entry."""
    if not (
        issue["type"] == expected["type"]
        and sorted(issue["ingredients"]) == sorted(expected["ingredients"])
        and set(expected["sources"]) <= {s["source_type"] for s in issue["conflicting_sources"]}
    ):
        return False
    if expected["type"] == "missing_field":
        return issue.get("field") == expected["field"] and issue["conflicting_sources"][0]["source_type"] in expected["sources"]
    return True


def min_sources(issue: dict, run: dict) -> int:
    """Required ``conflicting_sources`` length: 2 for mismatch, duplication and allergy; 1 for omission;
    for missing_field 2 when an ingredient of the issue is in 2 or more source types, else 1."""
    if issue["type"] == "omission":
        return 1
    if issue["type"] != "missing_field":
        return 2
    ings = set(issue["ingredients"])
    types = {
        rec["source_type"]
        for rec in run["extraction"]
        if rec["status"] == "ok"
        for e in rec["entries"]
        if ings & set(e["ingredients"])
    }
    return 2 if len(types) >= 2 else 1


def _binom_tail_ge(k: int, n: int, p: float) -> float:
    return sum(math.comb(n, i) * p**i * (1 - p) ** (n - i) for i in range(k, n + 1))


def clopper_pearson(k: int, n: int, alpha: float = 0.05) -> list[float | None]:
    """Exact (Clopper-Pearson) two-sided interval for k successes in n trials, by bisection on the
    binomial tails. Reported next to the bootstrap CI, which is degenerate ([1, 1]) at 100% recall."""
    if n == 0:
        return [None, None]

    def solve(target: float, f) -> float:  # f increasing in p
        lo, hi = 0.0, 1.0
        for _ in range(200):
            mid = (lo + hi) / 2
            lo, hi = (mid, hi) if f(mid) < target else (lo, mid)
        return (lo + hi) / 2

    lower = 0.0 if k == 0 else solve(alpha / 2, lambda p: _binom_tail_ge(k, n, p))
    upper = 1.0 if k == n else solve(1 - alpha / 2, lambda p: _binom_tail_ge(k + 1, n, p))
    return [round(lower, 4), round(upper, 4)]


def _ci(values: list[float]) -> list[float]:
    if not values:
        return [None, None]  # type: ignore[list-item]
    s = sorted(values)
    lo = s[int(0.025 * (len(s) - 1))]
    hi = s[int(round(0.975 * (len(s) - 1)))]
    return [round(lo, 4), round(hi, 4)]


def _ratio(num: float, den: float) -> float | None:
    return round(num / den, 4) if den else None


def _stats(agg: dict) -> dict[str, float | None]:
    tot = agg["tot"]
    out: dict[str, float | None] = {
        "clean": _ratio(tot["clean"], tot["n_clean"]),
        "extras": _ratio(tot["extras"], tot["n_cases"]),
    }
    for t in ISSUE_TYPES:
        out[f"rec:{t}"] = _ratio(*agg["rec"][t])
        out[f"prec:{t}"] = _ratio(*agg["prec"][t])
    return out


def _agg(per_patient: dict[str, dict], sample: list[str]) -> dict:
    tot = {"clean": 0, "n_clean": 0, "extras": 0, "n_cases": 0}
    rec = {t: [0, 0] for t in ISSUE_TYPES}
    prec = {t: [0, 0] for t in ISSUE_TYPES}
    for p in sample:
        d = per_patient[p]
        tot["clean"] += d["clean_alerts"]
        tot["n_clean"] += 1
        for c in d["cases"]:
            tot["extras"] += c["extras"]
            tot["n_cases"] += 1
            rec[c["type"]][0] += c["matched"]
            rec[c["type"]][1] += 1
            for t, (n, tp) in c["predicted"].items():
                prec[t][0] += tp
                prec[t][1] += n
    return {"tot": tot, "rec": rec, "prec": prec}


def bootstrap_stats(per_patient: dict[str, dict], patients: list[str], seed: int, resamples: int = RESAMPLES) -> list[dict]:
    """Patient-level bootstrap: the resampling unit is the patient, so a patient's clean list and all
    of its injected cases always enter (or leave) a resample together."""
    rng = random.Random(seed)
    out = []
    for _ in range(resamples):
        sample = [patients[rng.randrange(len(patients))] for _ in patients]
        out.append(_stats(_agg(per_patient, sample)))
    return out


def _mode_metrics(per_patient: dict[str, dict], patients: list[str], seed: int) -> dict:
    """per_patient[p] = {"clean_alerts": int, "cases": [{type, matched, extras, predicted: {type: (n, tp)}}]}.

    95% CIs: percentile bootstrap over patients (1000 resamples, fixed seed); recall also gets the
    exact Clopper-Pearson interval."""
    boots: dict[str, list[float]] = {}
    for stats in bootstrap_stats(per_patient, patients, seed):
        for k, v in stats.items():
            if v is not None:
                boots.setdefault(k, []).append(v)
    point = _agg(per_patient, patients)
    tot = point["tot"]
    out: dict = {"n_patients": len(patients), "recall": {}, "precision": {}}
    for t in ISSUE_TYPES:
        hits, n = point["rec"][t]
        out["recall"][t] = {
            "cases": n, "detected": hits, "recall": _ratio(hits, n),
            "ci95": _ci(boots.get(f"rec:{t}", [])), "ci95_exact": clopper_pearson(hits, n),
        }
        tp, pn = point["prec"][t]
        out["precision"][t] = {
            "predicted": pn, "true_positive": tp, "precision": _ratio(tp, pn), "ci95": _ci(boots.get(f"prec:{t}", [])),
        }
    out["clean_false_alerts"] = {
        "lists": tot["n_clean"], "alerts": tot["clean"],
        "mean_per_list": _ratio(tot["clean"], tot["n_clean"]), "ci95": _ci(boots.get("clean", [])),
    }
    out["extra_issues_per_injected_case"] = {
        "cases": tot["n_cases"], "extra": tot["extras"],
        "mean_per_case": _ratio(tot["extras"], tot["n_cases"]), "ci95": _ci(boots.get("extras", [])),
    }
    return out


def _extraction(patients: list[dict], runs: dict[str, dict]) -> dict:
    out = {}
    for scope in ("test", "all"):
        correct = {f: 0 for f in FIELDS}
        total = 0
        fabricated = 0
        failed_sources = 0
        for p in patients:
            if scope == "test" and p["split"] != "test":
                continue
            run = runs[p["patient_ref"]]
            for rec in run["extraction"]:
                gold = p["gold"][rec["source_type"]]
                if rec["status"] != "ok":
                    failed_sources += 1
                    total += len(gold)
                    continue
                for ext, g in zip(rec["entries"], gold):
                    total += 1
                    for f in FIELDS:
                        correct[f] += ext[f] == g[f]
                        fabricated += g[f] is None and ext[f] is not None
        per_field = {f: _ratio(correct[f], total) for f in FIELDS}
        out[scope] = {
            "entries": total,
            "field_accuracy": per_field,
            "overall_accuracy": _ratio(sum(correct.values()), total * len(FIELDS)),
            "fabricated_values": fabricated,
            "failed_sources": failed_sources,
        }
    return out


def _kinds(run: dict, matched_issue: dict | None = None) -> dict[str, int]:
    """Alert counts by kind (issue type or notice type), excluding the matched injected issue."""
    out: dict[str, int] = {}
    for i in run["issues"]:
        if i is not matched_issue:
            out[f"issue:{i['type']}"] = out.get(f"issue:{i['type']}", 0) + 1
    for n in run["notices"]:
        out[f"notice:{n['type']}"] = out.get(f"notice:{n['type']}", 0) + 1
    return out


def _breakdown(rows: list[tuple[str, dict[str, int]]], split_of: dict[str, str]) -> dict:
    """Which issue and notice kinds make up the false-alert counts (all kinds count, incl. missing_field)."""
    out = {}
    for scope in ("test", "all"):
        picked = [k for ref, k in rows if scope == "all" or split_of[ref] == "test"]
        totals: dict[str, int] = {}
        for kinds in picked:
            for k, v in kinds.items():
                totals[k] = totals.get(k, 0) + v
        out[scope] = {"units": len(picked), "by_kind": dict(sorted(totals.items()))}
    return out


def _missing_field_coverage(cases: list[dict]) -> dict:
    out = {}
    for scope in ("test", "all"):
        picked = [c for c in cases if c["type"] == "missing_field" and (scope == "all" or c["split"] == "test")]
        out[scope] = {
            "cases": len(picked),
            "by_field": {f: sum(c["field"] == f for c in picked) for f in ("dose", "frequency")},
            "by_source": {s: sum(c["source"] == s for c in picked) for s in ("home_list", "patient_reported", "new_order")},
        }
    return out


def _extraction_null_preserved(cases: list[dict]) -> dict:
    """Mock extraction of every blanked missing_field line must give null for the blanked field."""
    key = {"dose": ("dose_value", "dose_unit"), "frequency": ("frequency_code",)}
    picked = [c for c in cases if c["type"] == "missing_field"]
    fabricated = [c["case_id"] for c in picked if any(parse_entry(c["after"])[k] is not None for k in key[c["field"]])]
    return {"cases": len(picked), "null_preserved": len(picked) - len(fabricated), "fabricated": fabricated}


def evaluate(out_dir: Path | None = DEFAULT_OUT) -> dict:
    invoke = make_invoke()
    patients = load_patients()
    cases = build_cases(patients)
    split_of = {p["patient_ref"]: p["split"] for p in patients}
    signatures: dict[str, dict[str, list]] = {m: {} for m in MODES}
    per_mode: dict[str, dict] = {}
    clean_runs_primary: dict[str, dict] = {}
    sources_complete = {"issues": 0, "violations": 0}
    clean_kinds: list[tuple[str, dict[str, int]]] = []
    case_kinds: list[tuple[str, dict[str, int]]] = []
    unchecked = {"clean_lists": 0, "injected_cases": 0}

    for m_index, mode in enumerate(MODES):
        per_patient = {p["patient_ref"]: {"clean_alerts": 0, "cases": []} for p in patients}
        for p in patients:
            run = reconcile(MedSnapshot.model_validate(p["snapshot"]), invoke, mode, run_id=f"eval-{p['patient_ref']}")
            per_patient[p["patient_ref"]]["clean_alerts"] = len(run["issues"]) + len(run["notices"])
            signatures[mode][p["patient_ref"]] = [issue_signature(i) for i in run["issues"]]
            if mode == PRIMARY_MODE:
                clean_runs_primary[p["patient_ref"]] = run
                clean_kinds.append((p["patient_ref"], _kinds(run)))
                unchecked["clean_lists"] += run["unchecked_comparisons"]
        for case in cases:
            run = reconcile(MedSnapshot.model_validate(case["snapshot"]), invoke, mode, run_id=f"eval-{case['case_id']}")
            matched_issue = next((i for i in run["issues"] if matches(i, case["expected"])), None)
            matched_one = matched_issue is not None
            if mode == PRIMARY_MODE:
                case_kinds.append((case["patient_ref"], _kinds(run, matched_issue)))
                unchecked["injected_cases"] += run["unchecked_comparisons"]
            predicted: dict[str, list[int]] = {}
            for i in run["issues"]:
                slot = predicted.setdefault(i["type"], [0, 0])
                slot[0] += 1
                slot[1] += matches(i, case["expected"])
            for issue in run["issues"]:
                sources_complete["issues"] += 1
                srcs = issue["conflicting_sources"]
                need = min_sources(issue, run)
                ok = len(srcs) >= need and all(
                    s.get("source_type") and s.get("evidence_ref") and s.get("available_at_time") and "raw_span" in s
                    for s in srcs
                )
                sources_complete["violations"] += not ok
            per_patient[case["patient_ref"]]["cases"].append({
                "type": case["type"],
                "matched": int(matched_one),
                "extras": len(run["issues"]) + len(run["notices"]) - int(matched_one),
                "predicted": {t: tuple(v) for t, v in predicted.items()},
            })
            signatures[mode][case["case_id"]] = [issue_signature(i) for i in run["issues"]]
        test_refs = [p for p in per_patient if split_of[p] == "test"]
        per_mode[mode] = {
            "test": _mode_metrics(per_patient, test_refs, BOOT_SEED + 1000 * m_index),
            "all": _mode_metrics(per_patient, list(per_patient), BOOT_SEED + 1000 * m_index + 500),
        }

    keys = sorted(signatures[MODES[0]])
    identical = sum(signatures[MODES[0]][k] == signatures[MODES[1]][k] for k in keys)
    primary = per_mode[PRIMARY_MODE]
    form = load_formulary()
    extraction = _extraction(patients, clean_runs_primary)
    frozen = json.loads(MANIFEST_FILE.read_text(encoding="utf-8"))
    results = {
        "label": "System Evaluation on synthetic data; not clinical performance. No expert pharmacist review yet.",
        "data_class": "synthetic",
        "versions": {
            "pipeline": PIPELINE_VERSION, "rules": RULES_VERSION, "formulary": form.version,
            "cross_reactivity": form.cross_version, "provider": "mock",
        },
        "test_manifest": {"sha256": frozen["sha256"], "generator_version": frozen["generator_version"]},
        "seeds": {"inject": INJECT_SEED, "bootstrap": BOOT_SEED, "resamples": RESAMPLES, "resampling_unit": "patient"},
        "counts": {
            "patients": len(patients),
            "test_patients": sum(p["split"] == "test" for p in patients),
            "dev_patients": sum(p["split"] == "dev" for p in patients),
            "injected_cases": len(cases),
            "cases_per_type": {t: sum(c["type"] == t for c in cases) for t in ISSUE_TYPES},
            "test_cases_per_type": {t: sum(c["type"] == t and c["split"] == "test" for c in cases) for t in ISSUE_TYPES},
            "missing_field_coverage": _missing_field_coverage(cases),
        },
        "primary_mode": PRIMARY_MODE,
        "recall": {t: {s: primary[s]["recall"][t] for s in ("test", "all")} for t in ISSUE_TYPES},
        "precision": {t: {s: primary[s]["precision"][t] for s in ("test", "all")} for t in ISSUE_TYPES},
        "clean_false_alerts": {s: primary[s]["clean_false_alerts"] for s in ("test", "all")},
        "extra_issues_per_injected_case": {s: primary[s]["extra_issues_per_injected_case"] for s in ("test", "all")},
        "alert_breakdown": {
            "note": (
                "False alerts count every issue and every notice, including missing_field (DECISIONS 2026-09-27). "
                "Clean lists are fully specified in every source, so clean-list false alerts assume complete "
                "sources; real lists (especially patient-reported) often omit dose or frequency, so missing_field "
                "volume will be higher on real data and needs pharmacist review before any non-synthetic use."
            ),
            "clean_lists": _breakdown(clean_kinds, split_of),
            "injected_case_extras": _breakdown(case_kinds, split_of),
        },
        "extraction": extraction,
        "extraction_null_preserved": _extraction_null_preserved(cases),
        "unchecked_comparisons": unchecked,
        "modes": per_mode,
        "mode_equality": {"runs_compared": len(keys), "identical": identical, "fraction": _ratio(identical, len(keys))},
        "issue_sources_complete": sources_complete,
        "thresholds": THRESHOLDS,
    }
    if out_dir is not None:
        out_dir.mkdir(parents=True, exist_ok=True)
        (out_dir / "results.json").write_text(
            json.dumps(results, ensure_ascii=False, indent=1, sort_keys=True) + "\n", encoding="utf-8"
        )
        (out_dir / "injection_log.jsonl").write_text(log_lines(cases), encoding="utf-8")
    return results


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    args = parser.parse_args()
    r = evaluate(args.out)
    for t in ISSUE_TYPES:
        print(f"{t:26s} recall test={r['recall'][t]['test']['recall']} all={r['recall'][t]['all']['recall']}")
    print("clean false alerts/list:", {s: r["clean_false_alerts"][s]["mean_per_list"] for s in ("test", "all")})
    print("extra issues/case:", {s: r["extra_issues_per_injected_case"][s]["mean_per_case"] for s in ("test", "all")})
    print("extraction overall:", {s: r["extraction"][s]["overall_accuracy"] for s in ("test", "all")})
    print("mode equality:", r["mode_equality"])
    print(f"wrote {args.out}/results.json and injection_log.jsonl")


if __name__ == "__main__":
    main()
