"""Frozen i2 protocol: metrics, populations, comparator, thresholds and manifests ``i2-cg-vs-sp-{dev,test}-v1``.

Fixed by rule before any result: a per-rule recall metric exists when its gold population on the split is
non-empty (RF-NEWS-AGG5 is UNMAPPABLE and is reported as null in the summary). Hash bindings (dataset tree, splits,
mapping, i2 adapter code, system code, handler versions) sit in ``$comment`` after the prefix ``i2-hashes ``; a run
refuses when any differs. Research prototype - not for clinical use.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

from eval.adapters import hashes, mapping
from eval.adapters.gold import load_split_gold, split_patients
from . import arms
from .score import gold_tasks

N_BOOT = 2000
SEED = 20260926
SPLITS = ("dev", "test")
ROOT = Path(__file__).resolve().parents[1]
I2_DIR = Path(__file__).resolve().parent
MANIFEST_DIR = ROOT / "eval" / "manifests" / "i2"
DATASET_NAME = "s1r-synthetic"
HASH_PREFIX = "i2-hashes "
COMMENT = ("Slice i2 manifest: Case Graph vs single prompt (System Evaluation on synthetic data — not clinical "
           "performance). Hash bindings follow as canonical JSON after the prefix 'i2-hashes '. ")
ITEM = "Case Graph"
# System code under test: a frozen run refuses if any of it changed after the freeze.
SYSTEM_GLOBS = ("casegraph/*.py", "casegraph/sources/*.py", "casegraph/config/*.json", "backend/app/triage/**/*.py",
                "backend/app/triage/**/*.json", "backend/app/voice/**/*.py", "backend/app/voice/**/*.json",
                "backend/app/gateway/**/*.py")


def _m(mid: str, task: str, name: str, params: dict[str, Any], primary: bool = False) -> dict[str, Any]:
    return {"id": mid, "item": ITEM, "task": task, "name": name, "params": params, "primary": primary}


def metrics(tasks: set[str]) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    spec = [
        _m("dept_top1", "dept", "topk_accuracy", {"k": 1, "estimand": "top-1 in E over evaluable DPs with a "
                                                  "mappable gold; an abstention counts as wrong"}, True),
        _m("dept_top3", "dept", "topk_accuracy", {"k": 3, "estimand": "top-3 in E, same population"}),
        _m("coverage", "abstention", "coverage", {"estimand": "answered share of the dept population plus the "
                                                  "NOT_EVALUABLE DPs"}),
        _m("selective_top1", "abstention", "selective_accuracy",
           {"estimand": "top-1 among answered DPs; answering a NOT_EVALUABLE DP is wrong"}),
        _m("calls_per_dp", "calls", "latency_summary", {"field": "n_calls", "stat": "mean",
                                                        "estimand": "mean gateway calls per DP"}),
    ]
    for t in sorted(x for x in tasks if x.startswith("rf_rule_RF-")):
        spec.append(_m(t, t, "accuracy", {"estimand": f"Arm A recall of {t.removeprefix('rf_rule_')}: gold DPs "
                                                      "where a mapped S4 rule fired"}))
    thresholds = [{"metric": f"rf_rule_{r}", "op": ">=", "value": 1.0, "rule": "point"}
                  for r in mapping.TEXT_RULES_S1R if f"rf_rule_{r}" in tasks]
    return spec, thresholds


def comparators() -> list[dict[str, Any]]:
    return [{"name": arms.ARM_B, "tasks": ["dept", "abstention", "calls"],
             "description": "Arm B: one gateway call per DP (casegraph.single_prompt.v1) over the whole serialized "
                            "snapshot; same registered handler versions; without the graph-only steps (Red-flag node, required-input "
                            "gate, freshness check, checkpoint), so it emits no screening output by design"}]


def system_sha256(root: Path = ROOT) -> str:
    h = hashlib.sha256()
    files = sorted({p for g in SYSTEM_GLOBS for p in root.glob(g) if p.is_file() and "__pycache__" not in p.parts})
    for p in files:
        h.update(p.relative_to(root).as_posix().encode() + b"\0" + p.read_bytes() + b"\0")
    return h.hexdigest()


def adapters_sha256() -> str:
    h = hashlib.sha256()
    for p in sorted(I2_DIR.rglob("*.py")):
        if "__pycache__" in p.parts or "tests" in p.relative_to(I2_DIR).parts:
            continue
        h.update(p.relative_to(I2_DIR).as_posix().encode() + b"\0" + p.read_bytes() + b"\0")
    return h.hexdigest()


def current_hashes(dataset: Path) -> dict[str, Any]:
    tree, errors = hashes.dataset_tree_sha256(dataset)
    return {
        "dataset_tree_sha256": tree if not errors else f"INVALID:{tree}",
        "split_sha256": hashes.split_sha256(dataset),
        "mapping_sha256": hashes.mapping_sha256(),
        "i2_adapters_sha256": adapters_sha256(),
        "system_sha256": system_sha256(),
        "handler_versions": arms.handler_versions(),
    }


def hash_comment(h: dict[str, Any]) -> str:
    return COMMENT + HASH_PREFIX + json.dumps(h, sort_keys=True, separators=(",", ":"))


def parse_hashes(m: dict[str, Any]) -> dict[str, Any]:
    c = m.get("$comment", "")
    if HASH_PREFIX not in c:
        raise ValueError(f"{m.get('evaluation_id')}: manifest has no i2 hash binding")
    return json.loads(c.rsplit(HASH_PREFIX, 1)[1])


def hash_mismatches(m: dict[str, Any], dataset: Path) -> list[str]:
    bound, now = parse_hashes(m), current_hashes(dataset)
    return sorted(k for k in now if bound.get(k) != now[k])


def evaluation_id(split: str) -> str:
    return f"i2-cg-vs-sp-{split}-v1"


def manifest_path(manifest_dir: Path, split: str) -> Path:
    return Path(manifest_dir) / f"{evaluation_id(split)}.json"


def build_manifest(split: str, dataset: Path, n_boot: int = N_BOOT) -> dict[str, Any]:
    gold = load_split_gold(dataset, split)
    members = sorted({(t, g["patient_ref"]) for g in gold.values() for t, _ in gold_tasks(g)})
    tasks = {t for t, _ in members}
    spec, thresholds = metrics(tasks)
    plist = split_patients(dataset, split)
    manifest_json = json.loads((Path(dataset) / "manifest.json").read_text(encoding="utf-8"))
    tree = hashes.dataset_tree_sha256(dataset)[0]
    return {
        "$comment": hash_comment(current_hashes(dataset)),
        "manifest_version": "1.0",
        "evaluation_id": evaluation_id(split),
        "slice": "i2",
        "dataset": {"name": DATASET_NAME, "version": f"s1r-{manifest_json.get('generator_version')}+tree:{tree}",
                    "data_class": manifest_json["data_class"]},
        "split": split,
        "split_version": hashes.split_sha256(dataset),
        "split_patient_list": plist,
        "task_patient_lists": {t: sorted({p for tt, p in members if tt == t}) for t in sorted(tasks)},
        "metrics": spec,
        "comparators": comparators(),
        "thresholds": thresholds,
        "bootstrap": {"n_boot": n_boot, "seed": SEED, "ci_level": 0.95, "method": "percentile"},
        "expert_review": {"done": False, "n_reviewers": 0},
    }


def write_manifest(path: Path, m: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(m, indent=1, ensure_ascii=False, sort_keys=False) + "\n", encoding="utf-8")
