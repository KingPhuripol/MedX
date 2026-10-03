"""Gated download/prepare/verify. Nothing here touches the network unless an explicit, approved --execute runs
`huggingface-cli` (not a dependency of this repository).

Required approval format in docs/DECISIONS.md (anything looser does not open the gate). Exactly one section:

    ## 2026-10-04 — DEC-NNNN: approve CT-RATE download
    - **Decision:** APPROVED: CT-RATE download
    - **Approved by:** <name or role>
    - **Scope:** <what, which files, storage plan>

with no line of that section saying not approved / not decided / reject / declin / denied / defer / pending /
postpone / on hold / superseded / revoked / withdrawn, no `## ... open:` heading, and no other section that names
DEC-NNNN together with superseded / revoked / withdrawn."""

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
        "DEC-NNNN must be ONE docs/DECISIONS.md section whose heading carries the id and whose body has the lines",
        "  - **Decision:** APPROVED: CT-RATE download",
        "  - **Approved by:** <name or role>",
        "and nothing like not approved / reject / defer / pending / revoked / superseded.",
    ])


_DENY = re.compile(r"not approved|not decided|reject|declin|denied|defer|pending|postpone|on hold|superseded|"
                   r"revoked|withdrawn|^## .*open:", re.IGNORECASE)
_WITHDRAWN = re.compile(r"superseded|revoked|withdrawn", re.IGNORECASE)
APPROVAL_LINE = "- **Decision:** APPROVED: CT-RATE download"


def _token(ref: str) -> re.Pattern:
    return re.compile(rf"(?<![\w-]){re.escape(ref)}(?!\w)")


def approval_resolves(ref: str, decisions_path: Path = DECISIONS_PATH) -> bool:
    """True only for one well-formed, explicit, unrevoked approval section (format in the module docstring)."""
    if not isinstance(ref, str) or not _DEC.fullmatch(ref) or not decisions_path.is_file():
        return False
    sections = re.split(r"(?m)^## ", decisions_path.read_text(encoding="utf-8"))[1:]
    tok = _token(ref)
    own = [s for s in sections if tok.search(s.splitlines()[0] if s.splitlines() else "")]
    if len(own) != 1:
        return False
    sec = own[0]
    lines = [ln.strip() for ln in ("## " + sec).splitlines()]
    if APPROVAL_LINE not in lines:
        return False
    if not any(ln.startswith("- **Approved by:**") and ln[len("- **Approved by:**"):].strip() for ln in lines):
        return False
    if any(_DENY.search(ln) for ln in lines):
        return False
    return not any(s is not sec and tok.search(s) and _WITHDRAWN.search(s) for s in sections)


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


def _sha256_file(p: Path) -> str:
    h = hashlib.sha256()
    with p.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def verify(root: str | Path, manifest: dict | None = None, volumes: bool = False, *,
           raw_root: str | Path | None = None, record: bool = False) -> dict:
    """Check sizes and git-blob-SHA1 / LFS-SHA256 of the CSV/TXT files. LFS blobs have a pointer-file git oid, so
    only their size (and sha256 when the manifest has one) can be checked by the provider's hashes; without a local
    record they are listed in ``unpinned_lfs``. ``record=True`` writes ``<root>/local_sha256.json`` (revision + sha256
    of every expected file) once, only if every check passes and no record exists; it never overwrites. Later runs
    compare to the record (mismatch or other revision = FAIL). ``root`` must exist and be strictly under ``raw_root``
    (default data/raw); nothing is ever created outside it. Writes verify_report.json under root."""
    raw_root = Path(raw_root) if raw_root is not None else REPO_ROOT / "data" / "raw"
    root = Path(root)
    if not root.is_dir():
        raise RefusedError(f"verify root {root} does not exist (verify never creates directories)")
    rroot, rraw = root.resolve(), raw_root.resolve()
    if rraw not in rroot.parents:
        raise RefusedError(f"verify root must be strictly under {raw_root}")
    root, manifest = rroot, manifest or load_manifest()
    rec_path = root / "local_sha256.json"
    rec = json.loads(rec_path.read_text(encoding="utf-8")) if rec_path.is_file() else None
    results, ok, unpinned = [], True, []
    local: dict[str, str] = {}
    for e in manifest["expected_files"]:
        p = root / e["path"]
        r = {"path": e["path"], "status": "ok", "checked": []}
        if not p.is_file():
            r["status"] = "missing"
        else:
            data = p.read_bytes()
            sha = hashlib.sha256(data).hexdigest()
            local[e["path"]] = sha
            if len(data) != e["size"]:
                r["status"] = f"size mismatch ({len(data)} != {e['size']})"
            r["checked"].append("size")
            if e["lfs"]:
                if e["lfs_sha256"]:
                    r["checked"].append("lfs_sha256")
                    if sha != e["lfs_sha256"]:
                        r["status"] = "lfs_sha256 mismatch"
                elif rec is None:
                    unpinned.append(e["path"])
            else:
                r["checked"].append("git_blob_sha1")
                if git_blob_sha1(data) != e["git_blob_sha1"]:
                    r["status"] = "git_blob_sha1 mismatch"
            if rec is not None:
                r["checked"].append("local_sha256")
                if rec.get("files", {}).get(e["path"]) != sha:
                    r["status"] = "local_sha256 mismatch"
        ok &= r["status"] == "ok"
        results.append(r)
    local_record = "none"
    if rec is not None:
        local_record = "compared"
        if rec.get("revision") != manifest["revision"]:
            ok, local_record = False, "revision mismatch"
    elif record and ok:
        rec_path.write_text(json.dumps({"revision": manifest["revision"], "files": dict(sorted(local.items()))},
                                       indent=2, sort_keys=True) + "\n", encoding="utf-8")
        local_record, unpinned = "written", []
    report = {"status": "PASS" if ok else "FAIL", "revision": manifest["revision"], "files": results,
              "local_record": local_record, "unpinned_lfs": sorted(unpinned)}
    if volumes:
        sums = {}
        for p in sorted(root.glob("dataset/*/*/*/*.nii.gz")):
            sums[p.relative_to(root).as_posix()] = _sha256_file(p)
        (root / "volume_sha256.json").write_text(json.dumps(sums, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        report["volume_checksums"] = len(sums)
    (root / "verify_report.json").write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return report
