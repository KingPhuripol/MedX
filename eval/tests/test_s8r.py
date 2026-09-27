"""S8R-A01..A15: split coverage, hash-chained ledger, non-finite rejection (slice s8r).

Every test uses a tmp_path ledger or a tmp_path git repo; the committed eval/ledger/ is only read
(S8R-A10). Synthetic data only. Research prototype - not for clinical use.
"""

from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path

import numpy as np
import pytest

from eval import metrics as M
from eval.__main__ import main
from eval.bootstrap import paired_cluster_bootstrap
from eval.errors import LedgerIntegrityError, RunRefused
from eval.jsonschema_lite import validate
from eval.ledger_chain import ZERO_HASH, Ledger, entry_hash
from eval.manifest import freeze
from eval.metrics import NonFiniteValueError
from eval.registry import REGISTRY
from eval.runner import OUTPUT_FILES, run, split_coverage

EVAL_DIR = Path(__file__).resolve().parents[1]
REPO = EVAL_DIR.parent
EX = EVAL_DIR / "examples"
MANIFEST = EX / "toy_manifest_test.json"
PREDS = EX / "toy_predictions.jsonl"
CMP = EX / "toy_comparator.jsonl"
BASE_M = json.loads(MANIFEST.read_text())
PIDS = BASE_M["split_patient_list"]
SYS_ROWS = [json.loads(x) for x in PREDS.read_text().splitlines()]
CMP_ROWS = [json.loads(x) for x in CMP.read_text().splitlines()]


@pytest.fixture(autouse=True)
def _isolated_default_ledger(tmp_path, monkeypatch):
    monkeypatch.setenv("EVAL_LEDGER_DIR", str(tmp_path / "env-ledger"))


@pytest.fixture
def ledger(tmp_path) -> Ledger:
    lg = Ledger(tmp_path / "ledger")
    lg.init()
    return lg


# ---------------------------------------------------------------- helpers


def write_manifest(tmp_path: Path, name: str = "m", n_boot: int = 50, **changes) -> Path:
    m = json.loads(json.dumps(BASE_M))
    m["bootstrap"]["n_boot"] = n_boot
    for k, v in changes.items():
        if v is None:
            m.pop(k, None)
        else:
            m[k] = v
    p = tmp_path / f"{name}.json"
    p.write_text(json.dumps(m, indent=2))
    return p


def write_jsonl(path: Path, rows) -> Path:
    path.write_text("".join(json.dumps(r) + "\n" for r in rows))
    return path


def cli(ledger: Ledger, *args: str) -> int:
    return main(["--ledger-dir", str(ledger.dir), *args])


def run_cli(ledger, manifest, out, preds=PREDS, comparator=CMP) -> int:
    args = ["run", "--manifest", str(manifest), "--predictions", str(preds), "--out", str(out)]
    if comparator:
        args += ["--comparator", str(comparator)]
    return cli(ledger, *args)


def ledger_bytes(lg: Ledger) -> tuple[bytes, bytes]:
    return tuple(p.read_bytes() if p.exists() else b"" for p in (lg.frozen_path, lg.runs_path))


def n_files(out: Path) -> int:
    return sum(1 for _ in out.iterdir()) if out.exists() else 0


def assert_refused_clean(rc: int, out: Path, lg: Ledger, before, code: int = 2) -> None:
    assert rc == code
    assert n_files(out) == 0
    assert ledger_bytes(lg) == before  # 0 new ledger lines / bytes


def drop(rows, pred) -> list[dict]:
    return [r for r in rows if not pred(r)]


GIT_C = ["-c", "user.name=s8r-test", "-c", "user.email=s8r@example.invalid", "-c", "commit.gpgsign=false",
         "-c", "core.hooksPath=/dev/null", "-c", "init.defaultBranch=main"]


def git(repo: Path, *args: str) -> subprocess.CompletedProcess:
    env = {k: v for k, v in os.environ.items() if not k.startswith("GIT_")}
    r = subprocess.run(["git", *GIT_C, "-C", str(repo), *args], capture_output=True, text=True, env=env)
    assert r.returncode == 0, r.stderr
    return r


def git_repo(tmp_path: Path) -> Path:
    repo = tmp_path / "repo"
    repo.mkdir()
    git(repo, "init", "-q")
    return repo


def commit_all(repo: Path, msg: str) -> None:
    git(repo, "add", "-A")
    git(repo, "commit", "-q", "-m", msg)


# ================================================================ Coverage (A01-A06)


def test_missing_listed_patient_refuses(tmp_path, ledger, capsys):
    m = write_manifest(tmp_path)
    assert cli(ledger, "freeze", str(m)) == 0
    cases = {
        "one_missing": (lambda r: r["task"] == "care_pathway" and r["patient_id"] == "SYN-P005", 39, 1),
        "all_but_one": (lambda r: r["task"] == "care_pathway" and r["patient_id"] != "SYN-P001", 1, 39),
    }
    for name, (pred, n_pred, n_miss) in cases.items():
        preds = write_jsonl(tmp_path / f"{name}.jsonl", drop(SYS_ROWS, pred))
        cmp_ = write_jsonl(tmp_path / f"{name}_cmp.jsonl", drop(CMP_ROWS, pred))
        out = tmp_path / f"out_{name}"
        before = ledger_bytes(ledger)
        capsys.readouterr()
        assert_refused_clean(run_cli(ledger, m, out, preds, cmp_), out, ledger, before)
        err = capsys.readouterr().err
        assert f"task=care_pathway population=None arm=system n_listed=40 n_predicted={n_pred} n_missing={n_miss}" \
            in err, err
        assert "SYN-P" in err  # example IDs are shown for synthetic data only
    assert ledger._read(ledger.runs_path) == []


def test_missing_in_comparator_refuses(tmp_path, ledger, capsys):
    m = write_manifest(tmp_path)
    assert cli(ledger, "freeze", str(m)) == 0
    cmp_ = write_jsonl(tmp_path / "cmp.jsonl", drop(CMP_ROWS, lambda r: r["task"] == "care_pathway"
                                                   and r["patient_id"] == "SYN-P011"))
    out = tmp_path / "out"
    before = ledger_bytes(ledger)
    assert_refused_clean(run_cli(ledger, m, out, PREDS, cmp_), out, ledger, before)
    err = capsys.readouterr().err
    assert "arm=comparator:single_prompt_no_graph n_listed=40 n_predicted=39 n_missing=1" in err, err


def test_task_patient_list_missing_refuses(tmp_path, ledger, capsys):
    m = write_manifest(tmp_path)
    assert cli(ledger, "freeze", str(m)) == 0
    cases = {
        "ct": (lambda r: r["task"] == "model_ct_seg" and r["patient_id"] == "SYN-P007",
               "task=model_ct_seg population=None arm=system n_listed=20 n_predicted=19 n_missing=1"),
        "pharma_pop": (lambda r: r["task"] == "pharma" and r["patient_id"] == "SYN-P025",
                       "task=pharma population=pharmacist_review arm=system n_listed=15 n_predicted=14 n_missing=1"),
    }
    for name, (pred, expect) in cases.items():
        preds = write_jsonl(tmp_path / f"{name}.jsonl", drop(SYS_ROWS, pred))
        cmp_ = write_jsonl(tmp_path / f"{name}_cmp.jsonl", drop(CMP_ROWS, pred))
        out = tmp_path / f"out_{name}"
        before = ledger_bytes(ledger)
        capsys.readouterr()
        assert_refused_clean(run_cli(ledger, m, out, preds, cmp_), out, ledger, before)
        assert expect in capsys.readouterr().err


def _abst_manifest(tmp_path: Path, metrics=None, n=10, name="abst") -> Path:
    pids = [f"SYN-A{i:02d}" for i in range(1, n + 1)]
    metrics = metrics or [
        {"id": "cov", "item": "Abstention", "task": "abst", "name": "coverage", "params": {}, "primary": False},
        {"id": "selacc", "item": "Abstention", "task": "abst", "name": "selective_accuracy", "params": {},
         "primary": True},
    ]
    return write_manifest(tmp_path, name, n_boot=300, evaluation_id=f"s8r-{name}", split_patient_list=pids,
                          task_patient_lists=None, metrics=metrics, thresholds=[],
                          comparators=[{"name": "always_answer", "tasks": ["abst"]}])


def _abst_rows(pids, comparator=None, wrong=()):
    out = []
    for i, p in enumerate(pids):
        r = {"patient_id": p, "decision_point_id": "T1", "task": "abst", "y_true": "a",
             "y_pred": "b" if p in wrong else "a"}
        if comparator:
            r["comparator"] = comparator
        out.append(r)
    return out


def test_missing_counts_as_abstain(tmp_path, ledger):
    m = _abst_manifest(tmp_path)
    pids = json.loads(m.read_text())["split_patient_list"]
    wrong = {pids[1], pids[4]}
    preds = write_jsonl(tmp_path / "p.jsonl", _abst_rows(pids[:9], wrong=wrong))  # 10 listed, 9 predicted
    cmp_ = write_jsonl(tmp_path / "c.jsonl", _abst_rows(pids[:9], "always_answer"))
    freeze(m, ledger)
    res = run(m, preds, tmp_path / "out", cmp_, ledger)
    by = {r["metric_id"]: r for r in res["rows"]}
    assert by["cov"]["point"] == 0.9  # exactly 9/10
    assert by["selacc"]["point"] == M.selective_accuracy(["a"] * 9, [("b" if p in wrong else "a") for p in pids[:9]])
    assert by["selacc"]["point"] == 7 / 9
    assert by["cov"]["n_patients"] == 10 and by["selacc"]["n_patients"] == 10
    cov = res["split_coverage"][0]
    assert (cov["n_listed"], cov["n_predicted"], cov["n_missing"]) == (10, 9, 1)
    assert cov["missing_policy"] == "counted_as_abstain" and cov["n_imputed_abstain_decision_points"] == 1
    assert cov["imputation_unit"] == "1 decision point per missing patient"
    md = (tmp_path / "out" / "results.md").read_text()
    assert "counted_as_abstain" in md


def test_abstain_imputation_paired(tmp_path, ledger):
    m = _abst_manifest(tmp_path)
    doc = json.loads(m.read_text())
    pids = doc["split_patient_list"]
    # system misses pids[9]; comparator misses pids[9] and pids[3]
    sys_rows = _abst_rows(pids[:9], wrong={pids[2]})
    cmp_rows = _abst_rows(pids[:3] + pids[4:9], "always_answer", wrong={pids[5], pids[6]})
    cov, s_rows, c_rows = split_coverage(doc, sys_rows, cmp_rows)
    s_keys = sorted((r["patient_id"], r["decision_point_id"]) for r in s_rows)
    c_keys = sorted((r["patient_id"], r["decision_point_id"]) for r in c_rows)
    assert s_keys == c_keys  # the comparator shares the imputed keys
    assert (pids[9], "__missing__") in s_keys and len({k[0] for k in s_keys}) == 10
    arms = {a["arm"]: a for a in cov[0]["arms"]}
    assert (arms["system"]["n_missing"], arms["comparator:always_answer"]["n_missing"]) == (1, 2)
    assert arms["comparator:always_answer"]["n_imputed_abstain_decision_points"] == 2
    # End to end: the paired draws are identical because both arms have the same patients in the same order.
    freeze(m, ledger)
    res = run(m, write_jsonl(tmp_path / "p.jsonl", sys_rows), tmp_path / "out",
              write_jsonl(tmp_path / "c.jsonl", cmp_rows), ledger)
    row = {r["metric_id"]: r for r in res["rows"]}["cov"]
    diff = row["comparisons"][0]["diff"]
    assert row["point"] == 0.9 and row["comparisons"][0]["comparator_point"] == 0.8
    s_sorted = sorted(s_rows, key=lambda r: (r["patient_id"], r["decision_point_id"]))
    c_sorted = sorted(c_rows, key=lambda r: (r["patient_id"], r["decision_point_id"]))
    ids = [r["patient_id"] for r in s_sorted]
    assert ids == [r["patient_id"] for r in c_sorted]
    a = np.array([r["y_pred"] is not None for r in s_sorted], float)
    b = np.array([r["y_pred"] is not None for r in c_sorted], float)
    ref = paired_cluster_bootstrap(ids, lambda i: float(a[i].mean()), ids, lambda i: float(b[i].mean()),
                                   n_boot=300, seed=doc["bootstrap"]["seed"])
    assert abs(diff["point"] - 0.1) < 1e-12
    assert abs(diff["ci_low"] - ref.ci_low) < 1e-12 and abs(diff["ci_high"] - ref.ci_high) < 1e-12


def test_mixed_task_missing_refuses(tmp_path, ledger):
    metrics = [
        {"id": "cov", "item": "Abstention", "task": "abst", "name": "coverage", "params": {}, "primary": False},
        {"id": "acc", "item": "Abstention", "task": "abst", "name": "accuracy", "params": {}, "primary": True},
    ]
    m = _abst_manifest(tmp_path, metrics=metrics, name="mixed")
    pids = json.loads(m.read_text())["split_patient_list"]
    freeze(m, ledger)
    out = tmp_path / "out"
    before = ledger_bytes(ledger)
    rc = run_cli(ledger, m, out, write_jsonl(tmp_path / "p.jsonl", _abst_rows(pids[:9])),
                 write_jsonl(tmp_path / "c.jsonl", _abst_rows(pids, "always_answer")))
    assert_refused_clean(rc, out, ledger, before)
    with pytest.raises(RunRefused, match="n_missing=1"):
        run(m, tmp_path / "p.jsonl", out, tmp_path / "c.jsonl", ledger)
    # complete predictions for the same mixed task succeed
    assert run_cli(ledger, m, out, write_jsonl(tmp_path / "p2.jsonl", _abst_rows(pids)),
                   write_jsonl(tmp_path / "c2.jsonl", _abst_rows(pids, "always_answer"))) == 0


def test_split_coverage_reported(tmp_path, ledger):
    m = write_manifest(tmp_path)
    freeze(m, ledger)
    res = run(m, PREDS, tmp_path / "t", CMP, ledger)
    schema = json.loads((EVAL_DIR / "schemas" / "results.schema.json").read_text())
    assert validate(res, schema) == []
    tasks = {r["task"] for r in res["rows"]}
    covered = {c["task"] for c in res["split_coverage"]}
    assert covered == tasks  # 100% of tasks
    for c in res["split_coverage"]:
        assert {"n_listed", "n_predicted", "n_missing", "missing_policy"} <= set(c)
        assert c["n_listed"] == c["n_predicted"] + c["n_missing"]
        for a in c["arms"]:
            assert c["n_listed"] == a["n_predicted"] + a["n_missing"]
    pops = {(c["task"], c["population"]): c["n_listed"] for c in res["split_coverage"]}
    assert pops[("model_ct_seg", None)] == 20 and pops[("pharma", "pharmacist_review")] == 15
    assert pops[("pharma", None)] == 35 and pops[("care_pathway", None)] == 40
    for f in ("results.md", "results.html"):
        text = (tmp_path / "t" / f).read_text()
        assert "Split coverage" in text
        assert all(k in text for k in ("n_listed", "n_predicted", "n_missing", "missing_policy"))
    # dev run without a list: n_listed is null with a reason
    dev = write_manifest(tmp_path, "dev", split="dev", evaluation_id="s8r-dev", split_patient_list=None,
                         task_patient_lists=None)
    res = run(dev, PREDS, tmp_path / "d", CMP, ledger)
    assert all(c["n_listed"] is None and c["reason"] and c["missing_policy"] == "not_checked"
               for c in res["split_coverage"])
    assert "null" in (tmp_path / "d" / "results.md").read_text()


def test_no_silent_omission_property(tmp_path, ledger):
    """200 seeded removal patterns: each run refuses (nothing written) or reports the true n_missing."""
    doc = json.loads(write_manifest(tmp_path, "prop", n_boot=1, split="dev", evaluation_id="s8r-prop").read_text())
    m = tmp_path / "prop.json"
    tl = doc["task_patient_lists"]
    tasks = list(dict.fromkeys(x["task"] for x in doc["metrics"]))
    arm_tasks = [("system", t) for t in tasks] + [(c["name"], t) for c in doc["comparators"] for t in c["tasks"]]
    abst_arms = [a for a in arm_tasks if a[1] == "abstention"]
    rng = np.random.Generator(np.random.PCG64(8))
    n_ok = n_refused = 0
    for it in range(200):
        sys_rows, cmp_rows = list(SYS_ROWS), list(CMP_ROWS)
        for _ in range(int(rng.integers(1, 4))):
            pool = abst_arms if rng.random() < 0.6 else arm_tasks
            arm, task = pool[int(rng.integers(0, len(pool)))]
            rows = sys_rows if arm == "system" else cmp_rows
            mine = [i for i, r in enumerate(rows) if r["task"] == task and r.get("comparator", "system") == arm]
            if not mine:
                continue
            if rng.random() < 0.5:  # remove whole patients
                pats = sorted({rows[i]["patient_id"] for i in mine})
                gone = set(rng.choice(pats, size=int(rng.integers(1, 4)), replace=False).tolist())
                kill = {i for i in mine if rows[i]["patient_id"] in gone}
            else:  # remove individual rows
                kill = set(rng.choice(mine, size=min(len(mine), int(rng.integers(1, 5))), replace=False).tolist())
            rows[:] = [r for i, r in enumerate(rows) if i not in kill]
        out = tmp_path / f"o{it}"
        p = write_jsonl(tmp_path / "p.jsonl", sys_rows)
        c = write_jsonl(tmp_path / "c.jsonl", cmp_rows)
        before = ledger_bytes(ledger)
        try:
            res = run(m, p, out, c, ledger)
        except (RunRefused, ValueError):
            n_refused += 1
            assert n_files(out) == 0 and ledger_bytes(ledger) == before
            continue
        n_ok += 1
        for cov in res["split_coverage"]:
            task, pop = cov["task"], cov["population"]
            key = task if pop is None else f"{task}:{pop}"
            listed = tl.get(key) or (sorted(set().union(*(v for k, v in tl.items() if k.startswith(task + ":"))))
                                     if any(k.startswith(task + ":") for k in tl) else PIDS)
            for a in cov["arms"]:
                name = a["arm"].split(":", 1)[1] if a["arm"].startswith("comparator:") else "system"
                remaining = {r["patient_id"] for r in (sys_rows if name == "system" else cmp_rows)
                             if r["task"] == task and r.get("comparator", "system") == name
                             and (pop is None or r.get("population") == pop)}
                true_removed = len(set(listed) - remaining)
                assert a["n_missing"] == true_removed, (it, cov, a)
            if task == "abstention":
                for r in res["rows"]:
                    if r["task"] == "abstention":
                        assert r["n_patients"] == cov["n_listed"]
    print(f"property: n_ok={n_ok} n_refused={n_refused}")
    assert n_ok >= 30 and n_refused >= 30, (n_ok, n_refused)


def test_task_patient_lists_validation(tmp_path, ledger, capsys):
    bad_cases = {
        "not_subset": {"model_ct_seg": PIDS[:5] + ["SYN-X999"]},
        "unknown_task": {"no_such_task": PIDS[:5]},
        "unknown_population": {"pharma:somewhere_else": PIDS[:5]},
    }
    for name, tl in bad_cases.items():
        m = write_manifest(tmp_path, name, task_patient_lists=tl)
        out = tmp_path / f"out_{name}"
        assert cli(ledger, "freeze", str(m)) == 3
        assert run_cli(ledger, m, out) == 3
        assert n_files(out) == 0
    nolist = write_manifest(tmp_path, "nolist", split="dev", split_patient_list=None,
                            task_patient_lists={"model_ct_seg": PIDS[:20]})
    assert run_cli(ledger, nolist, tmp_path / "o_nolist") == 3
    assert "requires split_patient_list" in capsys.readouterr().err
    # coverage is checked against the task list when one is declared: CT predictions for 20 patients
    # against a 10-patient list are refused (predictions outside the frozen task list) ...
    narrow = write_manifest(tmp_path, "narrow", evaluation_id="s8r-narrow",
                            task_patient_lists={**BASE_M["task_patient_lists"], "model_ct_seg": PIDS[:10]})
    assert cli(ledger, "freeze", str(narrow)) == 0
    assert run_cli(ledger, narrow, tmp_path / "o_narrow") == 2
    assert "not on the frozen task patient list" in capsys.readouterr().err
    # ... and without task lists, the CT task is checked against the full split list (20 missing).
    full = write_manifest(tmp_path, "full", evaluation_id="s8r-full", task_patient_lists=None)
    assert cli(ledger, "freeze", str(full)) == 0
    assert run_cli(ledger, full, tmp_path / "o_full") == 2
    assert "task=model_ct_seg population=None arm=system n_listed=40 n_predicted=20 n_missing=20" \
        in capsys.readouterr().err


# ================================================================ Ledger (A07-A11, A15)


def _populate(tmp_path: Path, lg: Ledger, n: int = 2) -> Path:
    """n freezes (distinct evaluation ids) and one run each; returns the first manifest."""
    first = None
    for i in range(n):
        m = write_manifest(tmp_path, f"lm{i}", n_boot=20, evaluation_id=f"s8r-ledger-{i}")
        assert cli(lg, "freeze", str(m)) == 0
        assert run_cli(lg, m, tmp_path / f"lo{i}") == 0
        first = first or m
    return first


def test_ledger_chain_valid(tmp_path, ledger):
    _populate(tmp_path, ledger, 3)
    summary = ledger.verify()
    assert summary["frozen"]["entries"] == 4 and summary["runs"]["entries"] == 4
    assert cli(ledger, "ledger", "verify") == 0
    for name, path in (("frozen", ledger.frozen_path), ("runs", ledger.runs_path)):
        prev = ZERO_HASH
        raw = path.read_bytes()
        assert raw.endswith(b"\n")
        for i, line in enumerate(raw[:-1].split(b"\n")):
            e = json.loads(line)
            assert {"seq", "prev_hash", "entry_hash", "ledger", "kind"} <= set(e)
            assert e["seq"] == i and e["ledger"] == name and e["prev_hash"] == prev
            assert e["entry_hash"] == entry_hash(e)
            assert json.dumps(e, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode() == line
            assert e["kind"] == ("genesis" if i == 0 else {"frozen": "freeze", "runs": "run"}[name])
            prev = e["entry_hash"]


def _tamper_case(tmp_path: Path, ledger: Ledger, mutate) -> None:
    m = _populate(tmp_path, ledger, 2)
    mutate(ledger)
    before = ledger_bytes(ledger)
    out = tmp_path / "after"
    assert_refused_clean(run_cli(ledger, m, out), out, ledger, before)
    m2 = write_manifest(tmp_path, "new", evaluation_id="s8r-new")
    assert cli(ledger, "freeze", str(m2)) == 2
    assert ledger_bytes(ledger) == before
    assert cli(ledger, "ledger", "verify") == 2
    with pytest.raises(LedgerIntegrityError):
        run(m, PREDS, out, CMP, ledger)
    assert n_files(out) == 0


def _lines(p: Path) -> list[bytes]:
    return p.read_bytes()[:-1].split(b"\n")


def _write_lines(p: Path, lines: list[bytes]) -> None:
    p.write_bytes(b"\n".join(lines) + b"\n")


def test_ledger_tamper_edit_refuses(tmp_path, ledger):
    def edit(lg):
        lines = _lines(lg.frozen_path)
        e = json.loads(lines[1])
        e["sha256"] = ("0" if e["sha256"][0] != "0" else "1") + e["sha256"][1:]  # one byte of an earlier entry
        lines[1] = json.dumps(e, sort_keys=True, separators=(",", ":")).encode()
        _write_lines(lg.frozen_path, lines)

    _tamper_case(tmp_path, ledger, edit)


def test_ledger_tamper_delete_line_refuses(tmp_path, ledger):
    def delete_middle(lg):
        lines = _lines(lg.runs_path)
        assert len(lines) == 3
        _write_lines(lg.runs_path, [lines[0], lines[2]])

    _tamper_case(tmp_path, ledger, delete_middle)


def test_ledger_tamper_delete_file_refuses(tmp_path, ledger):
    _tamper_case(tmp_path, ledger, lambda lg: lg.frozen_path.unlink())
    assert not ledger.frozen_path.exists()  # never re-created


def test_ledger_tamper_reorder_whitespace_refuses(tmp_path):
    def reorder(lg):
        lines = _lines(lg.runs_path)
        _write_lines(lg.runs_path, [lines[0], lines[2], lines[1]])

    def whitespace(lg):
        lines = _lines(lg.frozen_path)
        lines[1] = lines[1].replace(b",", b", ", 1)
        _write_lines(lg.frozen_path, lines)

    for i, mutate in enumerate((reorder, whitespace)):
        d = tmp_path / f"case{i}"
        d.mkdir()
        lg = Ledger(d / "ledger")
        lg.init()
        _tamper_case(d, lg, mutate)


def test_ledger_tail_truncation_git_anchor(tmp_path):
    repo = git_repo(tmp_path)
    lg = Ledger(repo / "eval" / "ledger")
    lg.init()
    m = _populate(tmp_path, lg, 2)
    commit_all(repo, "eval(ledger): freeze and run")
    assert lg.verify()["runs"]["git_anchor"] == "HEAD prefix ok"
    lines = _lines(lg.runs_path)
    _write_lines(lg.runs_path, lines[:-1])  # tail truncation: the chain alone is still valid
    copy = Ledger(tmp_path / "untracked-copy")
    copy.dir.mkdir()
    copy.frozen_path.write_bytes(lg.frozen_path.read_bytes())
    copy.runs_path.write_bytes(lg.runs_path.read_bytes())
    copy.verify()  # outside git the truncation is invisible ...
    before = ledger_bytes(lg)
    out = tmp_path / "after"
    assert_refused_clean(run_cli(lg, m, out), out, lg, before)  # ... the git anchor catches it
    assert cli(lg, "freeze", str(write_manifest(tmp_path, "x", evaluation_id="s8r-x"))) == 2
    with pytest.raises(LedgerIntegrityError, match="byte prefix"):
        lg.verify()
    # --git-history: a committed rewrite (truncation committed on top) is detected
    commit_all(repo, "truncate")
    lg.verify()
    with pytest.raises(LedgerIntegrityError, match="append-only"):
        lg.verify(git_history=True)
    assert cli(lg, "ledger", "verify", "--git-history") == 2


def test_ledger_missing_not_autocreated(tmp_path):
    lg = Ledger(tmp_path / "never")
    m = write_manifest(tmp_path)
    out = tmp_path / "out"
    assert cli(lg, "freeze", str(m)) == 2
    assert run_cli(lg, m, out) == 2
    dev = write_manifest(tmp_path, "dev", split="dev", evaluation_id="s8r-dev")
    assert run_cli(lg, dev, out) == 2  # dev runs verify the ledger too
    with pytest.raises(LedgerIntegrityError, match="never auto-created"):
        freeze(m, lg)
    assert not lg.dir.exists() and n_files(out) == 0
    # a default ledger dir pointing at a fresh directory is refused, too
    assert main(["run", "--manifest", str(dev), "--predictions", str(PREDS), "--out", str(out)]) == 2


def test_ledger_init_guards(tmp_path):
    lg = Ledger(tmp_path / "a" / "ledger")
    assert main(["ledger", "init", "--ledger-dir", str(lg.dir)]) == 0
    assert lg.verify()["frozen"]["entries"] == 1
    assert main(["ledger", "init", "--ledger-dir", str(lg.dir)]) == 2  # files exist
    with pytest.raises(RunRefused, match="already exist"):
        lg.init()
    lg.runs_path.unlink()  # one file present is also refused
    assert main(["ledger", "init", "--ledger-dir", str(lg.dir)]) == 2
    repo = git_repo(tmp_path)
    tracked = Ledger(repo / "ledger")
    tracked.init()
    commit_all(repo, "ledger genesis")
    git(repo, "rm", "-q", "-r", "ledger")
    commit_all(repo, "remove ledger")
    assert not tracked.dir.exists()
    assert main(["--ledger-dir", str(tracked.dir), "ledger", "init"]) == 2  # path has git history
    with pytest.raises(RunRefused, match="git history"):
        tracked.init()
    assert not tracked.frozen_path.exists()


def test_committed_ledger_tracked_and_valid():
    files = ["eval/ledger/frozen.jsonl", "eval/ledger/runs.jsonl"]
    r = subprocess.run(["git", "-C", str(REPO), "ls-files", "--error-unmatch", *files], capture_output=True)
    assert r.returncode == 0, r.stderr
    for f in files:
        assert subprocess.run(["git", "-C", str(REPO), "check-ignore", "-q", f]).returncode == 1
    attrs = (REPO / ".gitattributes").read_text()
    assert "eval/ledger/*.jsonl -text -merge" in attrs
    assert "!eval/ledger/*.jsonl" in (REPO / ".gitignore").read_text()
    lg = Ledger(EVAL_DIR / "ledger")
    s = lg.verify(git_history=True)
    assert s["frozen"]["git_anchor"] == s["runs"]["git_anchor"] == "HEAD prefix ok"
    assert s["frozen"]["committed_versions"] >= 1
    assert main(["--ledger-dir", str(lg.dir), "ledger", "verify", "--git-history"]) == 0
    assert not (EVAL_DIR / "ledger" / ".gitkeep").exists()


def test_ledger_readme_policy(capsys):
    text = (EVAL_DIR / "ledger" / "README.md").read_text()
    assert len(text.splitlines()) <= 40
    for section in ("## Location", "## Format", "## Commit policy"):
        assert section in text
    for phrase in ("main", "eval(ledger): freeze <evaluation_id>", "eval(ledger): run <evaluation_id>",
                   "never amended, rebased, squashed or force-pushed", "never by editing lines",
                   "not detectable locally"):
        assert phrase in text, phrase
    with pytest.raises(SystemExit):
        main(["ledger", "--help"])
    help_text = capsys.readouterr().out
    assert "never amended, rebased, squashed or force-pushed" in help_text and "eval(ledger): freeze" in help_text


def test_real_data_requires_committed_ledger(tmp_path, capsys):
    mimic = {"name": "toy-as-mimic", "version": "1", "data_class": "mimic"}
    m = write_manifest(tmp_path, "mimic", n_boot=20, evaluation_id="s8r-mimic", dataset=mimic)
    # (a) untracked ledger (a fresh --ledger-dir outside git)
    loose = Ledger(tmp_path / "loose")
    loose.init()
    assert cli(loose, "freeze", str(m)) == 0
    before = ledger_bytes(loose)
    assert_refused_clean(run_cli(loose, m, tmp_path / "oa"), tmp_path / "oa", loose, before)
    assert "not committed in git" in capsys.readouterr().err
    # (b) tracked, but the freeze line is uncommitted
    repo = git_repo(tmp_path)
    lg = Ledger(repo / "eval" / "ledger")
    lg.init()
    commit_all(repo, "ledger genesis")
    assert cli(lg, "freeze", str(m)) == 0
    before = ledger_bytes(lg)
    assert_refused_clean(run_cli(lg, m, tmp_path / "ob"), tmp_path / "ob", lg, before)
    err = capsys.readouterr().err
    assert "uncommitted lines" in err and "SYN-P" not in err
    commit_all(repo, "eval(ledger): freeze s8r-mimic")
    assert run_cli(lg, m, tmp_path / "ok1") == 0  # committed freeze -> succeeds
    # (c) the previous run line is uncommitted
    before = ledger_bytes(lg)
    assert_refused_clean(run_cli(lg, m, tmp_path / "oc"), tmp_path / "oc", lg, before)
    commit_all(repo, "eval(ledger): run s8r-mimic")
    assert run_cli(lg, m, tmp_path / "ok2") == 0
    # synthetic data is exempt (tests stay hermetic)
    syn = write_manifest(tmp_path, "syn", n_boot=20, evaluation_id="s8r-syn")
    assert cli(loose, "freeze", str(syn)) == 0 and run_cli(loose, syn, tmp_path / "osyn") == 0


def test_ledger_has_no_patient_ids(tmp_path, ledger):
    _populate(tmp_path, ledger, 2)
    abst = _abst_manifest(tmp_path)
    pids = json.loads(abst.read_text())["split_patient_list"]
    freeze(abst, ledger)
    run(abst, write_jsonl(tmp_path / "p.jsonl", _abst_rows(pids[:8])), tmp_path / "oa",
        write_jsonl(tmp_path / "c.jsonl", _abst_rows(pids, "always_answer")), ledger)
    all_ids = set(PIDS) | set(pids)
    allowed = {"seq", "prev_hash", "entry_hash", "ledger", "kind", "format", "created_at", "evaluation_id",
               "sha256", "frozen_at", "split", "frozen", "manifest_sha256", "predictions_sha256",
               "comparator_sha256", "results_sha256", "recorded_at"}
    n = 0
    for p in (ledger.frozen_path, ledger.runs_path):
        for line in p.read_text().splitlines():
            n += 1
            assert not any(pid in line for pid in all_ids)
            assert "SYN-" not in line
            assert set(json.loads(line)) <= allowed
    assert n == 1 + 3 + 1 + 3


# ================================================================ Non-finite (A12-A14)


LITERALS = ["NaN", "Infinity", "-Infinity", "1e999"]


@pytest.mark.parametrize("literal", LITERALS)
def test_parse_rejects_nonfinite(tmp_path, ledger, capsys, literal):
    m = write_manifest(tmp_path)
    freeze(m, ledger)
    # predictions: replace a latency on line k
    k = next(i for i, r in enumerate(SYS_ROWS) if "latency_s" in r) + 1
    lines = PREDS.read_text().splitlines()
    lines[k - 1] = lines[k - 1].replace('"latency_s":', f'"latency_s":{literal},"_x":', 1)
    bad_p = tmp_path / "bad_preds.jsonl"
    bad_p.write_text("\n".join(lines) + "\n")
    # comparator: same on line j
    j = [i for i, r in enumerate(CMP_ROWS) if "latency_s" in r][2] + 1
    clines = CMP.read_text().splitlines()
    assert '"latency_s":' in clines[j - 1]
    clines[j - 1] = clines[j - 1].replace('"latency_s":', f'"latency_s":{literal},"_x":', 1)
    bad_c = tmp_path / "bad_cmp.jsonl"
    bad_c.write_text("\n".join(clines) + "\n")
    # manifest: a threshold value
    mtext = m.read_text().replace('"value": 0.5', f'"value": {literal}', 1)
    bad_m = tmp_path / "bad_manifest.json"
    bad_m.write_text(mtext)
    m_line = next(i for i, x in enumerate(mtext.splitlines(), 1) if f'"value": {literal}' in x)
    cases = [(m, bad_p, CMP, f"bad_preds.jsonl line {k}"), (m, PREDS, bad_c, f"bad_cmp.jsonl line {j}"),
             (bad_m, PREDS, CMP, f"bad_manifest.json line {m_line}")]
    for i, (mm, pp, cc, where) in enumerate(cases):
        out = tmp_path / f"out{i}"
        before = ledger_bytes(ledger)
        capsys.readouterr()
        rc = run_cli(ledger, mm, out, pp, cc)
        err = capsys.readouterr().err
        assert rc == 3 and where in err and "non-finite" in err, (rc, err)
        assert n_files(out) == 0 and ledger_bytes(ledger) == before
    assert cli(ledger, "freeze", str(bad_m)) == 3


def _row(**kw):
    return {"patient_id": "p1", "decision_point_id": "d1", "task": "t", **kw}


def _metric_cases(b):
    """metric name -> (pure-function call with a non-finite value, registry rows, params)."""
    return {
        "accuracy": (lambda: M.accuracy(["a", b], ["a", "a"]), [_row(y_true="a", y_pred=b)], {}),
        "macro_f1": (lambda: M.macro_f1(["a", "b"], ["a", b], ["a", "b"]), [_row(y_true="a", y_pred=b)],
                     {"labels": ["a", "b"]}),
        "multilabel_macro_f1": (lambda: M.multilabel_macro_f1([["a"]], [["a", b]], ["a"]),
                                [_row(y_true=["a"], y_pred=[b])], {"labels": ["a"]}),
        "auroc": (lambda: M.auroc([0, 1], [0.2, b]), [_row(y_true=0, y_score=0.1), _row(y_true=1, y_score=b)], {}),
        "dice": (lambda: M.dice([[1, 0]], [[b, 0]]), [_row(mask_true=[1, 0], mask_pred=[b, 0])], {}),
        "hit_at_k": (lambda: M.hit_at_k([["a", b]], [["a"]], 1), [_row(suggested=["a", b], ordered=["a"])],
                     {"k": 1}),
        "set_prf": (lambda: M.set_prf([["a"]], [["a", b]]), [_row(suggested=["a"], ordered=["a", b])],
                    {"component": "f1"}),
        "calls_per_patient": (lambda: M.calls_per_patient(["p"], [b]), [_row(n_calls=b)], {}),
        "latency_per_patient": (lambda: M.latency_per_patient(["p"], [b]), [_row(latency_s=b)], {}),
        "cost_per_patient": (lambda: M.cost_per_patient(["p"], [b]), [_row(cost=b)], {}),
        "latency_summary": (lambda: M.latency_summary([1.0, b]), [_row(latency_s=b)], {}),
        "response_latency": (lambda: M.response_latency([b]), [_row(response_latency_s=b)], {}),
        "total_time": (lambda: M.total_time([b]), [_row(total_time_s=b)], {}),
        "field_prf": (lambda: M.field_prf([{"a": "x"}], [{"a": b}]),
                      [_row(gold_fields={"a": "x"}, extracted_fields={"a": b})], {"component": "f1"}),
        "topk_accuracy": (lambda: M.topk_accuracy(["a"], [["a", b]], 1), [_row(y_true="a", ranked=["a", b])],
                          {"k": 1}),
        "per_issue_type_pr": (
            lambda: M.per_issue_type_pr([{"gold": [{"type": "dup", "id": b}], "flagged": []}], [], ["dup"]),
            [_row(population="synthetic_error_injection", gold=[{"type": "dup", "id": b}], flagged=[])],
            {"issue_type": "dup", "component": "recall"}),
        "coverage": (lambda: M.coverage(["a", b]), [_row(y_pred=b)], {}),
        "selective_accuracy": (lambda: M.selective_accuracy(["a", "a"], ["a", b]), [_row(y_true="a", y_pred=b)], {}),
        "replay_determinism": (lambda: M.replay_determinism([{"n": "h"}], [{"n": b}]),
                               [_row(original_hashes={"n": "h"}, replay_hashes={"n": b})],
                               {"component": "graph_fraction"}),
        "recomputed_nodes": (lambda: M.recomputed_nodes([b], [3]), [_row(n_recomputed=b, n_nodes_full=3)],
                             {"component": "ratio"}),
    }


def test_metric_cases_cover_registry():
    assert set(_metric_cases(1.0)) == set(REGISTRY) and len(REGISTRY) == 20


@pytest.mark.parametrize("value", ["nan", "inf", "-inf"])
@pytest.mark.parametrize("metric", sorted(REGISTRY))
def test_metric_rejects_nonfinite(metric, value):
    for bad in (float(value), np.float64(value)):
        pure, rows, params = _metric_cases(bad)[metric]
        with pytest.raises(NonFiniteValueError):
            pure()
        with pytest.raises(NonFiniteValueError):
            REGISTRY[metric](rows, params)


def test_auroc_binary_rejects_nonfinite():
    for bad in (float("nan"), float("inf"), -np.inf, np.float64("nan")):
        with pytest.raises(NonFiniteValueError):
            M.auroc([0, 1, 1], [0.1, 0.9, bad])
        with pytest.raises(NonFiniteValueError):
            M.auroc([0, 1], np.array([0.1, bad]))
        with pytest.raises(NonFiniteValueError):
            M.auroc(["x", "y"], [{"x": 0.2, "y": bad}, {"x": 0.6, "y": 0.4}], mode="multiclass", labels=["x", "y"])
        with pytest.raises(NonFiniteValueError):
            M.auroc([["x"], ["y"]], [[0.2, 0.8], [bad, 0.1]], mode="multilabel", labels=["x", "y"])
        rows = [_row(y_true=0, y_score=0.1), _row(decision_point_id="d2", y_true=1, y_score=bad)]
        for params in ({"mode": "binary"},):
            with pytest.raises(NonFiniteValueError):
                REGISTRY["auroc"](rows, params)
        mrows = [_row(y_true="x", y_score={"x": bad, "y": 0.1})]
        for mode in ("multiclass", "multilabel"):
            r = mrows if mode == "multiclass" else [dict(mrows[0], y_true=["x"])]
            with pytest.raises(NonFiniteValueError):
                REGISTRY["auroc"](r, {"mode": mode, "labels": ["x", "y"]})
    # sanity: finite +large scores still work (inf was the only way to fake an extreme rank)
    assert M.auroc([0, 1], [0.1, 1e300]) == 1.0


def test_dice_rejects_nan_mask():
    gold = np.zeros((2, 2, 2))
    pred = np.zeros((2, 2, 2))
    pred[0, 0, 0] = np.nan  # np.asarray(nan, bool) is True - would have counted as foreground
    for fn in (lambda: M.dice([gold], [pred]), lambda: M.dice_case(gold, pred), lambda: M.dice_summary([gold], [pred]),
               lambda: M.dice([[[0, float("nan")]]], [[[0, 0]]])):
        with pytest.raises(NonFiniteValueError):
            fn()
    with pytest.raises(NonFiniteValueError):
        REGISTRY["dice"]([_row(mask_true=gold.tolist(), mask_pred=pred.tolist())], {})


def test_nan_is_not_abstain():
    for bad in (float("nan"), np.float64("nan")):
        with pytest.raises(NonFiniteValueError):
            M.coverage(["a", bad, None])
        with pytest.raises(NonFiniteValueError):
            M.selective_accuracy(["a", "a"], ["a", bad])
        rows = [_row(y_true="a", y_pred="a"), _row(decision_point_id="d2", y_true="a", y_pred=bad)]
        for name in ("coverage", "selective_accuracy"):
            with pytest.raises(NonFiniteValueError):
                REGISTRY[name](rows, {})
    assert not M._is_missing(float("nan")) and M._is_missing(None)
    # None still counts as abstain
    assert M.coverage(["a", None]) == 0.5 and M.selective_accuracy(["a", "b"], ["a", None]) == 1.0
    rows = [_row(y_true="a", y_pred="a"), _row(decision_point_id="d2", y_true="a", y_pred=None),
            _row(decision_point_id="d3", y_true="a")]
    assert REGISTRY["coverage"](rows, {}).stat(np.arange(3)) == 1 / 3


def test_byte_reproducible_with_frozen_entry_hash(tmp_path, ledger):
    m = write_manifest(tmp_path)
    entry = freeze(m, ledger)
    run(m, PREDS, tmp_path / "a", CMP, ledger)
    run(m, PREDS, tmp_path / "b", CMP, ledger)
    for f in OUTPUT_FILES:
        assert (tmp_path / "a" / f).read_bytes() == (tmp_path / "b" / f).read_bytes()
    res = json.loads((tmp_path / "a" / "results.json").read_text())
    assert res["frozen_entry_hash"] == entry["entry_hash"]
    assert entry["entry_hash"] in (tmp_path / "a" / "results.md").read_text()


def test_refusal_messages_hide_real_patient_ids(tmp_path, ledger, capsys):
    """Refusal/error messages show example patient IDs only for synthetic data (clinical-risk row, s8r)."""
    mimic = {"name": "toy-as-mimic", "version": "1", "data_class": "mimic"}
    m = write_manifest(tmp_path, "mimic_dev", n_boot=20, split="dev", evaluation_id="s8r-mimic-dev", dataset=mimic)
    foreign = write_jsonl(tmp_path / "foreign.jsonl", SYS_ROWS + [dict(SYS_ROWS[0], patient_id="SYN-X999")])
    missing = write_jsonl(tmp_path / "missing.jsonl", drop(SYS_ROWS, lambda r: r["patient_id"] == "SYN-P005"))
    # one decision point of a multi-DP patient removed from the comparator only: key mismatch (exit 3)
    dp = next(r for r in CMP_ROWS if r["task"] == "care_pathway" and r["patient_id"] == "SYN-P001")
    cmp_gap = write_jsonl(tmp_path / "cmp_gap.jsonl", [r for r in CMP_ROWS if r is not dp])
    cases = ((foreign, CMP, 2, "not in split_patient_list"), (missing, CMP, 2, "n_missing=1"),
             (PREDS, cmp_gap, 3, "does not cover the same decision points"))
    for i, (preds, cmp_, code, expect) in enumerate(cases):
        capsys.readouterr()
        rc = run_cli(ledger, m, tmp_path / f"o{i}", preds, cmp_)
        err = capsys.readouterr().err
        assert rc == code and expect in err, (i, rc, err)
        assert "SYN-" not in err, (i, err)
    # synthetic data still shows examples
    syn = write_manifest(tmp_path, "syn_dev", n_boot=20, split="dev", evaluation_id="s8r-syn-dev")
    capsys.readouterr()
    assert run_cli(ledger, syn, tmp_path / "osyn", foreign) == 2
    assert "SYN-X999" in capsys.readouterr().err
