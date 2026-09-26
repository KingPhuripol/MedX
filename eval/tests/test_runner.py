"""S8-A12..A18: runner guards, thresholds, ledgers, reproducibility, labelling, schema, isolation, demo.

Ledger tests always use a tmp_path ledger (initialised with genesis entries, s8r); the committed
eval/ledger/ is never written.
"""

from __future__ import annotations

import ast
import hashlib
import json
import re
from pathlib import Path

import pytest

from eval.__main__ import main
from eval.jsonschema_lite import validate
from eval.manifest import Ledger, ManifestError, freeze
from eval.runner import OUTPUT_FILES, RunRefused, _threshold, run
from eval.report import BANNER_NO_REVIEW, BANNER_REVIEW

EVAL_DIR = Path(__file__).resolve().parents[1]
EX = EVAL_DIR / "examples"
MANIFEST = EX / "toy_manifest_test.json"
PREDS = EX / "toy_predictions.jsonl"
CMP = EX / "toy_comparator.jsonl"
ITEMS = {"Model, by modality", "Case Graph", "Provider swap", "Voice Agent", "Department suggestion",
         "Pharma Agent", "Abstention", "Replay / Regenerate"}


@pytest.fixture(autouse=True)
def _isolated_ledger(tmp_path, monkeypatch):
    monkeypatch.setenv("EVAL_LEDGER_DIR", str(tmp_path / "env-ledger"))


@pytest.fixture
def ledger(tmp_path) -> Ledger:
    lg = Ledger(tmp_path / "ledger")
    lg.init()  # s8r: ledgers are never auto-created
    return lg


def variant(tmp_path: Path, name: str, **changes) -> Path:
    m = json.loads(MANIFEST.read_text())
    m["bootstrap"]["n_boot"] = 200  # keep tests fast; the committed toy manifest uses the default 2000
    for k, v in changes.items():
        if v is None:
            m.pop(k, None)
        else:
            m[k] = v
    p = tmp_path / f"{name}.json"
    p.write_text(json.dumps(m, indent=2))
    return p


def cli(ledger: Ledger, *args: str) -> int:
    return main(["--ledger-dir", str(ledger.dir), *args])


def run_cli(ledger: Ledger, manifest: Path, out: Path, preds: Path = PREDS, comparator: Path | None = CMP) -> int:
    args = ["run", "--manifest", str(manifest), "--predictions", str(preds), "--out", str(out)]
    if comparator:
        args += ["--comparator", str(comparator)]
    return cli(ledger, *args)


def assert_refused(rc: int, out: Path) -> None:
    assert rc != 0
    assert not out.exists() or not any(out.iterdir())


def sha(p: Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest()


# ---------------------------------------------------------------- A12


def test_runner_refuses_unfrozen_test(tmp_path, ledger):
    m = variant(tmp_path, "m")
    out = tmp_path / "out"
    assert_refused(run_cli(ledger, m, out), out)
    with pytest.raises(RunRefused, match="frozen"):
        run(m, PREDS, out, CMP, ledger)
    assert ledger._read(ledger.runs_path) == []  # only the genesis entry: nothing recorded


def test_runner_refuses_hash_mismatch(tmp_path, ledger):
    m = variant(tmp_path, "m")
    assert cli(ledger, "freeze", str(m)) == 0
    doc = json.loads(m.read_text())
    doc["thresholds"][0]["value"] = 0.1  # moving a threshold after freezing
    m.write_text(json.dumps(doc))
    out = tmp_path / "out"
    assert_refused(run_cli(ledger, m, out), out)
    with pytest.raises(RunRefused, match="hash mismatch"):
        run(m, PREDS, out, CMP, ledger)
    with pytest.raises(ManifestError, match="different hash"):
        freeze(m, ledger)


def test_runner_refuses_foreign_patient(tmp_path, ledger):
    pids = json.loads(MANIFEST.read_text())["split_patient_list"]
    m = variant(tmp_path, "m", split_patient_list=pids[:-1])
    assert cli(ledger, "freeze", str(m)) == 0
    out = tmp_path / "out"
    assert_refused(run_cli(ledger, m, out), out)
    with pytest.raises(RunRefused, match="not in split_patient_list"):
        run(m, PREDS, out, CMP, ledger)


def test_runner_requires_split_list(tmp_path, ledger):
    m = variant(tmp_path, "m", split_patient_list=None)
    assert cli(ledger, "freeze", str(m)) != 0  # cannot be frozen
    out = tmp_path / "out"
    assert_refused(run_cli(ledger, m, out), out)
    with pytest.raises(RunRefused, match="split_patient_list"):
        run(m, PREDS, out, CMP, ledger)


def test_runner_refuses_resubmission(tmp_path, ledger):
    m = variant(tmp_path, "m")
    assert cli(ledger, "freeze", str(m)) == 0
    assert run_cli(ledger, m, tmp_path / "out1") == 0
    other = tmp_path / "preds2.jsonl"
    lines = PREDS.read_text().splitlines()
    first = json.loads(lines[0])
    first["y_pred"] = []  # a "better" set of predictions submitted after seeing results
    other.write_text("\n".join([json.dumps(first)] + lines[1:]) + "\n")
    out2 = tmp_path / "out2"
    assert_refused(run_cli(ledger, m, out2, preds=other), out2)
    with pytest.raises(RunRefused, match="resubmission"):
        run(m, other, out2, CMP, ledger)
    assert len(ledger.runs("s8-toy-test-0001")) == 1


def test_runner_rerun_same_inputs_ok(tmp_path, ledger):
    m = variant(tmp_path, "m")
    assert cli(ledger, "freeze", str(m)) == 0
    assert cli(ledger, "freeze", str(m)) == 0  # idempotent
    assert len(ledger._read(ledger.frozen_path)) == 1
    out = tmp_path / "out"
    assert run_cli(ledger, m, out) == 0
    before = {f: sha(out / f) for f in OUTPUT_FILES}
    assert run_cli(ledger, m, out) == 0  # same inputs, same directory: identical bytes
    assert {f: sha(out / f) for f in OUTPUT_FILES} == before
    assert len(ledger.runs("s8-toy-test-0001")) == 2
    # a differing existing results file is never overwritten
    (out / "results.md").write_text("tampered")
    assert run_cli(ledger, m, out) != 0
    assert (out / "results.md").read_text() == "tampered"


def test_runner_missing_prediction_errors(tmp_path, ledger):
    """A07 at runner level: a missing prediction is an error; a missing comparator row too."""
    m = variant(tmp_path, "m", split="dev", evaluation_id="s8-toy-dev")
    lines = PREDS.read_text().splitlines()
    rows = [json.loads(x) for x in lines]
    i = next(k for k, r in enumerate(rows) if r["task"] == "department")
    del rows[i]["ranked"]
    bad = tmp_path / "bad.jsonl"
    bad.write_text("".join(json.dumps(r) + "\n" for r in rows))
    out = tmp_path / "out"
    assert_refused(run_cli(ledger, m, out, preds=bad), out)
    cmp_lines = CMP.read_text().splitlines()
    short = tmp_path / "short_cmp.jsonl"
    short.write_text("\n".join(cmp_lines[1:]) + "\n")
    assert_refused(run_cli(ledger, m, out, comparator=short), out)


# ---------------------------------------------------------------- A13


def test_threshold_rules(tmp_path, ledger):
    row = {"point": 0.80, "ci_low": 0.70, "ci_high": 0.90}
    t = lambda op, v, rule: _threshold(row, {"op": op, "value": v, "rule": rule})["status"]  # noqa: E731
    assert t(">=", 0.75, "point") == "met"
    assert t(">=", 0.75, "ci_lower") == "not met"
    assert t("<=", 0.85, "ci_upper") == "not met"
    assert t("<=", 0.95, "ci_upper") == "met"
    assert t(">", 0.70, "ci_lower") == "not met" and t(">=", 0.70, "ci_lower") == "met"
    assert t("<", 0.80, "point") == "not met"
    assert _threshold({"point": None, "ci_low": None, "ci_high": None},
                      {"op": ">=", "value": 0.5, "rule": "point"})["status"] == "undefined"
    # Integration: only predeclared thresholds produce a pass/fail cell.
    m = variant(tmp_path, "m", split="dev", evaluation_id="s8-toy-dev")
    out = tmp_path / "out"
    assert run_cli(ledger, m, out) == 0
    res = json.loads((out / "results.json").read_text())
    declared = {x["metric"] for x in json.loads(m.read_text())["thresholds"]}
    for r in res["rows"]:
        assert bool(r["thresholds"]) == (r["metric_id"] in declared)
    md = (out / "results.md").read_text()
    assert "not declared" in md and "on ci_lower:" in md and "on point:" in md and "on ci_upper:" in md
    by_id = {r["metric_id"]: r for r in res["rows"]}
    th = by_id["cp_hit3"]["thresholds"][0]
    assert th["rule"] == "ci_lower" and th["compared_value"] == by_id["cp_hit3"]["ci_low"]


def test_ledgers_append_only(tmp_path, ledger):
    committed = {p: p.read_bytes() for p in (EVAL_DIR / "ledger").glob("*.jsonl")}
    snapshots = []

    def snap():
        snapshots.append(tuple(p.read_bytes() if p.exists() else b"" for p in (ledger.frozen_path, ledger.runs_path)))

    m1 = variant(tmp_path, "m1")
    m2 = variant(tmp_path, "m2", evaluation_id="s8-toy-test-0002")
    snap()
    cli(ledger, "freeze", str(m1))
    snap()
    run_cli(ledger, m1, tmp_path / "o1")
    snap()
    cli(ledger, "freeze", str(m2))
    snap()
    run_cli(ledger, m2, tmp_path / "o2")
    snap()
    run_cli(ledger, m1, tmp_path / "o1")
    snap()
    run_cli(ledger, m1, tmp_path / "o3", comparator=None)  # refused (different inputs), ledger unchanged
    snap()
    for a, b in zip(snapshots, snapshots[1:]):
        for x, y in zip(a, b):
            assert y.startswith(x)  # earlier lines are never rewritten
    assert snapshots[-1] == snapshots[-2]
    assert len(ledger._read(ledger.frozen_path)) == 2 and len(ledger._read(ledger.runs_path)) == 3
    ledger.verify()  # s8r: still a valid hash chain after every append
    # the committed eval/ledger/ is never written by tests
    assert {p: p.read_bytes() for p in (EVAL_DIR / "ledger").glob("*.jsonl")} == committed


# ---------------------------------------------------------------- A14


def test_byte_reproducible(tmp_path, ledger):
    m = variant(tmp_path, "m")
    freeze(m, ledger)
    run(m, PREDS, tmp_path / "a", CMP, ledger)
    run(m, PREDS, tmp_path / "b", CMP, ledger)
    for f in OUTPUT_FILES:
        assert sha(tmp_path / "a" / f) == sha(tmp_path / "b" / f)
    text = (tmp_path / "a" / "results.json").read_text()
    assert str(tmp_path) not in text and "/Users/" not in text
    res = json.loads(text)
    assert res["frozen_entry_hash"] == ledger.frozen("s8-toy-test-0001")[0]["entry_hash"]  # s8r
    assert res["bootstrap"]["seed"] == 20260926 and res["bootstrap"]["n_boot"] == 200
    assert res["environment"]["numpy_version"] and len(res["predictions_sha256"]) == 64


def test_seed_changes_ci(tmp_path, ledger):
    m1 = variant(tmp_path, "m1", split="dev", evaluation_id="dev-a")
    doc = json.loads(m1.read_text())
    doc["bootstrap"]["seed"] = 1
    m2 = tmp_path / "m2.json"
    m2.write_text(json.dumps(doc))
    r1 = run(m1, PREDS, tmp_path / "a", CMP, ledger)
    r2 = run(m2, PREDS, tmp_path / "b", CMP, ledger)
    b1 = [(r["ci_low"], r["ci_high"]) for r in r1["rows"]]
    b2 = [(r["ci_low"], r["ci_high"]) for r in r2["rows"]]
    assert b1 != b2
    assert [r["point"] for r in r1["rows"]] == [r["point"] for r in r2["rows"]]


# ---------------------------------------------------------------- A15


def test_report_labels(tmp_path, ledger):
    m = variant(tmp_path, "m")
    freeze(m, ledger)
    run(m, PREDS, tmp_path / "t", CMP, ledger)
    md, html = (tmp_path / "t" / "results.md").read_text(), (tmp_path / "t" / "results.html").read_text()
    for text in (md, html):
        assert BANNER_NO_REVIEW in text
        assert "Research prototype" in text and "Synthetic data" in text
        assert "UNFROZEN" not in text
    dev = variant(tmp_path, "dev", split="dev", evaluation_id="s8-toy-dev")
    run(dev, PREDS, tmp_path / "d", CMP, ledger)
    for f in ("results.md", "results.html"):
        text = (tmp_path / "d" / f).read_text()
        assert "UNFROZEN - exploratory (dev split)" in text and BANNER_NO_REVIEW in text
    assert json.loads((tmp_path / "d" / "results.json").read_text())["stamp"] == "UNFROZEN - exploratory (dev split)"
    rev = variant(tmp_path, "rev", split="dev", evaluation_id="s8-toy-rev",
                  expert_review={"done": True, "n_reviewers": 2},
                  dataset={"name": "x", "version": "1", "data_class": "mimic"})
    run(rev, PREDS, tmp_path / "r", CMP, ledger)
    for f in ("results.md", "results.html"):
        text = (tmp_path / "r" / f).read_text()
        assert BANNER_REVIEW in text and BANNER_NO_REVIEW not in text
        assert "Research prototype" in text and "Synthetic data" not in text


def test_report_no_clinical_claims(tmp_path, ledger):
    m = variant(tmp_path, "m")
    freeze(m, ledger)
    run(m, PREDS, tmp_path / "t", CMP, ledger)
    forbidden = re.compile(r"diagnos|clinical efficacy demonstrated|accuracy of diagnosis|clinical efficacy",
                           re.IGNORECASE)
    for f in OUTPUT_FILES:
        text = (tmp_path / "t" / f).read_text()
        for banner in (BANNER_NO_REVIEW, BANNER_REVIEW):
            text = text.replace(banner, "")
        assert not forbidden.search(text), forbidden.search(text)


# ---------------------------------------------------------------- A16


def test_results_schema(tmp_path, ledger):
    m = variant(tmp_path, "m")
    freeze(m, ledger)
    run(m, PREDS, tmp_path / "t", CMP, ledger)
    res = json.loads((tmp_path / "t" / "results.json").read_text())
    schema = json.loads((EVAL_DIR / "schemas" / "results.schema.json").read_text())
    assert validate(res, schema) == []
    keys = ("point", "ci_low", "ci_high", "ci_level", "n_boot", "seed", "n_patients", "n_decision_points")
    assert res["rows"]
    for r in res["rows"]:
        assert all(k in r for k in keys)
        if r["point"] is None:
            assert r["reason"]
        else:
            assert r["ci_low"] is not None and r["ci_high"] is not None and r["ci_low"] <= r["ci_high"]
        assert r["n_patients"] > 0 and r["n_decision_points"] >= r["n_patients"]
    # an invalid results object is rejected by the schema
    bad = dict(res, rows=[{k: v for k, v in res["rows"][0].items() if k != "ci_low"}])
    assert validate(bad, schema)
    # s8r: split coverage is reported for every task, and is required by the schema
    assert {c["task"] for c in res["split_coverage"]} == {r["task"] for r in res["rows"]}
    for c in res["split_coverage"]:
        assert c["n_listed"] == c["n_predicted"] + c["n_missing"] and c["missing_policy"] == "complete"
    assert validate({k: v for k, v in res.items() if k != "split_coverage"}, schema)
    bad_cov = dict(res, split_coverage=[dict(res["split_coverage"][0], missing_policy="dropped")])
    assert validate(bad_cov, schema)


# ---------------------------------------------------------------- A17


def test_eval_isolation():
    forbidden_runtime = {"backend", "app", "casegraph", "web", "slices", "sklearn", "scipy", "socket", "urllib",
                         "http", "requests", "httpx", "aiohttp"}
    forbidden_tests = {"backend", "app", "casegraph", "web", "slices", "urllib", "http", "requests", "httpx",
                       "aiohttp"}  # tests may import socket only to assert it is blocked
    files = sorted(EVAL_DIR.rglob("*.py"))
    assert len(files) >= 8
    violations = []
    for p in files:
        banned = forbidden_tests if "tests" in p.relative_to(EVAL_DIR).parts else forbidden_runtime
        for node in ast.walk(ast.parse(p.read_text(encoding="utf-8"))):
            mods = []
            if isinstance(node, ast.Import):
                mods = [a.name for a in node.names]
            elif isinstance(node, ast.ImportFrom) and node.module and node.level == 0:
                mods = [node.module]
            for mod in mods:
                if mod.split(".")[0] in banned:
                    violations.append(f"{p.relative_to(EVAL_DIR)}: {mod}")
    assert violations == []
    # Fixtures are synthetic and live under eval/.
    for p in (MANIFEST, PREDS, CMP):
        assert EVAL_DIR in p.parents
    assert json.loads(MANIFEST.read_text())["dataset"]["data_class"] == "synthetic"
    assert all(json.loads(x)["patient_id"].startswith("SYN-") for x in PREDS.read_text().splitlines())


@pytest.mark.filterwarnings("ignore:A test tried to use socket.socket")
def test_network_blocked():
    import socket

    from pytest_socket import SocketBlockedError

    with pytest.raises(SocketBlockedError):
        socket.socket(socket.AF_INET, socket.SOCK_STREAM)


# ---------------------------------------------------------------- A18


def test_demo_end_to_end(tmp_path):
    out = tmp_path / "demo"
    assert main(["demo", "--out", str(out)]) == 0
    for f in OUTPUT_FILES:
        assert (out / f).stat().st_size > 0
    res = json.loads((out / "results.json").read_text())
    assert {r["item"] for r in res["rows"]} == ITEMS  # 8/8 Table 3.2 families
    assert res["frozen"] and res["split"] == "test" and res["bootstrap"]["n_boot"] == 2000
    md = (out / "results.md").read_text()
    assert all(item in md for item in ITEMS)
    computed = [c for r in res["rows"] for c in r["comparisons"] if c["status"] == "computed"]
    assert computed and all(c["diff"] is not None for c in computed)
    assert main(["demo", "--out", str(out)]) == 0  # idempotent re-run reproduces the same bytes
