"""B1: the CT-RATE dataset manifest is complete, schema-valid and consistent with the planner evidence."""

from __future__ import annotations

import copy
import hashlib
import json

import jsonschema
import pytest

from research.data.ctrate import types
from research.data.ctrate.split import DEFAULT_SEED, DEV_FRACTION

from .conftest import REPO_ROOT

MANIFEST = REPO_ROOT / "research/data/ctrate/ctrate.manifest.json"
SCHEMA = REPO_ROOT / "schemas/dataset-manifest.schema.json"
EVIDENCE = REPO_ROOT / "slices/ctrate-loader/evidence/hf_api_snapshot_2026-10-03.json"


def _validator():
    return jsonschema.Draft202012Validator(json.loads(SCHEMA.read_text()))


def _m():
    return json.loads(MANIFEST.read_text())


def test_manifest_schema_valid():
    assert list(_validator().iter_errors(_m())) == []


@pytest.mark.parametrize("field", json.loads(SCHEMA.read_text())["required"])
def test_removed_required_field_fails(field):
    m = _m()
    del m[field]
    assert list(_validator().iter_errors(m)), field


def test_bad_revision_and_extra_field_fail():
    m = _m()
    m["revision"] = "main"
    assert list(_validator().iter_errors(m))
    m = _m()
    m["unexpected"] = 1
    assert list(_validator().iter_errors(m))


def test_pinned_facts_and_evidence_crosscheck():
    m, ev = _m(), json.loads(EVIDENCE.read_text())
    assert m["revision"] == ev["api_root"]["sha"] == types.PINNED_REVISION
    assert m["license"] == {"name": "CC BY-NC-SA 4.0", "url": "https://creativecommons.org/licenses/by-nc-sa/4.0/",
                            "retrieved_on": "2026-10-03"}
    assert m["terms"]["verbatim_sha256"] == hashlib.sha256(ev["extra_gated_prompt"].encode()).hexdigest()
    assert m["access"]["approval_ref"] is None  # no approval recorded by this slice
    files = {e["path"]: e for v in ev["tree"].values() for e in v if e["type"] == "file"}
    assert len(m["expected_files"]) == 8
    for e in m["expected_files"]:
        src = files[e["path"]]
        assert (e["size"], e["git_blob_sha1"]) == (src["size"], src["git_oid"])
        assert e["lfs"] == (src["lfs_sha256"] is not None)
        assert set(e) >= {"size", "git_blob_sha1", "lfs_sha256"}


def test_constants_match_manifest():
    m = _m()
    assert m["split_policy"]["seed"] == DEFAULT_SEED and m["split_policy"]["dev_fraction"] == DEV_FRACTION
    tc = m["time_convention"]
    assert tc["name"] == types.TIME_CONVENTION and tc["anchor"] == types.ANCHOR.isoformat()
    assert m["local_root"] == "data/raw/ctrate"
    assert copy.deepcopy(m)["expected_counts"]["patients"] == 21304
