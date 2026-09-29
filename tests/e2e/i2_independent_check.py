"""Checker-owned independent probes for slice i2 (not collected by pytest: no test_ prefix).

Run: PYTHONPATH=backend:. .venv/bin/python tests/e2e/i2_independent_check.py <out.json>
Synthetic data only, mock provider only, offline.
"""

from __future__ import annotations

import ast
import itertools
import json
import re
import sys
from collections import Counter, defaultdict
from datetime import datetime, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT / "backend"), str(ROOT)]

from app.config import Settings  # noqa: E402
from app.gateway import build_provider  # noqa: E402
from app.gateway.contract import GatewayRequest, canonical_sha256  # noqa: E402
from app.gateway.service import invoke_provider  # noqa: E402
from app.triage import department, redflags  # noqa: E402
from app.triage.models import Case, Snapshot as S4Snapshot  # noqa: E402

from casegraph import providers as P  # noqa: E402
from casegraph.compiler import build_snapshot, compile_graph  # noqa: E402
from casegraph.data import Alerts, Demographics, MedicationList, Vitals, VoiceFact, VoiceIntakeFacts, IntakeTranscript, sha256_json  # noqa: E402
from casegraph.executor import Executor  # noqa: E402
from casegraph.export import ImportValidationError, import_graph, inspect_lines, to_json  # noqa: E402
from casegraph.library import ProviderAssignment, ProviderConfig  # noqa: E402
from casegraph.sources import s1r  # noqa: E402
from casegraph.store import MemoryStateStore, OutputStore, next_version  # noqa: E402
from casegraph.types import NodeType  # noqa: E402

DATASET = ROOT / "data" / "synthetic" / "v1"
OVERCLAIM = re.compile(r"no red.?flags?|all clear|ไม่มี.*(สัญญาณอันตราย|red flag)", re.I)
out: dict = {}


def executor():
    return Executor(P.mock_gateways(), OutputStore(), MemoryStateStore())


# ------------------------------------------------------------------ A02 one evidence type system
def a02():
    res = {"evidence_py_absent": not (ROOT / "casegraph" / "evidence.py").exists()}
    subclasses = []
    for base in ("backend", "casegraph", "eval", "eval_i2", "data_factory"):
        for p in (ROOT / base).rglob("*.py"):
            if "tests" in p.parts:
                continue
            tree = ast.parse(p.read_text(encoding="utf-8"))
            for n in ast.walk(tree):
                if isinstance(n, ast.ClassDef):
                    for b in n.bases:
                        name = getattr(b, "id", None) or getattr(b, "attr", None)
                        if name in ("EvidenceItem",) and p != ROOT / "casegraph" / "data.py":
                            subclasses.append(f"{p.relative_to(ROOT)}:{n.name}")
    res["evidenceitem_subclasses_outside_data"] = subclasses
    res["intake_evidence_refs"] = sorted(
        str(p.relative_to(ROOT)) for p in (ROOT / "backend").rglob("*.py") if "IntakeEvidence" in p.read_text())
    n_snap = n_items = bad = 0
    for split in s1r.SPLITS:
        for path, snap in zip(s1r.snapshot_paths(DATASET, split), s1r.load_split(DATASET, split), strict=True):
            raw = json.loads(path.read_text(encoding="utf-8"))
            for item, src in zip(snap.items, raw["items"], strict=True):
                n_items += 1
                if s1r.roundtrip(item) != {**src, "data_class": "synthetic"}:
                    bad += 1
            n_snap += 1
    res.update(n_snapshots=n_snap, n_items=n_items, lossless_mismatch=bad)
    out["A02"] = res


# ------------------------------------------------------------------ A04/A05/A08/A10/A16 over dev (+train)
def over_split(split: str, ex=None, cfg=None):
    ex = ex or executor()
    stats = Counter()
    regex_hits, time_bad, rf_bad, pharma_bad, rt_bad = [], [], [], [], []
    screening_missing = []
    status_hist = Counter()
    for snap in s1r.load_split(DATASET, split):
        v, pv = next_version(ex.state, snap.patient_ref)
        g = ex.run_sync(compile_graph(build_snapshot(snap.items, snap.T, snap.patient_ref), cfg, version=v, parent_version=pv))
        stats["dp"] += 1
        types = {n.type for n in g.nodes}
        has_tx = any(isinstance(i, IntakeTranscript) for i in snap.items)
        stats["has_transcript"] += has_tx
        if (NodeType.READER_TEXT in types) != has_tx:
            rt_bad.append(snap.dp_id)
        has_ml = any(isinstance(i, MedicationList) for i in snap.items)
        stats["has_medlist"] += has_ml
        ph = g.by_type(NodeType.PHARMA_AGENT)
        if has_ml and (ph is None or ph.status == "error"):
            pharma_bad.append(snap.dp_id)
        if ph is not None and ph.status == "ok":
            stats["pharma_ok"] += 1
            stats[f"pharma_label:{ph.output['MedicationIssues'].get('label')}"] += 1
        # time validity
        for r in g.evidence:
            if r.available_at_time > g.T:
                time_bad.append(f"{snap.dp_id}:{r.item_id}")
        for n in g.nodes:
            f = (n.output or {}).get("Findings") or {}
            for fact in list(f.get("facts", [])) + list(f.get("intake", [])):
                for t in fact.get("evidence_turns", []):
                    if datetime.fromisoformat(t["spoken_at"]) > g.T:
                        time_bad.append(f"{snap.dp_id}:turn")
        rf = g.by_type(NodeType.RED_FLAG)
        a = rf.output["Alerts"]
        if a["rule_set_version"] != "rf-1.1.0" or len(a["rule_results"]) != 16 or any(
                r["rule_id"].startswith("RF-PH") for r in a["rule_results"]):
            rf_bad.append(snap.dp_id)
        s = g.red_flag_screening
        status_hist[s.status] += 1
        if not (s.rule_set_version and s.label and s.scope and s.n_declared == 16):
            screening_missing.append(snap.dp_id)
        text = to_json(g) + "\n".join(inspect_lines(g))
        m = OVERCLAIM.search(text)
        if m:
            regex_hits.append(f"{snap.dp_id}:{m.group(0)}")
    return dict(stats=dict(stats), reader_text_iff_transcript_bad=rt_bad, time_violations=time_bad,
                red_flag_not_rf110_16=rf_bad, pharma_errors_on_medlist=pharma_bad,
                screening_fields_missing=screening_missing, screening_status=dict(status_hist),
                overclaim_regex_hits=regex_hits[:20], n_overclaim=len(regex_hits))


# ------------------------------------------------------------------ A08/A14 parity on S4 author fixtures
def fixture_items(c: dict):
    case = c["case"]
    ref = "PT-" + case["case_ref"]
    by_time = defaultdict(dict)
    demo = {}
    facts = []
    demo_t = None
    for f in case["facts"]:
        k, v, t = f["kind"], f["value"], datetime.fromisoformat(f["available_at_time"])
        if k.startswith("vital."):
            name = k.removeprefix("vital.")
            by_time[t]["consciousness" if name == "avpu" else name] = v
        elif k in ("age", "sex"):
            demo["age_years" if k == "age" else "sex"] = v
            demo_t = t if demo_t is None else max(demo_t, t)
        else:
            facts.append(VoiceFact(field=k, state="KNOWN", value=v, value_text=str(v)[:500], event_time=t,
                                   available_at_time=t))
    meta = dict(patient_ref=ref, source="s4-fixture", provenance="cases_v1", version="1", data_class="synthetic")
    items = []
    for i, (t, vit) in enumerate(sorted(by_time.items())):
        items.append(Vitals(item_id=f"V{i}", event_time=t, available_at_time=t, **meta, **vit))
    if demo:
        items.append(Demographics(item_id="D", event_time=demo_t, available_at_time=demo_t, **meta, **demo))
    if facts:
        ft = max(f.available_at_time for f in facts)
        items.append(VoiceIntakeFacts(item_id="VF", event_time=min(f.event_time for f in facts), available_at_time=ft,
                                      facts=tuple(facts), **meta))
    return ref, items


def parity():
    fx = json.loads((ROOT / "backend/app/triage/fixtures/cases_v1.json").read_text())
    provider = build_provider("mock", Settings())

    def invoke(req: GatewayRequest):
        return invoke_provider(provider, req)

    rf_mismatch, dept_mismatch, abst = [], [], []
    for c in fx["cases"]:
        T = datetime.fromisoformat(c["as_of"])
        case = Case.model_validate(c["case"])
        snap = S4Snapshot(case, T)
        alerts, ne = redflags.evaluate(snap)
        s4_alerts = sorted(a.rule_id for a in alerts)
        s4_ne = sorted(n.rule_id for n in ne)
        s4_dept = department.suggest(snap, invoke)
        ref, items = fixture_items(c)
        ex = executor()
        g = ex.run_sync(compile_graph(build_snapshot(items, T, ref)))
        a = g.by_type(NodeType.RED_FLAG).output["Alerts"]
        cg_alerts = sorted(x["rule_id"] for x in a["alerts"])
        cg_ne = sorted(a["rules_not_evaluated"])
        if (cg_alerts, cg_ne) != (s4_alerts, s4_ne):
            rf_mismatch.append(dict(case=c["case"]["case_ref"], split=c["split"], s4_alerts=s4_alerts, cg_alerts=cg_alerts,
                                    s4_not_evaluable=s4_ne, cg_not_evaluated=cg_ne,
                                    cg_missing=a["missing_inputs"]))
        rn = g.by_type(NodeType.REASONING)
        ds = (rn.output or {}).get("DepartmentSuggestion") if rn.output else None
        cg = None if ds is None else dict(status=ds["status"], top3=[e["code"] for e in ds["top3"]],
                                          missing=sorted(ds["missing_information"]))
        s4 = dict(status=s4_dept.status, top3=[e.code for e in s4_dept.top3], missing=sorted(s4_dept.missing_information))
        if rn.status == "abstained" and ds is None:
            cg = dict(status="abstained(graph_gate)", top3=[], missing=sorted(rn.missing_inputs))
        if cg != s4:
            dept_mismatch.append(dict(case=c["case"]["case_ref"], split=c["split"], s4=s4, cg=cg,
                                      node_status=rn.status))
        if s4_dept.status == "abstained":
            abst.append(dict(case=c["case"]["case_ref"], node_calls=rn.gateway_calls, node_status=rn.status))
    out["A08_parity"] = dict(n=len(fx["cases"]), mismatches=rf_mismatch)
    out["A14_parity"] = dict(n=len(fx["cases"]), mismatches=dept_mismatch, s4_abstentions=abst)


# ------------------------------------------------------------------ A13 alerts invariant & import validation
def a13():
    snap = s1r.load_split(DATASET, "dev")[0]
    ex = executor()
    g = ex.run_sync(compile_graph(build_snapshot(snap.items, snap.T, snap.patient_ref)))
    rf = g.by_type(NodeType.RED_FLAG)
    a = rf.output["Alerts"]
    res = {}
    for name, mutate in (
        ("missing", lambda rr: rr[1:]),
        ("extra", lambda rr: rr + [dict(rr[0], rule_id="RF-EXTRA")]),
        ("duplicate", lambda rr: rr + [rr[0]]),
    ):
        bad = dict(a, rule_results=mutate(list(a["rule_results"])))
        try:
            Alerts.model_validate(bad)
            res[name] = "ACCEPTED"
        except ValueError:
            res[name] = "rejected"
    doc = json.loads(to_json(g))
    idx = next(i for i, n in enumerate(doc["nodes"]) if n["type"] == "red_flag")
    t1 = json.loads(json.dumps(doc))
    t1["nodes"][idx]["output"]["Alerts"]["label"] = "tampered"
    t2 = json.loads(json.dumps(doc))
    t2["nodes"][idx]["output_sha256"] = "0" * 64
    t3 = json.loads(json.dumps(doc))
    rr = t3["nodes"][idx]["output"]["Alerts"]["rule_results"]
    t3["nodes"][idx]["output"]["Alerts"]["rule_results"] = rr[1:]
    t3["nodes"][idx]["output_sha256"] = sha256_json(t3["nodes"][idx]["output"])
    for name, d in (("tampered_output", t1), ("tampered_sha", t2), ("invalid_alerts_rehashed", t3)):
        try:
            import_graph(json.dumps(d))
            res[f"import_{name}"] = "ACCEPTED"
        except (ImportValidationError, ValueError) as exc:
            res[f"import_{name}"] = f"rejected:{type(exc).__name__}"
    try:
        import_graph(json.dumps(dict(doc, schema_version="casegraph-export/0.2")))
        res["import_0.2"] = "ACCEPTED"
    except Exception as exc:  # noqa: BLE001
        res["import_0.2"] = type(exc).__name__
    res["schema_version"] = doc["schema_version"]
    out["A13"] = res


# ------------------------------------------------------------------ A08 placeholder unreachable, A16 hook swap
def a08_a16():
    cfg = ProviderConfig()
    out["A08_default_red_flag_version"] = cfg.assignments[NodeType.RED_FLAG].model_version
    out["A16_default_pharma"] = cfg.assignments[NodeType.PHARMA_AGENT].model_version
    calls = []

    def test_pharma(lists):
        calls.append(len(lists))
        return (), ()

    P.register_pharma_provider("checker-pharma-0.1", test_pharma, label="CHECKER TEST PROVIDER")
    swapped = cfg.with_assignment(NodeType.PHARMA_AGENT, ProviderAssignment(provider="rules",
                                                                            model_version="checker-pharma-0.1"))
    r = over_split("dev", cfg=swapped)
    out["A16_swap_dev"] = dict(n_medlist=r["stats"].get("has_medlist"), provider_calls=len(calls),
                               pharma_errors=r["pharma_errors_on_medlist"], pharma_ok=r["stats"].get("pharma_ok"),
                               labels={k: v for k, v in r["stats"].items() if k.startswith("pharma_label")})


# ------------------------------------------------------------------ A06 import scan, A15 resume grep
def scans():
    df = []
    for base in ("backend", "casegraph"):
        for p in (ROOT / base).rglob("*.py"):
            src = p.read_text(encoding="utf-8")
            if re.search(r"^\s*(from|import)\s+data_factory", src, re.M):
                df.append(str(p.relative_to(ROOT)))
    out["A06_data_factory_imports"] = df
    resume = []
    for base in ("backend", "casegraph", "eval", "eval_i2"):
        for p in (ROOT / base).rglob("*.py"):
            if "tests" in p.parts:
                continue
            for i, line in enumerate(p.read_text(encoding="utf-8").splitlines(), 1):
                if ".resume(" in line:
                    resume.append(f"{p.relative_to(ROOT)}:{i}")
    out["A15_resume_callers_nontest"] = resume
    out["A15_triage_imports_casegraph_executor"] = [
        str(p.relative_to(ROOT)) for p in (ROOT / "backend/app/triage").rglob("*.py")
        if re.search(r"casegraph", p.read_text(encoding="utf-8"))]


if __name__ == "__main__":
    a02()
    out["dev"] = over_split("dev")
    out["train"] = over_split("train")
    parity()
    a13()
    a08_a16()
    scans()
    Path(sys.argv[1]).write_text(json.dumps(out, indent=1, ensure_ascii=False, default=str))
    print(json.dumps({k: (v if k not in ("A08_parity", "A14_parity") else {"n": v["n"], "n_mismatch": len(v["mismatches"])})
                      for k, v in out.items()}, indent=1, ensure_ascii=False, default=str)[:6000])
