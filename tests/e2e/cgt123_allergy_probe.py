"""cg-t123 e6d7a31 independent probe: conversation allergy x record matrix at T3 never reads as 'no allergy'.
Offline, synthetic, no server. Run: PYTHONPATH=backend:. .venv/bin/python tests/e2e/cgt123_allergy_probe.py <scratch> <out.json>
make test: casegraph/tests/test_cgl6_probes.py::test_allergy_probe_reference (80 combos / 0 bad / 71 gap combos)"""
import itertools, json, sys
from pathlib import Path
from casegraph.executor import PENDING_KEY, Executor
from casegraph.providers import mock_gateways
from casegraph.staged import build_versions
from casegraph.store import OutputStore, SQLiteStateStore
from casegraph.tests.fixtures import M
from casegraph.tests.staged_fixtures import T1, allergy, base, conv_allergy, order
from casegraph.types import NodeType

STATUS = {"none": None, "present": ("KNOWN", "present"), "absent": ("KNOWN", "absent"), "unknown": ("UNKNOWN", None)}
ALLG = {"none": None, "named": ("KNOWN", ["sulfa"]), "blank": ("KNOWN", [" "]), "unk": ("UNKNOWN", None), "ref": ("REFUSED", None)}
LIST = {"missing": None, "known": "known", "nka": "no_known_allergy", "unknown": "unknown"}


def run_probe(root):
    root = Path(root); root.mkdir(parents=True, exist_ok=True)
    rows, bad = [], []
    for i, (s, a, l) in enumerate(itertools.product(STATUS, ALLG, LIST)):
        p = f"SYN-P{i}"
        items = list(base(p, with_allergy=False))
        if LIST[l]:
            items.append(allergy(p, f"{p}-al", T1 - 48 * 60 * M, status=LIST[l]))
        if STATUS[s] or ALLG[a]:
            items.append(conv_allergy(p, f"{p}-c", T1 - 15 * M, status=STATUS[s], allergens=ALLG[a]))
        items.append(order(p, f"{p}-o", T1 + 30 * M))
        ex = Executor(mock_gateways(), OutputStore(root / f"o{i}"), SQLiteStateStore(root / f"s{i}.db"))
        t3 = build_versions(ex, items, T1, T1 + 120 * M)[-1]
        assert t3.stage == "T3"
        mi = t3.by_type(NodeType.PHARMA_AGENT).output["MedicationIssues"]
        rws = {c["check"]: c for c in mi["check_results"] if c["check"].startswith("allergy")}
        shown = t3.by_type(NodeType.HUMAN_CHECKPOINT).output[PENDING_KEY]["for_review"]["pharma_agent"]["MedicationIssues"]["conversation_allergy_facts"]
        present = s == "present"; named = a == "named"
        # independent expectation: is the allergy picture incomplete/contradictory?
        # round 5: an UNKNOWN conversation allergy_status and a blank/unparseable allergen are gaps too (rule 6)
        gap = (LIST[l] in (None, "unknown")) or a in ("unk", "ref", "blank") or s == "unknown" or (present and not named) or (present and LIST[l] == "no_known_allergy")
        notneg = mi["status"] != "evaluated"
        ok = (not gap or (notneg and any(r["status"] == "not_evaluated" for r in rws.values())))
        if gap is False:
            ok = ok and not (set(rws) - {"allergy_conflict"} and any(r["status"] == "not_evaluated" for r in rws.values()))
        kinds = {f["kind"] for f in shown}
        if STATUS[s]: ok = ok and "allergy_status" in kinds
        if ALLG[a]: ok = ok and "allergens" in kinds
        rows.append([s, a, l, gap, mi["status"], sorted(rws), ok])
        if not ok: bad.append(rows[-1])
    return {"combos": len(rows), "bad": bad, "pass": not bad, "gap_combos": sum(r[3] for r in rows)}


def main(argv):
    out = run_probe(argv[0])
    Path(argv[1]).write_text(json.dumps(out, indent=1))
    print(out["combos"], "combos;", len(out["bad"]), "bad;", out["gap_combos"], "gap combos")
    for b in out["bad"][:10]: print(b)


if __name__ == "__main__":
    main(sys.argv[1:])
