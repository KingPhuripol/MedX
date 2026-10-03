"""Generate the cg-l3 legacy fixtures with the code of main at 28ac4d2 (gates-8, no ``gates_version`` field).

Run ONCE, from a throwaway worktree of 28ac4d2 (never from this branch)::

    MAIN=<main checkout>
    git worktree add /tmp/cg-28ac4d2 28ac4d2
    cd /tmp/cg-28ac4d2 && PYTHONPATH=backend:. $MAIN/.venv/bin/python \\
        <this branch>/casegraph/tests/fixtures/legacy_28ac4d2/make_legacy.py --out <this branch>/casegraph/tests/fixtures/legacy_28ac4d2
    git worktree remove --force /tmp/cg-28ac4d2

Writes export_0_4_T3.json (F-CXR T3, S5 Pharma), export_0_3_unstaged.json (unstaged s2_config graph, placeholder
Pharma, re-serialised as 0.3) and outputs/<cache_key>.json for every node of both. Synthetic only.
"""

from __future__ import annotations

import argparse
import json
import shutil
import tempfile
from pathlib import Path

from casegraph.executor import PHARMA_GATES_VERSION, Executor
from casegraph.export import to_json
from casegraph.providers import mock_gateways
from casegraph.staged import build_versions
from casegraph.store import OutputStore, SQLiteStateStore
from casegraph.tests.conftest import compile_case
from casegraph.tests.fixtures import F1_T1
from casegraph.tests.staged_fixtures import FIXTURES_STAGED, T1


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", type=Path, required=True)
    out = ap.parse_args().out
    assert PHARMA_GATES_VERSION == "cg-pharma-gates-8", "run this with the code of 28ac4d2"
    (out / "outputs").mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)

        def ex(name):
            return Executor(mock_gateways(), OutputStore(tmp / name / "outputs"), SQLiteStateStore(tmp / name / "state.db"))

        _, items, horizon = FIXTURES_STAGED["F-CXR"]()
        g4 = build_versions(ex("a"), items, T1, horizon)[-1]
        assert g4.stage == "T3" and g4.by_type(__import__("casegraph.types", fromlist=["NodeType"]).NodeType.PHARMA_AGENT)
        (out / "export_0_4_T3.json").write_text(to_json(g4))
        from casegraph.compiler import validate  # noqa: F401  (compile_case validates)

        g3 = ex("b").run_sync(compile_case("F1", F1_T1.replace(hour=10)))
        data = {k: v for k, v in json.loads(to_json(g3)).items() if k not in ("stage", "trigger_refs")} | {
            "schema_version": "casegraph-export/0.3"}
        (out / "export_0_3_unstaged.json").write_text(json.dumps(data, sort_keys=True, indent=2, ensure_ascii=False) + "\n")
        for name, g in (("a", g4), ("b", g3)):
            for n in g.nodes:
                shutil.copy(tmp / name / "outputs" / f"{n.cache_key}.json", out / "outputs" / f"{n.cache_key}.json")


if __name__ == "__main__":
    main()
