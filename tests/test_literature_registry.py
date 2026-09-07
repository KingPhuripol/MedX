"""Prove the literature registry's rules actually fail when they are broken.

`scripts/verify_harness.py` grew ten new checks for `project_state/literature.json`.
A check that has only ever been observed passing is not evidence of anything: these
tests break the registry ten different ways and assert the harness objects each time.

The rule underneath all of them is one rule. A citation written from memory must be
distinguishable from a citation checked against its source, and the only thing that
makes it distinguishable is a machine refusing to accept the first.
"""

from __future__ import annotations

import copy
import importlib.util
import json
import shutil
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
REGISTRY = ROOT / "project_state/literature.json"


def load_harness(root: Path):
    """Import verify_harness with ROOT pointed at a throwaway copy of the repository."""
    spec = importlib.util.spec_from_file_location(f"verify_harness_{root.name}", ROOT / "scripts/verify_harness.py")
    module = importlib.util.module_from_spec(spec)
    sys.path.insert(0, str(ROOT / "scripts"))
    try:
        spec.loader.exec_module(module)
    finally:
        sys.path.remove(str(ROOT / "scripts"))
    module.ROOT = root
    return module


@pytest.fixture
def sandbox(tmp_path):
    """A copy of just enough of the repository for check_literature to run against."""
    shutil.copytree(ROOT / "project_state", tmp_path / "project_state")
    (tmp_path / "docs/academic").mkdir(parents=True)
    (tmp_path / "docs/research").mkdir(parents=True)
    shutil.copy(ROOT / "docs/academic/PROJECT_IDEA_CLAIMS.md", tmp_path / "docs/academic/PROJECT_IDEA_CLAIMS.md")
    shutil.copy(ROOT / "docs/research/RELATED_WORK.md", tmp_path / "docs/research/RELATED_WORK.md")
    return tmp_path


def run(sandbox_root: Path, mutate=None) -> list[str]:
    payload = json.loads((sandbox_root / "project_state/literature.json").read_text(encoding="utf-8"))
    if mutate is not None:
        payload = copy.deepcopy(payload)
        mutate(payload)
        (sandbox_root / "project_state/literature.json").write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    module = load_harness(sandbox_root)
    checks = module.Checks()
    module.check_literature(checks)
    return checks.errors


def first(payload: dict, verdict: str = "ACCEPTED") -> dict:
    return next(item for item in payload["references"] if item["verdict"] == verdict)


def test_the_registry_as_committed_passes(sandbox):
    assert run(sandbox) == [], "the committed literature registry must satisfy its own rules"


def test_accepted_without_evidence_fails(sandbox):
    def mutate(payload):
        first(payload)["evidence"] = []
    assert any("without any evidence" in error for error in run(sandbox, mutate))


def test_accepted_while_unverified_fails(sandbox):
    def mutate(payload):
        first(payload)["verification"]["status"] = "UNVERIFIED"
    assert any("is ACCEPTED while its verification status" in error for error in run(sandbox, mutate))


def test_reference_without_any_identifier_fails(sandbox):
    def mutate(payload):
        first(payload)["identifiers"] = {"doi": None, "arxiv_id": None, "pmid": None, "url": None}
    assert any("carries no identifier" in error for error in run(sandbox, mutate))


def test_apa_string_drifting_from_the_recorded_year_fails(sandbox):
    """The formatted string and the structured fields must describe the same paper."""
    def mutate(payload):
        first(payload)["citation"]["year"] = 1999
    assert any("does not contain the recorded year" in error for error in run(sandbox, mutate))


def test_apa_string_drifting_from_the_recorded_doi_fails(sandbox):
    def mutate(payload):
        record = first(payload)
        record["identifiers"]["doi"] = "10.0000/not-the-recorded-doi"
    assert any("does not contain the recorded DOI" in error for error in run(sandbox, mutate))


def test_supporting_an_unknown_claim_fails(sandbox):
    def mutate(payload):
        first(payload)["supports_claims"] = ["C-99"]
    assert any("supports unknown claim C-99" in error for error in run(sandbox, mutate))


def test_referencing_an_unknown_risk_fails(sandbox):
    def mutate(payload):
        first(payload)["blocking_risks"] = ["RISK-9999"]
    assert any("unknown risk RISK-9999" in error for error in run(sandbox, mutate))


def test_a_conflict_may_not_be_accepted(sandbox):
    def mutate(payload):
        record = first(payload)
        record["verification"]["status"] = "CONFLICT"
        record["verification"]["conflict_note"] = "the source disagrees"
    assert any("ACCEPTED despite a verification conflict" in error for error in run(sandbox, mutate))


def test_rejected_without_a_reason_fails(sandbox):
    def mutate(payload):
        record = first(payload)
        record["verdict"] = "REJECTED"
        record["excluded_reason"] = None
    assert any("REJECTED without an excluded_reason" in error for error in run(sandbox, mutate))


def test_five_baseline_families_fails(sandbox):
    """BENCHMARK_CONTRACT.md requires six comparison arms. Five is a silently missing control."""
    def mutate(payload):
        payload["baseline_families"] = payload["baseline_families"][:5]
    assert any("must be exactly the six" in error for error in run(sandbox, mutate))


def test_selecting_a_candidate_without_naming_one_fails(sandbox):
    def mutate(payload):
        payload["baseline_families"][0]["resolution"] = "CANDIDATE_SELECTED"
        payload["baseline_families"][0]["selected_reference"] = None
    assert any("claims a candidate but names no reference" in error for error in run(sandbox, mutate))


def test_selecting_a_rejected_candidate_fails(sandbox):
    def mutate(payload):
        record = first(payload)
        record["verdict"] = "REJECTED"
        record["excluded_reason"] = "out of scope"
        payload["baseline_families"][0]["resolution"] = "CANDIDATE_SELECTED"
        payload["baseline_families"][0]["selected_reference"] = record["reference_id"]
    assert any("whose verdict does not permit use" in error for error in run(sandbox, mutate))


def test_a_document_citing_an_unknown_literature_id_fails(sandbox):
    (sandbox / "docs/research/RELATED_WORK.md").write_text(
        (sandbox / "docs/research/RELATED_WORK.md").read_text(encoding="utf-8") + "\n\nSee LIT-9999.\n",
        encoding="utf-8",
    )
    assert any("LIT-9999" in error for error in run(sandbox))


def test_an_accepted_reference_absent_from_the_survey_fails(sandbox):
    """An accepted citation nobody reads is still a citation the reader must be able to see."""
    text = (sandbox / "docs/research/RELATED_WORK.md").read_text(encoding="utf-8")
    (sandbox / "docs/research/RELATED_WORK.md").write_text(text.replace("LIT-0001", "the first record"), encoding="utf-8")
    assert any("absent from RELATED_WORK.md" in error for error in run(sandbox))


def test_a_recorded_search_may_not_use_the_reconstructed_escape_hatch(sandbox):
    def mutate(payload):
        search = payload["searches"][0]
        search["protocol_status"] = "RECORDED"
    assert any("NOT RECORDED" in error for error in run(sandbox, mutate))


def test_a_reconstructed_search_must_explain_itself(sandbox):
    def mutate(payload):
        payload["searches"][0]["notes"] = None
    assert any("RECONSTRUCTED without notes" in error for error in run(sandbox, mutate))


def test_the_four_definition_of_done_coverage_areas_must_each_be_covered(sandbox):
    """TASK-0004's definition of done, asserted rather than narrated."""
    def mutate(payload):
        for record in payload["references"]:
            if "graph_faithfulness" in record["coverage_areas"]:
                record["verdict"] = "CONDITIONAL"
    assert any("coverage areas with no ACCEPTED reference: graph_faithfulness" in error for error in run(sandbox, mutate))


def test_a_baseline_candidate_must_carry_a_comparison_block(sandbox):
    def mutate(payload):
        next(item for item in payload["references"] if item["role"] == "baseline_candidate")["comparison"] = None
    assert any("comparison block and role baseline_candidate" in error for error in run(sandbox, mutate))
