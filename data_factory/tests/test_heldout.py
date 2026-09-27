"""Slice s6r: generator v1.2.1 held-out mode (S6R-A06, A07, A08, A12). Synthetic data only."""

from __future__ import annotations

import hashlib
import json
import re
import shutil
import subprocess
import sys

import pytest

from data_factory import audit
from data_factory.generate import GENERATOR_VERSION, generate

from .conftest import REPO_ROOT, Dataset, load
from .test_care_gold import V111_INPUTS_SHA256, inputs_sha256

HELDOUT_SEED = 20260927
# v1.2.0 at seed 20260926 (tree 19033a72...): sha over every gold file, *.json with `label_version` removed.
V120_GOLD_SHA256 = "226bc07505c93228fdd935c35b21986f4a570034327a4f69a01a941f5c8ac5ae"
QUOTA_KEYS = ("red_flag", "missing_info", "no_medication", "late_items", "near_miss", "text_near_miss")


@pytest.fixture(scope="session")
def heldout(tmp_path_factory) -> Dataset:
    out = tmp_path_factory.mktemp("heldout") / "s6r-heldout"
    generate(HELDOUT_SEED, out, heldout=True)
    return Dataset(out)


def gold_sha256_without_label_version(root) -> str:
    h = hashlib.sha256()
    for p in sorted((root / "gold").rglob("*")):
        if not p.is_file():
            continue
        if p.suffix == ".json":
            g = load(p)
            g.pop("label_version")
            b = json.dumps(g, sort_keys=True, ensure_ascii=False).encode()
        else:
            b = p.read_bytes()
        h.update(p.relative_to(root).as_posix().encode() + b"\0" + hashlib.sha256(b).hexdigest().encode() + b"\n")
    return h.hexdigest()


def quota_counts(ds: Dataset, split: str) -> dict[str, int]:
    sc = [c["gold"]["scenario"] for c in ds.cases.values() if c["split"] == split]
    return {"red_flag": sum(bool(s["red_flag"]) for s in sc), "missing_info": sum(bool(s["missing"]) for s in sc),
            "no_medication": sum(not s["has_meds"] for s in sc), "late_items": sum(bool(s["late"]) for s in sc),
            "near_miss": sum(bool(s["near_miss"]) for s in sc),
            "text_near_miss": sum(bool(s["text_near_miss"]) for s in sc),
            "pregnancy": sum(bool(s["pregnant"]) for s in sc)}


def test_inputs_unchanged_vs_v120(dataset):
    assert GENERATOR_VERSION == "1.2.1"
    assert inputs_sha256(dataset.root) == V111_INPUTS_SHA256  # v1.2.0 inputs == v1.1.1 inputs (pinned in s6)
    assert gold_sha256_without_label_version(dataset.root) == V120_GOLD_SHA256
    assert {c["gold"]["label_version"] for c in dataset.cases.values()} == {"1.2.1"}
    assert "heldout" not in dataset.manifest


def test_templates_unchanged():
    r = subprocess.run(["git", "diff", "--stat", "c08584c", "--", "data_factory/templates/"], cwd=REPO_ROOT,
                       capture_output=True, text=True, check=True)
    assert r.stdout == ""


def test_heldout_only_test_split(heldout):
    for d in ("inputs", "gold"):
        assert sorted(p.name for p in (heldout.root / d).iterdir() if p.is_dir()) == ["test"]
    assert set(heldout.splits.values()) == {"test"}


def test_heldout_seed_recorded(heldout):
    m = heldout.manifest
    assert m["seed"] == HELDOUT_SEED and m["generator_version"] == "1.2.1" and m["heldout"] is True
    card = (heldout.root / "DATACARD.md").read_text("utf-8")
    assert f"seed `{HELDOUT_SEED}`" in card and "(1.2.1)" in card and "Held-out mode" in card


def test_heldout_size(heldout):
    refs = {c["gold"]["patient_ref"] for c in heldout.cases.values()}
    assert len(heldout.splits) == len(refs) == 72
    per = {}
    for c in heldout.cases.values():
        per[c["gold"]["patient_ref"]] = per.get(c["gold"]["patient_ref"], 0) + 1
    assert sum(1 for n in per.values() if n > 1) == 8
    assert len(heldout.cases) == 80
    assert sum(len(c["gold"]["decision_times"]) for c in heldout.cases.values()) == 160
    assert all(re.fullmatch(r"SYNH-\d{4}", r) for r in refs)
    assert all(re.fullmatch(r"SYNHE-\d{4}", cid) for cid in heldout.cases)


def test_heldout_disjoint_from_all_splits(heldout, dataset):
    refs = set(heldout.splits)
    assert len(dataset.splits) == 180 and not refs & set(dataset.splits)
    assert not set(heldout.cases) & set(dataset.cases)
    committed = set()
    for p in REPO_ROOT.glob("slices/*/eval/**/*.jsonl"):
        for line in p.read_text("utf-8").splitlines():
            if line.strip():
                pid = json.loads(line).get("patient_id")
                if pid:
                    committed.add(pid)
    assert committed and not refs & committed


def test_heldout_case_mix(heldout, dataset):
    v1, h = quota_counts(dataset, "test"), quota_counts(heldout, "test")
    for k in QUOTA_KEYS:
        assert abs(h[k] - 2 * v1[k]) <= 2, (k, h[k], v1[k])


def test_heldout_reproducible(heldout, tmp_path):
    again = generate(HELDOUT_SEED, tmp_path / "again", heldout=True)
    assert again["tree_sha256"] == heldout.manifest["tree_sha256"]


def test_heldout_audit_pass(heldout):
    assert audit.run_audit(heldout.root, write_report=False)["status"] == "PASS"
    r = subprocess.run([sys.executable, "scripts/temporal_leakage_audit.py", "--dataset", str(heldout.root)],
                       cwd=REPO_ROOT, capture_output=True, text=True)
    assert r.returncode == 0, r.stdout[-500:]


def test_audit_bans_care_gold_in_heldout_inputs(heldout, tmp_path):
    root = tmp_path / "planted"
    shutil.copytree(heldout.root, root)
    snap = sorted((root / "inputs" / "test").glob("*/snapshot_T1.json"))[0]
    doc = load(snap)
    doc["items"][0]["care"] = {"next_info": ["NI-ECG-12LEAD"]}
    snap.write_text(json.dumps(doc, ensure_ascii=False), "utf-8")
    rep = audit.run_audit(root, write_report=False)
    assert rep["status"] == "FAIL" and rep["steps"]["gold_separation"].startswith("FAIL")
    r = subprocess.run([sys.executable, "scripts/temporal_leakage_audit.py", "--dataset", str(root)],
                       cwd=REPO_ROOT, capture_output=True, text=True)
    assert r.returncode != 0


@pytest.mark.xfail(strict=True, reason="S6R-A07 pregnancy: held-out 7 vs 2x v1 test 1 (+-2). Pregnancy is not a QUOTAS "
                   "key (it follows the complaint cycle and the roster); needs a planner/owner decision (D-s6r-2)")
def test_heldout_case_mix_pregnancy(heldout, dataset):
    v1, h = quota_counts(dataset, "test"), quota_counts(heldout, "test")
    assert abs(h["pregnancy"] - 2 * v1["pregnancy"]) <= 2, (h["pregnancy"], v1["pregnancy"])
