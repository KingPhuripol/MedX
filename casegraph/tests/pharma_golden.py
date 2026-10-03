"""Slice cg-l3: golden tripwire that forces a ``PHARMA_GATES_VERSION`` bump when Pharma behaviour changes.

Synthetic, offline, mock only. Research prototype: not clinical performance. A golden file covers a fixed corpus; it is
not a proof that behaviour is unchanged outside that corpus.

    python -m casegraph.tests.pharma_golden --check
    python -m casegraph.tests.pharma_golden --write [--accept-input-drift]   # only after a deliberate version bump
"""

from __future__ import annotations

import argparse
import collections
import json
import subprocess
import sys
import tempfile
from dataclasses import dataclass, field
from datetime import timedelta, timezone
from pathlib import Path
from typing import Any

from casegraph import executor as executor_mod
from casegraph.data import sha256_json
from casegraph.executor import Executor
from casegraph.library import ProviderAssignment
from casegraph.sources import s1r
from casegraph.staged import build_versions
from casegraph.store import OutputStore, SQLiteStateStore
from casegraph.types import NodeType

CORPUS_ID = "cg-l3-corpus-1"
S1R_SEED = 20260926
SYN_COUNT = 8
GOLDEN_PATH = Path(__file__).resolve().parent / "golden" / "pharma_gates_golden.json"
REGEN = "python -m casegraph.tests.pharma_golden --write"
BKK = timezone(timedelta(hours=7))

OK, VERSION_MISMATCH, KEY_DRIFT = "ok", "version_mismatch", "key_drift"
INPUT_DRIFT, NO_BUMP = "input_drift", "semantics_changed_without_bump"
CHANGED_BY_BUMP = "changed_with_version_bump"  # informational: output differs and the version differs (expected)


def _executor(root: Path) -> Executor:
    from casegraph.providers import mock_gateways

    root.mkdir(parents=True, exist_ok=True)
    return Executor(mock_gateways(), OutputStore(root / "outputs"), SQLiteStateStore(root / "state.db"))


def _semantic_sha(output: dict[str, Any] | None) -> str:
    if output and isinstance(output.get("MedicationIssues"), dict):
        mi = {k: v for k, v in output["MedicationIssues"].items() if k != "gates_version"}
        output = {**output, "MedicationIssues": mi}
    return sha256_json(output)


def _entry(graph, node, items_by_id) -> dict[str, Any]:
    """Hash of everything that feeds the node EXCEPT the gate-semantics version, plus what it produced."""
    upstream = sorted([e.src, e.data_type, graph.node(e.src).status, graph.node(e.src).output_sha256]
                      for e in graph.edges if e.dst == node.id)
    input_sha = sha256_json({
        "provider": node.provider, "model_version": node.model_version, "params": node.params,
        "evidence": [[r, items_by_id[r].content_sha256()] for r in node.evidence_refs], "upstream": upstream})
    mi = (node.output or {}).get("MedicationIssues") or {}
    return {
        "input_sha256": input_sha, "output_sha256": node.output_sha256, "semantic_sha256": _semantic_sha(node.output),
        "status": mi.get("status"), "node_status": node.status, "gates_version": mi.get("gates_version"),
        "fact_use": dict(sorted(collections.Counter(u["use"] for u in mi.get("conversation_fact_use", ())).items())),
    }


def _add(entries, prefix, graphs, items):
    items_by_id = {i.item_id: i for i in items}
    for g in graphs:
        node = g.by_type(NodeType.PHARMA_AGENT)
        if node is not None:
            entries[f"{prefix}|{g.stage or "-"}|v{g.version}"] = _entry(g, node, items_by_id)


def syn_subset(dataset: Path) -> list[str]:
    return [p.parent.name for p in s1r.snapshot_paths(dataset, "dev") if p.name == "snapshot_T1.json"][:SYN_COUNT]


def build_corpus(dataset: Path) -> dict[str, Any]:
    from casegraph.tests.conftest import compile_case, s2_config
    from casegraph.tests.fixtures import DAY, F1_T1, H, M, _common
    from casegraph.tests.staged_fixtures import FIXTURES_STAGED, T1, conv_meds
    from casegraph.tests.test_cgt123_conversation_meds import VARIANTS

    entries: dict[str, Any] = {}
    ids = syn_subset(dataset)
    cases = []
    for name, fx in sorted(FIXTURES_STAGED.items()):
        p, items, horizon = fx()
        cases.append((name, p, list(items), T1, horizon))
    for cid in ids:
        sc = s1r.load_staged_case(dataset, "dev", cid, "T2")
        cases.append((cid, sc.items[0].patient_ref, list(sc.items), sc.t1, sc.horizon))
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        n = 0
        for variant in sorted(VARIANTS):
            for name, p, base_items, t1, horizon in cases:
                items = list(base_items)
                specs = VARIANTS[variant]  # applied exactly as the property sweep applies them
                for k, spec in enumerate(specs if isinstance(specs, list) else ([specs] if specs else [])):
                    kw = dict(spec)
                    t = t1 - kw.pop("minus", 15) * M
                    items.append(conv_meds(p, f"{p}-cm-{variant}-{k}", t.astimezone(BKK) if kw.pop("tz", False) else t, **kw))
                n += 1
                _add(entries, f"{variant}|{name}", build_versions(_executor(root / f"c{n}"), items, t1, horizon), items)
        # anchor model_path: the project_model Pharma path is explicitly not_evaluated
        cfg = s2_config().with_assignment(
            NodeType.PHARMA_AGENT, ProviderAssignment(provider="project_model", model_version="proj-mock-0.1"))
        g = _executor(root / "am").run_sync(compile_case("F1", F1_T1.replace(hour=10), cfg))
        from casegraph.tests.fixtures import f1
        _add(entries, "anchor|model_path", [g], f1())
        # anchor placeholder_api1: the placeholder-pharma-0.2 duplicate/missing-dose case
        from casegraph.compiler import build_snapshot, compile_graph

        from casegraph.tests.test_executor import _meds

        pid = "SYN-PH1"
        items = [_meds(pid, "ph-a", {"name": "Paracetamol", "dose": "500 mg"}, {"name": "Amlodipine", "dose": "5 mg"}),
                 _meds(pid, "ph-b", {"name": "paracetamol"})]
        g = _executor(root / "ap").run_sync(compile_graph(build_snapshot(items, DAY + 9 * H), s2_config()))
        _add(entries, "anchor|placeholder_api1", [g], items)
    return {
        "pharma_gates_version": executor_mod.PHARMA_GATES_VERSION, "corpus_id": CORPUS_ID, "s1r_seed": S1R_SEED,
        "syn_subset": ids, "regenerate_command": REGEN, "entries": dict(sorted(entries.items())),
    }


@dataclass
class Report:
    version_mismatch: bool = False
    key_drift: bool = False
    detail: list[str] = field(default_factory=list)
    classes: dict[str, str] = field(default_factory=dict)  # key -> class

    def keys(self, cls: str) -> list[str]:
        return sorted(k for k, c in self.classes.items() if c == cls)

    @property
    def ok(self) -> bool:
        return not self.version_mismatch and not self.key_drift and all(
            c in (OK, CHANGED_BY_BUMP) for c in self.classes.values())

    def text(self) -> str:
        counts = collections.Counter(self.classes.values())
        lines = [f"version_mismatch={self.version_mismatch} key_drift={self.key_drift} {dict(sorted(counts.items()))}",
                 *self.detail]
        for cls in (INPUT_DRIFT, NO_BUMP):
            lines += [f"  {cls}: {k}" for k in self.keys(cls)[:20]]
        return "\n".join(lines)


def compare(golden: dict[str, Any], current: dict[str, Any]) -> Report:
    rep = Report()
    same_version = golden["pharma_gates_version"] == current["pharma_gates_version"]
    if not same_version:
        rep.version_mismatch = True
        rep.detail.append(f"golden {golden['pharma_gates_version']} != current {current['pharma_gates_version']}: "
                          f"regenerate with `{REGEN}` after reviewing the changed keys")
    gk, ck = set(golden["entries"]), set(current["entries"])
    if gk != ck or golden["syn_subset"] != current["syn_subset"] or golden["corpus_id"] != current["corpus_id"]:
        rep.key_drift = True
        rep.detail.append(f"key set differs: only golden {sorted(gk - ck)[:5]}, only current {sorted(ck - gk)[:5]}")
    for k in sorted(gk & ck):
        g, c = golden["entries"][k], current["entries"][k]
        if g["input_sha256"] != c["input_sha256"]:
            rep.classes[k] = INPUT_DRIFT
        elif g["output_sha256"] != c["output_sha256"]:
            rep.classes[k] = NO_BUMP if same_version else CHANGED_BY_BUMP
        else:
            rep.classes[k] = OK
    return rep


def changed_semantics(golden: dict[str, Any], current: dict[str, Any]) -> list[str]:
    return sorted(k for k in set(golden["entries"]) & set(current["entries"])
                  if golden["entries"][k]["semantic_sha256"] != current["entries"][k]["semantic_sha256"])


def write_golden(path: Path, current: dict[str, Any], *, accept_input_drift: bool = False, out=print) -> int:
    """Rewrite ``path``. Exit 2 (file untouched) on an unbumped semantics change or unaccepted input drift."""
    if path.exists():
        golden = json.loads(path.read_text())
        rep = compare(golden, current)
        if rep.keys(NO_BUMP):
            out(f"REFUSED: {len(rep.keys(NO_BUMP))} entries changed behaviour without a PHARMA_GATES_VERSION bump "
                f"(still {current['pharma_gates_version']}); bump it, then regenerate. e.g. {rep.keys(NO_BUMP)[:3]}")
            return 2
        if rep.keys(INPUT_DRIFT) and not accept_input_drift:
            out(f"REFUSED: input drift in {len(rep.keys(INPUT_DRIFT))} entries; review and pass --accept-input-drift")
            return 2
        changed = changed_semantics(golden, current)
    else:
        changed = []
    out(f"semantic_sha256 changed for {len(changed)} keys: {changed}")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(current, sort_keys=True, indent=2) + "\n")
    out(f"wrote {path}")
    return 0


def main(argv: list[str] | None = None, *, current: dict[str, Any] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="pharma_golden")
    mode = ap.add_mutually_exclusive_group()
    mode.add_argument("--check", action="store_true")
    mode.add_argument("--write", action="store_true")
    ap.add_argument("--accept-input-drift", action="store_true")
    ap.add_argument("--golden", type=Path, default=GOLDEN_PATH)
    ap.add_argument("--dataset", type=Path, help="existing S1r dataset (default: generate seed 20260926 in a temp dir)")
    args = ap.parse_args(argv)
    if current is None:
        if args.dataset is not None:
            current = build_corpus(args.dataset)
        else:
            with tempfile.TemporaryDirectory() as tmp:
                out = Path(tmp) / "v1"
                subprocess.run([sys.executable, "-m", "data_factory", "generate", "--seed", str(S1R_SEED), "--out", str(out)],
                               cwd=Path(__file__).resolve().parents[2], check=True, capture_output=True)
                current = build_corpus(out)
    if args.write:
        return write_golden(args.golden, current, accept_input_drift=args.accept_input_drift)
    rep = compare(json.loads(args.golden.read_text()), current)
    print(rep.text())
    return 0 if rep.ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
