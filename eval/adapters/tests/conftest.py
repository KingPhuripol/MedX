"""Fixtures for the e1 adapter tests. Synthetic data only; every ledger is a tmp ledger.

The S1r dataset is generated into a tmp dir with ``python -m data_factory generate`` in a subprocess
(no import of ``data_factory.generate`` under ``eval/``). Research prototype - not for clinical use.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

from eval.adapters import inputs
from eval.adapters.inputs import CaseInputs
from eval.ledger_chain import Ledger

REPO = Path(__file__).resolve().parents[3]
SEED = 20260926
N_BOOT = 200


@pytest.fixture(autouse=True)
def _isolated_default_ledger(tmp_path, monkeypatch):
    monkeypatch.setenv("EVAL_LEDGER_DIR", str(tmp_path / "env-ledger"))


def generate(out: Path) -> Path:
    env = {**os.environ, "PYTHONPATH": f"{REPO}{os.pathsep}{REPO / 'backend'}"}
    subprocess.run([sys.executable, "-m", "data_factory", "generate", "--seed", str(SEED), "--out", str(out)],
                   check=True, cwd=REPO, env=env, capture_output=True)
    return out


@pytest.fixture(scope="session")
def ds(tmp_path_factory) -> Path:
    """The S1r v1.1.1 dataset (seed 20260926) in a tmp dir. Read-only: copy it before changing anything."""
    return generate(tmp_path_factory.mktemp("s1r") / "v1")


@pytest.fixture
def ds_copy(ds, tmp_path) -> Path:
    dst = tmp_path / "ds"
    shutil.copytree(ds, dst)
    return dst


@pytest.fixture(scope="session")
def dev_outputs(ds):
    from eval.adapters import pipeline

    return pipeline.system_outputs(ds, "dev")


@pytest.fixture(scope="session")
def e1_run(ds, tmp_path_factory):
    """Manifests (n_boot=200) -> freeze all 4 in a tmp ledger -> run dev and test once each."""
    from eval.adapters import pipeline
    from eval.manifest import freeze

    root = tmp_path_factory.mktemp("e1run")
    mdir = root / "manifests"
    paths = pipeline.make_manifests(ds, mdir, n_boot=N_BOOT)
    ledger = Ledger(root / "ledger")
    ledger.init()
    for p in paths:
        freeze(p, ledger)
    frozen_copy = root / "ledger-after-freeze"
    shutil.copytree(root / "ledger", frozen_copy)
    out = root / "out"
    for split in ("dev", "test"):
        pipeline.run_split(split, ds, mdir, out, root / "ledger")
    return {"root": root, "manifests": mdir, "ledger": root / "ledger", "ledger_after_freeze": frozen_copy,
            "out": out}


# ---------------------------------------------------------------- hand-built mini cases

NURSE_OPEN = "สวัสดีค่ะ วันนี้มาด้วยอาการอะไรคะ"
AS_OF = "2030-01-01T10:00:00+07:00"


def hand_case(cid: str, patient_turns: list[str], vitals: dict | None = None, demo: dict | None = None,
              nurse: tuple[str, ...] = (NURSE_OPEN, "เป็นมานานเท่าไรแล้วคะ", "แพ้ยาอะไรไหมคะ")) -> CaseInputs:
    turns = []
    for i, text in enumerate(patient_turns):
        turns += [("nurse", nurse[i]), ("patient", text)]
    tt = [{"speaker": sp, "spoken_at": f"2030-01-01T09:{i:02d}:00+07:00", "text": tx, "turn_index": i}
          for i, (sp, tx) in enumerate(turns)]
    common = {"patient_ref": "SYNP-9001", "encounter_ref": cid, "provenance": "hand", "version": "hand"}
    items = [{**common, "data_type": "IntakeTranscript", "item_id": f"{cid}-TX", "language": "th", "source": "hand",
              "event_time": tt[0]["spoken_at"], "observed_at": f"2030-01-01T09:{len(tt):02d}:00+07:00",
              "available_at_time": f"2030-01-01T09:{len(tt) + 1:02d}:00+07:00", "turns": tt}]
    if vitals is not None:
        v = {"hr": 80, "rr": 16, "sbp": 120, "dbp": 80, "spo2": 98, "temp_c": 36.8, "consciousness": "A",
             "on_oxygen": False, **vitals}
        items.append({**common, **v, "data_type": "Vitals", "item_id": f"{cid}-VS1", "source": "hand-triage",
                      "event_time": "2030-01-01T08:50:00+07:00", "observed_at": "2030-01-01T08:51:00+07:00",
                      "available_at_time": "2030-01-01T08:52:00+07:00"})
    d = {"age_years": 40, "sex": "male", **(demo or {})}
    items.append({**common, **d, "data_type": "Demographics", "item_id": f"{cid}-DEMO", "source": "hand-reg",
                  "event_time": "2030-01-01T08:40:00+07:00", "observed_at": "2030-01-01T08:40:00+07:00",
                  "available_at_time": "2030-01-01T08:40:00+07:00"})
    snap = {"as_of": AS_OF, "case_id": cid, "patient_ref": "SYNP-9001", "encounter_ref": cid, "items": items}
    inputs.check_time_valid(snap, cid)
    return CaseInputs(cid, "SYNP-9001", {"T1": snap})
