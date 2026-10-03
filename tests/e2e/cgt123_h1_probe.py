"""cg-t123 915c2ea independent probe (H-1): Reader:Text failing at T3 must never let Pharma read allergy/medication conversation as evaluated.
Run: PYTHONPATH=backend:. .venv/bin/python tests/e2e/cgt123_h1_probe.py <scratch> <out.json>"""
import json, sys
from pathlib import Path
from casegraph import reader_text
from casegraph.executor import PENDING_KEY, Executor
from casegraph.providers import mock_gateways
from casegraph.staged import build_versions
from casegraph.store import OutputStore, SQLiteStateStore
from casegraph.tests.fixtures import M
from casegraph.tests.staged_fixtures import T1, allergy, base, conv_allergy, order
from casegraph.types import NodeType

root = Path(sys.argv[1]); root.mkdir(parents=True, exist_ok=True)
real = reader_text.read_clinical_text
def boom(*a, **k): raise reader_text.ReaderError("provider_down")
rows, bad = [], []
for i, (rec, conv, fail) in enumerate((r, c, f) for r in (None, "known", "no_known_allergy", "unknown") for c in (False, True) for f in (False, True)):
    p = f"SYN-H{i}"
    items = list(base(p, with_allergy=False))
    if rec: items.append(allergy(p, f"{p}-al", T1 - 48 * 60 * M, status=rec))
    if conv: items.append(conv_allergy(p, f"{p}-c", T1 - 15 * M))
    items.append(order(p, f"{p}-o", T1 + 30 * M))
    reader_text.read_clinical_text = boom if fail else real
    try:
        ex = Executor(mock_gateways(), OutputStore(root / f"o{i}"), SQLiteStateStore(root / f"s{i}.db"))
        vs = build_versions(ex, items, T1, T1 + 120 * M)
    finally:
        reader_text.read_clinical_text = real
    t3 = vs[-1]; assert t3.stage == "T3"
    mi = t3.by_type(NodeType.PHARMA_AGENT).output["MedicationIssues"]
    ck = {c["check"]: c for c in mi["check_results"]}
    rt = [n for n in t3.nodes if n.type is NodeType.READER_TEXT]
    ok = True
    if fail and rt and any(n.status == "error" for n in rt):
        ok = mi["status"] != "evaluated" and ck.get("allergy_conversation", {}).get("status") == "not_evaluated" \
             and ck.get("medication_conversation", {}).get("status") == "not_evaluated"
    elif fail and not rt:
        ok = True  # no conversation read at all, record gates speak
    # a failed reader must never be reported as evaluated even when records are complete
    if fail and rt:
        ok = ok and mi["status"] != "evaluated"
    rows.append([rec, conv, fail, len(rt), mi["status"], ok])
    if not ok: bad.append(rows[-1])
out = {"combos": len(rows), "bad": bad, "pass": not bad, "rows": rows}
Path(sys.argv[2]).write_text(json.dumps(out, indent=1))
print(out["combos"], "combos;", len(bad), "bad")
for r in rows: print(r)
