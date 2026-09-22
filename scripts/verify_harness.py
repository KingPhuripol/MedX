#!/usr/bin/env python3
"""Validate the complete Claude Code Harness using only the Python standard library."""

from __future__ import annotations

import argparse
import json
import os
import py_compile
import re
from pathlib import Path

from harness_lib import ValidationError, iso_datetime, load_json, parse_frontmatter, validate_file


ROOT = Path(__file__).resolve().parents[1]

SOURCE_DOCS = [
    "docs/PROJECT_CHARTER.md",
    "docs/DECISION_LOG.md",
    "docs/research/RESEARCH_SPEC.md",
    "docs/research/ARCHITECTURE_SPEC.md",
    "docs/research/TRAINING_SPEC.md",
    "docs/research/BENCHMARK_CONTRACT.md",
    "docs/research/SUCCESS_CRITERIA.md",
    "docs/research/RELATED_WORK.md",
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
    "new-experiment",
    "run-smoke-test",
    "run-benchmark",
    "architecture-ablation",
    "data-audit",
    "temporal-leakage-audit",
    "integration-check",
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
    "project_state/evaluations.json": "schemas/evaluation-record.schema.json",
    "project_state/contract_versions.json": "schemas/contract-versions.schema.json",
    "project_state/dataset_feasibility.json": "schemas/dataset-feasibility.schema.json",
    "project_state/literature.json": "schemas/literature.schema.json",
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
    "scripts/verify_citations.py",
    ".claude/hooks/approval_gate.py",
    ".claude/hooks/post_edit_checks.py",
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

    # A dataset dimension may only claim VERIFIED if it cites where it was verified.
    # This is the rule the whole feasibility survey rests on: without it, an assumption
    # written confidently is indistinguishable from a checked fact.
    feasibility = ROOT / "project_state/dataset_feasibility.json"
    if feasibility.is_file():
        payload = load_json(feasibility)
        for entry in payload["datasets"]:
            ds_id = entry["dataset_id"]
            has_evidence = bool(entry["evidence"])
            if entry["verdict"] != "UNDER_REVIEW":
                checks.require(has_evidence, f"{ds_id} has verdict {entry['verdict']} without any evidence")
            # A missing dimension is already a schema failure recorded above. Read
            # defensively so this loop reports that failure rather than masking it
            # behind a KeyError traceback.
            for dimension in ("license", "access", "patient_linkage", "temporal_validity", "care_setting"):
                if (entry.get(dimension) or {}).get("status") == "VERIFIED":
                    checks.require(has_evidence, f"{ds_id}.{dimension} is VERIFIED without any evidence")
            # DEC-0016 names one evaluated care setting. A dataset may only be said to
            # cover it on a verified basis: claiming coverage from an unread provenance
            # is exactly how a product built for one setting gets evaluated on another.
            # NO is a legitimate answer — it marks unlinked capability evidence — and
            # carries no evidence burden.
            care_setting = entry.get("care_setting") or {}
            if care_setting.get("covers_evaluated_setting") == "YES":
                checks.require(
                    care_setting["status"] == "VERIFIED",
                    f"{ds_id}.care_setting claims it covers the evaluated setting but its status is {care_setting['status']}",
                )
    for manifest_path in manifests:
        manifest = load_json(manifest_path)
        tier_requires = manifest["run_tier"] >= 3
        checks.require(manifest["approvals"]["required"] == tier_requires, f"{manifest['experiment_id']} approval requirement does not match tier")
        if manifest["status"] in {"approved", "running", "completed"} and tier_requires:
            checks.require(bool(manifest["approvals"]["approval_ids"]), f"{manifest['experiment_id']} lacks approval ID")


BASELINE_FAMILIES = {
    "fixed_path_medical_open",
    "same_backbone_fixed_path",
    "static_typed_dag",
    "random_or_shuffled_router",
    "sparse_moe_routing",
    "proposed_dynamic_typed_dag",
}

# TASK-0004 names these four coverage areas in its definition of done. Asserting
# them here is what turns the DoD from a sentence someone narrates into a
# condition the harness can fail on.
REQUIRED_COVERAGE = {
    "medical_multimodal",
    "dynamic_sparse_computation",
    "graph_faithfulness",
    "clinical_front_door",
}


def check_literature(checks: Checks) -> None:
    """Enforce the citation contract behind TASK-0004.

    The rule the whole registry rests on: a reference may only be ACCEPTED if it
    was checked against a primary source and says where. Without it a citation
    written from memory is indistinguishable from one that was verified, which is
    precisely the failure mode `PROJECT_IDEA_CLAIMS.md` was written to prevent.
    """

    registry = ROOT / "project_state/literature.json"
    if not registry.is_file():
        return
    payload = load_json(registry)
    searches = payload["searches"]
    references = payload["references"]
    families = payload["baseline_families"]

    search_ids = [item["search_id"] for item in searches]
    reference_ids = [item["reference_id"] for item in references]
    checks.require(len(search_ids) == len(set(search_ids)), "literature search IDs are not unique")
    checks.require(len(reference_ids) == len(set(reference_ids)), "literature reference IDs are not unique")
    known_searches = set(search_ids)
    known_references = set(reference_ids)

    known_datasets: set[str] = set()
    for filename, collection, field, sink in (
        ("dataset_feasibility.json", "datasets", "dataset_id", known_datasets),
    ):
        source = ROOT / "project_state" / filename
        if source.exists():
            sink.update(str(item[field]) for item in load_json(source)[collection])

    claims_file = ROOT / "docs/academic/PROJECT_IDEA_CLAIMS.md"
    known_claims: set[str] = set()
    if claims_file.is_file():
        known_claims = set(re.findall(r"\bC-\d{2}[a-z]?\b", claims_file.read_text(encoding="utf-8")))

    for item in searches:
        sid = item["search_id"]
        # A round whose queries were never written down may say so, but it may not
        # pretend the protocol exists. RECONSTRUCTED buys honesty, not silence.
        if item["protocol_status"] == "RECONSTRUCTED":
            checks.require(bool(item.get("notes")), f"{sid} is RECONSTRUCTED without notes explaining why the protocol was not recorded")
        else:
            # RECONSTRUCTED exists so a round with no written-down queries can still be
            # recorded honestly. It must not become the door a RECORDED search walks through.
            placeholder = [q for q in item["queries"] if q.strip().upper().startswith("NOT RECORDED")]
            checks.require(not placeholder, f"{sid} claims protocol_status RECORDED but carries a 'NOT RECORDED' placeholder query")
        checks.require(item["date_window_from"] <= item["date_window_to"], f"{sid} has an inverted date window")
        for reference_id in item["yielded"]:
            checks.require(reference_id in known_references, f"{sid} yielded unknown reference {reference_id}")

    accepted_coverage: set[str] = set()
    for item in references:
        lid = item["reference_id"]
        verdict = item["verdict"]
        verification = item["verification"]
        has_evidence = bool(item["evidence"])

        checks.require(item["found_by"] in known_searches, f"{lid} was found by unknown search {item['found_by']}")
        if verdict != "UNDER_REVIEW":
            checks.require(has_evidence, f"{lid} has verdict {verdict} without any evidence")
        if verdict == "ACCEPTED":
            checks.require(verification["status"] == "VERIFIED", f"{lid} is ACCEPTED while its verification status is {verification['status']}")
            accepted_coverage.update(item["coverage_areas"])
        if verdict == "REJECTED":
            checks.require(bool(item.get("excluded_reason")), f"{lid} is REJECTED without an excluded_reason")
        if verification["status"] == "VERIFIED":
            checks.require(verification["method"] != "not_verified", f"{lid} claims VERIFIED with method not_verified")
            checks.require(bool(verification["verified_on"]), f"{lid} claims VERIFIED without a verification date")
            checks.require(bool(verification["verified_fields"]), f"{lid} claims VERIFIED without naming a single verified field")
            checks.require(has_evidence, f"{lid} claims VERIFIED without any evidence")
        if verification["status"] == "CONFLICT":
            checks.require(bool(verification.get("conflict_note")), f"{lid} is in CONFLICT without a conflict_note")
            checks.require(verdict != "ACCEPTED", f"{lid} is ACCEPTED despite a verification conflict")

        identifiers = item["identifiers"]
        checks.require(any(identifiers[key] for key in ("doi", "arxiv_id", "pmid", "url")), f"{lid} carries no identifier of any kind")

        # A formatted string drifts from its fields the moment either is edited by
        # hand. These two checks catch the drift at the point it happens.
        citation = item["citation"]
        checks.require(str(citation["year"]) in citation["apa7"], f"{lid}: apa7 string does not contain the recorded year {citation['year']}")
        if identifiers["doi"]:
            checks.require(identifiers["doi"] in citation["apa7"], f"{lid}: apa7 string does not contain the recorded DOI")

        has_comparison = item.get("comparison") is not None
        checks.require(has_comparison == (item["role"] == "baseline_candidate"), f"{lid}: comparison block and role baseline_candidate must appear together")

        for claim in item.get("supports_claims", []):
            checks.require(claim in known_claims, f"{lid} supports unknown claim {claim}")
        for dataset_id in item.get("related_datasets", []):
            checks.require(dataset_id in known_datasets, f"{lid} references unknown dataset {dataset_id}; survey it in dataset_feasibility.json first")

    missing_coverage = sorted(REQUIRED_COVERAGE - accepted_coverage)
    checks.require(not missing_coverage, f"TASK-0004 coverage areas with no ACCEPTED reference: {', '.join(missing_coverage)}")

    observed_families = [item["family"] for item in families]
    checks.require(sorted(observed_families) == sorted(BASELINE_FAMILIES), f"baseline families must be exactly the six in BENCHMARK_CONTRACT.md, got {sorted(observed_families)}")
    checks.require(len(observed_families) == len(set(observed_families)), "a baseline family is recorded more than once")
    verdict_by_reference = {item["reference_id"]: item["verdict"] for item in references}
    for item in families:
        family = item["family"]
        selected = item["selected_reference"]
        if item["resolution"] in {"CANDIDATE_SELECTED", "CANDIDATE_CONDITIONAL"}:
            checks.require(bool(selected), f"baseline family {family} claims a candidate but names no reference")
            if selected:
                checks.require(verdict_by_reference.get(selected) in {"ACCEPTED", "CONDITIONAL"}, f"baseline family {family} selects {selected}, whose verdict does not permit use")
        if item["resolution"] == "NO_VALID_CANDIDATE":
            checks.require(bool(item["considered"]), f"baseline family {family} reports no valid candidate without listing what was considered")
        for reference_id in item["considered"]:
            checks.require(reference_id in known_references, f"baseline family {family} considered unknown reference {reference_id}")

    # LIT ids earn the same referential integrity TASK/RISK/DEC already have: an id
    # written into a document must resolve, and an accepted reference nobody reads
    # must still be visible in the human-readable survey.
    referenced: set[str] = set()
    for folder in ("docs", ".planning"):
        base = ROOT / folder
        if not base.is_dir():
            continue
        for document in sorted(base.rglob("*.md")):
            referenced.update(re.findall(r"\bLIT-\d{4}\b", document.read_text(encoding="utf-8")))
    dangling = sorted(referenced - known_references)
    checks.require(not dangling, f"documents cite literature IDs that do not exist: {', '.join(dangling)}")

    related_work = ROOT / "docs/research/RELATED_WORK.md"
    if related_work.is_file():
        survey_text = related_work.read_text(encoding="utf-8")
        unlisted = sorted(item["reference_id"] for item in references if item["verdict"] == "ACCEPTED" and item["reference_id"] not in survey_text)
        checks.require(not unlisted, f"ACCEPTED references absent from RELATED_WORK.md: {', '.join(unlisted)}")


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
    checks.require("PreToolUse" in hooks and "PostToolUse" in hooks, "settings lacks required hooks")
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
        check_literature(checks)
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
