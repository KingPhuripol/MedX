"""Frozen evaluation manifest + append-only ledgers (slice s8). Research prototype - not for clinical use."""

from __future__ import annotations

import datetime as _dt
import hashlib
import json
import os
from pathlib import Path
from typing import Any

from .jsonschema_lite import validate
from .registry import REGISTRY

PKG_DIR = Path(__file__).resolve().parent
SCHEMA_PATH = PKG_DIR / "schemas" / "eval_manifest.schema.json"
DEFAULT_LEDGER_DIR = PKG_DIR / "ledger"


class ManifestError(ValueError):
    pass


def canonical_bytes(obj: Any) -> bytes:
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False).encode("utf-8")


def sha256_bytes(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()


def manifest_sha256(manifest: dict[str, Any]) -> str:
    return sha256_bytes(canonical_bytes(manifest))


def load_manifest(path: str | os.PathLike[str]) -> dict[str, Any]:
    with open(path, encoding="utf-8") as f:
        return json.load(f)


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
        if x["name"] not in REGISTRY:
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
    return errors


def check_manifest(m: dict[str, Any]) -> None:
    errors = manifest_errors(m)
    if errors:
        raise ManifestError("invalid manifest:\n  " + "\n  ".join(errors))


class Ledger:
    """Append-only JSONL ledgers: ``frozen.jsonl`` and ``runs.jsonl``. Lines are never rewritten."""

    def __init__(self, directory: str | os.PathLike[str] | None = None):
        d = directory or os.environ.get("EVAL_LEDGER_DIR") or DEFAULT_LEDGER_DIR
        self.dir = Path(d)
        self.frozen_path = self.dir / "frozen.jsonl"
        self.runs_path = self.dir / "runs.jsonl"

    @staticmethod
    def _read(path: Path) -> list[dict[str, Any]]:
        if not path.exists():
            return []
        return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]

    def _append(self, path: Path, entry: dict[str, Any]) -> None:
        self.dir.mkdir(parents=True, exist_ok=True)
        with open(path, "ab") as f:
            f.write(canonical_bytes(entry) + b"\n")

    def frozen(self, evaluation_id: str) -> list[dict[str, Any]]:
        return [e for e in self._read(self.frozen_path) if e["evaluation_id"] == evaluation_id]

    def runs(self, evaluation_id: str) -> list[dict[str, Any]]:
        return [e for e in self._read(self.runs_path) if e["evaluation_id"] == evaluation_id]

    def append_frozen(self, entry: dict[str, Any]) -> None:
        self._append(self.frozen_path, entry)

    def append_run(self, entry: dict[str, Any]) -> None:
        self._append(self.runs_path, entry)


def utc_now() -> str:
    return _dt.datetime.now(_dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def freeze(manifest_path: str | os.PathLike[str], ledger: Ledger) -> dict[str, Any]:
    """Validate and freeze a manifest. Idempotent for identical content; refuses a changed manifest."""
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
    entry = {"evaluation_id": m["evaluation_id"], "sha256": digest, "frozen_at": utc_now()}
    ledger.append_frozen(entry)
    return entry
