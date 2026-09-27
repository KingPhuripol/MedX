"""Experiment-manifest validation: JSON Schema + semantic tier/approval rules.

Single implementation shared by `scripts/validate_manifest.py` (CLI) and the training launcher
(`python -m research.train`), so a manifest the CLI rejects can never be launched.
"""

from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path

import jsonschema

ROOT = Path(__file__).resolve().parents[1]
SCHEMA_PATH = ROOT / "schemas" / "experiment-manifest.schema.json"
DECISIONS_PATH = ROOT / "docs" / "DECISIONS.md"
TERMINAL = {"completed", "failed", "stopped", "invalidated"}
LOCAL_ONLY_CLASSES = {"mimic", "hospital"}
DATED_HEADING = re.compile(r"^##\s+(\d{4}-\d{2}-\d{2}\b.*?)\s*$")


def sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def dated_headings(decisions_path: Path) -> set[str]:
    """Dated `## YYYY-MM-DD ...` headings of the decisions log (exact heading text, no '## ')."""
    if not decisions_path.is_file():
        return set()
    return {m.group(1) for line in decisions_path.read_text(encoding="utf-8").splitlines() if (m := DATED_HEADING.match(line))}


def schema_errors(manifest: object) -> list[str]:
    schema = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))
    validator = jsonschema.Draft202012Validator(schema)
    errors = sorted(validator.iter_errors(manifest), key=lambda e: list(e.absolute_path))
    return [f"schema: {'/'.join(map(str, e.absolute_path)) or '<root>'}: {e.message}" for e in errors]


def semantic_errors(manifest: dict, *, root: Path = ROOT, decisions_path: Path = DECISIONS_PATH) -> list[str]:
    errors: list[str] = []
    tier = manifest["run_tier"]
    status = manifest["status"]
    res = manifest["resources"]
    exp_id = manifest["experiment_id"]

    # Tier boundaries (CLAUDE.md training tiers).
    if res["gpu_count"] > 1 and tier < 3:
        errors.append(f"gpu_count {res['gpu_count']} > 1 requires tier >= 3 (manifest says tier {tier})")
    if res["max_minutes"] > 60 and tier < 3:
        errors.append(f"max_minutes {res['max_minutes']} > 60 requires tier >= 3 (manifest says tier {tier})")
    if tier == 0 and (res["gpu_count"] != 0 or manifest["data"]["data_class"] != "synthetic"):
        errors.append("tier 0 requires gpu_count 0 and data_class synthetic")

    # Human approval for Tier 3/4, recorded in docs/DECISIONS.md; Tier 4 is approved per run.
    approval = manifest.get("approval")
    if tier >= 3:
        if approval is None:
            errors.append(f"tier {tier} requires an approval block recorded in docs/DECISIONS.md")
        else:
            if approval["decision_ref"] not in dated_headings(decisions_path):
                errors.append(
                    f"approval.decision_ref {approval['decision_ref']!r} not found as a dated heading in {decisions_path.name}"
                )
            if approval["run_id"] != exp_id:
                errors.append(f"approval.run_id {approval['run_id']!r} must equal experiment_id {exp_id!r} (approval is per run)")

    # Reproducibility pins: placeholders are only acceptable while planned.
    if manifest["code"]["revision"] == "UNPINNED" and status != "planned":
        errors.append(f"code.revision UNPINNED is only allowed while status is planned (status {status})")
    for ds in manifest["data"]["datasets"]:
        for key in ("dataset_version", "split_version"):
            if ds[key].startswith("UNRESOLVED:") and status != "planned":
                errors.append(f"data {ds['name']}.{key} {ds[key]!r} is only allowed while status is planned (status {status})")
    if manifest["model"]["hub_revision"] in (None, "UNPINNED") and manifest["model"]["hf_repo_id"] and status != "planned":
        errors.append(f"model.hub_revision must be pinned once status is {status}")

    config_path = root / manifest["code"]["config_path"]
    if not config_path.is_file():
        errors.append(f"code.config_path {manifest['code']['config_path']} does not exist")
    elif sha256_file(config_path) != manifest["code"]["config_sha256"]:
        errors.append(f"code.config_sha256 mismatch for {manifest['code']['config_path']} (recomputed {sha256_file(config_path)})")

    # Result block iff terminal.
    has_result = manifest.get("result") is not None
    if status in TERMINAL and not has_result:
        errors.append(f"terminal status {status} requires a result block")
    if status not in TERMINAL and has_result:
        errors.append(f"non-terminal status {status} must not have a result block")

    # PhysioNet / hospital data stay on team-controlled machines (proposal 1.3.4).
    data = manifest["data"]
    if data["data_class"] in LOCAL_ONLY_CLASSES and data["locality"] != "local_only":
        errors.append(f"data_class {data['data_class']} requires locality local_only (got {data['locality']})")
    return errors


def validate_manifest(manifest: object, *, root: Path = ROOT, decisions_path: Path = DECISIONS_PATH) -> list[str]:
    """All errors for a parsed manifest; empty list means valid."""
    errors = schema_errors(manifest)
    if errors:
        return errors
    return semantic_errors(manifest, root=root, decisions_path=decisions_path)  # type: ignore[arg-type]


def validate_path(path: Path, *, root: Path = ROOT, decisions_path: Path = DECISIONS_PATH) -> list[str]:
    try:
        manifest = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        return [f"cannot read manifest: {exc}"]
    return validate_manifest(manifest, root=root, decisions_path=decisions_path)
