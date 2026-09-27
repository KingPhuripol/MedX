"""System Evaluation of slice s6 on synthetic data (not clinical performance). Evaluation harness, not the engine.

This is the only module under ``app/care`` that reads gold labels: it joins engine outputs (computed from
``inputs/<split>/<case>/snapshot_T*.json`` only) with ``gold/<split>/*.json`` to write eval-harness records.

    python -m app.care.evaluate --split dev|test                  # predictions + comparator JSONL
    python -m app.care.evaluate --split dev|test --write-manifest # predeclared manifest (from gold, not predictions)

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
from collections import Counter
from pathlib import Path
from typing import Any

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
    prior = train_prior(root)
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


def manifest(split: str) -> dict[str, Any]:
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
        "evaluation_id": f"s6-care-{split}-0001",
        "slice": "s6",
        "dataset": {"name": f"s1r-synthetic-v{meta['generator_version']}", "version": meta["tree_sha256"],
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


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="python -m app.care.evaluate", description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--split", required=True, choices=("dev", "test"))
    ap.add_argument("--out-dir", default=str(EVAL_DIR))
    ap.add_argument("--manifest", default=None, help="default: slices/s6/eval/manifest_<split>.json")
    ap.add_argument("--write-manifest", action="store_true")
    a = ap.parse_args(argv)
    out = Path(a.out_dir)
    out.mkdir(parents=True, exist_ok=True)
    mpath = Path(a.manifest) if a.manifest else EVAL_DIR / f"manifest_{a.split}.json"
    if a.write_manifest:
        p = mpath
        p.write_text(json.dumps(manifest(a.split), indent=2, ensure_ascii=False) + "\n", "utf-8")
        print(f"wrote {p}")
        return 0
    m = json.loads(mpath.read_text("utf-8"))
    tree = _dataset_meta(dataset.root())["tree_sha256"]
    if m["dataset"]["version"] != tree:
        print(f"REFUSED: dataset tree_sha256 {tree} != manifest dataset.version {m['dataset']['version']}; "
              "run `make data` at the default seed")
        return 2
    preds, cmps, summary = records(a.split)
    (out / f"predictions_{a.split}.jsonl").write_bytes(_dump_jsonl(preds))
    (out / f"comparator_{a.split}.jsonl").write_bytes(_dump_jsonl(cmps))
    (out / f"summary_{a.split}.json").write_text(json.dumps(summary, indent=2, ensure_ascii=False) + "\n", "utf-8")
    print(json.dumps(summary, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
