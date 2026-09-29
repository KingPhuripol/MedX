"""Frozen evaluation manifest + hash-chained ledgers (slices s8, s8r). Research prototype - not for clinical use."""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

from .errors import LedgerIntegrityError, RunRefused
from .jsonio import canonical_bytes, load_json_file, sha256_bytes, utc_now
from .jsonschema_lite import validate
from .ledger_chain import DEFAULT_LEDGER_DIR, PKG_DIR, Ledger
from .registry import METRICS, population_for

SCHEMA_PATH = PKG_DIR / "schemas" / "eval_manifest.schema.json"


class ManifestError(ValueError):
    pass


def manifest_sha256(manifest: dict[str, Any]) -> str:
    return sha256_bytes(canonical_bytes(manifest))


def load_manifest(path: str | os.PathLike[str]) -> dict[str, Any]:
    """Strict parse: NaN / Infinity / overflowing floats raise ``NonFiniteValueError`` (file + line)."""
    return load_json_file(path)


def task_list_keys(m: dict[str, Any]) -> list[str]:
    return sorted((m.get("task_patient_lists") or {}).keys())


def manifest_errors(m: dict[str, Any]) -> list[str]:
    errors = validate(m, json.loads(SCHEMA_PATH.read_text(encoding="utf-8")))
    if errors:
        return errors
    if m["split"] == "test" and not m.get("split_patient_list"):
        errors.append("$.split_patient_list: required for the test split")
    ids = [x["id"] for x in m["metrics"]]
    if len(set(ids)) != len(ids):
        errors.append("$.metrics: metric ids must be unique")
    for x in m["metrics"]:
        if x["name"] not in METRICS:
            errors.append(f"$.metrics[{x['id']}]: unknown metric name {x['name']!r}")
    tasks = {x["task"] for x in m["metrics"]}
    names = [c["name"] for c in m["comparators"]]
    if len(set(names)) != len(names):
        errors.append("$.comparators: names must be unique")
    for c in m["comparators"]:
        for t in c["tasks"]:
            if t not in tasks:
                errors.append(f"$.comparators[{c['name']}]: task {t!r} has no metric")
    for t in m["thresholds"]:
        if t["metric"] not in ids:
            errors.append(f"$.thresholds: unknown metric id {t['metric']!r}")
    errors += _task_list_errors(m, tasks)
    return errors


def _task_list_errors(m: dict[str, Any], tasks: set[str]) -> list[str]:
    """``task_patient_lists``: keys ``<task>`` or ``<task>:<population>``; each list a subset of the split list."""
    tl = m.get("task_patient_lists")
    if tl is None:
        return []
    errors = []
    plist = m.get("split_patient_list")
    if plist is None:
        return ["$.task_patient_lists: requires split_patient_list (each list must be a subset of it)"]
    allowed = set(plist)
    for key, pids in sorted(tl.items()):
        task, _, pop = key.partition(":")
        if task not in tasks:
            errors.append(f"$.task_patient_lists[{key!r}]: unknown task {task!r} (no metric declares it)")
            continue
        if pop:
            pops = set()
            for x in m["metrics"]:
                if x["task"] == task:
                    pops |= population_for(x["name"], x["params"])[1]
            if pop not in pops:
                errors.append(f"$.task_patient_lists[{key!r}]: population {pop!r} is not declared by a metric "
                              f"of task {task!r} (declared: {sorted(pops)})")
        outside = [p for p in pids if p not in allowed]
        if outside:
            errors.append(f"$.task_patient_lists[{key!r}]: {len(outside)} patient(s) not in split_patient_list")
    return errors


def check_manifest(m: dict[str, Any]) -> None:
    errors = manifest_errors(m)
    if errors:
        raise ManifestError("invalid manifest:\n  " + "\n  ".join(errors))


def freeze(manifest_path: str | os.PathLike[str], ledger: Ledger) -> dict[str, Any]:
    """Validate and freeze a manifest. Idempotent for identical content; refuses a changed manifest.

    The ledger is verified first; a missing or tampered ledger refuses (``LedgerIntegrityError``).
    """
    ledger.verify()
    m = load_manifest(manifest_path)
    check_manifest(m)
    digest = manifest_sha256(m)
    prior = ledger.frozen(m["evaluation_id"])
    if prior:
        if any(e["sha256"] == digest for e in prior):
            return {**prior[0], "already_frozen": True}
        raise ManifestError(
            f"evaluation_id {m['evaluation_id']!r} is already frozen with a different hash; "
            "a frozen manifest cannot change - declare a new evaluation_id"
        )
    return ledger.append_frozen({"evaluation_id": m["evaluation_id"], "sha256": digest, "frozen_at": utc_now()})


__all__ = ["Ledger", "LedgerIntegrityError", "ManifestError", "RunRefused", "DEFAULT_LEDGER_DIR", "PKG_DIR",
           "canonical_bytes", "sha256_bytes", "utc_now", "freeze", "load_manifest", "manifest_errors",
           "manifest_sha256", "check_manifest", "task_list_keys"]
