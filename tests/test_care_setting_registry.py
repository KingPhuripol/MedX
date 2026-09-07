"""Prove the care-setting rules fail when they are broken.

DEC-0016 fixes one evaluated care setting, and `schemas/dataset-feasibility.schema.json`
now requires every surveyed dataset to record the setting its data was collected in.
Two rules carry that: a `care_setting` block is mandatory, and a dataset may only claim
it covers the evaluated setting on a `VERIFIED` basis.

A check that has only ever been seen passing is not evidence. These tests break each
rule and assert the harness objects. The rule underneath both is the one RISK-0014
exists for: a product built for the emergency-department triage point must not be
evaluated on a cohort that was never triaged, and the only thing that keeps those
apart is a machine refusing to accept an unrecorded setting.
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
FEASIBILITY = "project_state/dataset_feasibility.json"


def load_harness(root: Path):
    """Import verify_harness with ROOT pointed at a throwaway copy of the repository."""
    spec = importlib.util.spec_from_file_location(f"verify_harness_cs_{root.name}", ROOT / "scripts/verify_harness.py")
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
    """A copy of just enough of the repository for check_json_and_state to run."""
    shutil.copytree(ROOT / "project_state", tmp_path / "project_state")
    shutil.copytree(ROOT / "schemas", tmp_path / "schemas")
    shutil.copytree(ROOT / "experiments", tmp_path / "experiments")
    return tmp_path


def run(sandbox_root: Path, mutate=None) -> list[str]:
    payload = json.loads((sandbox_root / FEASIBILITY).read_text(encoding="utf-8"))
    if mutate is not None:
        payload = copy.deepcopy(payload)
        mutate(payload)
        (sandbox_root / FEASIBILITY).write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    module = load_harness(sandbox_root)
    checks = module.Checks()
    module.check_json_and_state(checks)
    return checks.errors


def dataset(payload: dict, dataset_id: str) -> dict:
    return next(item for item in payload["datasets"] if item["dataset_id"] == dataset_id)


def test_the_survey_as_committed_passes(sandbox):
    assert run(sandbox) == [], "the committed feasibility survey must satisfy its own rules"


def test_a_dataset_without_a_care_setting_fails(sandbox):
    """The schema makes the block mandatory, so a survey cannot skip the question."""
    def mutate(payload):
        del dataset(payload, "DS-0001")["care_setting"]
    assert any("care_setting" in error for error in run(sandbox, mutate))


def test_verified_care_setting_without_evidence_fails(sandbox):
    """Same rule the other four dimensions carry: VERIFIED must cite where."""
    def mutate(payload):
        record = dataset(payload, "DS-0001")
        assert record["care_setting"]["status"] == "VERIFIED"
        record["evidence"] = []
    assert any("care_setting is VERIFIED without any evidence" in error for error in run(sandbox, mutate))


def test_claiming_coverage_of_the_evaluated_setting_while_unverified_fails(sandbox):
    """DS-0002's provenance was never read, so it may not claim to cover the triage point."""
    def mutate(payload):
        record = dataset(payload, "DS-0002")
        assert record["care_setting"]["status"] == "UNVERIFIED"
        record["care_setting"]["covers_evaluated_setting"] = "YES"
    assert any("claims it covers the evaluated setting" in error for error in run(sandbox, mutate))


def test_declining_to_cover_the_evaluated_setting_carries_no_evidence_burden(sandbox):
    """NO is a legitimate answer — it marks unlinked capability evidence, not a defect."""
    def mutate(payload):
        record = dataset(payload, "DS-0006")
        record["care_setting"]["covers_evaluated_setting"] = "NO"
        record["care_setting"]["status"] = "UNVERIFIED"
    assert run(sandbox, mutate) == []


def test_an_unknown_covers_value_is_rejected_by_the_schema(sandbox):
    def mutate(payload):
        dataset(payload, "DS-0003")["care_setting"]["covers_evaluated_setting"] = "PROBABLY"
    assert run(sandbox, mutate), "the enum must refuse a value outside YES/NO/PARTIAL/UNKNOWN"


def test_no_surveyed_dataset_yet_covers_the_evaluated_setting(sandbox):
    """RISK-0014, asserted rather than narrated.

    This is not a rule the harness enforces — it is a fact about the current survey,
    pinned here so that the day MIMIC-IV-ED lands as DS-0008 (TASK-0031) someone has
    to come and delete this test deliberately, rather than the gap quietly closing
    in a document while the data never changed.
    """
    payload = json.loads((ROOT / FEASIBILITY).read_text(encoding="utf-8"))
    covering = [
        item["dataset_id"]
        for item in payload["datasets"]
        if item["care_setting"]["covers_evaluated_setting"] == "YES"
    ]
    assert covering == [], (
        "a dataset now claims to cover the evaluated triage setting; if that is DS-0008, "
        "close RISK-0014 and delete this test"
    )
