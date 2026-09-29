"""Durable, tamper-evident, hash-chained ledgers (slice s8r). Research prototype - not for clinical use.

``frozen.jsonl`` and ``runs.jsonl`` each start with a genesis entry. Line ``i`` is the canonical JSON of
an entry with ``seq == i``, ``ledger`` == the file's name, ``prev_hash`` == the previous entry's
``entry_hash`` (64 zeros for genesis) and ``entry_hash = sha256(canonical_bytes(entry minus entry_hash))``.

``verify()`` runs before every freeze and run. A missing file, a bad or non-canonical line, a broken chain,
a seq gap/re-order, or a git-anchor mismatch (the committed ``HEAD`` version is not a byte prefix of the
working file, i.e. tail truncation or an edit of committed lines) raises ``LedgerIntegrityError``.
A missing ledger is never auto-created; ``init()`` only writes genesis files on an absent, history-free path.
Entries hold only evaluation IDs, hashes, seq, timestamps and kind - never patient IDs or data.
"""

from __future__ import annotations

import os
import subprocess
from pathlib import Path
from typing import Any

from .errors import LedgerIntegrityError, RunRefused
from .jsonio import canonical_bytes, loads_strict, sha256_bytes, utc_now
from .metrics import NonFiniteValueError

PKG_DIR = Path(__file__).resolve().parent
DEFAULT_LEDGER_DIR = PKG_DIR / "ledger"
NAMES = ("frozen", "runs")
ZERO_HASH = "0" * 64
FORMAT = "s8r-hash-chain-v1"
APPEND_KINDS = {"frozen": "freeze", "runs": "run"}
_GIT_ENV_DROP = ("GIT_DIR", "GIT_WORK_TREE", "GIT_INDEX_FILE", "GIT_OBJECT_DIRECTORY")


def entry_hash(entry: dict[str, Any]) -> str:
    return sha256_bytes(canonical_bytes({k: v for k, v in entry.items() if k != "entry_hash"}))


def _git(cwd: Path, *args: str) -> subprocess.CompletedProcess[bytes] | None:
    env = {k: v for k, v in os.environ.items() if k not in _GIT_ENV_DROP}
    env["GIT_TERMINAL_PROMPT"] = "0"
    try:
        return subprocess.run(["git", "-C", str(cwd), *args], capture_output=True, env=env, check=False)
    except OSError:
        return None


def _nearest_existing(p: Path) -> Path:
    p = p.resolve()
    while not p.exists():
        p = p.parent
    return p if p.is_dir() else p.parent


def git_location(path: Path) -> tuple[Path, str] | None:
    """(repo root, path relative to root) if ``path`` lies inside a git work tree, else None."""
    r = _git(_nearest_existing(path.parent), "rev-parse", "--show-toplevel")
    if r is None or r.returncode != 0:
        return None
    root = Path(r.stdout.decode().strip()).resolve()
    try:
        rel = path.resolve().relative_to(root)
    except ValueError:
        return None
    return root, rel.as_posix()


def committed_bytes(path: Path, rev: str = "HEAD") -> bytes | None:
    """The version of ``path`` in ``rev`` (None if not in a git repo or not committed there)."""
    loc = git_location(path)
    if loc is None:
        return None
    r = _git(loc[0], "show", f"{rev}:{loc[1]}")
    return r.stdout if r is not None and r.returncode == 0 else None


class Ledger:
    """Append-only, hash-chained JSONL ledgers ``frozen.jsonl`` and ``runs.jsonl``."""

    def __init__(self, directory: str | os.PathLike[str] | None = None):
        d = directory or os.environ.get("EVAL_LEDGER_DIR") or DEFAULT_LEDGER_DIR
        self.dir = Path(d)
        self.frozen_path = self.dir / "frozen.jsonl"
        self.runs_path = self.dir / "runs.jsonl"

    def path(self, name: str) -> Path:
        return {"frozen": self.frozen_path, "runs": self.runs_path}[name]

    # ------------------------------------------------------------ parsing / verification

    def _parse(self, name: str) -> list[dict[str, Any]]:
        p = self.path(name)
        if not p.is_file():
            raise LedgerIntegrityError(
                f"ledger file {p} is missing; ledgers are never auto-created "
                "(a new ledger needs `python -m eval ledger init --ledger-dir DIR` on a history-free path)"
            )
        raw = p.read_bytes()
        if not raw.endswith(b"\n"):
            raise LedgerIntegrityError(f"{p.name}: file is empty or does not end in a newline")
        entries: list[dict[str, Any]] = []
        prev = ZERO_HASH
        for i, line in enumerate(raw[:-1].split(b"\n")):
            where = f"{p.name} line {i + 1}"
            try:
                e = loads_strict(line.decode("utf-8"), p.name, i + 1)
            except (UnicodeDecodeError, ValueError, NonFiniteValueError) as exc:
                raise LedgerIntegrityError(f"{where}: not valid JSON ({exc})") from None
            if not isinstance(e, dict):
                raise LedgerIntegrityError(f"{where}: not a JSON object")
            if canonical_bytes(e) != line:
                raise LedgerIntegrityError(f"{where}: not byte-identical to its canonical form (edited?)")
            if e.get("seq") != i:
                raise LedgerIntegrityError(f"{where}: seq {e.get('seq')!r} != {i} (gap, deletion or re-order)")
            if e.get("ledger") != name:
                raise LedgerIntegrityError(f"{where}: ledger {e.get('ledger')!r} != {name!r}")
            if e.get("prev_hash") != prev:
                raise LedgerIntegrityError(f"{where}: prev_hash does not match the previous entry (broken chain)")
            if e.get("entry_hash") != entry_hash(e):
                raise LedgerIntegrityError(f"{where}: entry_hash does not match the entry content (edited)")
            if (e.get("kind") == "genesis") != (i == 0):
                raise LedgerIntegrityError(f"{where}: genesis must be exactly the first entry")
            if i > 0 and e.get("kind") != APPEND_KINDS[name]:
                raise LedgerIntegrityError(f"{where}: unexpected kind {e.get('kind')!r}")
            prev = e["entry_hash"]
            entries.append(e)
        return entries

    def _check_anchor(self, name: str) -> str:
        p = self.path(name)
        head = committed_bytes(p)
        if head is None:
            return "untracked"
        if not p.read_bytes().startswith(head):
            raise LedgerIntegrityError(
                f"{p.name}: the committed HEAD version is not a byte prefix of the working file "
                "(committed lines were truncated, removed or edited)"
            )
        return "HEAD prefix ok"

    def _check_history(self, name: str) -> int:
        p = self.path(name)
        loc = git_location(p)
        if loc is None or committed_bytes(p) is None:
            raise LedgerIntegrityError(f"{p.name}: not committed in a git repository; no history to verify")
        root, rel = loc
        r = _git(root, "rev-list", "--reverse", "--topo-order", "HEAD", "--", rel)
        if r is None or r.returncode != 0:
            raise LedgerIntegrityError(f"{p.name}: git rev-list failed")
        commits = r.stdout.decode().split()
        prev = b""
        for c in commits:
            s = _git(root, "show", f"{c}:{rel}")
            if s is None or s.returncode != 0:
                raise LedgerIntegrityError(f"{p.name}: deleted in commit {c[:12]}")
            if not s.stdout.startswith(prev):
                raise LedgerIntegrityError(f"{p.name}: commit {c[:12]} is not an append-only extension of its parent")
            prev = s.stdout
        if not p.read_bytes().startswith(prev):
            raise LedgerIntegrityError(f"{p.name}: working file is not an extension of the last committed version")
        return len(commits)

    def verify(self, git_history: bool = False) -> dict[str, Any]:
        """Verify both ledgers. Raises ``LedgerIntegrityError``; returns a summary on success."""
        out: dict[str, Any] = {}
        for name in NAMES:
            entries = self._parse(name)
            info: dict[str, Any] = {"entries": len(entries), "git_anchor": self._check_anchor(name)}
            if git_history:
                info["committed_versions"] = self._check_history(name)
            out[name] = info
        return out

    # ------------------------------------------------------------ creation

    def init(self) -> None:
        """Write genesis entries. Only on an absent path with no git history (a tracked ledger cannot be reset)."""
        existing = [p for p in (self.frozen_path, self.runs_path) if p.exists()]
        if existing:
            raise RunRefused(f"ledger init refused: {', '.join(str(p) for p in existing)} already exist(s)")
        for p in (self.frozen_path, self.runs_path):
            loc = git_location(p)
            if loc is None:
                continue
            r = _git(loc[0], "log", "--all", "--format=%H", "--", loc[1])
            if r is None or r.returncode != 0 or r.stdout.strip():
                raise RunRefused(f"ledger init refused: {loc[1]} has git history; a tracked ledger is never re-created")
        self.dir.mkdir(parents=True, exist_ok=True)
        for name in NAMES:
            g = {"kind": "genesis", "ledger": name, "seq": 0, "prev_hash": ZERO_HASH, "format": FORMAT,
                 "created_at": utc_now()}
            g["entry_hash"] = entry_hash(g)
            with open(self.path(name), "xb") as f:
                f.write(canonical_bytes(g) + b"\n")

    # ------------------------------------------------------------ reading / appending

    def _append(self, name: str, payload: dict[str, Any]) -> dict[str, Any]:
        entries = self._parse(name)
        e = {**payload, "kind": APPEND_KINDS[name], "ledger": name, "seq": len(entries),
             "prev_hash": entries[-1]["entry_hash"]}
        e["entry_hash"] = entry_hash(e)
        with open(self.path(name), "ab") as f:
            f.write(canonical_bytes(e) + b"\n")
        return e

    def frozen(self, evaluation_id: str) -> list[dict[str, Any]]:
        return [e for e in self._parse("frozen")[1:] if e["evaluation_id"] == evaluation_id]

    def runs(self, evaluation_id: str) -> list[dict[str, Any]]:
        return [e for e in self._parse("runs")[1:] if e["evaluation_id"] == evaluation_id]

    def _read(self, path: Path) -> list[dict[str, Any]]:
        """All non-genesis entries of one ledger file (kept for s8 callers)."""
        name = "frozen" if path == self.frozen_path else "runs"
        return self._parse(name)[1:]

    def append_frozen(self, entry: dict[str, Any]) -> dict[str, Any]:
        return self._append("frozen", entry)

    def append_run(self, entry: dict[str, Any]) -> dict[str, Any]:
        return self._append("runs", entry)

    def require_committed(self) -> None:
        """Real-data guard: both ledgers are committed in git and have no uncommitted lines."""
        for name in NAMES:
            p = self.path(name)
            head = committed_bytes(p)
            if head is None:
                raise RunRefused(
                    f"real-data test run refused: {p.name} is not committed in git; commit the ledger "
                    "(see eval/ledger/README.md) - an untracked --ledger-dir cannot be used for real data"
                )
            if p.read_bytes() != head:
                raise RunRefused(
                    f"real-data test run refused: {p.name} has uncommitted lines; commit the freeze "
                    "(`eval(ledger): freeze <id>`) or the previous run (`eval(ledger): run <id>`) first"
                )
