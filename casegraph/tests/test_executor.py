"""Executor: S2-A12..A15, A18, A19; S2R-A11."""

from __future__ import annotations

import threading
from datetime import datetime, timedelta, timezone

import pytest

from casegraph.compiler import build_snapshot, compile_graph
from casegraph.data import sha256_json
from casegraph.executor import PENDING_KEY, ResumeError
from casegraph.library import LibraryConfig, ProviderAssignment, ProviderConfig
from casegraph.providers import LocalGateway
from casegraph.store import SQLiteStateStore
from casegraph.types import NodeType as N

from .conftest import Env, FakeProvider, compile_case, s2_config
from .fixtures import CASES, DAY, F1_T1, F2_T, F3_T, F5_T, H, cxr, f1

CONFIRM_AT = datetime(2026, 1, 2, 9, 0, tzinfo=timezone.utc)


def _ts(s: str) -> datetime:
    return datetime.fromisoformat(s)


def _with_fake(env: Env, provider_id: str, **kw) -> FakeProvider:
    fake = FakeProvider(**kw)
    env.gateways[provider_id] = LocalGateway(fake, audit_sink=env.audit.append)
    return fake


# ------------------------------------------------------------------------------------ A12


def test_independent_readers_run_concurrently(env):
    barrier = threading.Barrier(3, timeout=5)
    for pid in ("project_model", "encoder_3d"):
        _with_fake(env, pid, barrier=barrier)
    cfg = s2_config().with_assignment(
        N.READER_VITALS_LABS, ProviderAssignment(provider="project_model", model_version="fake-0.1"))
    graph = env.executor().run_sync(compile_case("F2", F2_T, cfg))
    readers = [graph.node(i) for i in ("reader_text", "reader_vitals_labs", "reader_ct_mri")]
    assert [r.status for r in readers] == ["ok", "ok", "ok"], [r.reason for r in readers]
    assert not barrier.broken
    spans = [(_ts(r.started_at), _ts(r.ended_at)) for r in readers]
    overlaps = sum(a[0] < b[1] and b[0] < a[1] for i, a in enumerate(spans) for b in spans[i + 1:])
    assert overlaps >= 1


# ------------------------------------------------------------------------------------ A13


@pytest.mark.parametrize("name,T", CASES)
def test_topological_order_respected(env, name, T):
    graph = env.executor().run_sync(compile_case(name, T))
    for e in graph.edges:
        assert _ts(graph.node(e.dst).started_at) >= _ts(graph.node(e.src).ended_at), e


# ------------------------------------------------------------------------------------ A14


def test_reasoning_abstains_with_missing_list(env):
    graph = env.executor().run_sync(compile_case("F3", F3_T))
    r = graph.node("reasoning")
    assert r.status == "abstained"
    assert list(r.missing_inputs) == ["Findings<-Vitals"]
    assert r.gateway_calls == 0 and r.output is None
    assert env.gateways["project_model"].calls == 1  # reader_text only
    payload = graph.node("human_checkpoint").output[PENDING_KEY]
    # s2r: F3 has no Vitals, so the Red-flag screen was NOT performed (was "evaluated" at edf8182: the defect).
    assert payload["alerts"] is not None and payload["alerts"]["status"] == "not_evaluated"
    assert payload["abstained"] == {"reasoning": ["Findings<-Vitals"]}
    outputs = [n.output for n in graph.nodes if n.output] + [payload["for_review"]]
    produced = {k for o in outputs for k in o} | {k for o in payload["for_review"].values() for k in o}
    assert not produced & {"CaseSummary", "DepartmentSuggestion", "CareSuggestion"}


# ------------------------------------------------------------------------------------ A15


EDITED = {"department": "edited-by-reviewer (synthetic)"}


@pytest.mark.parametrize("action", ["confirm", "edit", "reject"])
def test_checkpoint_pending_and_resume(env, action):
    graph = env.executor().run_sync(compile_case("F1", F1_T1))
    assert graph.node("human_checkpoint").status == "pending_confirmation"
    # persisted in the file StateStore: visible to a brand-new store instance
    fresh_state = SQLiteStateStore(env.root / "state.db")
    assert '"pending_confirmation"' in fresh_state.load_run("SYN-F1/v1")

    calls_before = env.calls
    ex2 = env.executor(clock=lambda: CONFIRM_AT)  # fresh Executor, same files
    result = ex2.resume("SYN-F1/v1", action, "dr-synthetic-01", "physician",
                        edited_payload=EDITED if action == "edit" else None)
    assert (result.action, result.reviewer_id, result.reviewer_role) == (action, "dr-synthetic-01", "physician")
    assert result.confirmed_at == CONFIRM_AT and result.confirmed_at.utcoffset() == timedelta(0)
    assert result.checkpoint_input_hash == graph.node("human_checkpoint").output[PENDING_KEY]["input_hash"]
    expected_payload = {"confirm": graph.node("human_checkpoint").output[PENDING_KEY], "edit": EDITED,
                        "reject": None}[action]
    assert result.payload == expected_payload
    assert env.calls == calls_before and sum(ex2.node_executions.values()) == 0

    after = env.executor().export("SYN-F1/v1")
    hc = after.node("human_checkpoint")
    assert hc.status == {"confirm": "confirmed", "edit": "edited", "reject": "rejected"}[action]
    assert hc.confirmation["reviewer_id"] == "dr-synthetic-01"
    with pytest.raises(ResumeError):  # a decision is recorded once
        ex2.resume("SYN-F1/v1", "confirm", "dr-synthetic-01", "physician")


def test_resume_wrong_role_rejected(env):
    env.executor().run_sync(compile_case("F1", F1_T1))
    ex = env.executor()
    for role in ("nurse", "pharmacist"):
        with pytest.raises(ResumeError, match="requires human:physician"):
            ex.resume("SYN-F1/v1", "confirm", "n-01", role)
    with pytest.raises(ResumeError):
        ex.resume("SYN-F1/v1", "approve", "dr-01", "physician")
    with pytest.raises(ResumeError):
        ex.resume("SYN-F1/v1", "edit", "dr-01", "physician")  # edit without payload
    assert ex.export("SYN-F1/v1").node("human_checkpoint").status == "pending_confirmation"
    assert ex.state.evidence("SYN-F1") == []
    # a checkpoint configured for a nurse accepts a nurse
    cfg = s2_config().with_assignment(N.HUMAN_CHECKPOINT,
                                           ProviderAssignment(provider="human:nurse", model_version="human"))
    ex.run_sync(compile_case("F3", F3_T, cfg))
    assert ex.resume("SYN-F3/v1", "confirm", "n-01", "nurse").reviewer_role == "nurse"


# ------------------------------------------------------------------------------------ A18


def _alerts(graph):
    return graph.node("red_flag").output["Alerts"]


@pytest.mark.parametrize("reasoning_state", ["ok", "abstained", "error"])
def test_red_flag_escalates_regardless_of_reasoning(env, reasoning_state):
    cfg = None
    if reasoning_state == "abstained":
        cfg = s2_config(ProviderConfig(library=LibraryConfig(reasoning_required_inputs=("Findings<-CXRImage",))))
    if reasoning_state == "error":
        _with_fake(env, "project_model", model_version="proj-mock-0.1", mode="error", tasks={"reasoning"})
    graph = env.executor().run_sync(compile_case("F5", F5_T, cfg))
    assert graph.node("reasoning").status == reasoning_state
    alerts = _alerts(graph)
    assert alerts["status"] == "evaluated"
    assert {"RF-PH-001", "RF-PH-002"} <= {a["rule_id"] for a in alerts["alerts"] if a["severity"] == "urgent"}
    assert all("PLACEHOLDER — not clinical" in a["message"] for a in alerts["alerts"])
    payload = graph.node("human_checkpoint").output[PENDING_KEY]
    assert payload["escalation"] is True and "urgent_red_flag" in payload["escalation_reasons"]
    assert payload["alerts"] == alerts


def test_red_flag_not_evaluated_without_inputs(env):
    # Only a CXR on encoder_2d: ImageTokens reach Reasoning only; Red-flag gets no Findings and no Vitals.
    items = [cxr("SYN-RF0", "rf0-cxr", DAY + 8 * H, DAY + 8 * H)]
    graph = env.executor().run_sync(compile_graph(build_snapshot(items, DAY + 9 * H), s2_config()))
    alerts = _alerts(graph)
    assert alerts["status"] == "not_evaluated" and alerts["alerts"] == []
    # s2r: plus each rule's declared Vitals.<key> (was ["Findings", "Vitals"] at edf8182)
    assert alerts["missing_inputs"] == ["Findings", "Vitals", "Vitals.hr", "Vitals.sbp", "Vitals.spo2", "Vitals.temp_c"]
    payload = graph.node("human_checkpoint").output[PENDING_KEY]
    assert payload["escalation"] is True and payload["escalation_reasons"] == ["red_flag_not_evaluated"]
    # also when the only Findings producer failed
    _with_fake(env, "project_model", model_version="proj-mock-0.1", mode="error", tasks={"reader_text"})
    g3 = env.executor().run_sync(compile_case("F3", F3_T))
    assert _alerts(g3)["status"] == "not_evaluated"
    assert g3.node("red_flag").errored_inputs == ("reader_text",)


# ------------------------------------------------------------------------------------ A19


@pytest.mark.parametrize("mode", ["error", "rejected", "schema_invalid", "raise"])
def test_provider_failure_fail_safe(env, mode):
    _with_fake(env, "project_model", model_version="proj-mock-0.1", mode=mode, tasks={"reader_text"})
    graph = env.executor().run_sync(compile_case("F1", F1_T1))
    rt = graph.node("reader_text")
    assert (rt.status, rt.output) == ("error", None)
    assert rt.output_sha256 == sha256_json(None) and rt.gateway_calls == 1
    r = graph.node("reasoning")
    assert r.status == "abstained" and r.output is None and r.gateway_calls == 0
    assert list(r.missing_inputs) == ["Findings<-ClinicalText"] and r.errored_inputs == ("reader_text",)
    assert graph.node("red_flag").status == "ok"
    payload = graph.node("human_checkpoint").output[PENDING_KEY]
    assert payload["errored"] == ["reader_text"] and payload["alerts"] is not None
    assert all(n.output is None for n in graph.nodes if n.status in ("error", "abstained"))
    assert "provider internals" not in graph.model_dump_json()


def test_errors_are_not_served_from_cache(env):
    _with_fake(env, "project_model", model_version="proj-mock-0.1", mode="error", tasks={"reader_text"})
    env.executor().run_sync(compile_case("F1", F1_T1))
    _with_fake(env, "project_model", model_version="proj-mock-0.1")
    g = env.executor().run_sync(compile_case("F1", F1_T1, version=2, parent_version=1))
    assert g.node("reader_text").status == "ok" and g.node("reader_text").cached is False
    assert g.node("reasoning").status == "ok"


def test_f1_t2_executes_all_seven_nodes(env):
    graph = env.executor().run_sync(compile_case("F1", F1_T1.replace(hour=10)))
    issues = graph.node("pharma_agent").output["MedicationIssues"]["issues"]
    assert {i["kind"] for i in issues} == {"duplicate", "dose_mismatch"}
    assert graph.node("reader_cxr").output["ImageTokens"]["encoder_provider"] == "encoder_2d"
    assert len(f1()) == 6  # i2: F1 gained Demographics and an S3 intake transcript


# ------------------------------------------------------------------------ S2R-A11 (s2r)


class _ReasoningOutput(FakeProvider):
    """Reasoning returns ``output`` verbatim; other tasks behave like FakeProvider(mode="ok")."""

    def __init__(self, output, **kw):
        super().__init__(model_version="proj-mock-0.1", **kw)
        self.output = output

    def invoke(self, request, request_sha256):
        from app.gateway.provider import ProviderResult

        if request.task == "reasoning":
            return ProviderResult(status="ok", model_version=self.model_version, output=self.output)
        return super().invoke(request, request_sha256)


# i2: the department part is S4 department.suggest (its own strict parser); the summary/care call no
# longer carries a department key, so only "text" and "care" are required of it.
@pytest.mark.parametrize("absent", ["care", "text"])
def test_reasoning_missing_keys_schema_invalid(env, absent):
    full = {"text": "synthetic summary", "care": ["synthetic item"]}
    env.gateways["project_model"] = LocalGateway(_ReasoningOutput({k: v for k, v in full.items() if k != absent}))
    r = env.executor().run_sync(compile_case("F1", F1_T1)).node("reasoning")
    assert (r.status, r.reason, r.output) == ("error", "schema_invalid", None)
    # an explicit null department is accepted: "no department proposed"
    env2 = Env(env.root / "explicit")
    env2.gateways["project_model"] = LocalGateway(_ReasoningOutput(full))
    ok = env2.executor().run_sync(compile_case("F1", F1_T1)).node("reasoning")
    # the fake answers the S4 department task with a non-S4 body: S4's strict parser records an error, and the
    # suggestion carries no top3 (never a fabricated department)
    dep = ok.output["DepartmentSuggestion"]
    assert ok.status == "ok" and dep["status"] == "error" and dep["top3"] == []
    assert ok.output["CareSuggestion"]["items"] == ["synthetic item"]


def _meds(pid, iid, *meds):
    from casegraph.data import MedicationEntry, MedicationList

    def entry(m):  # i2: s1 MedicationEntry shape; "500 mg" -> dose_value/dose_unit
        value, unit = m["dose"].split() if m.get("dose") else (None, None)
        return MedicationEntry(generic_name=m["name"], dose_value=value and float(value), dose_unit=unit)

    return MedicationList(item_id=iid, patient_ref=pid, event_time=DAY + 8 * H, available_at_time=DAY + 8 * H,
                          source="synthetic-fixture", provenance="casegraph/tests", version="1",
                          data_class="synthetic", list_source="home_list", entries=tuple(entry(m) for m in meds))


def test_pharma_missing_dose_not_evaluated(env):
    pid = "SYN-PH1"
    items = [_meds(pid, "ph-a", {"name": "Paracetamol", "dose": "500 mg"}, {"name": "Amlodipine", "dose": "5 mg"}),
             _meds(pid, "ph-b", {"name": "paracetamol"})]  # second entry has no dose
    graph = env.executor().run_sync(compile_graph(build_snapshot(items, DAY + 9 * H), s2_config()))
    mi = graph.node("pharma_agent").output["MedicationIssues"]
    gaps = [(c["medication"], c["check"], c["missing_inputs"]) for c in mi["checks_not_evaluated"]]
    assert gaps == [("paracetamol", "dose_mismatch", ["MedicationList.dose@ph-b"])]
    assert mi["status"] == "partially_evaluated" and mi["status"] != "evaluated"
    assert mi["missing_inputs"] == ["MedicationList.dose@ph-b"]
    assert {i["kind"] for i in mi["issues"]} == {"duplicate"}  # no mismatch claimed, none silently cleared
    assert mi["rule_set_version"] == "placeholder-pharma-0.2"


def test_pharma_model_path_not_evaluated(env):
    cfg = s2_config().with_assignment(
        N.PHARMA_AGENT, ProviderAssignment(provider="project_model", model_version="proj-mock-0.1"))
    graph = env.executor().run_sync(compile_case("F1", F1_T1.replace(hour=10), cfg))
    pa = graph.node("pharma_agent")
    assert pa.status == "ok" and pa.gateway_calls == 1
    mi = pa.output["MedicationIssues"]
    assert mi["status"] == "not_evaluated" and mi["issues"] == [] and mi["check_results"] == []
    assert mi["missing_inputs"] == ["structured_rule_checks"] and mi["summary"]


def test_reasoning_without_declared_required_inputs_fails_safe(env):
    """s2r sweep: a Reasoning node whose params lack ``required_inputs`` errors; it never runs unguarded."""
    from casegraph.compiler import validate

    graph = compile_case("F3", F3_T)
    spec = graph.spec.model_copy(update={"nodes": tuple(
        n.model_copy(update={"params": {k: v for k, v in n.params.items() if k != "required_inputs"}})
        if n.type is N.REASONING else n for n in graph.spec.nodes)})
    out = env.executor().run_sync(validate(spec, graph.snapshot))
    r = out.node("reasoning")
    assert (r.status, r.reason, r.output, r.gateway_calls) == ("error", "required_inputs_undeclared", None, 0)
    assert "reasoning" in out.node("human_checkpoint").output[PENDING_KEY]["errored"]
