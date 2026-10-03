"""B7: no network, no real data; plan-download is stdout-only; prepare --execute refuses without all 4 gates."""

from __future__ import annotations

import hashlib
import json
import subprocess

import pytest

from research.data.ctrate import access
from research.data.ctrate.__main__ import main

from .conftest import REPO_ROOT

def sec(num="9001", *, head=None, decision="- **Decision:** APPROVED: CT-RATE download",
        by="- **Approved by:** Test Owner", extra=""):
    head = head or f"2026-10-04 — DEC-{num}: approve CT-RATE metadata download (test fixture)"
    return "\n".join(["## " + head, "", decision, by, extra, ""])


DEC = sec()


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
    v = lambda **k: access.verify(tmp_path, man, raw_root=tmp_path.parent, **k)  # noqa: E731
    assert v()["status"] == "PASS"
    (tmp_path / "a.csv").write_bytes(b"synthetic,csv\n!")
    assert v()["status"] == "FAIL"
    (tmp_path / "a.csv").unlink()
    assert v()["files"][0]["status"] == "missing"


def _write(path, text):
    path.write_text("# Decisions\n\n" + text, encoding="utf-8")


ADV = {
    "prefix_id": ("DEC-0001", sec("00012")),
    "not_approved": ("DEC-9001", sec(extra="Not approved: downloading CT-RATE for now.")),
    "deferred": ("DEC-9001", sec(extra="The download is deferred.")),
    "pending": ("DEC-9001", sec(extra="Storage plan pending.")),
    "rejected": ("DEC-9001", sec(extra="Request rejected by the owner.")),
    "open_heading": ("DEC-9001", sec(head="OPEN: DEC-9001 CT-RATE download")),
    "missing_decision_line": ("DEC-9001", sec(decision="- **Decision:** discussed CT-RATE download")),
    "decision_line_not_approved": ("DEC-9001", sec(decision="- **Decision:** APPROVED: CT-RATE metadata only")),
    "empty_approver": ("DEC-9001", sec(by="- **Approved by:**   ")),
    "no_approver": ("DEC-9001", sec(by="")),
    "duplicate_heading": ("DEC-9001", sec() + "\n" + sec()),
    "later_revoked": ("DEC-9001", sec() + "\n## 2026-10-09 — note\n\nDEC-9001 revoked.\n"),
    "later_superseded": ("DEC-9001", sec() + "\n## 2026-10-09 — note\n\nDEC-9001 is superseded by DEC-9002.\n"),
    "id_only_in_body": ("DEC-9001", "## 2026-10-04 — other\n\nDEC-9001\n- **Decision:** APPROVED: CT-RATE download\n"
                        "- **Approved by:** X\n"),
    "bad_ref_shape": ("DEC-90011", sec("90011")),
    "bad_ref_lower": ("dec-9001", sec()),
    "well_formed": ("DEC-9001", sec()),
}


@pytest.mark.parametrize("case", sorted(ADV))
def test_approval_resolves_adversarial(tmp_path, case):
    ref, text = ADV[case]
    _write(tmp_path / "D.md", text)
    assert access.approval_resolves(ref, tmp_path / "D.md") is (case == "well_formed")


def test_approval_other_ids_do_not_interfere(tmp_path):
    _write(tmp_path / "D.md", sec("9002", extra="rejected") + "\n" + sec("9001"))
    assert access.approval_resolves("DEC-9001", tmp_path / "D.md")
    assert not access.approval_resolves("DEC-9002", tmp_path / "D.md")


def test_real_decisions_file_has_no_ctrate_approval():
    assert not access.approval_resolves("DEC-0001") and not access.load_manifest()["access"]["approval_ref"]


def test_plan_download_prints_required_approval_format(capsys):
    assert main(["plan-download"]) == 0
    out = capsys.readouterr().out
    assert "APPROVED: CT-RATE download" in out and "Approved by" in out


@pytest.fixture
def lfs_tree(tmp_path):
    raw = tmp_path / "data_raw"
    root = raw / "ctrate"
    root.mkdir(parents=True)
    body, other = b"aaaa", b"bbbb"
    (root / "a.csv").write_bytes(body)
    (root / "b.csv").write_bytes(other)
    man = {"revision": "1" * 40, "expected_files": [
        {"path": "a.csv", "size": 4, "git_blob_sha1": access.git_blob_sha1(body), "lfs": False, "lfs_sha256": None},
        {"path": "b.csv", "size": 4, "git_blob_sha1": "0" * 40, "lfs": True, "lfs_sha256": None}]}
    return raw, root, man


@pytest.mark.parametrize("case", ["elsewhere", "dotdot", "nonexistent", "symlink_escape"])
def test_verify_refuses_outside_raw(tmp_path, case):
    raw = tmp_path / "data" / "raw"
    raw.mkdir(parents=True)
    (tmp_path / "data" / "processed").mkdir()
    (tmp_path / "elsewhere").mkdir()
    (raw / "link").symlink_to(tmp_path / "elsewhere")
    target = {"elsewhere": tmp_path / "elsewhere", "dotdot": raw / ".." / "processed",
              "nonexistent": raw / "x", "symlink_escape": raw / "link"}[case]
    before = sorted(p.relative_to(tmp_path).as_posix() for p in tmp_path.rglob("*"))
    with pytest.raises(access.RefusedError):
        access.verify(target, {"revision": "1" * 40, "expected_files": []}, raw_root=raw)
    assert sorted(p.relative_to(tmp_path).as_posix() for p in tmp_path.rglob("*")) == before


def test_verify_refuses_raw_root_itself(lfs_tree):
    raw, _, man = lfs_tree
    with pytest.raises(access.RefusedError):
        access.verify(raw, man, raw_root=raw)


def test_verify_record_then_detects_same_size_tamper(lfs_tree):
    raw, root, man = lfs_tree
    r0 = access.verify(root, man, raw_root=raw)
    assert r0["status"] == "PASS" and r0["unpinned_lfs"] == ["b.csv"] and not (root / "local_sha256.json").exists()
    r1 = access.verify(root, man, raw_root=raw, record=True)
    assert r1["status"] == "PASS" and r1["local_record"] == "written" and r1["unpinned_lfs"] == []
    rec = json.loads((root / "local_sha256.json").read_text())
    assert rec["revision"] == "1" * 40 and set(rec["files"]) == {"a.csv", "b.csv"}
    (root / "b.csv").write_bytes(b"bbbX")  # same size
    r2 = access.verify(root, man, raw_root=raw)
    assert r2["status"] == "FAIL" and {f["path"]: f["status"] for f in r2["files"]}["b.csv"] == "local_sha256 mismatch"


def test_verify_record_not_written_if_checks_fail(lfs_tree):
    raw, root, man = lfs_tree
    (root / "a.csv").write_bytes(b"aaaX")
    assert access.verify(root, man, raw_root=raw, record=True)["status"] == "FAIL"
    assert not (root / "local_sha256.json").exists()


def test_verify_record_never_overwrites(lfs_tree):
    raw, root, man = lfs_tree
    access.verify(root, man, raw_root=raw, record=True)
    first = (root / "local_sha256.json").read_bytes()
    (root / "b.csv").write_bytes(b"bbbX")
    r = access.verify(root, man, raw_root=raw, record=True)
    assert r["status"] == "FAIL" and (root / "local_sha256.json").read_bytes() == first


def test_verify_record_revision_mismatch_fails(lfs_tree):
    raw, root, man = lfs_tree
    access.verify(root, man, raw_root=raw, record=True)
    r = access.verify(root, man | {"revision": "2" * 40}, raw_root=raw)
    assert r["status"] == "FAIL" and r["local_record"] == "revision mismatch"


def test_cli_verify_refuses_outside_raw(tmp_path, capsys):
    assert main(["verify", str(tmp_path / "nope")]) == 2
    assert "REFUSED" in capsys.readouterr().err and not (tmp_path / "nope").exists()


def test_repo_has_no_data_or_volumes_tracked():
    listing = subprocess.run(["git", "ls-files"], cwd=REPO_ROOT, capture_output=True, text=True, check=True,
                             timeout=60).stdout.splitlines()
    assert not [f for f in listing if f.startswith("data/")]
    assert not [f for f in listing if f.endswith((".nii", ".nii.gz"))]
