"""Dump the S6 care urgency outputs at a pinned commit (slice int2, INT2-A07). Synthetic data, offline, mock provider.

    git worktree add /tmp/int2-d423d15 d423d15
    python scripts/int2_dump_s6_urgency.py --repo /tmp/int2-d423d15 --out backend/tests/care/fixtures/s6_urgency_d423d15.json
    python scripts/int2_dump_s6_urgency.py --repo /tmp/int2-d423d15 --check backend/tests/care/fixtures/s6_urgency_d423d15.json

``--repo`` must be a checkout of ``COMMIT``. Its own factory CLI generates S1r v1 (seed 20260926, 400 decision points)
and the S6r held-out set (seed 20260927 ``--heldout``, 160) into a temp dir; its own care engine then assesses every
snapshot (all splits) through the gateway service with the mock provider, in a subprocess whose import path is that
checkout only. Per decision point: alert rule ids and evidence refs, ``escalation_required``, status, reason,
``missing_information`` and the six pre-I2 screening fields. ``--check`` requires byte-identical output.
``row_of`` is shared with ``backend/tests/care/test_int2.py`` so both sides extract the same fields.
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any

COMMIT = "d423d15e17c098630eebb748686fa192fa624b00"
DATASETS = (("v1", 20260926, False), ("heldout", 20260927, True))
SCREENING_FIELDS = ("status", "performed", "banner", "rules_evaluated", "rules_not_evaluated", "missing_inputs")
COMMAND = ("python scripts/int2_dump_s6_urgency.py --repo <git worktree at d423d15> "
           "--out backend/tests/care/fixtures/s6_urgency_d423d15.json")


def row_of(r: Any) -> dict[str, Any]:
    """The urgency fields of one care result (an S6 or int2 ``CareResult``)."""
    s = r.red_flag_screening
    return {"alerts": [{"rule_id": a.rule_id, "evidence_refs": list(a.evidence_refs)} for a in r.alerts],
            "escalation_required": r.escalation_required, "status": r.status, "reason": r.reason,
            "missing_information": list(r.missing_information),
            "screening": {k: (list(v) if isinstance(v := getattr(s, k), (list, tuple)) else v)
                          for k in SCREENING_FIELDS}}


def snapshots(root: Path) -> list[tuple[str, str, str, Path]]:
    """(split, case_id, decision point, path) for every snapshot in the dataset, sorted."""
    out = []
    for p in sorted((root / "inputs").glob("*/*/snapshot_T*.json")):
        out.append((p.parent.parent.name, p.parent.name, p.stem.removeprefix("snapshot_"), p))
    return out


def assess_all(roots: dict[str, Path]) -> list[dict[str, Any]]:
    """Assess every snapshot with the ``app.care`` importable on ``sys.path`` (mock provider, offline)."""
    from app.care import engine
    from app.config import Settings
    from app.gateway import build_provider
    from app.gateway.service import invoke_provider

    provider = build_provider("mock", Settings())
    rows = []
    for name, root in roots.items():
        for split, case_id, dp, path in snapshots(root):
            doc = json.loads(path.read_text("utf-8"))
            r = engine.assess(doc, lambda q: invoke_provider(provider, q), decision_point=dp)
            rows.append({"dataset": name, "split": split, "case_id": case_id, "dp": dp, **row_of(r)})
    return rows


def render(header: dict[str, Any], rows: list[dict[str, Any]]) -> bytes:
    """One row per line, sorted keys: deterministic bytes."""
    lines = [json.dumps(r, sort_keys=True, ensure_ascii=False, separators=(",", ":")) for r in rows]
    head = json.dumps(header, sort_keys=True, ensure_ascii=False, indent=1)
    return ('{"header":' + head + ',\n"rows":[\n' + ",\n".join(lines) + "\n]}\n").encode("utf-8")


def _tree_sha(root: Path) -> str:
    return json.loads((root / "manifest.json").read_text("utf-8"))["tree_sha256"]


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--repo", type=Path, required=True, help=f"a checkout of {COMMIT}")
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--out", type=Path)
    g.add_argument("--check", type=Path)
    g.add_argument("--inner", help=argparse.SUPPRESS)  # JSON {name: root}; run inside the pinned checkout
    a = ap.parse_args(argv)
    repo = a.repo.resolve()
    if a.inner:
        rows = assess_all({k: Path(v) for k, v in json.loads(a.inner).items()})
        sys.stdout.write(json.dumps(rows, ensure_ascii=False))
        return 0
    head = subprocess.run(["git", "-C", str(repo), "rev-parse", "HEAD"], capture_output=True, text=True,
                          check=True).stdout.strip()
    if head != COMMIT:
        print(f"REFUSED: {repo} is at {head}, expected {COMMIT}", file=sys.stderr)
        return 2
    with tempfile.TemporaryDirectory(prefix="int2-s6-") as tmp:
        roots: dict[str, Path] = {}
        for name, seed, heldout in DATASETS:
            out = Path(tmp) / name
            cmd = [sys.executable, "-m", "data_factory", "generate", "--seed", str(seed), "--out", str(out)]
            subprocess.run(cmd + (["--heldout"] if heldout else []), cwd=repo, check=True, capture_output=True)
            roots[name] = out
        env = {k: v for k, v in os.environ.items() if k not in ("PYTHONPATH", "CARE_DATASET")}
        env["PYTHONPATH"] = f"{repo / 'backend'}{os.pathsep}{repo}"
        res = subprocess.run([sys.executable, str(Path(__file__).resolve()), "--repo", str(repo), "--inner",
                              json.dumps({k: str(v) for k, v in roots.items()})],
                             cwd=repo, env=env, capture_output=True, check=False)
        if res.returncode != 0:
            print(res.stderr.decode("utf-8", "replace"), file=sys.stderr)
            return 1
        rows = json.loads(res.stdout)
        header = {
            "slice": "int2", "criterion": "INT2-A07",
            "generated_from_commit": COMMIT,
            "command": COMMAND,
            "datasets": {name: {"seed": seed, "heldout": heldout, "tree_sha256": _tree_sha(roots[name]),
                                "n_decision_points": sum(1 for r in rows if r["dataset"] == name)}
                         for name, seed, heldout in DATASETS},
            "fields": ["alerts[].rule_id", "alerts[].evidence_refs", "escalation_required", "status", "reason",
                       "missing_information", *(f"screening.{k}" for k in SCREENING_FIELDS)],
            "note": "Synthetic data, mock provider, offline. Care engine at the pinned commit (S6 frozen behaviour).",
        }
    data = render(header, rows)
    if a.out:
        a.out.parent.mkdir(parents=True, exist_ok=True)
        a.out.write_bytes(data)
        print(f"wrote {a.out} ({len(rows)} decision points)")
        return 0
    same = a.check.read_bytes() == data
    print(f"{'CHECK OK' if same else 'CHECK FAILED'}: {a.check} vs {COMMIT} ({len(rows)} decision points)")
    return 0 if same else 1


if __name__ == "__main__":
    raise SystemExit(main())
