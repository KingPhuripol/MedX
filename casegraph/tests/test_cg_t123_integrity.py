"""Slice cg-t123 A4-A7a: temporal validity, immutability, replay, role guard, Red-flag non-suppression, T3 inputs.

Synthetic, offline, mock only. Research prototype: not clinical performance.
"""

from __future__ import annotations

import json
import subprocess
import sys
from datetime import datetime
from pathlib import Path

import pytest

from casegraph.compiler import GraphValidationError, Snapshot, build_snapshot, compile_stage, snapshot_id_for, validate
from casegraph.compiler import evidence_ref
from casegraph.data import dump_evidence
from casegraph.executor import PENDING_KEY, ResumeError
from casegraph.library import ProviderAssignment, ProviderConfig
from casegraph.providers import LocalGateway, register_pharma_provider
from casegraph.sources import s1r
from casegraph.staged import build_version, build_versions
from casegraph.stages import plan_stages
from casegraph.store import GraphVersionExists, replay
from casegraph.types import NodeType

from .conftest import Env, FakeProvider
from .fixtures import M
from .staged_fixtures import FIXTURES_STAGED, T1

ROOT = Path(__file__).resolve().parents[2]
AUDIT = ROOT / "scripts" / "temporal_leakage_audit.py"


@pytest.fixture(scope="module")
def dataset(s1r_dataset) -> Path:
    return s1r_dataset


class Clock:
    def __init__(self, now):
        self.now = now

    def __call__(self):
        return self.now


def _hc(graph):
    return graph.by_type(NodeType.HUMAN_CHECKPOINT)


def _payload(graph):
    return _hc(graph).output[PENDING_KEY]


# ------------------------------------------------------------------------------------------ A4


@pytest.mark.parametrize("name", sorted(FIXTURES_STAGED))
def test_stage_temporal(env, tmp_path, name):
    _, items, horizon = FIXTURES_STAGED[name]()
    ex = env.executor()
    graphs = build_versions(ex, items, T1, horizon)
    for g in graphs:
        assert all(r.available_at_time <= g.T for r in g.evidence)
        assert all(datetime.fromisoformat(p["available_at_time"]) <= g.T for p in _payload(g)["prior_confirmed"])
        # the version journey passes the project's temporal leakage audit at its own T
        spec, stored = ex.state.load_graph(g.graph_id)
        path = tmp_path / f"{name}-{g.graph_id.replace('/', '_')}.json"
        path.write_text(json.dumps({"items": dump_evidence(stored)}))
        r = subprocess.run([sys.executable, str(AUDIT), str(path), "--as-of", g.T.isoformat()],
                           capture_output=True, text=True, cwd=ROOT)
        assert r.returncode == 0, (g.graph_id, r.stdout)


def test_temporal_leakage_audit_dataset(dataset):
    r = subprocess.run([sys.executable, str(AUDIT), "--dataset", str(dataset)], capture_output=True, text=True,
                       cwd=ROOT)
    assert r.returncode == 0, r.stdout


def test_f_future_creates_no_version_and_forgeries_are_rejected(env):
    p, items, horizon = FIXTURES_STAGED["F-FUTURE"]()
    graphs = build_versions(env.executor(), items, T1, horizon)
    assert [g.stage for g in graphs] == ["T1"]  # the order and the result after the horizon create nothing
    assert not any(r.item_id.endswith(("order", "labs")) for g in graphs for r in g.evidence)
    # (2) a forged spec: T moved before an item it lists, with a consistent snapshot id
    full = build_snapshot(items, horizon + 10 * M, p)
    spec = compile_stage(full, "T3", trigger_refs=[f"{p}-order"]).spec
    forged = spec.model_copy(update={"T": horizon})
    forged = forged.model_copy(update={"snapshot_id": snapshot_id_for(p, horizon, forged.evidence)})
    with pytest.raises(GraphValidationError) as e:
        validate(forged)
    assert e.value.code == "future_evidence"
    # (3) compile_stage given a Snapshot that carries a future item
    late_items = tuple(sorted(items, key=lambda i: (i.available_at_time, i.item_id)))
    refs = tuple(evidence_ref(i) for i in late_items)
    leaky = Snapshot(p, horizon, late_items, snapshot_id_for(p, horizon, refs))
    with pytest.raises(GraphValidationError) as e:
        compile_stage(leaky, "T3", trigger_refs=[f"{p}-order"])
    assert e.value.code == "future_evidence"


def test_f_lateconfirm_is_absent_before_its_time_and_present_after(env):
    """The T1 nurse confirmation is stamped after T2's T: absent from T2, present in T3 (later T)."""
    p, items, horizon = FIXTURES_STAGED["F-CXR"]()
    clock = Clock(T1 + 55 * M)  # T2 is at t1+40, T3 at t1+70
    ex = env.executor(clock=clock)
    graphs = []

    def confirm_t1(g):
        graphs.append(g)
        if g.stage == "T1":
            ex.resume(g.graph_id, "confirm", "nurse-1", "nurse")

    out = build_versions(ex, items, T1, horizon, after_version=confirm_t1)
    t1, t2, t3 = out
    confirmed = f"confirmed:{t1.graph_id}:human_checkpoint"
    assert confirmed not in {r.item_id for r in t2.evidence} and _payload(t2)["prior_confirmed"] == []
    assert confirmed in {r.item_id for r in t3.evidence}
    (prior,) = _payload(t3)["prior_confirmed"]
    assert prior["item_id"] == confirmed and prior["reviewer_role"] == "nurse" and prior["action"] == "confirm"
    assert datetime.fromisoformat(prior["available_at_time"]) <= t3.T


def test_rejected_result_never_re_enters_and_edited_content_reaches_the_pharmacist(env):
    p, items, horizon = FIXTURES_STAGED["F-CXR"]()
    clock = Clock(T1 + 5 * M)
    ex = env.executor(clock=clock)

    def review(g):
        if g.stage == "T1":
            clock.now = T1 + 5 * M
            ex.resume(g.graph_id, "reject", "nurse-1", "nurse")  # a reject appends nothing
        if g.stage == "T2":
            clock.now = T1 + 60 * M  # after T2 (t1+40), before T3 (t1+70)
            ex.resume(g.graph_id, "edit", "doc-1", "physician", edited_payload={"care": ["synthetic edited care"]})

    t1, t2, t3 = build_versions(ex, items, T1, horizon, after_version=review)
    (prior,) = _payload(t3)["prior_confirmed"]
    assert prior["reviewer_role"] == "physician" and prior["action"] == "edit"
    assert prior["content"] == {"care": ["synthetic edited care"]}
    assert not any(r.item_id.startswith(f"confirmed:{t1.graph_id}") for r in t3.evidence)  # nothing from the reject
    # T3 carries no Reasoning output: the pharmacist is not shown an unconfirmed AI suggestion
    assert "reasoning" not in _payload(t3)["for_review"] and "pharma_agent" in _payload(t3)["for_review"]
    assert not any(k in json.dumps(_payload(t3)["for_review"]) for k in ("CareSuggestion", "DepartmentSuggestion"))


def test_confirmed_t2_content_is_prior_context_not_for_review(env):
    p, items, horizon = FIXTURES_STAGED["F-CXR"]()
    clock = Clock(T1 + 60 * M)
    ex = env.executor(clock=clock)
    out = build_versions(ex, items, T1, horizon, after_version=lambda g: (
        ex.resume(g.graph_id, "confirm", "doc-1", "physician") if g.stage == "T2" else None))
    payload = _payload(out[2])
    (prior,) = payload["prior_confirmed"]
    assert "reasoning" in prior["content"]  # the physician-confirmed Reasoning output, as context
    assert "reasoning" not in payload["for_review"]


# ------------------------------------------------------------------------------------------ A5


def _bytes(ex, graph_id):
    spec, items = ex.state.load_graph(graph_id)
    return spec.to_json(), json.dumps(dump_evidence(items)), ex.state.load_run(graph_id)


def test_stage_immutability(env):
    p, items, horizon = FIXTURES_STAGED["F-CXR"]()
    clock = Clock(T1 + 5 * M)
    ex = env.executor(clock=clock)
    plans = plan_stages(items, T1, horizon)
    t1 = build_version(ex, items, plans[0])
    ex.resume(t1.graph_id, "confirm", "nurse-1", "nurse")
    before = _bytes(ex, t1.graph_id)
    store_files = {n.cache_key: ex.outputs.path(n.cache_key).read_bytes() for n in t1.nodes}
    t2 = build_version(ex, items, plans[1])
    t3 = build_version(ex, items, plans[2])
    assert _bytes(ex, t1.graph_id) == before
    assert {k: ex.outputs.path(k).read_bytes() for k in store_files} == store_files
    for g in (t1, t2, t3):  # insert-only: re-saving any version raises
        spec, stored = ex.state.load_graph(g.graph_id)
        with pytest.raises(GraphVersionExists):
            ex.state.save_graph(spec, stored)


def test_stage_replay(env):
    p, items, horizon = FIXTURES_STAGED["F-CXR"]()
    ex = env.executor()
    graphs = build_versions(ex, items, T1, horizon)
    calls, execs = env.calls, sum(ex.node_executions.values())
    for g in graphs:
        again = replay(g.graph_id, ex.outputs, ex.state)
        assert [n.output_sha256 for n in again.nodes] == [n.output_sha256 for n in g.nodes]
        assert [n.output for n in again.nodes] == [n.output for n in g.nodes]
        assert (again.stage, again.trigger_refs) == (g.stage, g.trigger_refs)
    assert env.calls == calls and sum(ex.node_executions.values()) == execs  # 0 provider calls, 0 node bodies


def test_regenerate_keeps_the_stage_and_triggers(env):
    from casegraph.store import regenerate

    p, items, horizon = FIXTURES_STAGED["F-CXR"]()
    ex = env.executor()
    t1, t2, t3 = build_versions(ex, items, T1, horizon)
    again = regenerate(ex, t2.graph_id)
    assert (again.stage, again.trigger_refs, again.T) == ("T2", t2.trigger_refs, t2.T)
    assert again.version == 4 and again.parent_version == 2
    assert _hc(again).provider == "human:physician"
    assert [n.output_sha256 for n in again.nodes if n.type is not NodeType.HUMAN_CHECKPOINT] == [
        n.output_sha256 for n in t2.nodes if n.type is not NodeType.HUMAN_CHECKPOINT]


def test_export_schema_0_4_and_legacy_0_3_import(env):
    from casegraph.export import ExportVersionError, import_graph, to_json

    p, items, horizon = FIXTURES_STAGED["F-CXR"]()
    g = build_versions(env.executor(), items, T1, horizon)[1]
    text = to_json(g)
    assert json.loads(text)["stage"] == "T2" and import_graph(text) == g and to_json(import_graph(text)) == text
    # a 0.3 export (no stage fields) imports read-only with stage null and re-exports byte-identical as 0.3
    data = json.loads(text)
    data = {k: v for k, v in data.items() if k not in ("stage", "trigger_refs")} | {
        "schema_version": "casegraph-export/0.3"}
    legacy = json.dumps(data, sort_keys=True, indent=2, ensure_ascii=False) + "\n"
    old = import_graph(legacy)
    assert old.stage is None and old.trigger_refs == () and to_json(old) == legacy
    with pytest.raises(ExportVersionError):
        import_graph(legacy.replace("casegraph-export/0.3", "casegraph-export/0.2"))
    with pytest.raises(ValueError):  # a 0.3 export cannot claim a stage
        import_graph(json.dumps({**json.loads(legacy), "stage": "T2"}))


# --------------------------------------------------------------------------------- role guard


def test_role_guard_per_stage(env):
    p, items, horizon = FIXTURES_STAGED["F-CXR"]()
    ex = env.executor(clock=Clock(T1 + 180 * M))  # after every version's T
    t1, t2, t3 = build_versions(ex, items, T1, horizon)  # all three pending at once
    assert [_hc(g).status for g in (t1, t2, t3)] == ["pending_confirmation"] * 3
    for graph, wrong in ((t1, "physician"), (t2, "nurse"), (t2, "pharmacist"), (t3, "physician"), (t3, "nurse")):
        with pytest.raises(ResumeError):
            ex.resume(graph.graph_id, "confirm", "x-1", wrong)
    for graph, right in ((t2, "physician"), (t3, "pharmacist"), (t1, "nurse")):
        assert ex.resume(graph.graph_id, "confirm", "x-1", right).reviewer_role == right


# ------------------------------------------------------------------------------------------ A6


class _Hostile:
    """A hostile Reasoning/Pharma provider behind the gateway seam (project_model)."""


def _hostile_env(env, mode):
    env.gateways["project_model"] = LocalGateway(
        FakeProvider(model_version="proj-mock-0.1", mode=mode, tasks={"reasoning", "pharma_agent"}),
        audit_sink=env.audit.append)


MODES = ["ok", "error", "schema_invalid", "raise"]  # "ok": a plain, harmless "no alerts"-style output


@pytest.mark.parametrize("mode", MODES)
def test_red_flag_not_suppressed_by_stage(env, mode):
    _hostile_env(env, mode)
    cfg = ProviderConfig().with_assignment(NodeType.PHARMA_AGENT, ProviderAssignment(
        provider="project_model", model_version="proj-mock-0.1"))
    p, items, horizon = FIXTURES_STAGED["F-RED"]()
    graphs = build_versions(env.executor(), items, T1, horizon, cfg)
    assert [g.stage for g in graphs] == ["T1", "T2", "T3"]
    for g in graphs:
        alerts = g.by_type(NodeType.RED_FLAG).output["Alerts"]
        assert "RF-SPO2" in {a["rule_id"] for a in alerts["alerts"] if a["severity"] == "urgent"}, g.stage
        payload = _payload(g)
        assert payload["alerts"] == alerts and payload["escalation"] is True
        assert "urgent_red_flag" in payload["escalation_reasons"]
    if mode in ("error", "schema_invalid", "raise"):  # the hostile node failed; the alert still got through
        assert graphs[0].by_type(NodeType.REASONING).status == "error"
        assert graphs[2].by_type(NodeType.PHARMA_AGENT).status == "error"


def _empty_pharma(lists):
    return (), ()


def _raising_pharma(lists):
    raise RuntimeError("hostile pharma internals")


def _bad_pharma(lists):
    return (), ("not an issue",)  # schema-invalid output


@pytest.mark.parametrize("fn", [_empty_pharma, _raising_pharma, _bad_pharma])
def test_red_flag_not_suppressed_by_hostile_pharma_hook(env, fn):
    version = f"hostile-{fn.__name__}-0.1"
    register_pharma_provider(version, fn, label="hostile test hook")
    cfg = ProviderConfig().with_assignment(NodeType.PHARMA_AGENT, ProviderAssignment(provider="rules",
                                                                                     model_version=version))
    p, items, horizon = FIXTURES_STAGED["F-RED"]()
    t3 = build_versions(env.executor(), items, T1, horizon, cfg)[2]
    alerts = t3.by_type(NodeType.RED_FLAG).output["Alerts"]
    assert _payload(t3)["alerts"] == alerts and _payload(t3)["escalation"] is True


# ------------------------------------------------------------------------------------------ A7a


def test_t3_pharma_inputs_syn(env, dataset):
    sc = s1r.load_staged_case(dataset, "dev", "SYNE-0007", "T2")
    ex = env.executor()
    graphs = build_versions(ex, sc.items, sc.t1, sc.horizon)
    t3 = next(g for g in graphs if g.stage == "T3")
    pharma = t3.by_type(NodeType.PHARMA_AGENT)
    by_id = {i.item_id: i for i in sc.items}
    got = {(by_id[r].data_type, getattr(by_id[r], "list_source", None)) for r in pharma.evidence_refs}
    assert got == {("MedicationList", "home_list"), ("MedicationList", "patient_reported"),
                   ("MedicationList", "new_order"), ("AllergyList", None)}
    assert [(e.src, e.data_type) for e in t3.edges if e.dst == "pharma_agent"] == [("reader_text", "Findings")]
    assert "pharma_agent" in _payload(t3)["for_review"]
    assert "MedicationIssues" in _payload(t3)["for_review"]["pharma_agent"]


def test_t3_missing_allergy_not_negative(env):
    p, items, horizon = FIXTURES_STAGED["F-T3ONLY"]()
    t1, t3 = build_versions(env.executor(), items, T1, horizon)
    assert (t1.stage, t3.stage) == ("T1", "T3")
    mi = t3.by_type(NodeType.PHARMA_AGENT).output["MedicationIssues"]
    assert "AllergyList" in mi["missing_inputs"] and mi["status"] != "evaluated"
    gate = [c for c in mi["check_results"] if c["check"] == "allergy_record"]
    assert len(gate) == 1 and gate[0]["status"] == "not_evaluated" and gate[0]["fired"] is None
    assert gate[0]["missing_inputs"] == ["AllergyList"]
    assert not any(c["check"].startswith("allergy") and c["status"] == "evaluated" for c in mi["check_results"])


def test_t3_unknown_allergy_status_is_not_evaluated(env):
    from .staged_fixtures import allergy, base, order

    p = "SYN-UNK"
    items = [*base(p, with_allergy=False), allergy(p, f"{p}-al", T1 - 48 * 60 * M, status="unknown"),
             order(p, f"{p}-order", T1 + 30 * M)]
    t3 = build_versions(env.executor(), items, T1, T1 + 2 * 60 * M)[1]
    mi = t3.by_type(NodeType.PHARMA_AGENT).output["MedicationIssues"]
    assert "AllergyList.status=unknown" in mi["missing_inputs"]


def _t3_pharma(env, items):
    t3 = build_versions(env.executor(), items, T1, T1 + 2 * 60 * M)[-1]
    assert t3.stage == "T3"
    return t3, t3.by_type(NodeType.PHARMA_AGENT).output["MedicationIssues"]


def _allergy_rows(mi):
    return {c["check"]: c for c in mi["check_results"] if c["check"].startswith("allergy")}


def _assert_not_negative(t3, mi, check, fact_kinds):
    row = _allergy_rows(mi)[check]
    assert row["status"] == "not_evaluated" and row["fired"] is None and row["missing_inputs"]
    assert mi["status"] != "evaluated" and set(row["missing_inputs"]) <= set(mi["missing_inputs"])
    shown = _payload(t3)["for_review"]["pharma_agent"]["MedicationIssues"]["conversation_allergy_facts"]
    assert {f["kind"] for f in shown} >= set(fact_kinds)


def test_t3only_conversation_allergy_unnamed_no_record(env):
    p, items, horizon = FIXTURES_STAGED["F-T3ONLY"]()
    t3, mi = _t3_pharma(env, items)
    assert {"allergy_record", "allergy_conversation"} <= set(_allergy_rows(mi))
    _assert_not_negative(t3, mi, "allergy_conversation", ["allergy_status"])


def test_conversation_allergy_contradicts_no_known_allergy(env):
    from .staged_fixtures import allergy, base, conv_allergy, order

    p = "SYN-CONTRA"
    items = [*base(p, with_allergy=False), allergy(p, f"{p}-al", T1 - 48 * 60 * M, status="no_known_allergy"),
             conv_allergy(p, f"{p}-conv", T1 - 15 * M, allergens=("UNKNOWN", None)), order(p, f"{p}-o", T1 + 30 * M)]
    t3, mi = _t3_pharma(env, items)
    rows = _allergy_rows(mi)
    assert "allergy_contradiction" in rows and "allergy_conversation" in rows
    _assert_not_negative(t3, mi, "allergy_contradiction", ["allergy_status", "allergens"])
    assert "AllergyList.status=no_known_allergy vs conversation.allergy_status=present" in mi["missing_inputs"]


def test_conversation_allergens_refused_is_not_dropped(env):
    from .staged_fixtures import base, conv_allergy, order

    p = "SYN-REFUSED"
    items = [*base(p), conv_allergy(p, f"{p}-conv", T1 - 15 * M, allergens=("REFUSED", None)),
             order(p, f"{p}-o", T1 + 30 * M)]
    t3, mi = _t3_pharma(env, items)
    assert _allergy_rows(mi)["allergy_conversation"]["missing_inputs"] == ["conversation.allergens=REFUSED"]
    _assert_not_negative(t3, mi, "allergy_conversation", ["allergens"])


def test_known_list_plus_unnamed_extra_allergy(env):
    from .staged_fixtures import base, conv_allergy, order

    p = "SYN-EXTRA"
    items = [*base(p), conv_allergy(p, f"{p}-conv", T1 - 15 * M), order(p, f"{p}-o", T1 + 30 * M)]
    t3, mi = _t3_pharma(env, items)
    assert "allergy_contradiction" not in _allergy_rows(mi)
    assert _allergy_rows(mi)["allergy_conversation"]["missing_inputs"] == ["conversation.allergens:unnamed_allergy"]
    _assert_not_negative(t3, mi, "allergy_conversation", ["allergy_status"])


def test_named_allergen_with_known_list_adds_no_gap(env):
    from .staged_fixtures import base, conv_allergy, order

    p = "SYN-NAMED"
    items = [*base(p), conv_allergy(p, f"{p}-conv", T1 - 15 * M, allergens=("KNOWN", ["sulfa"])),
             order(p, f"{p}-o", T1 + 30 * M)]
    _, mi = _t3_pharma(env, items)
    assert not {"allergy_conversation", "allergy_contradiction"} & set(_allergy_rows(mi))


def test_pharma_never_runs_before_new_orders(env, dataset):
    """T1 for a case with a home list and a patient-reported list has no Pharma node (3.2.2/3.2.4)."""
    sc = s1r.load_staged_case(dataset, "dev", "SYNE-0007", "T1")
    (t1,) = build_versions(env.executor(), sc.items, sc.t1, sc.horizon)
    assert t1.stage == "T1" and t1.by_type(NodeType.PHARMA_AGENT) is None
    assert any(i.data_type == "MedicationList" for i in sc.items)


# ------------------------------------------------------------------------------------------ A7b


def _graph_signatures(output: dict) -> list[tuple]:
    from casegraph.pharma_s5 import issue_signature

    return sorted(issue_signature({
        "type": i["kind"], "rule_id": i["rule_id"], "ingredients": i["ingredients"],
        "conflicting_sources": i["conflicting_sources"], "severity": i["severity"],
        "severity_rank": i["severity_rank"], "field": i["field"]}) for i in output["issues"])


def test_s5_parity(tmp_path, dataset, monkeypatch):
    """The graph's Pharma issue signatures equal a direct app.pharma.pipeline.reconcile on the same MedSnapshot."""
    from casegraph import pharma_s5

    captured: list = []
    real = pharma_s5.reconcile

    def spy(snapshot, invoke, mode, **kw):
        captured.append((snapshot, invoke))
        return real(snapshot, invoke, mode, **kw)

    monkeypatch.setattr(pharma_s5, "reconcile", spy)
    ids = sorted(p.name for p in (dataset / "inputs" / "dev").iterdir())[:12]
    checked = 0
    for case_id in ids:
        sc = s1r.load_staged_case(dataset, "dev", case_id, "T2")
        captured.clear()
        env = Env(tmp_path / case_id)
        t3 = [g for g in build_versions(env.executor(), sc.items, sc.t1, sc.horizon) if g.stage == "T3"]
        for g in t3:
            snap, invoke = captured[-1]
            direct = pharma_s5.reconcile_direct(snap, invoke)
            mi = g.by_type(NodeType.PHARMA_AGENT).output["MedicationIssues"]
            assert _graph_signatures(mi) == sorted(pharma_s5.issue_signature(i) for i in direct["issues"]), case_id
            checked += 1
    assert checked >= 1


# ------------------------------------------------------------------ H-1: failed Reader:Text at T3


def _failing_reader(monkeypatch):
    from casegraph import reader_text

    def boom(*_a, **_k):
        raise reader_text.ReaderError("provider_down")

    monkeypatch.setattr(reader_text, "read_clinical_text", boom)


@pytest.mark.parametrize("record", ["no_known_allergy", "known", "none"])
def test_failed_reader_text_at_t3_is_never_a_full_evaluation(env, monkeypatch, record):
    from .staged_fixtures import allergy, base, conv_allergy, order

    p = f"SYN-RDERR-{record}"
    items = [*base(p, with_allergy=False)]
    if record != "none":
        items.append(allergy(p, f"{p}-al", T1 - 48 * 60 * M, status=record))
    items += [conv_allergy(p, f"{p}-conv", T1 - 15 * M), order(p, f"{p}-o", T1 + 30 * M)]
    _failing_reader(monkeypatch)
    t3, mi = _t3_pharma(env, items)
    pharma = t3.by_type(NodeType.PHARMA_AGENT)
    assert t3.by_type(NodeType.READER_TEXT).status == "error"
    assert pharma.status == "ok" and "reader_text" in pharma.errored_inputs
    assert mi["status"] != "evaluated"
    rows = _allergy_rows(mi)
    assert rows["allergy_conversation"]["status"] == "not_evaluated"
    assert rows["allergy_conversation"]["missing_inputs"] == ["Findings<-Reader:Text:errored"]
    med = {c["check"]: c for c in mi["check_results"]}["medication_conversation"]
    assert med["status"] == "not_evaluated" and med["fired"] is None
    assert "Findings<-Reader:Text:errored" in mi["missing_inputs"]


def test_no_reader_text_node_means_no_conversation_evidence(env):
    from .staged_fixtures import allergy, base, order

    p = "SYN-NOREADER"
    items = [*base(p, with_allergy=False), allergy(p, f"{p}-al", T1 - 48 * 60 * M, status="known"),
             order(p, f"{p}-o", T1 + 30 * M)]
    items = [i for i in items if i.data_type not in ("VoiceIntakeFacts", "ClinicalText")]
    t3, mi = _t3_pharma(env, items)
    pharma = t3.by_type(NodeType.PHARMA_AGENT)
    assert not any(n.type is NodeType.READER_TEXT for n in t3.nodes), "fixture still produces a Reader:Text node"
    # nothing was dropped: no errored input, no fabricated conversation row; record gates are unchanged
    assert pharma.errored_inputs == ()
    assert not {"allergy_conversation", "medication_conversation"} & {c["check"] for c in mi["check_results"]}
