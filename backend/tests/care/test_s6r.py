"""Slice s6r: retired test run, v1 test refusal, rules v1.1.0 changelog, dev before/after, held-out test-0002."""

from __future__ import annotations

import hashlib
import json
import re
import shutil
import subprocess

from app.care import evaluate

from .conftest import run

REPO = evaluate.REPO_ROOT
S6 = evaluate.EVAL_DIR
RETIRED_FILES = ("results_test/results.json", "results_test/results.md", "results_test/results.html",
                 "summary_test.json")


def _ledger_runs(eid: str) -> list[dict]:
    lines = (S6 / "ledger" / "runs.jsonl").read_text("utf-8").splitlines()
    return [e for e in map(json.loads, lines) if e.get("evaluation_id") == eid]


def test_retired_label_present():
    for f in RETIRED_FILES:
        assert evaluate.RETIRED_LABEL in (S6 / f).read_text("utf-8"), f
    assert (S6 / "results_test/results.md").read_text("utf-8").splitlines()[0].startswith(
        f"> **RETIRED: {evaluate.RETIRED_LABEL}**")
    assert json.loads((S6 / "summary_test.json").read_text("utf-8"))["retired"]["label"] == evaluate.RETIRED_LABEL


def test_retired_hash_matches_ledger():
    res = json.loads((S6 / "results_test/results.json").read_text("utf-8"))
    info = res.pop("retired")
    sha = hashlib.sha256(evaluate.results_json_bytes(res)).hexdigest()
    assert sha == info["original_results_sha256"]
    assert sha in {e["results_sha256"] for e in _ledger_runs(evaluate.RETIRED_ID)}
    assert info["decision"] == "DECISIONS.md 2026-09-27"


def test_retire_idempotent(tmp_path):
    base = tmp_path / "eval"
    (base / "results_test").mkdir(parents=True)
    for f in RETIRED_FILES:
        shutil.copy(S6 / f, base / f)
    evaluate.retire(base)
    once = {f: (base / f).read_bytes() for f in RETIRED_FILES}
    assert once == {f: (S6 / f).read_bytes() for f in RETIRED_FILES}  # committed files are already retired
    evaluate.retire(base)
    assert {f: (base / f).read_bytes() for f in RETIRED_FILES} == once


def test_no_report_cites_retired_as_test():
    """Only the retired evidence itself (labelled), its ledger/manifest, specs, decisions and code name it."""
    files = subprocess.run(["git", "ls-files"], cwd=REPO, capture_output=True, text=True, check=True).stdout.split()
    allowed = {f"slices/s6/eval/{f}" for f in RETIRED_FILES} | {
        "slices/s6/eval/ledger/runs.jsonl", "slices/s6/eval/ledger/frozen.jsonl", "slices/s6/eval/manifest_test.json",
        "docs/DECISIONS.md", "slices/s6/SPEC.md", "slices/s6r/SPEC.md"}
    hits = []
    for f in files:
        p = REPO / f
        if f in allowed or p.suffix in {".py"} or not p.is_file():
            continue
        try:
            text = p.read_text("utf-8")
        except UnicodeDecodeError:
            continue
        if evaluate.RETIRED_ID in text and evaluate.RETIRED_LABEL not in text:
            hits.append(f)
    assert hits == []


def test_evaluate_refuses_retired_test(tmp_path, dataset, capsys):
    out = tmp_path / "out"
    rc = evaluate.main(["--split", "test", "--dataset", str(dataset.root), "--out-dir", str(out)])
    assert rc == 2 and not out.exists()
    err = capsys.readouterr().err
    assert "DECISIONS.md 2026-09-27" in err and "retired" in err
    assert evaluate.main(["--split", "test", "--dataset", str(dataset.root), "--write-manifest",
                          "--manifest", str(tmp_path / "m.json")]) == 2
    assert not (tmp_path / "m.json").exists()
