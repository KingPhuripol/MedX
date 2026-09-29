"""Fixtures for the i2 comparison tests. Synthetic data only; every ledger is a tmp ledger.

The S1r dataset is generated into a tmp dir with ``python -m data_factory generate`` in a subprocess (no import of
``data_factory`` under ``eval_i2/``). The frozen test-split run here is a tmp-ledger contract check of the harness
(hashes, completeness, labels, reproducibility); it never touches ``eval/ledger`` or ``eval/results``.
Research prototype - not for clinical use.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

from eval.ledger_chain import Ledger
from eval.manifest import freeze

REPO = Path(__file__).resolve().parents[2]
SEED = 20260926
N_BOOT = 200


@pytest.fixture(autouse=True)
def _isolated_default_ledger(tmp_path, monkeypatch):
    monkeypatch.setenv("EVAL_LEDGER_DIR", str(tmp_path / "env-ledger"))


@pytest.fixture(scope="session")
def ds(tmp_path_factory) -> Path:
    out = tmp_path_factory.mktemp("s1r") / "v1"
    env = {**os.environ, "PYTHONPATH": f"{REPO}{os.pathsep}{REPO / 'backend'}"}
    subprocess.run([sys.executable, "-m", "data_factory", "generate", "--seed", str(SEED), "--out", str(out)],
                   check=True, cwd=REPO, env=env, capture_output=True)
    return out


@pytest.fixture(scope="session")
def i2_run(ds, tmp_path_factory):
    """Manifests (n_boot=200) -> freeze both in a tmp ledger -> run dev and test once each."""
    from eval_i2 import pipeline

    root = tmp_path_factory.mktemp("i2run")
    mdir = root / "manifests"
    paths = pipeline.make_manifests(ds, mdir, n_boot=N_BOOT)
    ledger = Ledger(root / "ledger")
    ledger.init()
    for p in paths:
        freeze(p, ledger)
    shutil.copytree(root / "ledger", root / "ledger-after-freeze")
    out = root / "out"
    for split in ("dev", "test"):
        pipeline.run_split(split, ds, mdir, out, root / "ledger")
    return {"root": root, "manifests": mdir, "ledger": root / "ledger",
            "ledger_after_freeze": root / "ledger-after-freeze", "out": out}
