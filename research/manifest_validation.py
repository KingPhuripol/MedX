"""Experiment-manifest validation: JSON Schema + semantic tier/approval rules.

Single implementation shared by `scripts/validate_manifest.py` (CLI) and the training launcher
(`python -m research.train`), so a manifest the CLI rejects can never be launched.

Tier >= 3 needs an explicit approval record (slice s9r): a fenced ```approval JSON block
(schemas/approval-record.schema.json) inside the dated DECISIONS.md section named by
`approval.decision_ref`, bound to this experiment's id, tier, GPUs, minutes, budget, approver and
date, and, for tier 4, to the manifest content hash (`approval_sha256`). The validator cannot prove a
human wrote the record; records reach main only through human-reviewed commits.
"""

from __future__ import annotations

import hashlib
import json
import math
import re
from dataclasses import dataclass
from pathlib import Path

import jsonschema

ROOT = Path(__file__).resolve().parents[1]
SCHEMA_PATH = ROOT / "schemas" / "experiment-manifest.schema.json"
APPROVAL_SCHEMA_PATH = ROOT / "schemas" / "approval-record.schema.json"
DECISIONS_PATH = ROOT / "docs" / "DECISIONS.md"
AGENTS_DIR = ROOT / ".claude" / "agents"
AGENT_TOKENS = {"claude", "agent", "assistant", "bot", "orchestrator", "planner", "builder", "checker", "reviewer"}
HASH_EXCLUDED_KEYS = ("approval", "status", "result")
TERMINAL = {"completed", "failed", "stopped", "invalidated"}
LOCAL_ONLY_CLASSES = {"mimic", "hospital"}


def sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _reject_constant(name: str) -> object:
    raise ValueError(f"non-finite number {name} is not allowed (JSON has no NaN/Infinity)")


def loads_strict(text: str) -> object:
    """json.loads that rejects NaN/Infinity/-Infinity literals and overflowing numbers such as 1e999.

    Python's json accepts these by default and no JSON Schema keyword rejects them, while every numeric
    comparison with NaN is False, so a NaN budget would pass a `manifest > record` check (s9r F1).
    """
    value = json.loads(text, parse_constant=_reject_constant)
    if bad := nonfinite_paths(value):
        raise ValueError(f"non-finite number at {bad[0]} is not allowed")
    return value


def nonfinite_paths(value: object, path: str = "") -> list[str]:
    """JSON-pointer-like paths of every NaN/Infinity float inside a parsed JSON value."""
    if isinstance(value, float) and not math.isfinite(value):
        return [path or "<root>"]
    if isinstance(value, dict):
        return [p for k, v in value.items() for p in nonfinite_paths(v, f"{path}/{k}")]
    if isinstance(value, list):
        return [p for i, v in enumerate(value) for p in nonfinite_paths(v, f"{path}/{i}")]
    return []


# ---------------------------------------------------------------------------------------------------
# Approval records (slice s9r): fenced ```approval JSON blocks inside dated DECISIONS.md sections
# ---------------------------------------------------------------------------------------------------

_HEADING = re.compile(r"^(#{1,6})\s+(.*?)\s*#*\s*$")
_FENCE_OPEN = re.compile(r"^ {0,3}(`{3,}|~{3,})\s*([^\s`]*)")


@dataclass(frozen=True)
class ApprovalBlock:
    """One fenced ```approval block found inside a dated section."""

    section: str  # exact dated heading text (without '## ')
    line: int  # 1-based line of the opening fence
    record: object  # parsed JSON (dict for a well-formed record) or None if the JSON is invalid
    parse_error: str | None = None


@dataclass(frozen=True)
class DecisionLog:
    blocks: tuple[ApprovalBlock, ...]
    headings: frozenset[str]  # dated headings
    section_text: dict  # dated heading -> text of the section outside approval blocks (prose, comments, other code)


def parse_decision_log(text: str) -> DecisionLog:
    """Extract approval blocks. Only fenced blocks with info string exactly `approval`, outside HTML
    comments and inside a dated `## YYYY-MM-DD ...` section, count. Prose never counts."""
    blocks: list[ApprovalBlock] = []
    headings: set[str] = set()
    other: dict[str, list[str]] = {}
    section: str | None = None
    fence: str | None = None
    fence_info, fence_line, fence_lines = "", 0, []
    in_comment = False
    for n, line in enumerate(text.splitlines(), start=1):
        if fence is not None:
            stripped = line.strip()
            if stripped and set(stripped) == {fence[0]} and len(stripped) >= len(fence):
                if fence_info == "approval" and section is not None:
                    body = "\n".join(fence_lines)
                    try:
                        blocks.append(ApprovalBlock(section, fence_line, loads_strict(body)))
                    except ValueError as exc:  # includes json.JSONDecodeError and non-finite numbers
                        blocks.append(ApprovalBlock(section, fence_line, None, f"invalid JSON: {exc}"))
                elif section is not None:
                    other[section] += fence_lines
                fence = None
            else:
                fence_lines.append(line)
            continue
        if section is not None:
            other[section].append(line)
        if in_comment:
            if "-->" in line:
                in_comment = False
            continue
        if "<!--" in line and "-->" not in line.split("<!--", 1)[1]:
            in_comment = True
            continue
        if m := _HEADING.match(line):
            level, title = len(m.group(1)), m.group(2)
            if level <= 2:
                section = title if level == 2 and re.match(r"^\d{4}-\d{2}-\d{2}\b", title) else None
                if section is not None:
                    headings.add(section)
                    other.setdefault(section, [])
            continue
        if m := _FENCE_OPEN.match(line):
            fence, fence_info, fence_line, fence_lines = m.group(1), m.group(2), n, []
    return DecisionLog(tuple(blocks), frozenset(headings), {k: "\n".join(v) for k, v in other.items()})


def load_decision_log(decisions_path: Path) -> DecisionLog:
    if not Path(decisions_path).is_file():
        return DecisionLog((), frozenset(), {})
    return parse_decision_log(Path(decisions_path).read_text(encoding="utf-8"))


def approval_sha256(manifest: dict) -> str:
    """sha256 of the canonical manifest JSON without approval/status/result (status changes keep the approval)."""
    content = {k: v for k, v in manifest.items() if k not in HASH_EXCLUDED_KEYS}
    canonical = json.dumps(content, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def is_agent_identity(name: str, agents_dir: Path = AGENTS_DIR) -> bool:
    """Case-insensitive: the name contains an agent stem (e.g. `research-lead`) or an agent token as a word."""
    norm = re.sub(r"[\s_]+", "-", name.strip().casefold())
    words = set(re.findall(r"\w+", norm.replace("-", " ")))
    stems = {p.stem.casefold() for p in Path(agents_dir).glob("*.md")} if Path(agents_dir).is_dir() else set()
    return any(stem in norm for stem in stems) or bool(words & AGENT_TOKENS)


def approval_errors(manifest: dict, log: DecisionLog, *, agents_dir: Path = AGENTS_DIR) -> list[str]:
    """Scope-bound approval checks for a Tier >= 3 manifest (schema-valid, with an approval block)."""
    approval, exp_id, tier = manifest["approval"], manifest["experiment_id"], manifest["run_tier"]
    ref = approval["decision_ref"]
    errors: list[str] = []
    if approval["run_id"] != exp_id:
        errors.append(f"approval.run_id {approval['run_id']!r} must equal experiment_id {exp_id!r} (approval is per run)")
    if is_agent_identity(approval["approved_by"], agents_dir):
        errors.append(f"approval.approved_by {approval['approved_by']!r} is an agent identity; only a human can approve tier {tier}")
    if ref not in log.headings:
        errors.append(f"approval.decision_ref {ref!r} not found as a dated heading in DECISIONS.md")
        return errors

    mine = [b for b in log.blocks if isinstance(b.record, dict) and b.record.get("experiment_id") == exp_id]
    if len(mine) > 1:
        where = ", ".join(f"line {b.line} under {b.section!r}" for b in mine)
        errors.append(f"duplicate approval records for experiment_id {exp_id!r} ({where}); exactly one is allowed in the log")
        return errors
    broken = [b for b in log.blocks if b.section == ref and not isinstance(b.record, dict)]
    if broken:
        errors.append(f"malformed approval block at line {broken[0].line} in section {ref!r}: "
                      f"{broken[0].parse_error or 'not a JSON object'}")
        return errors
    if not mine:
        others = sorted({str(b.record.get("experiment_id")) for b in log.blocks if b.section == ref and isinstance(b.record, dict)})
        if others:
            errors.append(f"section {ref!r} approves only other experiments {others}, not experiment_id {exp_id!r}")
        elif exp_id in log.section_text.get(ref, ""):
            errors.append(f"section {ref!r} mentions {exp_id!r} only in prose or a comment; an approval must be a fenced "
                          "```approval block")
        else:
            errors.append(f"section {ref!r} contains no fenced ```approval record for experiment_id {exp_id!r}")
        return errors
    block = mine[0]
    if block.section != ref:
        errors.append(f"approval record for {exp_id!r} is under heading {block.section!r}, not under decision_ref {ref!r}")
        return errors

    record = block.record
    if bad := nonfinite_paths(record):
        errors.append(f"approval record (line {block.line}) has a non-finite number at {', '.join(bad)}; NaN/Infinity never approve")
        return errors
    schema = json.loads(APPROVAL_SCHEMA_PATH.read_text(encoding="utf-8"))
    rec_errors = sorted(jsonschema.Draft202012Validator(schema).iter_errors(record), key=lambda e: list(e.absolute_path))
    if rec_errors:
        errors += [f"approval record schema (line {block.line}): {'/'.join(map(str, e.absolute_path)) or '<root>'}: {e.message}"
                   for e in rec_errors]
        return errors

    res, budget = manifest["resources"], manifest["resources"]["budget"]
    if record["tier"] != tier:
        errors.append(f"approval record tier {record['tier']} != manifest run_tier {tier}")
    if record["gpu_count"] != res["gpu_count"]:
        errors.append(f"manifest resources.gpu_count {res['gpu_count']} != approved gpu_count {record['gpu_count']}")
    # `not (a <= b)` so an incomparable value (NaN) is rejected, never accepted (s9r F1).
    if not res["max_minutes"] <= record["max_minutes"]:
        errors.append(f"manifest max_minutes {res['max_minutes']} exceeds approved max_minutes {record['max_minutes']}")
    if not budget["gpu_hours"] <= record["gpu_hours"]:
        errors.append(f"manifest budget.gpu_hours {budget['gpu_hours']} exceeds approved gpu_hours {record['gpu_hours']}")
    if not budget["cost_usd_max"] <= record["cost_usd_max"]:
        errors.append(f"manifest budget.cost_usd_max {budget['cost_usd_max']} exceeds approved cost_usd_max {record['cost_usd_max']}")
    if record["approved_by"] != approval["approved_by"]:
        errors.append(f"approval.approved_by {approval['approved_by']!r} != record approved_by {record['approved_by']!r}")
    if record["approved_by"] != approval["approved_by"] and is_agent_identity(record["approved_by"], agents_dir):
        errors.append(f"record approved_by {record['approved_by']!r} is an agent identity; only a human can approve tier {tier}")
    heading_date = ref[:10]
    if not record["date"] == approval["date"] == heading_date:
        errors.append(f"approval date mismatch: record {record['date']}, approval.date {approval['date']}, heading {heading_date}")
    if tier >= 4 and "manifest_sha256" not in record:
        errors.append("tier 4 approval record must carry manifest_sha256 (scripts/validate_manifest.py --approval-sha)")
    if "manifest_sha256" in record and record["manifest_sha256"] != approval_sha256(manifest):
        errors.append(f"approval record manifest_sha256 does not match the manifest content (recomputed {approval_sha256(manifest)}); "
                      "resources, config, data, code or model changed after approval")
    return errors


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

    # Human approval for Tier 3/4: an explicit, scope-bound record in docs/DECISIONS.md (slice s9r).
    approval = manifest.get("approval")
    if tier >= 3:
        if approval is None:
            errors.append(f"tier {tier} requires an approval block recorded in docs/DECISIONS.md")
        else:
            errors += approval_errors(manifest, load_decision_log(decisions_path))

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
    if bad := nonfinite_paths(manifest):
        return [f"manifest has a non-finite number (NaN/Infinity) at {p}" for p in bad]
    errors = schema_errors(manifest)
    if errors:
        return errors
    return semantic_errors(manifest, root=root, decisions_path=decisions_path)  # type: ignore[arg-type]


def validate_path(path: Path, *, root: Path = ROOT, decisions_path: Path = DECISIONS_PATH) -> list[str]:
    try:
        manifest = loads_strict(Path(path).read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        return [f"cannot read manifest: {exc}"]
    return validate_manifest(manifest, root=root, decisions_path=decisions_path)
