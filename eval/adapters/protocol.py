"""Frozen e1 protocol: metrics, populations, comparators, thresholds and manifests (slice e1).

Research prototype - not for clinical use. The metric set per split is fixed by rule before any result:
a metric exists when its gold population is non-empty; otherwise the summary reports it as null with a reason.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from . import hashes
from .gold import load_split_gold, split_patients
from .score import gold_tasks

N_BOOT = 2000
SEED = 20260926
MANIFEST_DIR = Path(__file__).resolve().parents[1] / "manifests" / "e1"
DATASET_NAME = "s1r-synthetic"
GENERATOR_VERSION = "1.1.1"
HASH_PREFIX = "e1-hashes "
COMMENT = ("Slice e1 frozen manifest (System Evaluation on synthetic data - not clinical performance). "
           "Hash bindings follow as canonical JSON after the prefix 'e1-hashes '. ")

VOICE_FIELDS = ("chief_complaint", "onset_duration", "allergy_status")
_ABBR = {"chief_complaint": "cc", "onset_duration": "dur", "allergy_status": "allergy"}


def _m(mid: str, item: str, task: str, name: str, params: dict[str, Any], primary: bool = False) -> dict[str, Any]:
    return {"id": mid, "item": item, "task": task, "name": name, "params": params, "primary": primary}


def voice_metrics() -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    metrics, thresholds = [], []
    for f in VOICE_FIELDS:
        task = "voice_cc" if f == "chief_complaint" else "voice_intake"
        for comp in ("precision", "recall", "f1"):
            mid = f"voice_{_ABBR[f]}_{comp}"
            metrics.append(_m(mid, "Voice Agent", task, "field_prf",
                              {"field": f, "fields": list(VOICE_FIELDS), "component": comp}, comp == "f1"))
        thresholds.append({"metric": f"voice_{_ABBR[f]}_f1", "op": ">=", "value": 0.8, "rule": "point"})
    for comp in ("precision", "recall", "f1"):
        metrics.append(_m(f"voice_micro_{comp}", "Voice Agent", "voice_intake", "field_prf",
                          {"fields": list(VOICE_FIELDS), "component": comp}))
    metrics.append(_m("voice_allergy_false_none_rate", "Voice Agent", "voice_allergy_false_none", "accuracy",
                      {"estimand": "false-none rate: share of cases with gold allergy known or MISSING where S3 "
                                   "records KNOWN none"}, True))
    thresholds.append({"metric": "voice_allergy_false_none_rate", "op": "<=", "value": 0, "rule": "point"})
    return metrics, thresholds


def triage_metrics(tasks: set[str]) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    D, A = "Department suggestion", "Abstention"
    spec = [
        _m("rf_case_recall", D, "rf_case_recall", "accuracy",
           {"estimand": "case-level red-flag recall: gold-positive DPs with >=1 S4 alert of any rule"}, True),
        _m("rf_rule_recall", D, "rf_rule_recall", "set_prf",
           {"component": "recall", "estimand": "rule-level recall pooled over gold (DP, rule) pairs; UNMAPPABLE "
                                               "pairs count as missed"}, True),
        _m("rf_rule_recall_mappable", D, "rf_rule_recall_mappable", "set_prf",
           {"component": "recall", "estimand": "rule-level recall over mappable gold (DP, rule) pairs (secondary)"}),
    ]
    for t in sorted(x for x in tasks if x.startswith("rf_rule_RF-")):
        rule = t.removeprefix("rf_rule_")
        spec.append(_m(t, D, t, "accuracy", {"estimand": f"per-rule recall of {rule}: gold DPs where a mapped "
                                                           "S4 rule fired"}))
    spec += [
        _m("rf_fpr", D, "rf_fpr", "accuracy",
           {"estimand": "false-positive rate: gold-negative DPs with >=1 S4 alert of any rule"}),
        _m("rf_fpr_mapped", D, "rf_fpr_mapped", "accuracy",
           {"estimand": "false-positive rate counting only S4 rules mapped to the S1r registry (secondary)"}),
        _m("rf_text_t1_recall", D, "rf_text_t1_recall", "accuracy",
           {"estimand": "text red-flag recall at T1: any alert of RF-CHEST, RF-STROKE, RF-THUNDER, RF-ANAPH"}),
        _m("rf_text_t1_fpr", D, "rf_text_t1_fpr", "accuracy",
           {"estimand": "text red-flag false-positive rate at T1 (same alert set)"}),
        _m("dept_top1", D, "dept", "topk_accuracy", {"k": 1}, True),
        _m("dept_top3", D, "dept", "topk_accuracy", {"k": 3}, True),
        _m("abst_coverage", A, "abstention", "coverage", {}, True),
        _m("abst_selective_top1", A, "abstention", "selective_accuracy",
           {"estimand": "top-1 accuracy among answered DPs; answering a NOT_EVALUABLE DP is wrong"}, True),
        _m("abst_rate_not_evaluable", A, "abst_on_not_evaluable", "accuracy",
           {"estimand": "abstain rate on NOT_EVALUABLE DPs (secondary)"}),
        _m("abst_false_abstain_rate", A, "false_abstain", "accuracy",
           {"estimand": "false-abstain rate on the department population (secondary)"}),
        _m("abst_expected_action_agreement", A, "expected_action", "accuracy",
           {"estimand": "3-class expected_action agreement (suggest/abstain/escalate) over every DP (secondary)"}),
    ]
    metrics = [x for x in spec if x["task"] in tasks]
    thresholds = [{"metric": m, "op": ">=", "value": v, "rule": "point"}
                  for m, v in (("rf_case_recall", 1.0), ("rf_rule_recall", 1.0), ("dept_top3", 0.8))
                  if any(x["id"] == m for x in metrics)]
    return metrics, thresholds


def comparators(s_star: dict[str, Any], majority: dict[str, Any], tasks: set[str]) -> list[dict[str, Any]]:
    out = [
        {"name": "always_answer", "tasks": [t for t in ("dept", "abstention") if t in tasks],
         "description": "S4 baseline.rank (kw-1.0.0) on the same gateway inputs with no abstain gate; empty ranking "
                        f"falls back to the train-majority E code {majority['code']} (train gold only)"},
        {"name": "shortcut_s_star", "tasks": [t for t in ("rf_text_t1_recall", "rf_text_t1_fpr") if t in tasks],
         "description": f"S1r lexical shortcut: contains({s_star['s_star']!r}) in any T1 patient turn; s* selected "
                        f"on train only by max F1 (train F1={s_star['train']['f1']:.4f})"},
        {"name": "shortcut_tamtee", "tasks": [t for t in ("rf_text_t1_recall", "rf_text_t1_fpr") if t in tasks],
         "description": "fixed rule: contains('ทันที') in any T1 patient turn"},
    ]
    return [c for c in out if c["tasks"]]


def task_lists(memberships: list[tuple[str, str, str]], plist: list[str]) -> dict[str, list[str]]:
    """Gold-derived patient list per task from (task, decision_point_id, patient_id) memberships."""
    by: dict[str, set[str]] = {}
    for task, _, pid in memberships:
        by.setdefault(task, set()).add(pid)
    return {t: [p for p in plist if p in s] for t, s in sorted(by.items())}


def hash_comment(h: dict[str, Any]) -> str:
    return COMMENT + HASH_PREFIX + json.dumps(h, sort_keys=True, separators=(",", ":"))


def parse_hashes(m: dict[str, Any]) -> dict[str, Any]:
    c = m.get("$comment", "")
    i = c.rfind(HASH_PREFIX)
    if i < 0:
        raise ValueError(f"{m.get('evaluation_id')}: $comment has no e1 hash bindings")
    return json.loads(c[i + len(HASH_PREFIX):])


VOICE_TASKS = ("voice_intake", "voice_cc", "voice_allergy_false_none")


def memberships(dataset: Path, split: str) -> list[tuple[str, str, str]]:
    """(task, decision_point_id, patient_id) for every scored record of the split, from gold only."""
    out = []
    for cid, g in load_split_gold(dataset, split).items():
        out += [(t, did, g["patient_ref"]) for t, did in gold_tasks(cid, g)]
    return out


def build_manifest(kind: str, split: str, dataset: Path, members: list[tuple[str, str, str]],
                   s_star: dict[str, Any], majority: dict[str, Any], n_boot: int = N_BOOT) -> dict[str, Any]:
    h = hashes.current(dataset)
    plist = split_patients(dataset, split)
    members = [x for x in members if (x[0] in VOICE_TASKS) == (kind == "voice")]
    tasks = {x[0] for x in members}
    if kind == "voice":
        metrics, thresholds = voice_metrics()
        comps: list[dict[str, Any]] = []
    else:
        metrics, thresholds = triage_metrics(tasks)
        comps = comparators(s_star, majority, tasks)
    metrics = [x for x in metrics if x["task"] in tasks]
    thresholds = [t for t in thresholds if any(x["id"] == t["metric"] for x in metrics)]
    return {
        "$comment": hash_comment({**h, "generator_version": GENERATOR_VERSION, "s_star": s_star["s_star"],
                                  "always_answer_fallback": majority["code"]}),
        "manifest_version": "1.0",
        "evaluation_id": f"e1-{kind}-{split}-v1",
        "slice": "e1",
        "dataset": {"name": DATASET_NAME, "version": f"s1r-{GENERATOR_VERSION}+tree:{h['dataset_tree_sha256']}",
                    "data_class": "synthetic"},
        "split": split,
        "split_version": h["split_sha256"],
        "split_patient_list": plist,
        "task_patient_lists": task_lists(members, plist),
        "metrics": metrics,
        "comparators": comps,
        "thresholds": thresholds,
        "bootstrap": {"n_boot": n_boot, "seed": SEED, "ci_level": 0.95, "method": "percentile"},
        "expert_review": {"done": False, "n_reviewers": 0},
    }


def manifest_path(manifest_dir: Path, kind: str, split: str) -> Path:
    return Path(manifest_dir) / f"e1-{kind}-{split}-v1.json"


def write_manifest(path: Path, m: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(m, ensure_ascii=False, indent=1, sort_keys=False) + "\n", encoding="utf-8")


def hash_mismatches(m: dict[str, Any], dataset: Path) -> list[str]:
    """Names of bound hashes that differ from the current files (dataset, split, mapping, adapter)."""
    frozen = parse_hashes(m)
    cur = hashes.current(dataset)
    bad = [k for k in ("dataset_tree_sha256", "split_sha256", "mapping_sha256", "adapters_sha256")
           if frozen.get(k) != cur[k]]
    if m["dataset"]["version"] != f"s1r-{GENERATOR_VERSION}+tree:{cur['dataset_tree_sha256']}" \
            and "dataset_tree_sha256" not in bad:
        bad.append("dataset_tree_sha256")
    if m["split_version"] != cur["split_sha256"] and "split_sha256" not in bad:
        bad.append("split_sha256")
    return bad

