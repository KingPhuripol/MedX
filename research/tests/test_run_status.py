"""S9R-A13: every launcher outcome after the run directory exists leaves a parseable run.json."""

from __future__ import annotations

import json

import pytest

from research.train import data, launcher, models, trainer

from .conftest import CONFIGS, DRYRUN_MANIFESTS


def _boom(exc):
    def raiser(*args, **kwargs):
        raise exc
    return raiser


def _fault_build(mp):
    mp.setattr(models, "build_model", _boom(RuntimeError("injected: build_model")))


def _fault_param_cap(mp):
    mp.setattr(launcher, "MAX_DRY_RUN_PARAMS", 10)


def _fault_dataset(mp):
    mp.setattr(data, "SyntheticCaseDataset", _boom(ValueError("injected: dataset")))


def _fault_collator(mp):
    mp.setattr(data, "Collator", _boom(TypeError("injected: collator")))


def _fault_optimizer(mp):
    mp.setattr(trainer, "make_optimizer", _boom(RuntimeError("injected: optimizer")))


def _fault_train_step(mp):
    mp.setattr(trainer, "train_steps", _boom(RuntimeError("injected: train step")))


def _fault_checkpoint(mp):
    mp.setattr(trainer, "save_checkpoint", _boom(OSError(28, "injected: No space left on device")))


def _fault_environment(mp):
    mp.setattr(launcher, "environment", _boom(ImportError("injected: environment")))


FAULTS = {
    "build_model": (_fault_build, "RuntimeError", 0),
    "param_cap": (_fault_param_cap, "LaunchRefused", 0),
    "dataset": (_fault_dataset, "ValueError", 0),
    "collator": (_fault_collator, "TypeError", 0),
    "optimizer": (_fault_optimizer, "RuntimeError", 0),
    "train_step": (_fault_train_step, "RuntimeError", 0),
    "checkpoint": (_fault_checkpoint, "OSError", 2),  # ckpt_every 2: fails when saving after step 2
    "environment": (_fault_environment, "ImportError", 0),
}


def _launch(tmp_path, stage="stage3"):
    out = tmp_path / "out"
    rc = launcher.main(["--config", str(CONFIGS[stage]), "--manifest", str(DRYRUN_MANIFESTS[stage]), "--dry-run",
                        "--output-root", str(out)])
    runs = sorted(out.glob("dryrun-*/run.json"))
    return rc, runs


@pytest.mark.parametrize("point", list(FAULTS))
def test_run_json_on_every_exception(point, tmp_path, monkeypatch, capsys):
    inject, error_type, steps = FAULTS[point]
    inject(monkeypatch)
    rc, runs = _launch(tmp_path)
    assert rc == launcher.EXIT_FAILED == 3
    assert len(runs) == 1
    meta = json.loads(runs[0].read_text(encoding="utf-8"))
    assert meta["status"] == "failed"
    assert meta["error_type"] == error_type and meta["error"]
    assert meta["steps_completed"] == steps
    assert meta["traceback_tail"] and meta["experiment_id"] == "dryrun-s3"
    assert "Traceback" in capsys.readouterr().err
    assert not list(runs[0].parent.glob(".run.json.*"))  # atomic writes leave no temp files


def test_run_json_written_before_model_build(tmp_path, monkeypatch):
    seen = []
    real = models.build_model

    def spy(cfg, *, dry_run):
        seen.append([json.loads(p.read_text())["status"] for p in (tmp_path / "out").glob("dryrun-*/run.json")])
        return real(cfg, dry_run=dry_run)

    monkeypatch.setattr(models, "build_model", spy)
    rc, runs = _launch(tmp_path)
    assert rc == 0 and seen == [["running"]]
    assert json.loads(runs[0].read_text())["status"] == "completed"


def test_interrupt_still_stopped(tmp_path, monkeypatch):
    real = trainer.train_steps
    calls = []

    def interrupt_on_second(*args, **kwargs):
        calls.append(1)
        if len(calls) == 2:
            raise KeyboardInterrupt
        return real(*args, **kwargs)

    monkeypatch.setattr(trainer, "train_steps", interrupt_on_second)
    rc, runs = _launch(tmp_path)
    assert rc == launcher.EXIT_INTERRUPTED == 130
    meta = json.loads(runs[0].read_text())
    assert meta["status"] == "stopped" and meta["steps_completed"] == 1
    assert meta["checkpoints"][-1]["interrupted"] is True


def test_interrupt_before_training_still_stopped(tmp_path, monkeypatch):
    monkeypatch.setattr(models, "build_model", _boom(KeyboardInterrupt()))
    rc, runs = _launch(tmp_path)
    assert rc == 130 and json.loads(runs[0].read_text())["status"] == "stopped"


def test_completed_run_records_substitution_events(tmp_path):
    rc, runs = _launch(tmp_path)
    meta = json.loads(runs[0].read_text())
    assert rc == 0 and meta["status"] == "completed" and meta["steps_completed"] == meta["max_steps"]
    assert "substitution_events" in meta and "error_type" not in meta
