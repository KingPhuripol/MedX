"""S9-A15, A16: committed manifests validate; the validator rejects unapproved or mis-tiered runs."""

from __future__ import annotations

import copy
import json
import subprocess
import sys

import pytest

from research.manifest_validation import validate_manifest

from .conftest import REPO_ROOT, load_json

MANIFEST_DIR = REPO_ROOT / "research" / "manifests"
NOTE = ("Tier-3/4 runs (beyond 1 GPU or 60 min, including any 8x B200 or ~27B full run) require explicit human "
        "approval recorded in docs/DECISIONS.md before launch.")
BASE = MANIFEST_DIR / "smoke-s3-lora-qwen3.8-27b.json"
APPROVAL_HEADING = "2026-10-01 — Approve test run (fixture only)"


def _committed():
    return sorted(MANIFEST_DIR.glob("*.json"))


def test_committed_manifests_valid():
    paths = _committed()
    names = {p.stem for p in paths}
    assert names == {"dryrun-s2", "dryrun-s3"} | {f"smoke-{s}-{c}" for s in ("s2-connector", "s3-lora")
                                                  for c in ("medgemma-27b-it", "qwen3.8-27b", "lingshu-32b")}
    out = subprocess.run([sys.executable, "scripts/validate_manifest.py", *map(str, paths)], cwd=REPO_ROOT,
                         capture_output=True, text=True, timeout=120)
    assert out.returncode == 0, out.stdout + out.stderr
    for p in paths:
        m = load_json(p)
        assert m["status"] == "planned" and m["approval_note"] == NOTE and "approval" not in m
        assert isinstance(m["training"]["seed"], int)
        assert m["data"]["external_api"] is False and m["data"]["locality"] == "local_only"
        assert m["resources"]["budget"]
        if m["experiment_id"].startswith("smoke-"):
            assert m["run_tier"] == 2 and m["resources"]["gpu_count"] == 1 and m["resources"]["max_minutes"] <= 60
            assert all(d["dataset_version"] and d["split_version"] for d in m["data"]["datasets"])
            assert m["model"]["hub_revision"] and len(m["model"]["hub_revision"]) == 40
        else:
            assert m["run_tier"] == 0 and m["resources"]["gpu_count"] == 0 and m["data"]["data_class"] == "synthetic"


def _tier(m, tier, gpus=8, minutes=600):
    m["run_tier"] = tier
    m["resources"].update(gpu_count=gpus, max_minutes=minutes, devices=f"{gpus}x NVIDIA B200")
    return m


def _approval(m, ref=APPROVAL_HEADING, run_id=None):
    m["approval"] = {"decision_ref": ref, "approved_by": "project owner", "date": "2026-10-01",
                     "budget": "80 GPU-hours, USD 640", "run_id": run_id or m["experiment_id"]}
    return m


def _del_seed(m):
    del m["training"]["seed"]
    return m


CASES = {
    "tier3_no_approval": (lambda m: _tier(m, 3), "requires an approval block"),
    "tier4_no_approval": (lambda m: _tier(m, 4), "tier 4 requires an approval block"),
    "tier4_runid_mismatch": (lambda m: _approval(_tier(m, 4), run_id="some-other-run"), "must equal experiment_id"),
    "decision_ref_missing": (lambda m: _approval(_tier(m, 3), ref="2026-01-01 — no such decision"), "not found as a dated heading"),
    "tier2_two_gpus": (lambda m: _tier(m, 2, gpus=2, minutes=60), "gpu_count 2 > 1 requires tier >= 3"),
    "tier2_90min": (lambda m: _tier(m, 2, gpus=1, minutes=90), "max_minutes 90 > 60 requires tier >= 3"),
    "unpinned_running": (lambda m: dict(m, status="running"), "UNPINNED is only allowed while status is planned"),
    "config_hash_mismatch": (lambda m: (m["code"].update(config_sha256="0" * 64), m)[1], "config_sha256 mismatch"),
    "mimic_not_local": (lambda m: (m["data"].update(locality="team_controlled_remote"), m)[1], "requires locality local_only"),
    "missing_seed": (_del_seed, "'seed' is a required property"),
}


@pytest.fixture
def decisions(tmp_path):
    """A DECISIONS.md with one dated heading, used only where the case needs a *valid* reference."""
    path = tmp_path / "DECISIONS.md"
    path.write_text(f"# Decisions\n\n## {APPROVAL_HEADING}\n- fixture\n", encoding="utf-8")
    return path


@pytest.mark.parametrize("case", list(CASES))
def test_validator_rejects(case, decisions):
    mutate, message = CASES[case]
    manifest = mutate(copy.deepcopy(load_json(BASE)))
    # decision_ref_missing checks the real docs/DECISIONS.md; the others use the fixture log so that
    # only the property under test can fail.
    kwargs = {} if case == "decision_ref_missing" else {"decisions_path": decisions}
    errors = validate_manifest(manifest, **kwargs)
    assert errors, case
    assert any(message in e for e in errors), (case, errors)


def test_validator_rejects_cli_exit_code(tmp_path):
    m = _tier(copy.deepcopy(load_json(BASE)), 3)
    path = tmp_path / "tier3.json"
    path.write_text(json.dumps(m))
    out = subprocess.run([sys.executable, "scripts/validate_manifest.py", str(path)], cwd=REPO_ROOT,
                         capture_output=True, text=True, timeout=120)
    assert out.returncode != 0 and "approval" in out.stdout


def test_validator_accepts_approved_tier3(decisions):
    m = _approval(_tier(copy.deepcopy(load_json(BASE)), 3))
    assert validate_manifest(m, decisions_path=decisions) == []
