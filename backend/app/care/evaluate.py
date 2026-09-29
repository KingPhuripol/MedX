"""System Evaluation of slice s6 on synthetic data (not clinical performance). Evaluation harness, not the engine.

This is the only module under ``app/care`` that reads gold labels: it joins engine outputs (computed from
``inputs/<split>/<case>/snapshot_T*.json`` only) with ``gold/<split>/*.json`` to write eval-harness records.

    python -m app.care.evaluate --split dev|test [--dataset DIR] [--evaluation-id ID]   # predictions + comparator
    python -m app.care.evaluate --split ... --write-manifest    # predeclared manifest (from gold, not predictions)
    python -m app.care.evaluate retire                          # s6r: relabel s6-care-test-0001 (idempotent)
    python -m app.care.evaluate before-after                    # s6r: dev-0001 vs dev-0002 table

The v1 dataset's test split is retired (DECISIONS.md 2026-09-27); ``--split test`` needs the s6r held-out set.
File names: evaluation id ``...-0001`` keeps the s6 names (``manifest_<split>.json``); any other id ``...-NNNN``
adds ``_NNNN`` (``manifest_test_0002.json``, ``results_test_0002/``, ``summary_test_0002.json``).

then ``python -m eval --ledger-dir slices/s6/eval/ledger run ...`` (``make care-eval SPLIT=...``).
Calls go through the gateway service with the offline mock provider. Output is deterministic (no timestamps).

Tasks (one row per decision point; ``patient_id`` = patient_ref, ``decision_point_id`` = <case_id>:T1|T2):
- ``care_coverage``: every decision point; ``y_pred`` "suggest" or null (abstained or error).
- ``care_next_info``: gold ``care.evaluable`` rows; ``suggested`` = ranked NI codes or null; ``ordered`` = gold
  ``next_info``. Comparators: ``always_answer`` (same engine, ``abstain=False``, every row),
  ``always_answer_on_answered`` (same, null where the system abstained: paired on answered rows) and
  ``train_prior`` (static top-3 most frequent gold NI codes on the train split, on the rows the system answered).
- ``care_ordered_proxy``: rows with non-empty gold ``ordered_after_T`` (proposal 3.6(3) proxy).
- ``care_pathway``: rows with a gold ``pathway``; ``y_pred`` = top-1 pathway ("none" if answered without one).
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
from collections import Counter
from pathlib import Path
from typing import Any

from eval.runner import results_json_bytes

from ..config import Settings
from ..gateway import build_provider
from ..gateway.service import invoke_provider
from . import dataset, engine
from .ruleset import CARE_RULES_VERSION

REPO_ROOT = dataset.REPO_ROOT
EVAL_DIR = REPO_ROOT / "slices" / "s6" / "eval"
LABEL = "System Evaluation on synthetic data — not clinical performance"
SEED = 20260926
K = 3
DEV_GATE = 0.80
TEST_FLAG = 0.70
MIN_ANSWERED = 30
NO_PATHWAY = "none"
V1_DATASET = REPO_ROOT / dataset.DEFAULT_DATASET  # the train prior always comes from v1 train
RETIRED_ID = "s6-care-test-0001"
RETIRED_LABEL = "seen — not a held-out result"
DECISION = "DECISIONS.md 2026-09-27"
DECISION_TITLE = "S6 test split redone on a fresh held-out set"
S6R_DIR = REPO_ROOT / "slices" / "s6r" / "eval"


def suffix(evaluation_id: str) -> str:
    n = evaluation_id.rsplit("-", 1)[-1]
    return "" if n == "0001" else f"_{n}"


def paths(split: str, evaluation_id: str, base: Path = EVAL_DIR) -> dict[str, Path]:
    x = f"{split}{suffix(evaluation_id)}"
    return {"manifest": base / f"manifest_{x}.json", "predictions": base / f"predictions_{x}.jsonl",
            "comparator": base / f"comparator_{x}.jsonl", "summary": base / f"summary_{x}.json",
            "results": base / f"results_{x}"}


def _gold(root: Path, split: str) -> list[dict[str, Any]]:
    out = []
    for p in sorted((root / "gold" / split).glob("*.json")):
        g = json.loads(p.read_text("utf-8"))
        for row in g["decision_times"]:
            out.append({"case_id": g["case_id"], "patient_id": g["patient_ref"], "dp": row["decision_point"],
                        "care": row["care"]})
    return sorted(out, key=lambda r: (r["patient_id"], r["dp"]))


def train_prior(root: Path) -> list[str]:
    counts = Counter(c for r in _gold(root, "train") if r["care"]["evaluable"] for c in r["care"]["next_info"])
    return [c for c, _ in sorted(counts.items(), key=lambda kv: (-kv[1], kv[0]))[:K]]


def _dataset_meta(root: Path) -> dict[str, Any]:
    return json.loads((root / "manifest.json").read_text("utf-8"))


def records(split: str) -> tuple[list[dict[str, Any]], list[dict[str, Any]], dict[str, Any]]:
    root = dataset.root()
    provider = build_provider("mock", Settings())
    invoke = lambda req: invoke_provider(provider, req)  # noqa: E731
    prior = train_prior(root if (root / "gold" / "train").is_dir() else V1_DATASET)
    preds: list[dict[str, Any]] = []
    cmps: list[dict[str, Any]] = []
    n_answered_eval = n_error = 0
    for g in _gold(root, split):
        snap = dataset.load_snapshot(split, g["case_id"], g["dp"])
        sysr = engine.assess(snap, invoke, decision_point=g["dp"])
        alw = engine.assess(snap, invoke, decision_point=g["dp"], abstain=False)
        answered = sysr.status == "suggested"
        n_error += sysr.status == "error"
        s_codes = [x.code for x in sysr.next_information] if answered else None
        a_codes = [x.code for x in alw.next_information]  # always answers; an error answers with nothing
        care = g["care"]
        key = {"patient_id": g["patient_id"], "decision_point_id": f"{g['case_id']}:{g['dp']}"}
        preds.append({**key, "task": "care_coverage", "y_true": care["expected_action"],
                      "y_pred": "suggest" if answered else None, "status": sysr.status})
        if care["evaluable"]:
            n_answered_eval += answered
            base = {**key, "task": "care_next_info", "ordered": care["next_info"]}
            preds.append({**base, "suggested": s_codes})
            cmps += [{**base, "comparator": "always_answer", "suggested": a_codes},
                     {**base, "comparator": "always_answer_on_answered", "suggested": a_codes if answered else None},
                     {**base, "comparator": "train_prior", "suggested": prior if answered else None}]
        if care["ordered_after_T"]:
            preds.append({**key, "task": "care_ordered_proxy", "ordered": care["ordered_after_T"],
                          "suggested": s_codes})
        if care["pathway"]:
            top1 = (sysr.pathway_options[0].code if sysr.pathway_options else NO_PATHWAY) if answered else None
            preds.append({**key, "task": "care_pathway", "y_true": care["pathway"], "y_pred": top1})
    summary = {
        "label": LABEL,
        "split": split,
        "rules_version": CARE_RULES_VERSION,
        "dataset_tree_sha256": _dataset_meta(root)["tree_sha256"],
        "train_prior_codes": prior,
        "n_decision_points": sum(1 for p in preds if p["task"] == "care_coverage"),
        "n_status_error": n_error,
        "n_answered_evaluable": n_answered_eval,
        "min_answered_evaluable": MIN_ANSWERED,
        "underpowered": n_answered_eval < MIN_ANSWERED,
        "note": "hit@3 is lenient (any one of the top 3 in the gold set counts); labels are synthetic reference "
                "labels, not expert-reviewed (D1)",
    }
    return preds, cmps, summary


def _dump_jsonl(rows: list[dict[str, Any]]) -> bytes:
    return "".join(json.dumps(r, sort_keys=True, ensure_ascii=False) + "\n" for r in rows).encode("utf-8")


def manifest(split: str, evaluation_id: str | None = None) -> dict[str, Any]:
    """Predeclared from the dataset and gold only (never from predictions)."""
    root = dataset.root()
    meta = _dataset_meta(root)
    gold = _gold(root, split)
    pids = sorted({g["patient_id"] for g in gold})

    def plist(pred) -> list[str]:
        return sorted({g["patient_id"] for g in gold if pred(g["care"])})

    splits_sha = hashlib.sha256((root / "splits.json").read_bytes()).hexdigest()
    exact = {"exact_ci": "patient_all_success"}
    gate = ({"metric": "care_selective_hit3", "op": ">=", "value": DEV_GATE, "rule": "point"} if split == "dev"
            else {"metric": "care_selective_hit3", "op": ">=", "value": TEST_FLAG, "rule": "point"})
    return {
        "$comment": (f"Slice s6 care suggestion with abstention. {LABEL}. Mock baseline ({CARE_RULES_VERSION}), "
                     "synthetic reference labels (not expert-reviewed). "
                     + ("Dev threshold is gating (selective hit@3 point >= 0.80 with >= 30 answered evaluable "
                        "decision points)." if split == "dev" else
                        "Test threshold is a non-gating overfitting-risk flag (< 0.70).")),
        "manifest_version": "1.0",
        "evaluation_id": evaluation_id or f"s6-care-{split}-0001",
        "slice": "s6",
        "dataset": {"name": f"{'s6r-heldout' if meta.get('heldout') else 's1r'}-synthetic-v{meta.get('output_version', meta['generator_version'])}",
                    "version": meta["tree_sha256"],
                    "data_class": "synthetic"},
        "split": split,
        "split_version": f"splits.json sha256 {splits_sha} (seed {meta['seed']})",
        "split_patient_list": pids,
        "task_patient_lists": {
            "care_coverage": pids,
            "care_next_info": plist(lambda c: c["evaluable"]),
            "care_ordered_proxy": plist(lambda c: bool(c["ordered_after_T"])),
            "care_pathway": plist(lambda c: bool(c["pathway"])),
        },
        "metrics": [
            {"id": "care_coverage", "item": "Abstention", "task": "care_coverage", "name": "coverage",
             "params": {}, "primary": False},
            {"id": "care_selective_hit3", "item": "Abstention", "task": "care_next_info",
             "name": "selective_hit_at_k", "params": {"k": K, **exact}, "primary": True},
            {"id": "care_ordered_proxy_hit3", "item": "Case Graph", "task": "care_ordered_proxy",
             "name": "selective_hit_at_k", "params": {"k": K, **exact}, "primary": False},
            {"id": "care_pathway_top1", "item": "Case Graph", "task": "care_pathway", "name": "selective_accuracy",
             "params": exact, "primary": False},
        ],
        "comparators": [
            {"name": "always_answer", "description": "Same engine and rules without abstention, every evaluable "
                                                     "decision point", "tasks": ["care_next_info"]},
            {"name": "always_answer_on_answered", "description": "Always-answer output on the decision points the "
                                                                 "system answered (paired)", "tasks": ["care_next_info"]},
            {"name": "train_prior", "description": "Static top-3 most frequent gold next-information codes on the "
                                                   "train split, on the decision points the system answered",
             "tasks": ["care_next_info"]},
        ],
        "thresholds": [gate],
        "bootstrap": {"n_boot": 2000, "seed": SEED, "ci_level": 0.95, "method": "percentile"},
        "expert_review": {"done": False, "n_reviewers": 0},
    }


def retire(base: Path = EVAL_DIR) -> dict[str, Any]:
    """Relabel the retired frozen test run (S6R-A01). Idempotent; ledger lines and paths are untouched.

    ``original_results_sha256`` is the sha256 of results.json without ``retired`` in the runner's serialisation,
    i.e. the ``results_sha256`` of a ledger run line for the retired evaluation id."""
    d = base / "results_test"
    res = json.loads((d / "results.json").read_text("utf-8"))
    if res.get("evaluation_id") != RETIRED_ID:
        raise RuntimeError(f"{d / 'results.json'} is not {RETIRED_ID}")
    orig = {k: v for k, v in res.items() if k != "retired"}
    info = {"label": RETIRED_LABEL,
            "reason": f"{RETIRED_ID} was recorded twice (runs seq 2 and 4) and its results were seen while scoping "
                      "changes; it is not a held-out result. The S6 test result is s6-care-test-0002.",
            "decision": DECISION,
            "original_results_sha256": hashlib.sha256(results_json_bytes(orig)).hexdigest()}
    (d / "results.json").write_bytes(results_json_bytes({**orig, "retired": info}))
    md = (d / "results.md").read_text("utf-8")
    line = f"> **RETIRED: {RETIRED_LABEL}** ({DECISION}: {DECISION_TITLE}; the S6 test result is s6-care-test-0002)\n\n"
    if not md.startswith(line):
        (d / "results.md").write_text(line + md, "utf-8")
    html = (d / "results.html").read_text("utf-8")
    div = (f'<div class="banner">RETIRED: {RETIRED_LABEL} ({DECISION}: {DECISION_TITLE}; the S6 test result is '
           's6-care-test-0002)</div>\n')
    if div not in html:
        (d / "results.html").write_text(html.replace("<body>\n", "<body>\n" + div, 1), "utf-8")
    sp = base / "summary_test.json"
    summ = json.loads(sp.read_text("utf-8"))
    sp.write_text(json.dumps({**summ, "retired": info}, indent=2, ensure_ascii=False) + "\n", "utf-8")
    return info


def _cell(row: dict[str, Any], pre: str = "") -> dict[str, Any]:
    keys = ("point", "ci_low", "ci_high", "n_patients", "n_decision_points", "n_patients_scored",
            "n_decision_points_scored", "exact_ci")
    return {k: row.get(pre + k) for k in keys}


def before_after(base: Path = EVAL_DIR, out: Path = S6R_DIR) -> dict[str, Any]:
    """Dev before/after table from the two committed dev results (S6R-A03). Values are copied, never recomputed."""
    cols = {}
    for eid in ("s6-care-dev-0001", "s6-care-dev-0002"):
        res = json.loads((paths("dev", eid, base)["results"] / "results.json").read_text("utf-8"))
        rows = {r["metric_id"]: r for r in res["rows"]}
        hit = rows["care_selective_hit3"]
        comp = {c["comparator"]: c for c in hit["comparisons"]}
        cols[eid] = {
            "evaluation_id": res["evaluation_id"], "dataset_version": res["dataset"]["version"],
            "predictions_sha256": res["predictions_sha256"],
            "metrics": {
                "coverage": _cell(rows["care_coverage"]),
                "selective_hit3": _cell(hit),
                "always_answer_hit3_all_evaluable": _cell(comp["always_answer"], "comparator_"),
                "always_answer_hit3_on_answered": _cell(comp["always_answer_on_answered"], "comparator_"),
                "train_prior_hit3": _cell(comp["train_prior"], "comparator_"),
                "ordered_proxy_hit3": _cell(rows["care_ordered_proxy_hit3"]),
                "pathway_top1": _cell(rows["care_pathway_top1"]),
            }}
    b, a = cols["s6-care-dev-0001"]["metrics"], cols["s6-care-dev-0002"]["metrics"]
    delta = {k: (None if a[k]["point"] is None or b[k]["point"] is None else round(a[k]["point"] - b[k]["point"], 6))
             for k in a}
    doc = {"label": LABEL, "split": "dev", "before": cols["s6-care-dev-0001"], "after": cols["s6-care-dev-0002"],
           "delta_point": delta,
           "note": "comparator cells (always_answer*, train_prior) come from the selective hit@3 row; point, CI and "
                   "counts are copied from results.json; hit@3 is lenient; synthetic reference labels (D1)"}
    out.mkdir(parents=True, exist_ok=True)
    (out / "dev_before_after.json").write_text(json.dumps(doc, indent=2, ensure_ascii=False) + "\n", "utf-8")

    def fmt(c: dict[str, Any]) -> str:
        if c["point"] is None:
            return "undefined"
        ci = "" if c["ci_low"] is None else f" [{c['ci_low']:.4f}, {c['ci_high']:.4f}]"
        ex = c["exact_ci"]
        ex_s = f"; exact {ex['x']}/{ex['n']} [{ex['ci_low']:.4f}, {ex['ci_high']:.4f}]" if ex else ""
        sc = "" if c["n_patients_scored"] is None else f" (scored {c['n_patients_scored']} / {c['n_decision_points_scored']})"
        return f"{c['point']:.4f}{ci}{ex_s}; n {c['n_patients']} / {c['n_decision_points']}{sc}"

    lines = [f"# S6 care suggestion: dev before/after ({LABEL})", "",
             f"- before: s6-care-dev-0001 (care-rules-1.0.0), dataset {cols['s6-care-dev-0001']['dataset_version']}",
             f"- after: s6-care-dev-0002 (care-rules-1.1.0), dataset {cols['s6-care-dev-0002']['dataset_version']}",
             "- point [patient-level bootstrap 95% CI]; exact = Clopper-Pearson patient-level when triggered; "
             "n patients / decision points (scored subset)", "",
             "| Metric | dev-0001 | dev-0002 | Δ point |", "|---|---|---|---|"]
    lines += [f"| {k} | {fmt(b[k])} | {fmt(a[k])} | {'-' if delta[k] is None else f'{delta[k]:+.4f}'} |" for k in a]
    lines += ["", "Hit@3 is lenient (any one of the top 3 in the gold set counts). Labels are synthetic reference "
              "labels, not expert-reviewed (D1). Dev only; no test data was used for any rule change."]
    (out / "dev_before_after.md").write_text("\n".join(lines) + "\n", "utf-8")
    return doc


def main(argv: list[str] | None = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    if argv[:1] == ["retire"]:
        print(json.dumps(retire(), ensure_ascii=False))
        return 0
    if argv[:1] == ["before-after"]:
        before_after()
        print(f"wrote {S6R_DIR / 'dev_before_after.json'} and .md")
        return 0
    ap = argparse.ArgumentParser(prog="python -m app.care.evaluate", description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--split", required=True, choices=("dev", "test"))
    ap.add_argument("--dataset", default=None, help="dataset directory (default: $CARE_DATASET or data/synthetic/v1)")
    ap.add_argument("--evaluation-id", default=None, help="default: s6-care-<split>-0001")
    ap.add_argument("--out-dir", default=str(EVAL_DIR))
    ap.add_argument("--manifest", default=None, help="default: slices/s6/eval/manifest_<split>[_NNNN].json")
    ap.add_argument("--write-manifest", action="store_true")
    a = ap.parse_args(argv)
    if a.dataset:
        os.environ["CARE_DATASET"] = a.dataset
    root = dataset.root()
    try:
        dataset.require_synthetic(root)  # int2: before anything is read, called or written
    except dataset.DatasetNotSynthetic:
        print(f"REFUSED: {root}/manifest.json does not declare data_class 'synthetic'; nothing written",
              file=sys.stderr)
        return 2
    if a.split == "test" and not _dataset_meta(root).get("heldout"):
        print(f"REFUSED: the test split of {root} is retired ({DECISION}: {DECISION_TITLE}); "
              f"{RETIRED_ID} is '{RETIRED_LABEL}'. Use --dataset data/synthetic/s6r-heldout", file=sys.stderr)
        return 2
    eid = a.evaluation_id or f"s6-care-{a.split}-0001"
    out = Path(a.out_dir)
    p = paths(a.split, eid, out)
    mpath = Path(a.manifest) if a.manifest else paths(a.split, eid)["manifest"]
    if a.write_manifest:
        mpath.write_text(json.dumps(manifest(a.split, eid), indent=2, ensure_ascii=False) + "\n", "utf-8")
        print(f"wrote {mpath}")
        return 0
    m = json.loads(mpath.read_text("utf-8"))
    tree = _dataset_meta(root)["tree_sha256"]
    if m["dataset"]["version"] != tree or m["evaluation_id"] != eid:
        print(f"REFUSED: dataset tree_sha256 {tree} / evaluation id {eid} != manifest {m['dataset']['version']} / "
              f"{m['evaluation_id']}; run `make data` at the manifest's seed", file=sys.stderr)
        return 2
    preds, cmps, summary = records(a.split)
    summary = {"evaluation_id": eid, **summary}
    out.mkdir(parents=True, exist_ok=True)
    p["predictions"].write_bytes(_dump_jsonl(preds))
    p["comparator"].write_bytes(_dump_jsonl(cmps))
    p["summary"].write_text(json.dumps(summary, indent=2, ensure_ascii=False) + "\n", "utf-8")
    print(json.dumps(summary, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
