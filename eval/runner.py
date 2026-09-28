"""Evaluation runner (slices s8, s8r). Research prototype - not for clinical use.

``run()`` scores prediction records against a manifest, computes patient-level bootstrap CIs
(paired for comparators), evaluates predeclared thresholds and writes results.json/.md/.html.
It refuses - exit 2, nothing written, no ledger line - when the ledger fails verification; on the
test split unless the manifest is frozen, unchanged since freezing, every patient is in
``split_patient_list`` and no different inputs were already recorded for the same ``evaluation_id``;
for real data (mimic/hospital) on test unless both ledgers are committed in git; and whenever a
listed patient has no predictions for a task with a non-abstention metric (split coverage, s8r).
For abstention-only tasks a missing listed patient is counted as abstain.
"""

from __future__ import annotations

import json
import os
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

import numpy as np

from . import __version__
from .bootstrap import RatioStat, cluster_bootstrap, paired_cluster_bootstrap
from .jsonschema_lite import validate
from .errors import LedgerIntegrityError, RunRefused
from .jsonio import loads_strict
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
from .metrics import MissingPredictionError, Undefined, exact_binomial_ci
from .registry import ABSTENTION_AWARE, population_for, prepare
from .report import labels_for, render_html, render_md

RESULTS_SCHEMA = PKG_DIR / "schemas" / "results.schema.json"
OUTPUT_FILES = ("results.json", "results.md", "results.html")
KEY_FIELDS = ("patient_id", "decision_point_id", "task")
MISSING_DP = "__missing__"
REAL_DATA = ("mimic", "hospital")
IMPUTATION_UNIT = "1 decision point per missing patient"
IMPUTATION_RULE = (
    "abstention-only tasks: a listed patient absent from every arm gets one decision point "
    f"{MISSING_DP!r} (y_pred=null) in every arm; any (patient, decision point) key present in one arm "
    "but absent from another is imputed as abstain (y_pred=null) where absent"
)


class InvalidManifest(RunRefused, ManifestError):
    """The manifest is invalid: the run is refused and the CLI exits 3 (invalid input)."""


def load_jsonl(path: str | os.PathLike[str]) -> tuple[list[dict[str, Any]], str]:
    """Strict JSONL parse. NaN/Infinity/overflow -> ``NonFiniteValueError`` naming the file and line."""
    raw = Path(path).read_bytes()
    name = Path(path).name
    rows = []
    for n, line in enumerate(raw.decode("utf-8").splitlines(), 1):
        if not line.strip():
            continue
        r = loads_strict(line, name, n)
        if not isinstance(r, dict):
            raise ValueError(f"{name} line {n}: not a JSON object")
        missing = [k for k in KEY_FIELDS if not isinstance(r.get(k), str) or not r[k]]
        if missing:
            raise ValueError(f"{name} line {n}: missing/invalid {missing}")
        if "imputed_missing" in r or r["decision_point_id"] == MISSING_DP:
            raise ValueError(f"{name} line {n}: 'imputed_missing' and decision_point_id {MISSING_DP!r} are "
                             "reserved for runner imputation")
        rows.append(r)
    return rows, sha256_bytes(raw)


def _examples(items: Sequence[Any], m: Mapping[str, Any]) -> str:
    """Up to 3 example IDs/keys for an error message - only for synthetic data (never real patient IDs)."""
    return f", e.g. {list(items)[:3]}" if m["dataset"]["data_class"] == "synthetic" else ""


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
        raise InvalidManifest("invalid manifest:\n  " + "\n  ".join(errors))
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
            raise RunRefused(f"{len(foreign)} patient(s) not in split_patient_list{_examples(foreign, m)}")
    if m["split"] == "test":
        for e in ledger.runs(m["evaluation_id"]):
            if (e["predictions_sha256"], e.get("comparator_sha256")) != (pred_sha, cmp_sha):
                raise RunRefused(
                    f"a test result was already recorded for {m['evaluation_id']!r} with different inputs; "
                    "resubmission to the test split is not allowed"
                )
    if m["split"] == "test" and m["dataset"]["data_class"] in REAL_DATA:
        ledger.require_committed()
    return bool(frozen)


# ---------------------------------------------------------------- split coverage (s8r)


def _abstention_only(m: dict[str, Any], task: str) -> bool:
    return all(x["name"] in ABSTENTION_AWARE for x in m["metrics"] if x["task"] == task)


def _coverage_units(m: dict[str, Any]) -> list[tuple[str, str | None, list[str] | None]]:
    """(task, population, listed patients) per task and per declared task population list."""
    plist = m.get("split_patient_list")
    tl = m.get("task_patient_lists") or {}
    tasks = list(dict.fromkeys(x["task"] for x in m["metrics"]))
    units: list[tuple[str, str | None, list[str] | None]] = []
    for task in tasks:
        pop_keys = sorted(k for k in tl if k.startswith(task + ":"))
        if plist is None:
            units.append((task, None, None))
            continue
        if task in tl:
            chosen = set(tl[task])
        elif pop_keys:
            chosen = set().union(*(tl[k] for k in pop_keys))
        else:
            chosen = set(plist)
        units.append((task, None, [p for p in plist if p in chosen]))
        for k in pop_keys:
            units.append((task, k.partition(":")[2], [p for p in plist if p in set(tl[k])]))
    return units


def _arms(m: dict[str, Any], task: str, rows: list[dict[str, Any]], cmp_rows: list[dict[str, Any]]):
    """[(arm label, comparator name or None, rows of the task)] - system first, then declared comparators."""
    arms = [("system", None, [r for r in rows if r["task"] == task])]
    for c in m["comparators"]:
        if task in c["tasks"]:
            arms.append((f"comparator:{c['name']}", c["name"],
                         [r for r in cmp_rows if r.get("comparator") == c["name"] and r["task"] == task]))
    return arms


def split_coverage(m: dict[str, Any], rows: list[dict[str, Any]], cmp_rows: list[dict[str, Any]]
                   ) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]]]:
    """Check that every listed patient has predictions in every provided arm.

    Returns ``(split_coverage entries, rows + imputed, cmp_rows + imputed)``. Raises ``RunRefused`` when a
    listed patient is missing for a task with any non-abstention metric (or a task-listed task has rows for
    patients outside its list). Abstention-only tasks count missing patients / keys as abstain.
    """
    synthetic = m["dataset"]["data_class"] == "synthetic"
    entries: list[dict[str, Any]] = []
    failures: list[str] = []
    new_rows, new_cmp = list(rows), list(cmp_rows)
    has_task_list = set(m.get("task_patient_lists") or {})
    for task, pop, listed in _coverage_units(m):
        abst = _abstention_only(m, task)
        arm_info = []
        imputed_by_arm: dict[str, int] = {}
        arms = _arms(m, task, rows, cmp_rows)
        provided = [a for a in arms if a[0] == "system" or a[2]]
        if pop is not None:
            arms = [(lab, name, [r for r in rs if r.get("population") == pop]) for lab, name, rs in arms]
            provided = [(lab, name, [r for r in rs if r.get("population") == pop]) for lab, name, rs in provided]
        if abst and pop is None:
            universe = listed if listed is not None else list(dict.fromkeys(
                r["patient_id"] for _, _, rs in provided for r in rs))
            for p in universe:
                keys = {lab: {r["decision_point_id"] for r in rs if r["patient_id"] == p} for lab, _, rs in provided}
                union = set().union(*keys.values()) or {MISSING_DP}
                for lab, name, _ in provided:
                    for dp in sorted(union - keys[lab]):
                        imp = {"patient_id": p, "decision_point_id": dp, "task": task, "y_pred": None,
                               "imputed_missing": True}
                        if name is None:
                            new_rows.append(imp)
                        else:
                            new_cmp.append({**imp, "comparator": name})
                        imputed_by_arm[lab] = imputed_by_arm.get(lab, 0) + 1
        for lab, name, rs in arms:
            predicted = {r["patient_id"] for r in rs}
            is_provided = lab == "system" or any(a[0] == lab for a in provided)
            if listed is None:
                info = {"arm": lab, "status": "provided" if is_provided else "not provided",
                        "n_predicted": len(predicted), "n_missing": None,
                        "n_imputed_abstain_decision_points": imputed_by_arm.get(lab, 0)}
                arm_info.append(info)
                continue
            missing = [p for p in listed if p not in predicted]
            outside = sorted(predicted - set(listed))
            key = task if pop is None else f"{task}:{pop}"
            if outside and (key in has_task_list or pop is not None):
                failures.append(f"task={task} population={pop} arm={lab}: {len(outside)} predicted patient(s) are "
                                f"not on the frozen task patient list"
                                + (f", e.g. {outside[:3]}" if synthetic else ""))
            if missing and is_provided and not abst:
                failures.append(f"task={task} population={pop} arm={lab} n_listed={len(listed)} "
                                f"n_predicted={len(listed) - len(missing)} n_missing={len(missing)}"
                                + (f" e.g. {missing[:3]}" if synthetic else ""))
            arm_info.append({"arm": lab, "status": "provided" if is_provided else "not provided",
                             "n_predicted": len(listed) - len(missing), "n_missing": len(missing),
                             "n_imputed_abstain_decision_points": imputed_by_arm.get(lab, 0)})
        sys_arm = arm_info[0]
        n_imp = sum(imputed_by_arm.values())
        entry = {
            "task": task,
            "population": pop,
            "n_listed": None if listed is None else len(listed),
            "n_predicted": sys_arm["n_predicted"],
            "n_missing": sys_arm["n_missing"],
            "missing_policy": ("not_checked" if listed is None
                               else "counted_as_abstain" if n_imp else "complete"),
            "n_imputed_abstain_decision_points": sys_arm["n_imputed_abstain_decision_points"],
            "imputation_unit": IMPUTATION_UNIT,
            "arms": arm_info,
        }
        if abst:
            entry["imputation_rule"] = IMPUTATION_RULE
        if listed is None:
            entry["reason"] = "no split_patient_list (exploratory run): the listed set is unknown, omission not checked"
        entries.append(entry)
    if failures:
        raise RunRefused(
            "split coverage: listed patient(s) have no predictions for a task with a non-abstention metric; "
            "they cannot be dropped or counted as abstain, so the run is refused\n  " + "\n  ".join(failures)
        )
    return entries, new_rows, new_cmp


def _threshold(row: dict[str, Any], th: dict[str, Any]) -> dict[str, Any]:
    v = {"point": row["point"], "ci_lower": row["ci_low"], "ci_upper": row["ci_high"]}[th["rule"]]
    ops = {">=": np.greater_equal, ">": np.greater, "<=": np.less_equal, "<": np.less}
    status = "undefined" if v is None else ("met" if bool(ops[th["op"]](v, th["value"])) else "not met")
    return {"op": th["op"], "value": th["value"], "rule": th["rule"], "compared_value": v, "status": status}


EXACT_CI_RULE = "patient_all_success"


def exact_interval(spec: dict[str, Any], stat: Any, ids: Sequence[str], res: dict[str, Any],
                   ci_level: float) -> dict[str, Any] | None:
    """Clopper-Pearson interval next to a zero-width or unstable bootstrap CI (slice s6, opt-in).

    Declared per metric with ``params.exact_ci = "patient_all_success"``: computed at patient level, where a
    patient succeeds only if every eligible decision point (den > 0) succeeds. Conservative; labelled so.
    """
    if spec["params"].get("exact_ci") != EXACT_CI_RULE or not isinstance(stat, RatioStat) or res["point"] is None:
        return None
    zero_width = res["ci_low"] is not None and res["ci_low"] == res["ci_high"]
    if not (zero_width or res["unstable"]):
        return None
    num: dict[str, float] = {}
    den: dict[str, float] = {}
    for pid, a, b in zip(ids, stat.num, stat.den):
        if not (0 <= a <= b <= 1):
            raise ValueError(f"{spec['id']}: exact_ci needs binary per-decision-point outcomes")
        num[pid] = num.get(pid, 0.0) + float(a)
        den[pid] = den.get(pid, 0.0) + float(b)
    eligible = [p for p in den if den[p] > 0]
    x = sum(1 for p in eligible if num[p] == den[p])
    ci = exact_binomial_ci(x, len(eligible), ci_level)
    return {
        "method": "clopper_pearson",
        "unit": "patient (success only if all eligible decision points succeed; conservative)",
        "trigger": "bootstrap CI has zero width" if zero_width else "bootstrap CI unstable (>1% degenerate)",
        "x": x,
        "n": len(eligible),
        "ci_level": ci_level,
        "ci_low": None if isinstance(ci, Undefined) else ci[0],
        "ci_high": None if isinstance(ci, Undefined) else ci[1],
    }


def scored_counts(stat: Any, ids: Sequence[str]) -> dict[str, int]:
    """Patients / decision points that enter the metric denominator (den > 0; answered rows for abstention-aware
    metrics). ``n_patients`` / ``n_decision_points`` stay the population denominators (s6, additive)."""
    if not isinstance(stat, RatioStat):
        return {}
    keep = [p for p, d in zip(ids, stat.den) if d > 0]
    return {"n_patients_scored": len(set(keep)), "n_decision_points_scored": len(keep)}


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
                    f"({len(missing)} missing{_examples(missing, m)}; {len(extra_k)} extra{_examples(extra_k, m)}); "
                    "rows are never dropped"
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
               "params": spec["params"], "primary": spec["primary"], **res,
               **scored_counts(prep.stat, ids), "details": prep.details}
        exact = exact_interval(spec, prep.stat, ids, res, b["ci_level"])
        if exact is not None:
            row["exact_ci"] = exact
        comps = []
        for name, ctasks in declared.items():
            if spec["task"] not in ctasks:
                continue
            crs = cmp_groups.get((name, spec["task"]))
            if crs is None:
                comps.append({"comparator": name, "status": "not provided", "comparator_point": None, "diff": None})
                continue
            crs = restrict(spec, crs)
            cids = [r["patient_id"] for r in crs]
            cprep = prepare(spec["name"], crs, spec["params"])
            cres = cluster_bootstrap(cids, cprep.stat, **bkw).to_dict()
            diff = paired_cluster_bootstrap(ids, prep.stat, cids, cprep.stat, **bkw)
            d = diff.to_dict()
            comp = {
                "comparator": name,
                "status": "computed",
                "comparator_point": cres["point"],
                "comparator_ci_low": cres["ci_low"],
                "comparator_ci_high": cres["ci_high"],
                "comparator_reason": cres["reason"],
                "comparator_unstable": cres["unstable"],
                "comparator_n_degenerate": cres["n_degenerate"],
                "comparator_n_patients": cres["n_patients"],
                "comparator_n_decision_points": cres["n_decision_points"],
                **{f"comparator_{k}": v for k, v in scored_counts(cprep.stat, cids).items()},
                "diff": {k: d[k] for k in ("point", "ci_low", "ci_high", "n_degenerate", "unstable", "reason")},
            }
            cexact = exact_interval(spec, cprep.stat, cids, cres, b["ci_level"])
            if cexact is not None:
                comp["comparator_exact_ci"] = cexact
            comps.append(comp)
        row["comparisons"] = comps
        row["thresholds"] = [_threshold(row, t) for t in m["thresholds"] if t["metric"] == spec["id"]]
        out.append(row)
    return out


def build_results(m: dict[str, Any], digest: str, rows, cmp_rows, pred_sha: str, cmp_sha: str | None,
                  frozen: bool, frozen_entry_hash: str | None = None) -> dict[str, Any]:
    stamp = None if frozen else f"UNFROZEN - exploratory ({m['split']} split)"
    b = m["bootstrap"]
    coverage, eval_rows, eval_cmp = split_coverage(m, rows, cmp_rows)
    results = {
        "schema_version": "1.1",
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
        "frozen_entry_hash": frozen_entry_hash,
        "split_coverage": coverage,
        "rows": evaluate(m, eval_rows, eval_cmp),
    }
    errors = validate(results, json.loads(RESULTS_SCHEMA.read_text(encoding="utf-8")))
    for c in coverage:
        for a in [c, *c["arms"]]:
            if c["n_listed"] is not None and c["n_listed"] != a["n_predicted"] + a["n_missing"]:
                errors.append(f"$.split_coverage[{c['task']}]: n_listed != n_predicted + n_missing")
    if errors:
        raise AssertionError("results do not match results.schema.json:\n  " + "\n  ".join(errors))
    return results


def results_json_bytes(results: dict[str, Any]) -> bytes:
    """The exact results.json bytes whose sha256 is the ledger's ``results_sha256``."""
    return (json.dumps(results, sort_keys=True, indent=2, ensure_ascii=False, allow_nan=False) + "\n").encode("utf-8")


def render_all(results: dict[str, Any]) -> dict[str, bytes]:
    return {
        "results.json": results_json_bytes(results),
        "results.md": render_md(results).encode("utf-8"),
        "results.html": render_html(results).encode("utf-8"),
    }


def rerender_of(m: dict[str, Any], ledger: Ledger, digest: str, pred_sha: str, cmp_sha: str | None
                ) -> dict[str, Any] | None:
    """Slice s6r: on the test split, identical manifest + predictions + comparator hashes to an existing run line
    make a re-render (report only, no second result). Dev keeps the s8 rule (every run appends a line)."""
    if m["split"] != "test":
        return None
    same = [e for e in ledger.runs(m["evaluation_id"])
            if (e["manifest_sha256"], e["predictions_sha256"], e.get("comparator_sha256")) == (digest, pred_sha, cmp_sha)]
    return same[0] if same else None


def run(manifest_path: str | os.PathLike[str], predictions_path: str | os.PathLike[str],
        out_dir: str | os.PathLike[str], comparator_path: str | os.PathLike[str] | None = None,
        ledger: Ledger | None = None) -> dict[str, Any]:
    ledger = ledger or Ledger()
    ledger.verify()  # LedgerIntegrityError (exit 2) before anything is read or written
    try:
        m = load_manifest(manifest_path)
    except (OSError, json.JSONDecodeError) as e:
        raise RunRefused(f"cannot read manifest: {e}") from e
    digest = manifest_sha256(m)
    rows, pred_sha = load_jsonl(predictions_path)
    cmp_rows, cmp_sha = load_jsonl(comparator_path) if comparator_path else ([], None)
    frozen = _refusal_checks(m, digest, rows, cmp_rows, pred_sha, cmp_sha, ledger)
    fe = [e for e in ledger.frozen(m["evaluation_id"]) if e["sha256"] == digest]
    results = build_results(m, digest, rows, cmp_rows, pred_sha, cmp_sha, frozen,
                            fe[0]["entry_hash"] if fe else None)
    files = render_all(results)

    out = Path(out_dir)
    for name, data in files.items():
        p = out / name
        if p.exists() and p.read_bytes() != data:
            raise RunRefused(f"{p} exists with different content; results are never overwritten")
    out.mkdir(parents=True, exist_ok=True)
    for name, data in files.items():
        (out / name).write_bytes(data)
    prior = rerender_of(m, ledger, digest, pred_sha, cmp_sha)
    if prior is not None:
        print(f"re-render of run seq {prior['seq']}; no ledger line appended")
        return results
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


__all__ = ["RunRefused", "LedgerIntegrityError", "run", "load_jsonl", "evaluate", "build_results", "render_all",
           "split_coverage", "ManifestError", "canonical_bytes"]
