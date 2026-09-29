"""Checker-owned: dump the red-flag screening block of every S1r dev Case Graph (plus the 'unavailable' block),
as the /assess API would return it (casegraph_run.screening_block), for the browser render probe.
Run: PYTHONPATH=backend:. .venv/bin/python tests/e2e/i2_dump_dev_screening.py <out.json>
"""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT / "backend"), str(ROOT)]
from app.triage import casegraph_run  # noqa: E402
from casegraph import providers as P  # noqa: E402
from casegraph.compiler import build_snapshot, compile_graph  # noqa: E402
from casegraph.executor import Executor  # noqa: E402
from casegraph.library import ProviderConfig  # noqa: E402
from casegraph.sources import s1r  # noqa: E402
from casegraph.store import MemoryStateStore, OutputStore, next_version  # noqa: E402

ex = Executor(P.mock_gateways(), OutputStore(), MemoryStateStore())
blocks = {}
for snap in s1r.load_split(ROOT / "data/synthetic/v1", "dev"):
    v, pv = next_version(ex.state, snap.patient_ref)
    g = ex.run_sync(compile_graph(build_snapshot(snap.items, snap.T, snap.patient_ref), ProviderConfig(), version=v,
                                  parent_version=pv))
    blocks[snap.dp_id] = casegraph_run.screening_block(g)
blocks["__unavailable__"] = casegraph_run.unavailable_screening()
Path(sys.argv[1]).write_text(json.dumps(blocks, ensure_ascii=False, default=str))
print(len(blocks), {s: sum(1 for b in blocks.values() if b["status"] == s) for s in {b["status"] for b in blocks.values()}})
