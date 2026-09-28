"""S6R-A02: an identical re-run on a frozen test manifest is a re-render (no ledger line); dev keeps the s8 rule."""

from __future__ import annotations

import json

import pytest

from eval import runner
from eval.__main__ import main
from eval.manifest import Ledger
from eval.runner import OUTPUT_FILES

from .test_runner import CMP, PREDS, variant


@pytest.fixture(autouse=True)
def _isolated_ledger(tmp_path, monkeypatch):
    monkeypatch.setenv("EVAL_LEDGER_DIR", str(tmp_path / "env-ledger"))


@pytest.fixture
def ledger(tmp_path) -> Ledger:
    lg = Ledger(tmp_path / "ledger")
    lg.init()
    return lg


def _run(ledger, m, out, preds=PREDS) -> int:
    return main(["--ledger-dir", str(ledger.dir), "run", "--manifest", str(m), "--predictions", str(preds),
                 "--comparator", str(CMP), "--out", str(out)])


def _counts(ledger) -> tuple[int, int]:
    return len(ledger._read(ledger.runs_path)), len(ledger._read(ledger.frozen_path))


def _frozen_test(tmp_path, ledger):
    m = variant(tmp_path, "m")
    assert main(["--ledger-dir", str(ledger.dir), "freeze", str(m)]) == 0
    return m


def test_test_rerender_no_run_line(tmp_path, ledger, capsys):
    m = _frozen_test(tmp_path, ledger)
    out = tmp_path / "out"
    assert _run(ledger, m, out) == 0
    before = _counts(ledger)
    capsys.readouterr()
    assert _run(ledger, m, out) == 0
    assert "re-render of run seq 1; no ledger line appended" in capsys.readouterr().out
    assert _counts(ledger) == before
    ledger.verify()


def test_dev_rerun_still_appends(tmp_path, ledger):
    m = variant(tmp_path, "m", split="dev", evaluation_id="s8-toy-dev")
    out = tmp_path / "out"
    assert _run(ledger, m, out) == 0
    n = _counts(ledger)[0]
    assert _run(ledger, m, out) == 0
    assert _counts(ledger)[0] == n + 1


def test_test_resubmission_still_refused(tmp_path, ledger):
    m = _frozen_test(tmp_path, ledger)
    assert _run(ledger, m, tmp_path / "out") == 0
    rows = [json.loads(x) for x in PREDS.read_text().splitlines() if x.strip()]
    rows[0] = {**rows[0], "note": "changed"}
    other = tmp_path / "other.jsonl"
    other.write_text("".join(json.dumps(r) + "\n" for r in rows))
    before = _counts(ledger)
    out2 = tmp_path / "out2"
    assert _run(ledger, m, out2, preds=other) == 2
    assert _counts(ledger) == before
    assert not out2.exists()


def test_rerender_new_dir_after_format_change(tmp_path, ledger, monkeypatch):
    m = _frozen_test(tmp_path, ledger)
    out = tmp_path / "out"
    assert _run(ledger, m, out) == 0
    before = _counts(ledger)
    old = {f: (out / f).read_bytes() for f in OUTPUT_FILES}
    real = runner.render_md
    monkeypatch.setattr(runner, "render_md", lambda r: real(r) + "\nformat change\n")
    assert _run(ledger, m, out) == 2  # never overwrite different bytes
    assert {f: (out / f).read_bytes() for f in OUTPUT_FILES} == old
    new = tmp_path / "out_v2"
    assert _run(ledger, m, new) == 0
    assert (new / "results.md").read_text().endswith("format change\n")
    assert _counts(ledger) == before
