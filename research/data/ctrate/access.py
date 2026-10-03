"""Gated download/prepare/verify. Nothing here touches the network unless an explicit, approved --execute runs
`huggingface-cli` (not a dependency of this repository)."""

from __future__ import annotations

import hashlib
import json
import os
import re
import subprocess
from pathlib import Path

from .types import HF_REPO

REPO_ROOT = Path(__file__).resolve().parents[3]
MANIFEST_PATH = REPO_ROOT / "research" / "data" / "ctrate" / "ctrate.manifest.json"
DECISIONS_PATH = REPO_ROOT / "docs" / "DECISIONS.md"
DEFAULT_INCLUDE = ("dataset/metadata/*", "dataset/radiology_text_reports/*", "dataset/multi_abnormality_labels/*")
_DEC = re.compile(r"DEC-[0-9]{4}")


class RefusedError(RuntimeError):
    """A gated action was refused; nothing was executed."""


def load_manifest(path: Path = MANIFEST_PATH) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def plan_download(revision: str | None = None, include: tuple[str, ...] = DEFAULT_INCLUDE) -> str:
    rev = revision or load_manifest()["revision"]
    inc = " ".join(f"--include '{p}'" for p in include)
    return "\n".join([
        "CT-RATE download plan (printed only; nothing is executed). Licence CC BY-NC-SA 4.0, gated, NO redistribution.",
        f"1. Accept the terms at https://huggingface.co/datasets/{HF_REPO} with your own HF account.",
        f"2. huggingface-cli download {HF_REPO} --repo-type dataset --revision {rev} {inc} --local-dir data/raw/ctrate",
        "   (HF_TOKEN in the environment. Volumes are several TB: add volume patterns only after a storage decision.)",
        "3. python -m research.data.ctrate verify data/raw/ctrate",
        "Executing needs: prepare --execute --approval DEC-NNNN --accept-terms, HF_TOKEN set, target under data/raw/.",
    ])


def approval_resolves(ref: str, decisions_path: Path = DECISIONS_PATH) -> bool:
    """The reference must be a DEC-NNNN id that is the heading of a DECISIONS.md section that mentions CT-RATE."""
    if not isinstance(ref, str) or not _DEC.fullmatch(ref) or not decisions_path.is_file():
        return False
    sections = re.split(r"(?m)^## ", decisions_path.read_text(encoding="utf-8"))[1:]
    return any(ref in s.splitlines()[0] and "CT-RATE" in s for s in sections)


def prepare(target: str | Path, *, approval: str | None, accept_terms: bool, execute: bool,
            env: dict | None = None, decisions_path: Path = DECISIONS_PATH, repo_root: Path = REPO_ROOT,
            include: tuple[str, ...] = DEFAULT_INCLUDE) -> list[str]:
    """Return the command that was (or, without execute, would be) run. Refuses unless all four gates hold."""
    env = os.environ if env is None else env
    if not execute:
        return ["(dry run) " + plan_download(include=include)]
    problems = []
    if not approval or not approval_resolves(approval, decisions_path):
        problems.append("--approval must be a DEC-NNNN heading in docs/DECISIONS.md that records CT-RATE access")
    if not env.get("HF_TOKEN"):
        problems.append("HF_TOKEN is not set")
    if not accept_terms:
        problems.append("--accept-terms not given")
    raw_root = (repo_root / "data" / "raw").resolve()
    tgt = Path(target)
    tgt = (repo_root / tgt if not tgt.is_absolute() else tgt).resolve()
    if raw_root != tgt and raw_root not in tgt.parents:
        problems.append("target must be under data/raw/")
    if problems:
        raise RefusedError("; ".join(problems))
    rev = load_manifest()["revision"]
    cmd = ["huggingface-cli", "download", HF_REPO, "--repo-type", "dataset", "--revision", rev,
           *[a for p in include for a in ("--include", p)], "--local-dir", str(tgt)]
    subprocess.run(cmd, check=True, env={**env})  # token travels in the environment, never argv
    return cmd


def git_blob_sha1(data: bytes) -> str:
    return hashlib.sha1(b"blob %d\0" % len(data) + data).hexdigest()  # noqa: S324 - git object id, not security


def verify(root: str | Path, manifest: dict | None = None, volumes: bool = False) -> dict:
    """Check sizes and git-blob-SHA1 / LFS-SHA256 of the CSV/TXT files. LFS blobs have a pointer-file git oid, so
    only their size (and sha256 when the manifest has one) can be checked. Writes verify_report.json under root."""
    root, manifest = Path(root), manifest or load_manifest()
    results, ok = [], True
    for e in manifest["expected_files"]:
        p = root / e["path"]
        r = {"path": e["path"], "status": "ok", "checked": []}
        if not p.is_file():
            r["status"] = "missing"
        else:
            data = p.read_bytes()
            if len(data) != e["size"]:
                r["status"] = f"size mismatch ({len(data)} != {e['size']})"
            r["checked"].append("size")
            if e["lfs"]:
                if e["lfs_sha256"]:
                    r["checked"].append("lfs_sha256")
                    if hashlib.sha256(data).hexdigest() != e["lfs_sha256"]:
                        r["status"] = "lfs_sha256 mismatch"
            else:
                r["checked"].append("git_blob_sha1")
                if git_blob_sha1(data) != e["git_blob_sha1"]:
                    r["status"] = "git_blob_sha1 mismatch"
        ok &= r["status"] == "ok"
        results.append(r)
    report = {"status": "PASS" if ok else "FAIL", "revision": manifest["revision"], "files": results}
    if volumes:
        sums = {}
        for p in sorted(root.glob("dataset/*/*/*/*.nii.gz")):
            h = hashlib.sha256()
            with p.open("rb") as fh:
                for chunk in iter(lambda: fh.read(1 << 20), b""):
                    h.update(chunk)
            sums[p.relative_to(root).as_posix()] = h.hexdigest()
        (root / "volume_sha256.json").write_text(json.dumps(sums, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        report["volume_checksums"] = len(sums)
    root.mkdir(parents=True, exist_ok=True)
    (root / "verify_report.json").write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return report
