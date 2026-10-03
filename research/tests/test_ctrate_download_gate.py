"""B7: no network, no real data; plan-download is stdout-only; prepare --execute refuses without all 4 gates."""

from __future__ import annotations

import hashlib
import subprocess

import pytest

from research.data.ctrate import access
from research.data.ctrate.__main__ import main

from .conftest import REPO_ROOT

DEC = "## 2026-10-04 — DEC-9001: approve CT-RATE metadata download (test fixture)\n\nCT-RATE access approved.\n"


@pytest.fixture
def decisions(tmp_path):
    p = tmp_path / "DECISIONS.md"
    p.write_text("# Decisions\n\n" + DEC, encoding="utf-8")
    return p


@pytest.fixture
def no_subprocess(monkeypatch):
    calls = []

    def boom(*a, **k):
        calls.append(a)
        raise AssertionError("subprocess must not be called")

    monkeypatch.setattr(subprocess, "run", boom)
    monkeypatch.setattr(subprocess, "Popen", boom)
    return calls


GOOD = dict(approval="DEC-9001", accept_terms=True, execute=True)
ENV = {"HF_TOKEN": "hf_fake_for_test"}


@pytest.mark.parametrize("override,env,target", [
    ({"approval": None}, ENV, "data/raw/ctrate"),
    ({"approval": "DEC-0001"}, ENV, "data/raw/ctrate"),   # does not resolve to a CT-RATE entry
    ({}, {}, "data/raw/ctrate"),                          # no HF_TOKEN
    ({"accept_terms": False}, ENV, "data/raw/ctrate"),
    ({}, ENV, "data/processed/ctrate"),                   # target outside data/raw
    ({}, ENV, "/tmp/elsewhere"),
    ({}, ENV, "data/raw/../processed"),
])
def test_prepare_execute_refuses(decisions, override, env, target, no_subprocess):
    with pytest.raises(access.RefusedError):
        access.prepare(target, env=env, decisions_path=decisions, **(GOOD | override))
    assert no_subprocess == []


def test_prepare_executes_only_when_all_gates_hold(decisions, monkeypatch):
    seen = {}
    monkeypatch.setattr(subprocess, "run", lambda cmd, **k: seen.update(cmd=cmd, env=k["env"]))
    cmd = access.prepare("data/raw/ctrate", env=ENV, decisions_path=decisions, **GOOD)
    assert cmd[:2] == ["huggingface-cli", "download"] and "--revision" in cmd and cmd == seen["cmd"]
    assert "hf_fake_for_test" not in " ".join(cmd) and seen["env"]["HF_TOKEN"] == "hf_fake_for_test"
    assert str(REPO_ROOT / "data/raw/ctrate") in cmd


def test_cli_refuses_with_nonzero_exit(capsys, monkeypatch, no_subprocess):
    monkeypatch.delenv("HF_TOKEN", raising=False)
    assert main(["prepare", "--execute"]) == 2
    assert "REFUSED" in capsys.readouterr().err and no_subprocess == []


def test_plan_download_prints_only(capsys, no_subprocess, tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    assert main(["plan-download"]) == 0
    out = capsys.readouterr().out
    assert "deeca4d89e9f978d4d1bccd88a55071ddbb146bb" in out and "accept the terms" in out.lower()
    assert list(tmp_path.iterdir()) == [] and no_subprocess == []


def test_verify_checks_size_and_hashes(tmp_path):
    body = b"synthetic,csv\n"
    blob = hashlib.sha1(b"blob %d\0" % len(body) + body).hexdigest()
    man = {"revision": "0" * 40, "expected_files": [
        {"path": "a.csv", "size": len(body), "git_blob_sha1": blob, "lfs": False, "lfs_sha256": None},
        {"path": "b.csv", "size": 3, "git_blob_sha1": "0" * 40, "lfs": True, "lfs_sha256": None}]}
    (tmp_path / "a.csv").write_bytes(body)
    (tmp_path / "b.csv").write_bytes(b"xyz")
    assert access.verify(tmp_path, man)["status"] == "PASS"
    (tmp_path / "a.csv").write_bytes(b"synthetic,csv\n!")
    assert access.verify(tmp_path, man)["status"] == "FAIL"
    (tmp_path / "a.csv").unlink()
    assert access.verify(tmp_path, man)["files"][0]["status"] == "missing"


def test_repo_has_no_data_or_volumes_tracked():
    listing = subprocess.run(["git", "ls-files"], cwd=REPO_ROOT, capture_output=True, text=True, check=True,
                             timeout=60).stdout.splitlines()
    assert not [f for f in listing if f.startswith("data/")]
    assert not [f for f in listing if f.endswith((".nii", ".nii.gz"))]
