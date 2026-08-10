#!/usr/bin/env python3
"""Validate the complete Claude Code Harness using only the Python standard library."""

from __future__ import annotations

import argparse
import json
import os
import py_compile
import sys
from pathlib import Path

from harness_lib import ValidationError, iso_datetime, load_json, parse_frontmatter, validate_file


ROOT = Path(__file__).resolve().parents[1]

SOURCE_DOCS = [
    "docs/PROJECT_CHARTER.md",
    "docs/DECISION_LOG.md",
    "docs/project_management/OFFICIAL_DEADLINES.md",
    "docs/project_management/MASTER_PLAN.md",
    "docs/project_management/MILESTONES.md",
    "docs/project_management/TASK_BOARD.md",
    "docs/project_management/RISK_REGISTER.md",
    "docs/project_management/TEAM_OWNERSHIP.md",
    "docs/project_management/WEEKLY_STATUS.md",
    "docs/research/RESEARCH_SPEC.md",
    "docs/research/ARCHITECTURE_SPEC.md",
    "docs/research/TRAINING_SPEC.md",
    "docs/research/BENCHMARK_CONTRACT.md",
    "docs/research/SUCCESS_CRITERIA.md",
    "docs/innovation/PRODUCT_SPEC.md",
    "docs/innovation/CLINICAL_WORKFLOW.md",
    "docs/innovation/SAFETY_SPEC.md",
    "docs/innovation/ACCEPTANCE_CRITERIA.md",
    "docs/shared/DATA_CONTRACT.md",
    "docs/shared/PATIENT_JOURNEY_SCHEMA.md",
    "docs/shared/MODEL_API_CONTRACT.md",
    "docs/shared/EVALUATION_CONTRACT.md",
    "docs/shared/HUMAN_APPROVAL_POLICY.md",
]

AGENT_NAMES = {
    "project-manager",
    "research-lead",
    "innovation-lead",
    "model-architect",
    "training-engineer",
    "evaluation-scientist",
    "literature-benchmark-scout",
    "data-governor-engineer",
    "software-engineer",
    "clinical-safety-reviewer",
    "integration-auditor",
    "documentation-agent",
}

SKILL_NAMES = {
    "project-status",
    "new-experiment",
    "run-smoke-test",
    "run-benchmark",
    "architecture-ablation",
    "data-audit",
    "temporal-leakage-audit",
    "integration-check",
    "proposal-readiness",
    "progress-readiness",
    "hf-release-check",
}

CODE_AGENTS = {
    "model-architect",
    "training-engineer",
    "evaluation-scientist",
    "data-governor-engineer",
    "software-engineer",
    "documentation-agent",
}
READ_ONLY_REVIEWERS = {"clinical-safety-reviewer", "integration-auditor"}

SCHEMA_BINDINGS = {
    "project_state/official_deadlines.json": "schemas/official-deadlines.schema.json",
    "project_state/tasks.json": "schemas/task.schema.json",
    "project_state/risks.json": "schemas/risk.schema.json",
    "project_state/decisions.json": "schemas/decision.schema.json",
    "project_state/approvals.json": "schemas/human-approval.schema.json",
    "project_state/evaluations.json": "schemas/evaluation-record.schema.json",
    "tests/fixtures/patient_journey/valid.json": "schemas/patient-journey.schema.json",
    "tests/fixtures/model_api/request.json": "schemas/model-api-request.schema.json",
    "tests/fixtures/model_api/response.json": "schemas/model-api-response.schema.json",
}

SCRIPT_FILES = [
    "scripts/bootstrap.sh",
    "scripts/run_smoke_test.sh",
    "scripts/harness_lib.py",
    "scripts/verify_harness.py",
    "scripts/validate_manifest.py",
    "scripts/new_experiment.py",
    "scripts/temporal_leakage_audit.py",
    "scripts/project_status.py",
    ".claude/hooks/approval_gate.py",
    ".claude/hooks/post_edit_checks.py",
    ".claude/hooks/session_context.py",
]

CANONICAL_DEADLINES = [
    ("Group Application", "2026-08-14", "2026-08-14", "23:55"),
    ("Project Idea", "2026-08-28", "2026-08-28", None),
    ("CITI", "2026-09-25", "2026-09-25", None),
    ("Proposal Report", "2026-10-02", "2026-10-02", None),
    ("Proposal Presentation", "2026-10-08", "2026-10-09", None),
    ("Progress Report", "2026-12-04", "2026-12-04", None),
    ("Progress Presentation", "2026-12-14", "2026-12-15", None),
]


class Checks:
    def __init__(self) -> None:
        self.errors: list[str] = []
        self.count = 0

    def require(self, condition: bool, message: str) -> None:
        self.count += 1
        if not condition:
            self.errors.append(message)

    def extend(self, errors: list[str]) -> None:
        self.count += 1
        self.errors.extend(errors)


def check_files(checks: Checks) -> None:
    required = ["README.md", "CLAUDE.md", ".claude/settings.json", "Makefile"] + SOURCE_DOCS + SCRIPT_FILES
    for path in required:
        checks.require((ROOT / path).is_file(), f"missing required file: {path}")
    claude = ROOT / "CLAUDE.md"
    if claude.exists():
        checks.require(len(claude.read_text(encoding="utf-8").splitlines()) <= 220, "CLAUDE.md exceeds 220 lines; move detail to scoped docs/rules")


def check_json_and_state(checks: Checks) -> None:
    for instance, schema in SCHEMA_BINDINGS.items():
        if (ROOT / instance).exists() and (ROOT / schema).exists():
            checks.extend(validate_file(ROOT / instance, ROOT / schema))

    manifest_schema = ROOT / "schemas/experiment-manifest.schema.json"
    manifests = sorted((ROOT / "experiments/manifests").glob("exp_*.json"))
    checks.require(bool(manifests), "no experiment manifests found")
    for manifest in manifests:
        checks.extend(validate_file(manifest, manifest_schema))

    tasks_payload = load_json(ROOT / "project_state/tasks.json")
    risks_payload = load_json(ROOT / "project_state/risks.json")
    decisions_payload = load_json(ROOT / "project_state/decisions.json")
    task_ids = [item["task_id"] for item in tasks_payload["tasks"]]
    risk_ids = [item["risk_id"] for item in risks_payload["risks"]]
    decision_ids = [item["decision_id"] for item in decisions_payload["decisions"]]
    checks.require(len(task_ids) == len(set(task_ids)), "task IDs are not unique")
    checks.require(len(risk_ids) == len(set(risk_ids)), "risk IDs are not unique")
    checks.require(len(decision_ids) == len(set(decision_ids)), "decision IDs are not unique")
    for item in tasks_payload["tasks"]:
        for dependency in item["dependencies"]:
            checks.require(dependency in task_ids, f"{item['task_id']} references unknown dependency {dependency}")
        if item["status"] == "DONE":
            checks.require(bool(item["evidence"]), f"{item['task_id']} is DONE without evidence")
    for item in risks_payload["risks"]:
        for task_id in item["linked_tasks"]:
            checks.require(task_id in task_ids, f"{item['risk_id']} references unknown task {task_id}")

    for manifest_path in manifests:
        manifest = load_json(manifest_path)
        checks.require(manifest["task_id"] in task_ids, f"{manifest['experiment_id']} references unknown task")
        for risk_id in manifest["risks"]:
            checks.require(risk_id in risk_ids, f"{manifest['experiment_id']} references unknown risk {risk_id}")
        tier_requires = manifest["run_tier"] >= 3
        checks.require(manifest["approvals"]["required"] == tier_requires, f"{manifest['experiment_id']} approval requirement does not match tier")
        if manifest["status"] in {"approved", "running", "completed"} and tier_requires:
            checks.require(bool(manifest["approvals"]["approval_ids"]), f"{manifest['experiment_id']} lacks approval ID")


def check_deadlines(checks: Checks) -> None:
    payload = load_json(ROOT / "project_state/official_deadlines.json")
    checks.require(payload.get("immutable") is True, "official deadline registry is not immutable")
    checks.require(payload.get("timezone") == "Asia/Bangkok", "official deadline timezone changed")
    observed = [
        (item["name"], item["official_date_start"], item["official_date_end"], item["official_time"])
        for item in payload["deadlines"]
    ]
    checks.require(observed == CANONICAL_DEADLINES, f"official deadlines differ from canonical registry: {observed!r}")
    checks.require(payload["deadlines"][0]["status"] in {"NEEDS_CONFIRMATION", "SUBMITTED", "COMPLETE"}, "Group Application status must be explicitly confirmed")


def check_agents_and_skills(checks: Checks) -> None:
    files = sorted((ROOT / ".claude/agents").glob("*.md"))
    names: dict[str, tuple[Path, dict[str, str]]] = {}
    for path in files:
        try:
            frontmatter, body = parse_frontmatter(path)
        except ValidationError as exc:
            checks.errors.append(str(exc))
            continue
        name = frontmatter.get("name", "")
        names[name] = (path, frontmatter)
        checks.require(bool(frontmatter.get("description")), f"{path}: missing description")
        checks.require(len(body.strip()) >= 500, f"{path}: agent prompt is too shallow")
    checks.require(set(names) == AGENT_NAMES, f"agent set mismatch: expected {sorted(AGENT_NAMES)}, got {sorted(names)}")
    for name in CODE_AGENTS:
        if name in names:
            checks.require(names[name][1].get("isolation") == "worktree", f"code-writing agent {name} lacks worktree isolation")
    for name in READ_ONLY_REVIEWERS:
        if name in names:
            frontmatter = names[name][1]
            tools = {part.strip() for part in frontmatter.get("tools", "").split(",")}
            checks.require(frontmatter.get("permissionMode") == "plan", f"reviewer {name} must use plan mode")
            checks.require(not tools.intersection({"Write", "Edit", "NotebookEdit"}), f"reviewer {name} has write tools")

    skill_files = sorted((ROOT / ".claude/skills").glob("*/SKILL.md"))
    skill_names: set[str] = set()
    for path in skill_files:
        try:
            frontmatter, body = parse_frontmatter(path)
        except ValidationError as exc:
            checks.errors.append(str(exc))
            continue
        name = frontmatter.get("name", path.parent.name)
        skill_names.add(name)
        checks.require(name == path.parent.name, f"skill name/path mismatch in {path}")
        checks.require(bool(frontmatter.get("description")), f"{path}: missing description")
        checks.require(len(body.strip()) >= 500, f"{path}: skill workflow is too shallow")
    checks.require(skill_names == SKILL_NAMES, f"skill set mismatch: expected {sorted(SKILL_NAMES)}, got {sorted(skill_names)}")


def check_settings_and_scripts(checks: Checks) -> None:
    settings = load_json(ROOT / ".claude/settings.json")
    hooks = settings.get("hooks", {})
    checks.require("PreToolUse" in hooks and "PostToolUse" in hooks and "SessionStart" in hooks, "settings lacks required hooks")
    deny = settings.get("permissions", {}).get("deny", [])
    checks.require("Write(./sources/**)" in deny and "Edit(./sources/**)" in deny, "settings does not protect synced sources")
    checks.require(settings.get("worktree", {}).get("baseRef") == "head", "worktree baseRef must be head")
    for relative in SCRIPT_FILES:
        path = ROOT / relative
        if path.suffix == ".py" and path.exists():
            try:
                py_compile.compile(str(path), doraise=True)
            except py_compile.PyCompileError as exc:
                checks.errors.append(f"Python compile failed for {relative}: {exc.msg}")
        if path.exists():
            checks.require(os.access(path, os.X_OK), f"script is not executable: {relative}")


def check_fixtures(checks: Checks) -> None:
    journey = load_json(ROOT / "tests/fixtures/patient_journey/valid.json")
    event_ids = [item["event_id"] for item in journey["events"]]
    checks.require(len(event_ids) == len(set(event_ids)), "patient fixture event IDs are not unique")
    for event in journey["events"]:
        checks.require(iso_datetime(event["available_at_time"]) >= iso_datetime(event["observed_at"]), f"{event['event_id']} is available before observation")
        if event["status"] == "AVAILABLE":
            checks.require("value" in event or bool(event.get("payload_ref")), f"{event['event_id']} has no payload/value")

    request = load_json(ROOT / "tests/fixtures/model_api/request.json")
    decision_time = iso_datetime(request["decision_time"])
    for evidence in request["evidence"]:
        checks.require(iso_datetime(evidence["available_at_time"]) <= decision_time, f"API fixture includes future evidence {evidence['evidence_id']}")
    response = load_json(ROOT / "tests/fixtures/model_api/response.json")
    checks.require(response["human_review"]["required"] is True, "API fixture does not require human review")
    checks.require(response["request_id"] == request["request_id"], "API request/response IDs differ")


def check_changed(path_text: str, checks: Checks) -> None:
    path = Path(path_text)
    if not path.is_absolute():
        path = ROOT / path
    if path.suffix == ".json" and path.exists():
        try:
            json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            checks.errors.append(f"changed JSON is invalid: {path}: {exc}")
    if path.suffix == ".py" and path.exists():
        try:
            py_compile.compile(str(path), doraise=True)
        except py_compile.PyCompileError as exc:
            checks.errors.append(f"changed Python does not compile: {path}: {exc.msg}")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--changed", help="Path just edited by a Claude Code hook")
    args = parser.parse_args()
    checks = Checks()
    try:
        if args.changed:
            check_changed(args.changed, checks)
        check_files(checks)
        check_json_and_state(checks)
        check_deadlines(checks)
        check_agents_and_skills(checks)
        check_settings_and_scripts(checks)
        check_fixtures(checks)
    except (ValidationError, KeyError, TypeError, OSError) as exc:
        checks.errors.append(f"verification could not complete: {exc}")

    if checks.errors:
        print(f"HARNESS VERIFICATION FAILED ({len(checks.errors)} errors / {checks.count} checks)")
        for error in checks.errors:
            print(f"- {error}")
        return 1
    print(f"HARNESS VERIFICATION PASSED ({checks.count} checks; {len(AGENT_NAMES)} agents; {len(SKILL_NAMES)} skills)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
