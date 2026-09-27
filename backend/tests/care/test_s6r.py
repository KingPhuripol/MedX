"""Slice s6r: retired test run, v1 test refusal, rules v1.1.0 changelog, dev before/after, held-out test-0002."""

from __future__ import annotations

import hashlib
import json
import re
import shutil
import subprocess

import pytest

from app.care import evaluate

from .conftest import run
from .test_api import physician  # noqa: F401  (fixture)

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


# ---------------------------------------------------------------- dev before/after (S6R-A03, A04)


def test_dev_before_after_matches_results():
    doc = json.loads((evaluate.S6R_DIR / "dev_before_after.json").read_text("utf-8"))
    assert doc["label"] == evaluate.LABEL
    for side, eid in (("before", "s6-care-dev-0001"), ("after", "s6-care-dev-0002")):
        res = json.loads((evaluate.paths("dev", eid)["results"] / "results.json").read_text("utf-8"))
        assert doc[side]["evaluation_id"] == eid == res["evaluation_id"]
        rows = {r["metric_id"]: r for r in res["rows"]}
        comp = {c["comparator"]: c for c in rows["care_selective_hit3"]["comparisons"]}
        src = {"coverage": (rows["care_coverage"], ""), "selective_hit3": (rows["care_selective_hit3"], ""),
               "always_answer_hit3_all_evaluable": (comp["always_answer"], "comparator_"),
               "always_answer_hit3_on_answered": (comp["always_answer_on_answered"], "comparator_"),
               "train_prior_hit3": (comp["train_prior"], "comparator_"),
               "ordered_proxy_hit3": (rows["care_ordered_proxy_hit3"], ""),
               "pathway_top1": (rows["care_pathway_top1"], "")}
        assert set(doc[side]["metrics"]) == set(src)
        for k, (row, pre) in src.items():
            cell = doc[side]["metrics"][k]
            for f in ("point", "ci_low", "ci_high", "n_patients", "n_decision_points", "n_patients_scored",
                      "n_decision_points_scored", "exact_ci"):
                assert cell[f] == row.get(pre + f), (side, k, f)
    md = (evaluate.S6R_DIR / "dev_before_after.md").read_text("utf-8")
    assert evaluate.LABEL in md and "s6-care-dev-0002" in md


def test_dev_improvement_without_regression():
    doc = json.loads((evaluate.S6R_DIR / "dev_before_after.json").read_text("utf-8"))
    b, a = doc["before"]["metrics"], doc["after"]["metrics"]
    assert a["selective_hit3"]["point"] >= max(0.80, b["selective_hit3"]["point"])
    assert a["pathway_top1"]["point"] >= b["pathway_top1"]["point"]
    assert a["ordered_proxy_hit3"]["point"] >= b["ordered_proxy_hit3"]["point"]
    assert a["coverage"] == b["coverage"]


# ---------------------------------------------------------------- held-out s6-care-test-0002 (S6R-A09, A10, A11)

HELDOUT_SEED = 20260927
TEST_0002 = evaluate.paths("test", "s6-care-test-0002")


@pytest.fixture(scope="session")
def heldout_root(tmp_path_factory):
    from data_factory.generate import generate

    out = tmp_path_factory.mktemp("care_heldout") / "s6r-heldout"
    generate(HELDOUT_SEED, out, heldout=True)
    return out


def test_manifest_0002_matches_s6_metric_set(heldout_root, monkeypatch):
    old = json.loads((S6 / "manifest_test.json").read_text("utf-8"))
    new = json.loads(TEST_0002["manifest"].read_text("utf-8"))
    for k in ("metrics", "comparators", "thresholds", "bootstrap", "expert_review", "split", "slice",
              "manifest_version"):
        assert new[k] == old[k], k
    meta = json.loads((heldout_root / "manifest.json").read_text("utf-8"))
    assert new["evaluation_id"] == "s6-care-test-0002"
    assert new["dataset"]["version"] == meta["tree_sha256"] and meta["heldout"] is True
    assert f"(seed {HELDOUT_SEED})" in new["split_version"]
    assert len(new["split_patient_list"]) == 72 and all(re.fullmatch(r"SYNH-\d{4}", p)
                                                         for p in new["split_patient_list"])
    monkeypatch.setenv("CARE_DATASET", str(heldout_root))
    assert evaluate.manifest("test", "s6-care-test-0002") == new  # from gold, reproducible


def test_results_0002_complete():
    p = TEST_0002["results"] / "results.json"
    if not p.is_file():
        pytest.skip("s6-care-test-0002 not run yet: freeze + single run pending decision D-s6r-2")
    res = json.loads(p.read_text("utf-8"))
    assert res["evaluation_id"] == "s6-care-test-0002" and res["frozen"] is True
    assert "System Evaluation" in json.dumps(res["labels"])
    assert all(c["missing_policy"] in ("complete", "counted_as_abstain") for c in res["split_coverage"])
    for row in res["rows"]:
        for f in ("point", "ci_low", "ci_high", "n_patients", "n_decision_points"):
            assert f in row
        if row["point"] is not None and (row["ci_low"] == row["ci_high"] or row["unstable"]):
            assert "exact_ci" in row
    summ = json.loads(TEST_0002["summary"].read_text("utf-8"))
    assert summ["underpowered"] == (summ["n_answered_evaluable"] < 30)
    runs = [e for e in _ledger_runs("s6-care-test-0002")]
    assert len(runs) == 1 and runs[0]["frozen"] is True


def test_cases_never_serve_heldout(physician, heldout_root, monkeypatch):
    served = {c["case_id"] for c in physician.get("/api/care/cases").json()["cases"]}
    assert served and not any(c.startswith("SYNH") for c in served)
    monkeypatch.setenv("CARE_DATASET", str(heldout_root))  # held-out has no dev split: nothing is served
    assert physician.get("/api/care/cases").status_code == 503
    assert physician.post("/api/care/cases/SYNHE-0001/assess", json={"decision_point": "T1"}).status_code in (404, 503)
