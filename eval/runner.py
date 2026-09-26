"""Evaluation runner (slice s8). Research prototype - not for clinical use.

``run()`` scores prediction records against a manifest, computes patient-level bootstrap CIs
(paired for comparators), evaluates predeclared thresholds and writes results.json/.md/.html.
On the test split it refuses - non-zero exit, nothing written - unless the manifest is frozen,
unchanged since freezing, every patient is in ``split_patient_list`` and no different inputs
were already recorded for the same ``evaluation_id``.
"""

from __future__ import annotations

import json
import os
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

import numpy as np

from . import __version__
from .bootstrap import cluster_bootstrap, paired_cluster_bootstrap
from .jsonschema_lite import validate
from .manifest import (
    PKG_DIR,
    Ledger,
    ManifestError,
    canonical_bytes,
    manifest_errors,
    manifest_sha256,
    load_manifest,
    sha256_bytes,
    utc_now,
)
from .metrics import MissingPredictionError
from .registry import population_for, prepare
from .report import labels_for, render_html, render_md

RESULTS_SCHEMA = PKG_DIR / "schemas" / "results.schema.json"
OUTPUT_FILES = ("results.json", "results.md", "results.html")
KEY_FIELDS = ("patient_id", "decision_point_id", "task")


class RunRefused(RuntimeError):
    """The run is not allowed; no results are written."""


def load_jsonl(path: str | os.PathLike[str]) -> tuple[list[dict[str, Any]], str]:
    raw = Path(path).read_bytes()
    rows = []
    for n, line in enumerate(raw.decode("utf-8").splitlines(), 1):
        if not line.strip():
            continue
        r = json.loads(line)
        missing = [k for k in KEY_FIELDS if not isinstance(r.get(k), str) or not r[k]]
        if missing:
            raise ValueError(f"{Path(path).name} line {n}: missing/invalid {missing}")
        rows.append(r)
    return rows, sha256_bytes(raw)


def _key(r: Mapping[str, Any]) -> tuple[str, str]:
    return (r["patient_id"], r["decision_point_id"])


def _by_task(rows: Sequence[dict[str, Any]], what: str) -> dict[str, list[dict[str, Any]]]:
    out: dict[str, list[dict[str, Any]]] = {}
    seen: set[tuple[str, ...]] = set()
    for r in rows:
        k = (r.get("comparator", ""), r["task"], *_key(r))
        if k in seen:
            raise ValueError(f"{what}: duplicate record {k}")
        seen.add(k)
        out.setdefault(r["task"], []).append(r)
    for v in out.values():
        v.sort(key=_key)
    return out


def _refusal_checks(m: dict[str, Any], digest: str, rows, cmp_rows, pred_sha: str, cmp_sha: str | None,
                    ledger: Ledger) -> bool:
    """Returns whether the manifest is frozen. Raises RunRefused."""
    errors = manifest_errors(m)
    if errors:
        raise RunRefused("invalid manifest:\n  " + "\n  ".join(errors))
    frozen = ledger.frozen(m["evaluation_id"])
    if frozen and not any(e["sha256"] == digest for e in frozen):
        raise RunRefused("manifest changed after freezing (hash mismatch); results would not be predeclared")
    if m["split"] == "test" and not frozen:
        raise RunRefused("test split requires a frozen manifest: run `python -m eval freeze <manifest>` first")
    plist = m.get("split_patient_list")
    if plist is not None:
        allowed = set(plist)
        foreign = sorted({r["patient_id"] for r in list(rows) + list(cmp_rows)} - allowed)
        if foreign:
            raise RunRefused(f"{len(foreign)} patient(s) not in split_patient_list, e.g. {foreign[:3]}")
    if m["split"] == "test":
        for e in ledger.runs(m["evaluation_id"]):
            if (e["predictions_sha256"], e.get("comparator_sha256")) != (pred_sha, cmp_sha):
                raise RunRefused(
                    f"a test result was already recorded for {m['evaluation_id']!r} with different inputs; "
                    "resubmission to the test split is not allowed"
                )
    return bool(frozen)


def _threshold(row: dict[str, Any], th: dict[str, Any]) -> dict[str, Any]:
    v = {"point": row["point"], "ci_lower": row["ci_low"], "ci_upper": row["ci_high"]}[th["rule"]]
    ops = {">=": np.greater_equal, ">": np.greater, "<=": np.less_equal, "<": np.less}
    status = "undefined" if v is None else ("met" if bool(ops[th["op"]](v, th["value"])) else "not met")
    return {"op": th["op"], "value": th["value"], "rule": th["rule"], "compared_value": v, "status": status}


def evaluate(m: dict[str, Any], rows: list[dict[str, Any]], cmp_rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    tasks = {x["task"] for x in m["metrics"]}
    sys_by_task = _by_task(rows, "predictions")
    extra = sorted(set(sys_by_task) - tasks)
    if extra:
        raise ValueError(f"predictions contain undeclared task(s) {extra}; ad-hoc rows are not evaluated")
    declared = {c["name"]: set(c["tasks"]) for c in m["comparators"]}
    cmp_groups: dict[tuple[str, str], list[dict[str, Any]]] = {}
    for r in cmp_rows:
        name = r.get("comparator")
        if name not in declared or r["task"] not in declared[name]:
            raise ValueError(f"comparator record for undeclared comparator/task {(name, r['task'])}")
    for name in declared:
        for task, rs in _by_task([r for r in cmp_rows if r["comparator"] == name], f"comparator {name}").items():
            sys_keys = [_key(r) for r in sys_by_task.get(task, [])]
            cmp_keys = [_key(r) for r in rs]
            if sys_keys != cmp_keys:
                missing = sorted(set(sys_keys) - set(cmp_keys))
                extra_k = sorted(set(cmp_keys) - set(sys_keys))
                raise MissingPredictionError(
                    f"comparator {name!r} task {task!r} does not cover the same decision points "
                    f"(missing {missing[:3]}, extra {extra_k[:3]}); rows are never dropped"
                )
            cmp_groups[(name, task)] = rs

    b = m["bootstrap"]
    bkw = dict(n_boot=b["n_boot"], seed=b["seed"], ci_level=b["ci_level"], method=b["method"])
    def restrict(spec: dict[str, Any], rs: list[dict[str, Any]]) -> list[dict[str, Any]]:
        pop, declared_pops = population_for(spec["name"], spec["params"])
        if pop is None:
            return rs
        bad = sorted({str(r.get("population")) for r in rs} - declared_pops)
        if bad:
            raise ValueError(f"{spec['id']}: undeclared population(s) {bad}; rows are never silently dropped")
        return [r for r in rs if r["population"] == pop]

    out = []
    for spec in m["metrics"]:
        task_rows = restrict(spec, sys_by_task.get(spec["task"], []))
        ids = [r["patient_id"] for r in task_rows]
        prep = prepare(spec["name"], task_rows, spec["params"])
        res = cluster_bootstrap(ids, prep.stat, **bkw).to_dict()
        row = {"metric_id": spec["id"], "item": spec["item"], "task": spec["task"], "metric": spec["name"],
               "params": spec["params"], "primary": spec["primary"], **res, "details": prep.details}
        comps = []
        for name, ctasks in declared.items():
            if spec["task"] not in ctasks:
                continue
            crs = cmp_groups.get((name, spec["task"]))
            if crs is None:
                comps.append({"comparator": name, "status": "not provided", "comparator_point": None, "diff": None})
                continue
            crs = restrict(spec, crs)
            cprep = prepare(spec["name"], crs, spec["params"])
            cres = cluster_bootstrap([r["patient_id"] for r in crs], cprep.stat, **bkw).to_dict()
            diff = paired_cluster_bootstrap(ids, prep.stat, [r["patient_id"] for r in crs], cprep.stat, **bkw)
            d = diff.to_dict()
            comps.append({
                "comparator": name,
                "status": "computed",
                "comparator_point": cres["point"],
                "comparator_ci_low": cres["ci_low"],
                "comparator_ci_high": cres["ci_high"],
                "comparator_reason": cres["reason"],
                "diff": {k: d[k] for k in ("point", "ci_low", "ci_high", "n_degenerate", "unstable", "reason")},
            })
        row["comparisons"] = comps
        row["thresholds"] = [_threshold(row, t) for t in m["thresholds"] if t["metric"] == spec["id"]]
        out.append(row)
    return out


def build_results(m: dict[str, Any], digest: str, rows, cmp_rows, pred_sha: str, cmp_sha: str | None,
                  frozen: bool) -> dict[str, Any]:
    stamp = None if frozen else f"UNFROZEN - exploratory ({m['split']} split)"
    b = m["bootstrap"]
    results = {
        "schema_version": "1.0",
        "evaluation_id": m["evaluation_id"],
        "slice": m["slice"],
        "split": m["split"],
        "split_version": m["split_version"],
        "dataset": m["dataset"],
        "frozen": frozen,
        "stamp": stamp,
        "manifest_sha256": digest,
        "predictions_sha256": pred_sha,
        "comparator_sha256": cmp_sha,
        "bootstrap": {"n_boot": b["n_boot"], "seed": b["seed"], "ci_level": b["ci_level"], "method": b["method"],
                      "unit": "patient", "rng": "numpy.random.Generator(PCG64(seed))"},
        "environment": {"numpy_version": np.__version__, "eval_version": __version__},
        "labels": labels_for(m),
        "expert_review": m["expert_review"],
        "n_patients": len({r["patient_id"] for r in rows}),
        "n_decision_points": len({_key(r) for r in rows}),
        "n_patients_in_split_list": len(m["split_patient_list"]) if m.get("split_patient_list") else None,
        "rows": evaluate(m, rows, cmp_rows),
    }
    errors = validate(results, json.loads(RESULTS_SCHEMA.read_text(encoding="utf-8")))
    if errors:
        raise AssertionError("results do not match results.schema.json:\n  " + "\n  ".join(errors))
    return results


def render_all(results: dict[str, Any]) -> dict[str, bytes]:
    js = json.dumps(results, sort_keys=True, indent=2, ensure_ascii=False, allow_nan=False) + "\n"
    return {
        "results.json": js.encode("utf-8"),
        "results.md": render_md(results).encode("utf-8"),
        "results.html": render_html(results).encode("utf-8"),
    }


def run(manifest_path: str | os.PathLike[str], predictions_path: str | os.PathLike[str],
        out_dir: str | os.PathLike[str], comparator_path: str | os.PathLike[str] | None = None,
        ledger: Ledger | None = None) -> dict[str, Any]:
    ledger = ledger or Ledger()
    try:
        m = load_manifest(manifest_path)
    except (OSError, json.JSONDecodeError) as e:
        raise RunRefused(f"cannot read manifest: {e}") from e
    digest = manifest_sha256(m)
    rows, pred_sha = load_jsonl(predictions_path)
    cmp_rows, cmp_sha = load_jsonl(comparator_path) if comparator_path else ([], None)
    frozen = _refusal_checks(m, digest, rows, cmp_rows, pred_sha, cmp_sha, ledger)
    results = build_results(m, digest, rows, cmp_rows, pred_sha, cmp_sha, frozen)
    files = render_all(results)

    out = Path(out_dir)
    for name, data in files.items():
        p = out / name
        if p.exists() and p.read_bytes() != data:
            raise RunRefused(f"{p} exists with different content; results are never overwritten")
    out.mkdir(parents=True, exist_ok=True)
    for name, data in files.items():
        (out / name).write_bytes(data)
    ledger.append_run({
        "evaluation_id": m["evaluation_id"],
        "split": m["split"],
        "frozen": frozen,
        "manifest_sha256": digest,
        "predictions_sha256": pred_sha,
        "comparator_sha256": cmp_sha,
        "results_sha256": sha256_bytes(files["results.json"]),
        "recorded_at": utc_now(),
    })
    return results


__all__ = ["RunRefused", "run", "load_jsonl", "evaluate", "build_results", "render_all", "ManifestError",
           "canonical_bytes"]
