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


# ---------------------------------------------------------------- rules 1.1.0 (S6R-A04)

CHANGELOG = REPO / "backend" / "app" / "care" / "rules" / "CHANGELOG.md"
_DP_ID = re.compile(r"\bSYN[A-Z]*-\d{4}(?::T[12])?\b")
_REF = re.compile(r"\b(?:PMID-\d+|RCP-NEWS-2012|LOINC)\b")


def _entries() -> list[str]:
    text = CHANGELOG.read_text("utf-8")
    return re.split(r"^### ", text.split("## care-rules-1.1.0", 1)[1], flags=re.M)[1:]


def test_rules_changelog_ids_train_dev_only(dataset):
    split_of = {r["case_id"]: r["split"] for r in dataset.rows}
    entries = _entries()
    assert len(entries) >= 2
    for e in entries:
        ids = _DP_ID.findall(e)
        assert ids, e[:60]
        for i in ids:
            assert i.startswith("SYNE-"), i  # never a held-out SYNH/SYNHE id
            assert split_of[i.split(":")[0]] in ("train", "dev"), i


def test_rules_changelog_sources_resolve():
    refs = {r["ref_id"] for r in json.loads((REPO / "data_factory/templates/references.json").read_text("utf-8"))}
    for e in _entries():
        if e.startswith("Explained"):
            continue
        found = _REF.findall(e.split("Sources:", 1)[1])
        assert found and set(found) <= refs, e[:60]


def _v100_rules() -> dict:
    raw = subprocess.run(["git", "show", "72d4c45:backend/app/care/rules/care_rules_v1.json"], cwd=REPO,
                         capture_output=True, check=True).stdout
    doc = json.loads(raw)
    assert doc["version"] == "care-rules-1.0.0"
    return doc


def test_engine_qsofa_news_cofire_sepsis_first(dataset, monkeypatch):
    """R1 regression: qSOFA + NEWS co-fire -> CP-SEPSIS-SCREEN first; alerts and screening identical to 1.0.0."""
    from app.care import engine, mock_rules, ruleset

    snap = dataset.snapshot("dev", "SYNE-0011", "T1")
    new, _ = run(snap, "T1")
    ids = {a.rule_id for a in new.alerts}
    assert "RF-QSOFA" in ids and ids & {"RF-SPO2", "RF-RR", "RF-SBP", "RF-HR", "RF-CONSC", "RF-TEMP"}
    assert [p.code for p in new.pathway_options][:2] == ["CP-SEPSIS-SCREEN", "CP-NEWS-URGENT-REVIEW"]
    old_doc = _v100_rules()
    for mod in (engine, mock_rules):
        monkeypatch.setattr(mod, "rules", lambda: old_doc)
    old, _ = run(snap, "T1")
    assert [p.code for p in old.pathway_options][0] == "CP-NEWS-URGENT-REVIEW"
    dump = lambda r: json.dumps([a.model_dump(mode="json") for a in r.alerts], sort_keys=True)  # noqa: E731
    assert dump(new) == dump(old)
    assert new.red_flag_screening.model_dump_json() == old.red_flag_screening.model_dump_json()
    assert new.escalation_required is old.escalation_required is True
    assert [x.code for x in new.next_information] == [x.code for x in old.next_information]
    assert ruleset.CARE_RULES_VERSION == "care-rules-1.1.0"
