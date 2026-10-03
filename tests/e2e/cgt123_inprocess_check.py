"""cg-t123 independent checker: in-process measurement of A1-A7 against the real compiler/executor/S5 hook.

Run: PYTHONPATH=backend:. .venv/bin/python tests/e2e/cgt123_inprocess_check.py <dataset> <scratch> <out.json>
In make test: casegraph/tests/test_cgl6_cgt123_acceptance.py (imports `run_check`; no work at import time).
Gold is re-derived here from raw journey.json `available_at_time` only (own code, not casegraph.stages).
Synthetic, offline, mock gateway only.
"""
from __future__ import annotations

import json
import subprocess
import sys
import traceback
from collections import Counter
from datetime import datetime, timedelta
from pathlib import Path

from casegraph.compiler import GraphValidationError, build_snapshot, compile_stage, validate
from casegraph.executor import PENDING_KEY, Executor, ResumeError
from casegraph.library import ProviderAssignment, ProviderConfig
from casegraph.providers import LocalGateway, mock_gateways
from casegraph.sources import s1r
from casegraph.staged import build_versions
from casegraph.stages import plan_stages
from casegraph.store import GraphVersionExists, MemoryStateStore, OutputStore, SQLiteStateStore, replay
from casegraph.tests.conftest import FakeProvider
from casegraph.tests.fixtures import DAY, H, M, _common, ct, cxr, labs, mri, s4_intake, vitals
from casegraph.tests.staged_fixtures import FIXTURES_STAGED, GOLD_STAGES, T1, allergy, home, order
from casegraph.types import NodeType

REPO = Path(__file__).resolve().parents[2]
AUDIT = REPO / "scripts" / "temporal_leakage_audit.py"
ROLE = {"T1": "human:nurse", "T2": "human:physician", "T3": "human:pharmacist"}
TASK = {"T1": "department", "T2": "care", "T3": None}


class Ctx:
    """Per-call state (replaces the old module globals)."""

    def __init__(self, dataset, scratch):
        self.dataset = Path(dataset)
        self.scratch = Path(scratch)
        self.scratch.mkdir(parents=True, exist_ok=True)
        self.R = {}
        self.cases = None
        self.built = {}  # label -> (env, ex, graphs, seen, items, t1, horizon)


def iso(s):
    return datetime.fromisoformat(s)


# ---------- independent gold (raw dicts only) ----------
def gold(raw, t1, horizon):
    arr = {}
    for it in raw:
        at = iso(it["available_at_time"]) if isinstance(it["available_at_time"], str) else it["available_at_time"]
        if not (t1 < at <= horizon):
            continue
        dt = it["data_type"]
        if dt in ("LabSeries", "CXRImage", "CTVolume", "MRIVolume"):
            arr.setdefault(at, []).append(("T2", it["item_id"]))
        elif dt == "MedicationList" and it.get("list_source") == "new_order":
            arr.setdefault(at, []).append(("T3", it["item_id"]))
    out = [("T1", t1, ())]
    for at in sorted(arr):
        for st in ("T2", "T3"):
            ids = tuple(sorted(i for s, i in arr[at] if s == st))
            if ids:
                out.append((st, at, ids))
    return out


def plan_tuple(plans):
    return [(p.stage, p.T, tuple(p.trigger_item_ids)) for p in plans]


# ---------- A1 ----------
def a1(c):
    res = {"syn": {}, "mismatch": [], "lists": 0}
    counts = {"T1": Counter(), "T2": Counter()}
    for split in s1r.SPLITS:
        for path in s1r.snapshot_paths(c.dataset, split):
            if path.name != "snapshot_T1.json":
                continue
            case = path.parent.name
            raw = json.loads((path.parent / "journey.json").read_text())["items"]
            for point in ("T1", "T2"):
                sc = s1r.load_staged_case(c.dataset, split, case, point)
                got = plan_tuple(plan_stages(sc.items, sc.t1, sc.horizon))
                want = gold(raw, sc.t1, sc.horizon)
                res["lists"] += 1
                if got != want:
                    res["mismatch"].append([case, point, [g[0] for g in got], [w[0] for w in want]])
                counts[point][tuple(g[0] for g in got)] += 1
    res["counts_T1"] = {"/".join(k): v for k, v in counts["T1"].items()}
    res["counts_T2"] = {"/".join(k): v for k, v in counts["T2"].items()}
    # own adversarial planner sets (own gold)
    P = "ADV"
    base = [*s4_intake(P, P, T1 - 20 * M), vitals(P, "v1", T1 - 10 * M, T1 - 9 * M)]
    e1, e2, e3 = T1 + 20 * M, T1 + 40 * M, T1 + 60 * M
    hz = T1 + 2 * H
    def raw_of(items):
        return [{"data_type": i.data_type, "item_id": i.item_id, "available_at_time": i.available_at_time,
                 "list_source": getattr(i, "list_source", None)} for i in items]
    cases = {
        "ct+mri+order same e": ([ct(P, "ct", e1 - M, e1), mri(P, "mri", e1 - M, e1), order(P, "o", e1)], hz),
        "two orders then lab": ([order(P, "o1", e1), order(P, "o2", e2), labs(P, "l", e2, e3)], hz),
        "two orders same e": ([order(P, "o1", e1), order(P, "o2", e1)], hz),
        "lab at exactly t1": ([labs(P, "l", T1 - M, T1)], hz),
        "order at exactly t1": ([order(P, "o", T1)], hz),
        "order at horizon": ([order(P, "o", hz)], hz),
        "order 1us after horizon": ([order(P, "o", hz + timedelta(microseconds=1))], hz),
        "order 1us after t1": ([order(P, "o", T1 + timedelta(microseconds=1))], hz),
        "home/pr lists only": ([home(P, "h", e1), ], hz),
        "lab,lab,cxr distinct": ([labs(P, "l1", e1 - M, e1), labs(P, "l2", e2 - M, e2), cxr(P, "c", e3 - M, e3)], hz),
        "order event before t1 avail after": ([order(P, "o", e1, event=T1 - 5 * H)], hz),
    }
    adv_bad = []
    for name, (extra, horizon) in cases.items():
        items = base + extra
        got = plan_tuple(plan_stages(items, T1, horizon))
        want = gold(raw_of(items), T1, horizon)
        if got != want:
            adv_bad.append([name, [g[0] for g in got], [w[0] for w in want]])
    res["adversarial_cases"] = len(cases)
    res["adversarial_mismatch"] = adv_bad
    # F-* fixtures
    fx_bad = []
    for name, fn in FIXTURES_STAGED.items():
        p, items, horizon = fn()
        got = [x.stage for x in plan_stages(items, T1, horizon)]
        want = [g[0] for g in gold(raw_of(items), T1, horizon)]
        if got != want or got != GOLD_STAGES[name]:
            fx_bad.append([name, got, want, GOLD_STAGES[name]])
    res["fixture_mismatch"] = fx_bad
    res["pass"] = (not res["mismatch"] and not adv_bad and not fx_bad and res["lists"] == 400
                   and res["counts_T1"] == {"T1": 200} and res["counts_T2"] == {"T1/T3/T2": 180, "T1/T2": 20})
    c.R["A1"] = res


# ---------- helpers ----------
class Env:
    def __init__(self, root):
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)
        self.audit = []
        self.gateways = mock_gateways(audit_sink=self.audit.append)

    def executor(self, **kw):
        return Executor(self.gateways, OutputStore(self.root / "outputs"), SQLiteStateStore(self.root / "state.db"), **kw)

    @property
    def calls(self):
        return sum(g.calls for g in self.gateways.values())


def build_counted(env, items, t1, horizon, cfg=None, ex=None, after=None):
    ex = ex or env.executor()
    seen = []
    st = {"a": len(env.audit), "c": env.calls}

    def hook(g):
        seen.append((len(env.audit) - st["a"], env.calls - st["c"]))
        st["a"], st["c"] = len(env.audit), env.calls
        if after:
            after(g)

    graphs = build_versions(ex, items, t1, horizon, cfg, after_version=hook)
    return ex, graphs, seen


def all_cases(dataset):
    """(label, patient, items, t1, horizon) for 40 dev SYN (T2 horizon) + fixtures."""
    out = []
    for path in s1r.snapshot_paths(dataset, "dev"):
        if path.name != "snapshot_T1.json":
            continue
        sc = s1r.load_staged_case(dataset, "dev", path.parent.name, "T2")
        out.append((f"SYN/{sc.case_id}", sc.patient_ref, list(sc.items), sc.t1, sc.horizon))
    for n, fn in FIXTURES_STAGED.items():
        p, items, hz = fn()
        out.append((n, p, items, T1, hz))
    return out


def build_all(c):
    c.cases = all_cases(c.dataset)
    for label, p, items, t1, hz in c.cases:
        env = Env(c.scratch / "all" / label.replace("/", "_"))
        ex, graphs, seen = build_counted(env, items, t1, hz)
        c.built[label] = (env, ex, graphs, seen, items, t1, hz)


# ---------- A2 ----------
def a2(c):
    bad, n = [], 0
    for label, (env, ex, graphs, seen, items, t1, hz) in c.built.items():
        for g in graphs:
            n += 1
            types = {x.type: x for x in g.nodes}
            hcs = [x for x in g.nodes if x.type is NodeType.HUMAN_CHECKPOINT]
            rfs = [x for x in g.nodes if x.type is NodeType.RED_FLAG]
            probs = []
            try:
                validate(g.spec())
            except Exception as e:  # noqa: BLE001
                probs.append(f"validate:{e}")
            if len(hcs) != 1 or hcs[0].provider != ROLE[g.stage]:
                probs.append("checkpoint")
            if len(rfs) != 1 or not any(e.src == rfs[0].id and e.dst == hcs[0].id and e.data_type == "Alerts" for e in g.edges):
                probs.append("redflag_edge")
            if (NodeType.PHARMA_AGENT in types) != (g.stage == "T3"):
                probs.append("pharma_iff_t3")
            t = TASK[g.stage]
            if t is None:
                if NodeType.REASONING in types:
                    probs.append("t3_reasoning")
            elif types.get(NodeType.REASONING) is None or types[NodeType.REASONING].params.get("task") != t:
                probs.append("reasoning_task")
            if probs:
                bad.append([label, g.graph_id, g.stage, probs])
    c.R["A2"] = {"versions": n, "bad": bad, "pass": not bad and n > 0}


# ---------- A3a / A3b ----------
def a3(c):
    bad_a, bad_b = [], []
    n_nodes = n_cached = 0
    for label, (env, ex, graphs, seen, items, t1, hz) in c.built.items():
        produced = set()
        for k, (g, (aud, cnt)) in enumerate(zip(graphs, seen)):
            if not (g.totals.gateway_calls == sum(x.gateway_calls for x in g.nodes) == aud == cnt):
                bad_a.append([label, g.graph_id, "count", g.totals.gateway_calls, aud, cnt])
            for x in g.nodes:
                n_nodes += 1
                if k >= 1 and x.cache_key in produced:
                    if not (x.cached and x.gateway_calls == 0):
                        bad_a.append([label, g.graph_id, x.id, "should_be_cached"])
                elif k >= 1 and x.cached:
                    bad_a.append([label, g.graph_id, x.id, "cached_without_earlier_key"])
                if k == 0 and x.cached:
                    bad_a.append([label, g.graph_id, x.id, "v1_cached"])
            if k >= 1:
                rt = g.by_type(NodeType.READER_TEXT)
                if not (rt.cached and rt.gateway_calls == 0):
                    bad_a.append([label, g.graph_id, "reader_text_not_cached"])
            produced |= {x.cache_key for x in g.nodes}
            # A3b: re-execute with an empty store at same version
            spec, its = ex.state.load_graph(g.graph_id)
            snap = build_snapshot(its, spec.T, patient_ref=spec.patient_ref)
            v = compile_stage(snap, spec.stage, None, spec.version, spec.parent_version, trigger_refs=spec.trigger_refs)
            again = Executor(env.gateways, OutputStore(), MemoryStateStore()).run_sync(v)
            for a, b in zip(g.nodes, again.nodes):
                if a.cached:
                    n_cached += 1
                    if a.output_sha256 != b.output_sha256:
                        bad_b.append([label, g.graph_id, a.id])
    # F-STALE
    _, _, gs, _, _, _, _ = c.built["F-STALE"]
    t1g, t3g = gs[0], gs[-1]
    rd1 = {r["vital"]: r["fresh"] for r in t1g.by_type(NodeType.RED_FLAG).output["Alerts"]["readings"]}
    rd3 = {r["vital"]: r["fresh"] for r in t3g.by_type(NodeType.RED_FLAG).output["Alerts"]["readings"]}
    stale_ok = bool(rd1) and all(rd1.values()) and bool(rd3) and not any(rd3.values()) and not t3g.by_type(NodeType.RED_FLAG).cached
    sc3 = t3g.red_flag_screening.status
    c.R["A3a"] = {"nodes": n_nodes, "bad": bad_a, "pass": not bad_a}
    c.R["A3b"] = {"cached_nodes_checked": n_cached, "bad": bad_b, "fstale_t1_fresh_t3_stale": stale_ok,
                "fstale_t3_screening": sc3, "pass": not bad_b and stale_ok and sc3 in ("partially_evaluated", "not_evaluated")}


# ---------- A4 ----------
def a4(c):
    res = {}
    # all evidence <= T
    bad = []
    for label, (env, ex, graphs, *_r) in c.built.items():
        for g in graphs:
            for r in g.evidence:
                if r.available_at_time > g.T:
                    bad.append([label, g.graph_id, r.item_id])
            hc = g.by_type(NodeType.HUMAN_CHECKPOINT)
            for pc in (hc.output or {}).get(PENDING_KEY, {}).get("prior_confirmed", []):
                if iso(pc["available_at_time"]) > g.T:
                    bad.append([label, g.graph_id, "prior_confirmed", pc["item_id"]])
    res["future_evidence_in_versions"] = bad
    # F-FUTURE no version
    _, _, gs, *_ = c.built["F-FUTURE"]
    res["f_future_versions"] = len(gs)
    # compile_stage with future item
    p, items, hz = FIXTURES_STAGED["F-CXR"]()
    adv = []
    snap = build_snapshot([i for i in items if i.available_at_time <= T1 + 40 * M], T1 + 40 * M, p)
    future_order = order(p, "futord", T1 + 3 * H)
    # (a) trigger id not in snapshot
    try:
        compile_stage(snap, "T3", trigger_refs=[future_order.item_id])
        adv.append("compile_stage future trigger accepted")
    except GraphValidationError:
        pass
    # (b) build_snapshot containing a future item
    try:
        build_snapshot([*items, future_order], T1 + 40 * M, p)
        compile_stage(build_snapshot([*items, future_order], T1 + 40 * M, p), "T2")
        # the snapshot builder may filter; ensure future item not in refs
        s2 = build_snapshot([*items, future_order], T1 + 40 * M, p)
        if any(i.item_id == "futord" for i in s2.items):
            adv.append("snapshot kept future item")
    except GraphValidationError:
        pass
    except Exception as e:  # noqa: BLE001
        adv.append(f"snapshot future raised {type(e).__name__}")
    # (c) forged spec: valid T2 spec with a future evidence ref
    env, ex, gs, *_ = c.built["F-CXR"]
    spec = gs[1].spec()
    d = spec.model_dump(mode="json")
    forged_ref = dict(d["evidence"][0])
    forged_ref["item_id"] = "forged-future"
    forged_ref["available_at_time"] = (spec.T + 2 * H).isoformat()
    d["evidence"].append(forged_ref)
    from casegraph.export import GraphSpec
    from casegraph.compiler import Snapshot, evidence_ref, snapshot_id_for
    d["snapshot_id"] = snapshot_id_for(spec.patient_ref, spec.T, GraphSpec.model_validate(d).evidence)  # consistent forgery
    try:
        validate(GraphSpec.model_validate(d))
        adv.append("forged spec future evidence validated")
    except GraphValidationError as e:
        if getattr(e, "code", "") != "future_evidence":
            adv.append(f"forged rejected with other code: {getattr(e, 'code', '')} {e}")
    except Exception as e:  # noqa: BLE001
        adv.append(f"forged raised {type(e).__name__}: {e}")
    # (d) hand-built Snapshot carrying a future item
    late = tuple(sorted(items, key=lambda i: (i.available_at_time, i.item_id)))
    refs = tuple(evidence_ref(i) for i in late)
    leaky = Snapshot(p, T1 + 40 * M, late, snapshot_id_for(p, T1 + 40 * M, refs))
    try:
        compile_stage(leaky, "T2")
        adv.append("leaky Snapshot compiled")
    except GraphValidationError as e:
        if getattr(e, "code", "") != "future_evidence":
            adv.append(f"leaky snapshot rejected with {getattr(e, 'code', '')}")
    res["adversarial_issues"] = adv
    # LATECONFIRM
    env2 = Env(c.scratch / "lateconfirm")
    p, items, hz = FIXTURES_STAGED["F-CXR"]()
    clock = [T1 + 55 * M]
    ex2 = env2.executor(clock=lambda: clock[0])
    def after(g):
        if g.stage == "T1":
            ex2.resume(g.graph_id, "confirm", "nurse-1", "nurse")
    t1g, t2g, t3g = build_versions(ex2, items, T1, hz, after_version=after)
    cid = f"confirmed:{t1g.graph_id}:human_checkpoint"
    res["lateconfirm_absent_t2"] = cid not in {r.item_id for r in t2g.evidence}
    res["lateconfirm_present_t3"] = cid in {r.item_id for r in t3g.evidence}
    # leakage audit CLI on every version: journey with the evidence items stored
    audit_bad = []
    for label in ("F-CXR", "F-SAME", "F-T3ONLY", "F-RED", "F-STALE", "F-PRE", "F-FUTURE"):
        env, ex, gs, seen, items, t1, hz = c.built[label]
        for g in gs:
            spec, its = ex.state.load_graph(g.graph_id)
            jp = c.scratch / f"journey_{label}_{g.version}.json"
            jp.write_text(json.dumps({"items": [i.model_dump(mode="json") for i in its]}))
            rc = subprocess.run([sys.executable, str(AUDIT), str(jp), "--as-of", g.T.isoformat()],
                                capture_output=True, text=True, cwd=REPO).returncode
            if rc != 0:
                audit_bad.append([label, g.version, rc])
    res["leakage_audit_version_failures"] = audit_bad
    rc = subprocess.run([sys.executable, str(AUDIT), "--dataset", str(c.dataset), "--report", str(c.scratch / "audit_report.json")],
                        capture_output=True, text=True, cwd=REPO)
    res["leakage_audit_dataset_rc"] = rc.returncode
    res["pass"] = (not bad and res["f_future_versions"] == 1 and not adv and res["lateconfirm_absent_t2"]
                   and res["lateconfirm_present_t3"] and not audit_bad and rc.returncode == 0)
    c.R["A4"] = res


# ---------- A5 ----------
def a5(c):
    res = {}
    import sqlite3
    p, items, hz = FIXTURES_STAGED["F-CXR"]()
    env = Env(c.scratch / "immut")
    clock = [T1 + 5 * M]
    ex = env.executor(clock=lambda: clock[0])
    plans = plan_stages(items, T1, hz)
    from casegraph.staged import build_version
    g1 = build_version(ex, items, plans[0], patient_ref=p)
    ex.resume(g1.graph_id, "confirm", "nurse-1", "nurse")
    def snapshot_state(gid):
        sdb = sqlite3.connect(env.root / "state.db")
        tables = [r[0] for r in sdb.execute("select name from sqlite_master where type='table'")]
        dump = {}
        for t in tables:
            cols = [c[1] for c in sdb.execute(f"pragma table_info({t})")]
            rows = sdb.execute(f"select * from {t}").fetchall()
            dump[t] = (cols, rows)
        sdb.close()
        return dump
    spec1, its1 = ex.state.load_graph(g1.graph_id)
    before = {
        "spec": spec1.model_dump_json(), "items": json.dumps([i.model_dump(mode="json") for i in its1], sort_keys=True),
        "run": ex.state.load_run(g1.graph_id),
        "outputs": {f.name: f.read_bytes() for f in (env.root / "outputs").rglob("*") if f.is_file()},
    }
    # build T2, T3
    clock[0] = T1 + 3 * H
    g2 = build_version(ex, items, plans[1], patient_ref=p)
    g3 = build_version(ex, items, plans[2], patient_ref=p)
    spec1b, its1b = ex.state.load_graph(g1.graph_id)
    after = {
        "spec": spec1b.model_dump_json(), "items": json.dumps([i.model_dump(mode="json") for i in its1b], sort_keys=True),
        "run": ex.state.load_run(g1.graph_id),
    }
    res["t1_spec_identical"] = before["spec"] == after["spec"]
    res["t1_items_identical"] = before["items"] == after["items"]
    res["t1_run_identical"] = before["run"] == after["run"]
    out_after = {f.name: f.read_bytes() for f in (env.root / "outputs").rglob("*") if f.is_file()}
    res["t1_outputs_identical"] = all(out_after.get(k) == v for k, v in before["outputs"].items())
    # re-save raises
    resave = []
    for g in (g1, g2, g3):
        spec, its = ex.state.load_graph(g.graph_id)
        try:
            ex.state.save_graph(spec, its)
            resave.append(f"{g.version} re-save accepted")
        except GraphVersionExists:
            pass
    res["resave_issues"] = resave
    # replay: 0 calls and same hashes
    c0 = env.calls
    rp_bad = []
    for g in (g1, g2, g3):
        out = replay(g.graph_id, ex.outputs, ex.state)
        rr = out if hasattr(out, "nodes") else getattr(out, "graph", out)
        try:
            ok = all(a.output_sha256 == b.output_sha256 for a, b in zip(g.nodes, rr.nodes))
        except Exception as e:  # noqa: BLE001
            ok = False
            rp_bad.append(f"{g.version}:{type(e).__name__}:{e}")
        if not ok:
            rp_bad.append(f"{g.version}: hash mismatch")
    res["replay_calls"] = env.calls - c0
    res["replay_issues"] = rp_bad
    # role guard
    guard = []
    for g, wrong in ((g2, ["nurse", "pharmacist"]), (g3, ["physician", "nurse"])):
        for role in wrong:
            try:
                ex.resume(g.graph_id, "confirm", "x", role)
                guard.append(f"{g.stage} resumed by {role}")
            except ResumeError:
                pass
    res["role_guard_issues"] = guard
    res["pass"] = (res["t1_spec_identical"] and res["t1_items_identical"] and res["t1_run_identical"]
                   and res["t1_outputs_identical"] and not resave and res["replay_calls"] == 0 and not rp_bad and not guard)
    c.R["A5"] = res


# ---------- A6 ----------
def a6(c):
    lost, runs = [], 0
    for mode in ("ok", "error", "schema_invalid", "raise"):
        for hostile in ("reasoning", "pharma", "both"):
            env = Env(c.scratch / f"a6_{mode}_{hostile}")
            tasks = {"reasoning", "pharma_agent"} if hostile == "both" else ({"reasoning"} if hostile == "reasoning" else {"pharma_agent"})
            env.gateways["project_model"] = LocalGateway(
                FakeProvider(model_version="proj-mock-0.1", mode=mode, tasks=tasks), audit_sink=env.audit.append)
            cfg = ProviderConfig().with_assignment(NodeType.PHARMA_AGENT, ProviderAssignment(provider="project_model", model_version="proj-mock-0.1"))
            cfg = cfg.with_assignment(NodeType.REASONING, ProviderAssignment(provider="project_model", model_version="proj-mock-0.1")) if hostile != "pharma" else cfg
            p, items, hz = FIXTURES_STAGED["F-RED"]()
            try:
                graphs = build_versions(env.executor(), items, T1, hz, cfg)
            except Exception as e:  # noqa: BLE001
                lost.append([mode, hostile, f"build raised {type(e).__name__}: {e}"])
                continue
            for g in graphs:
                runs += 1
                alerts = g.by_type(NodeType.RED_FLAG).output["Alerts"]
                hc = g.by_type(NodeType.HUMAN_CHECKPOINT)
                pay = (hc.output or {}).get(PENDING_KEY)
                urgent = {a["rule_id"] for a in alerts["alerts"] if a["severity"] == "urgent"}
                if pay is None or pay["alerts"] != alerts or pay["escalation"] is not True or "RF-SPO2" not in urgent:
                    lost.append([mode, hostile, g.stage, "alert lost/escalation false"])
    c.R["A6"] = {"runs": runs, "lost": lost, "pass": not lost and runs > 0}


# ---------- A7 ----------
def a7(c):
    res = {"t3_versions": 0, "bad": []}
    from casegraph import pharma_s5
    from app.pharma.pipeline import issue_signature
    captured = []
    real = pharma_s5.reconcile

    def spy(snapshot, invoke, mode, **kw):
        captured.append((snapshot, invoke))
        return real(snapshot, invoke, mode, **kw)
    pharma_s5.reconcile = spy
    parity_bad, parity_n, gold_med = [], 0, 0
    try:
        for label, (env, ex, graphs, seen, items, t1, hz) in c.built.items():
            for g in graphs:
                if g.stage != "T3":
                    continue
                res["t3_versions"] += 1
                ph = g.by_type(NodeType.PHARMA_AGENT)
                refs = set(ph.evidence_refs)
                by_id = {i.item_id: i for i in items}
                types_at = [(by_id[r].data_type, getattr(by_id[r], "list_source", None)) for r in refs if r in by_id]
                have_new = ("MedicationList", "new_order") in types_at
                have_home = any(i.data_type == "MedicationList" and getattr(i, "list_source", None) == "home_list" and i.available_at_time <= g.T for i in items)
                have_pr = any(i.data_type == "MedicationList" and getattr(i, "list_source", None) == "patient_reported" and i.available_at_time <= g.T for i in items)
                have_al = any(i.data_type == "AllergyList" and i.available_at_time <= g.T for i in items)
                if not have_new:
                    res["bad"].append([label, "no new_order ref"])
                if have_home and ("MedicationList", "home_list") not in types_at:
                    res["bad"].append([label, "home_list missing"])
                if have_pr and ("MedicationList", "patient_reported") not in types_at:
                    res["bad"].append([label, "patient_reported missing"])
                if have_al and ("AllergyList", None) not in types_at:
                    res["bad"].append([label, "AllergyList missing"])
                fe = [e for e in g.edges if e.dst == ph.id and e.data_type == "Findings"]
                if len(fe) != 1 or fe[0].src != "reader_text":
                    res["bad"].append([label, f"findings edges {[(e.src) for e in fe]}"])
                hc = g.by_type(NodeType.HUMAN_CHECKPOINT)
                pay = hc.output[PENDING_KEY]
                if "MedicationIssues" not in json.dumps(pay.get("for_review", pay)):
                    res["bad"].append([label, "MedicationIssues not in checkpoint for_review"])
                # not_evaluated allergy when absent
                if not have_al:
                    mi = ph.output["MedicationIssues"]
                    miss = json.dumps(mi.get("check_results"))
                    if "AllergyList" not in miss or mi["status"] == "evaluated":
                        res["bad"].append([label, "missing allergy not reported not_evaluated", mi["status"]])
        for label, p_, items, t1, hz in c.cases:
            if not (label.startswith("SYN/") or label == "F-T3ONLY"):
                continue
            env = Env(c.scratch / "parity" / label.replace("/", "_"))
            captured.clear()
            gs = build_versions(env.executor(), items, t1, hz)
            for g in gs:
                if g.stage != "T3":
                    continue
                ph = g.by_type(NodeType.PHARMA_AGENT)
                snap, invoke = captured[-1]
                direct = pharma_s5.reconcile_direct(snap, invoke)
                sig_g = sorted(issue_signature({"type": i["kind"], "rule_id": i["rule_id"], "ingredients": i["ingredients"],
                                                "conflicting_sources": i["conflicting_sources"], "severity": i["severity"],
                                                "severity_rank": i["severity_rank"], "field": i["field"]})
                               for i in ph.output["MedicationIssues"]["issues"])
                sig_d = sorted(issue_signature(i) for i in direct["issues"])
                parity_n += 1
                if sig_g != sig_d:
                    parity_bad.append(label)
    finally:
        pharma_s5.reconcile = real
    # captured only populated when executed (non-cached) -> verify gateway counting
    res["parity_checked"] = parity_n
    res["parity_bad"] = parity_bad
    # S5 cached? (parity relies on last spy capture; guard: run count)
    res["secondary_gold_med_issues"] = "NOT_MEASURABLE: gold/*.json has no medication_issues key"
    res["pass"] = not res["bad"]
    res["a7b_pass"] = not parity_bad and parity_n >= 36
    c.R["A7a"] = {k: res[k] for k in ("t3_versions", "bad", "pass")}
    c.R["A7b"] = {k: res[k] for k in ("parity_checked", "parity_bad", "secondary_gold_med_issues", "a7b_pass")}


STEPS = (("build_all", build_all), ("A1", a1), ("A2", a2), ("A3", a3), ("A4", a4), ("A5", a5), ("A6", a6), ("A7", a7))
METRICS = ("A1", "A2", "A3a", "A3b", "A4", "A5", "A6", "A7a", "A7b")


def status(v):
    return "PASS" if v and (v.get("pass") or v.get("a7b_pass")) else "FAIL/ERR"


def run_check(dataset, scratch, quiet=False) -> dict:
    c = Ctx(dataset, scratch)
    for name, fn in STEPS:
        try:
            fn(c)
        except Exception:  # noqa: BLE001
            c.R.setdefault("errors", {})[name] = traceback.format_exc()
            if not quiet:
                print("ERROR in", name, file=sys.stderr)
                traceback.print_exc()
    return c.R


def main(argv):
    out = Path(argv[2])
    R = run_check(argv[0], argv[1])
    out.write_text(json.dumps(R, indent=2, default=str))
    for k in METRICS:
        print(k, status(R.get(k)))


if __name__ == "__main__":
    main(sys.argv[1:])
