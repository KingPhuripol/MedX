"""B5: scripts/temporal_leakage_audit.py --dataset passes on a build and fails on injected future items."""

from __future__ import annotations

import json
import shutil
import subprocess
import sys

from research.data.ctrate.build import build

from .conftest import REPO_ROOT

SCRIPT = REPO_ROOT / "scripts/temporal_leakage_audit.py"


def _run(ds, tmp):
    p = subprocess.run([sys.executable, str(SCRIPT), "--dataset", str(ds), "--report", str(tmp / "rep.json")],
                       capture_output=True, text=True, cwd=REPO_ROOT, timeout=60)
    return p.returncode, p.stdout


def _inject(ds, kind, into):
    case = next((ds / "inputs/train").iterdir())
    src = json.loads((ds / "label_sources/train" / f"{case.name}.json").read_text())
    gold = json.loads((ds / "gold/train" / f"{case.name}.json").read_text())
    item = src["report"] if kind == "report" else gold["labels"]
    if item == "missing" or item is None:  # pick a case that has both
        for c in sorted((ds / "inputs/train").iterdir()):
            s = json.loads((ds / "label_sources/train" / f"{c.name}.json").read_text())
            g = json.loads((ds / "gold/train" / f"{c.name}.json").read_text())
            if s["report"] != "missing" and g["labels"] is not None:
                case, item = c, s["report"] if kind == "report" else g["labels"]
                break
    for name in into:
        p = case / name
        doc = json.loads(p.read_text())
        doc["items"].append(item)
        p.write_text(json.dumps(doc), encoding="utf-8")


def test_pass_on_fixture_build(ctrate_raw, tmp_path):
    ds = tmp_path / "b"
    build(ctrate_raw, ds, unseal_test=True)
    rc, out = _run(ds, tmp_path)
    assert rc == 0, out
    assert json.loads(out)["status"] == "PASS" and json.loads(out)["case_x_T"] > 0


def test_fail_when_report_item_injected_into_snapshot(ctrate_raw, tmp_path):
    ds = tmp_path / "b"
    build(ctrate_raw, ds)
    _inject(ds, "report", ["snapshot_T0.json"])
    rc, out = _run(ds, tmp_path)
    assert rc == 1 and "future items in snapshot" in out


def test_fail_when_label_item_injected_into_journey_and_snapshot(ctrate_raw, tmp_path):
    ds = tmp_path / "b"
    build(ctrate_raw, ds)
    _inject(ds, "labels", ["journey.json", "snapshot_T0.json"])
    rc, out = _run(ds, tmp_path)
    assert rc == 1 and "future items in snapshot" in out


def test_item_times_ordered_in_outputs(ctrate_raw, tmp_path):
    ds = tmp_path / "b"
    build(ctrate_raw, ds)
    case = next((ds / "inputs/train").iterdir()).name
    v = json.loads((ds / "inputs/train" / case / "journey.json").read_text())["items"][0]
    rep = json.loads((ds / "label_sources/train" / f"{case}.json").read_text())["report"]
    lab = json.loads((ds / "gold/train" / f"{case}.json").read_text())["labels"]
    assert v["available_at_time"] < rep["available_at_time"] < lab["available_at_time"]
    shutil.rmtree(ds)
