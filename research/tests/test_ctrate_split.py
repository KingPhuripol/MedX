"""B3, B8: patient-level split, determinism, sealed test gold."""

from __future__ import annotations

import inspect
import json

import pytest

from research.data.ctrate.build import build
from research.data.ctrate.loader import load_tree
from research.data.ctrate.split import (DEFAULT_SEED, SealedTestError, assign_patients, gold_labels,
                                        sealed_report_sources, split_manifest)

from . import ctrate_fixture as fx


def _setup(raw, seed=DEFAULT_SEED):
    r = load_tree(raw)
    a = assign_patients((v.patient_ref for v in r.volumes), seed)
    return r, a


def test_same_pid_in_train_and_valid_are_different_patients(ctrate_raw):
    r, a = _setup(ctrate_raw)
    assert a["train_7"] in ("train", "dev") and a["valid_7"] == "test"
    assert len(a) == len({v.patient_ref for v in r.volumes})


def test_no_patient_in_more_than_one_split_across_scans_and_reconstructions(ctrate_raw):
    r, a = _setup(ctrate_raw)
    seen: dict[str, set] = {}
    for it in [*r.volumes, *r.reports, *r.labels]:
        seen.setdefault(it.patient_ref, set()).add(a[it.patient_ref])
    assert all(len(s) == 1 for s in seen.values())
    assert {v.scan_ref for v in r.volumes if v.patient_ref == "train_2"} == {"train_2_a", "train_2_b"}
    assert len({a[v.patient_ref] for v in r.volumes if v.patient_ref == "train_3"}) == 1
    for v in r.volumes:
        assert (a[v.patient_ref] == "test") == (v.split == "valid")


def test_dev_size_is_exactly_round_fraction_of_train_patients(ctrate_raw):
    _, a = _setup(ctrate_raw)
    n_train = sum(k.startswith("train_") for k in a)
    assert n_train == len(fx.TRAIN_PIDS)
    assert sum(v == "dev" for v in a.values()) == round(0.10 * n_train)
    big = assign_patients([f"train_{i}" for i in range(1, 201)])
    assert sum(v == "dev" for v in big.values()) == 20


def test_assignment_takes_patient_keys_only():
    params = list(inspect.signature(assign_patients).parameters)
    assert params == ["patient_keys", "seed", "dev_fraction"]
    with pytest.raises(ValueError):
        assign_patients(["train_1_a"])  # scan ref is not a patient key
    with pytest.raises(ValueError):
        assign_patients(["train_01"])


def test_split_manifest_deterministic_and_seed_effect(ctrate_raw):
    r, a = _setup(ctrate_raw)
    m1 = json.dumps(split_manifest(r, a), sort_keys=True)
    r2, a2 = _setup(ctrate_raw)
    assert m1 == json.dumps(split_manifest(r2, a2), sort_keys=True)
    other = next(s for s in range(1, 50) if {k for k, v in assign_patients(a, s).items() if v == "dev"}
                 != {k for k, v in a.items() if v == "dev"})
    ao = assign_patients(a, other)
    assert {k for k, v in ao.items() if v == "dev"} != {k for k, v in a.items() if v == "dev"}
    assert {k for k, v in ao.items() if v == "test"} == {k for k, v in a.items() if v == "test"}
    assert split_manifest(r, ao, other)["manifest_sha256"] != split_manifest(r, a)["manifest_sha256"]


def test_build_split_manifest_byte_identical_across_runs(ctrate_raw, tmp_path):
    build(ctrate_raw, tmp_path / "b1")
    build(ctrate_raw, tmp_path / "b2")
    assert (tmp_path / "b1/split_manifest.json").read_bytes() == (tmp_path / "b2/split_manifest.json").read_bytes()
    sm = json.loads((tmp_path / "b1/split_manifest.json").read_text())
    assert sm["exclusions"]["by_reason"] == {"provider_no_chest": 1} and sm["revision"]
    assert sm["splits"]["test"]["patients"] == len(fx.VALID_PIDS)


def test_build_refuses_nonempty_out(ctrate_raw, tmp_path):
    build(ctrate_raw, tmp_path / "b1")
    with pytest.raises(FileExistsError):
        build(ctrate_raw, tmp_path / "b1")


def test_test_gold_sealed(ctrate_raw, tmp_path):
    r, a = _setup(ctrate_raw)
    with pytest.raises(SealedTestError):
        gold_labels(r, a, "test")
    with pytest.raises(SealedTestError):
        gold_labels(r, a, "test", purpose="dev_tuning")
    with pytest.raises(SealedTestError):
        sealed_report_sources(r, a, "test")
    assert gold_labels(r, a, "test", purpose="final_eval")
    assert gold_labels(r, a, "train")
    # build: nothing about test is written without --unseal-test
    build(ctrate_raw, tmp_path / "sealed")
    for sub in ("inputs", "gold", "label_sources"):
        assert not (tmp_path / "sealed" / sub / "test").exists()
    build(ctrate_raw, tmp_path / "open", unseal_test=True)
    assert (tmp_path / "open/gold/test").is_dir()


def test_unseal_help_documents_joint_unseal(capsys):
    from research.data.ctrate.__main__ import main
    with pytest.raises(SystemExit):
        main(["build", "--help"])
    out = " ".join(capsys.readouterr().out.split()).lower()
    assert "--unseal-test" in out and "inputs, label sources and gold together" in out
