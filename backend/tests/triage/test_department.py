import json

import pytest

from app.gateway import ProviderResult, build_provider
from app.gateway import mock_tasks
from app.gateway import service as gateway_service
from app.config import Settings
from app.db import create_schema, make_engine
from app.triage import department, engine, evaluate, redflags
from app.triage.fixtures import load_entries
from app.triage.models import Snapshot

ENTRIES = load_entries()
MISSING = [e for e in ENTRIES if e.gold.missing_required]
RED = [e for e in ENTRIES if e.gold.red_flag_rules]
BY_REF = {e.case.case_ref: e for e in ENTRIES}


class FakeProvider:
    name = "fake"

    def __init__(self, status="ok", output=None, reason=None, raises=False):
        self.status, self.output, self.reason, self.raises = status, output, reason, raises
        self.calls = 0

    def invoke(self, request, sha):
        self.calls += 1
        if self.raises:
            raise RuntimeError("secret internals")
        return ProviderResult(status=self.status, model_version="fake-1", output=self.output, reason=self.reason)


def invoker(provider):
    eng = make_engine("sqlite://")
    create_schema(eng)
    return lambda req: gateway_service.invoke(eng, provider, req, None)


def mock():
    return invoker(build_provider("mock", Settings()))


@pytest.mark.parametrize("entry", MISSING, ids=[e.case.case_ref for e in MISSING])
def test_abstains_when_required_missing(entry):
    provider = FakeProvider(output={"ranking": []})
    a = engine.assess(entry.case, entry.as_of, invoker(provider), actor_id=1)
    assert a.department.status == "abstained"
    assert a.department.top3 == []
    assert a.department.missing_information == entry.gold.missing_required
    assert provider.calls == 0  # validated before the provider
    assert sorted(x.rule_id for x in a.alerts) == entry.gold.red_flag_rules
    assert a.escalation_required is bool(entry.gold.red_flag_rules)


def test_department_top3_threshold():
    report = evaluate.build_report()
    overall = report["metrics"]["overall"]["dept_top3_accuracy_answered"]
    assert overall["den"] >= 30 and overall["value"] >= 0.80
    for split in ("dev", "holdout"):
        m = report["metrics"][split]["dept_top1_accuracy_answered"]
        assert m["value"] is not None and m["ci95"] is not None
    assert report["label"] == "System Evaluation on synthetic fixtures — not clinical performance"
    assert report["flags"]["redflag_recall_gate_pass"] is True
    assert all(fp["justification"] != "UNJUSTIFIED — needs review" for fp in report["false_positives"])


def _assess(client, ref, as_of=None):
    body = {"as_of": as_of or BY_REF[ref].as_of.isoformat()}
    return client.post(f"/api/triage/cases/{ref}/assess", json=body)


def test_department_via_gateway(client, login, audit_rows):
    login("nurse1")
    before = len(audit_rows())
    resp = _assess(client, "SYN-S4-001")
    assert resp.status_code == 201
    dept = resp.json()["department"]
    rows = audit_rows()[before:]
    gw = [r for r in rows if r["action"] == "gateway.invoke"]
    assert len(gw) == 1
    assert gw[0]["target"] == "task/triage.department.v1"
    assert gw[0]["details"]["data_class"] == "synthetic"
    assert gw[0]["details"]["request_sha256"] == dept["request_sha256"]
    assert gw[0]["actor_role"] == "nurse"
    assert dept["provider"] == "mock" and dept["status"] == "suggested"
    assert dept["uncertainty_label"] == "MOCK baseline — not calibrated"
    # A missing-field case abstains before the provider: no gateway call.
    before = len(audit_rows())
    assert _assess(client, "SYN-S4-023").json()["department"]["status"] == "abstained"
    assert [r for r in audit_rows()[before:] if r["action"] == "gateway.invoke"] == []


FAILS = {
    "error": FakeProvider(status="error", reason="provider_timeout"),
    "rejected": FakeProvider(status="rejected", reason="policy_non_synthetic"),
    "invalid": FakeProvider(output={"ranking": [{"code": "ER", "score": 2.0, "evidence_refs": ["nope"]}]}),
    "exception": FakeProvider(raises=True),
}


@pytest.mark.parametrize("mode", list(FAILS))
def test_department_fail_safe(app, client, login, mode):
    app.state.provider = FAILS[mode]
    login("nurse1")
    for ref in ("SYN-S4-001", "SYN-S4-029"):
        resp = _assess(client, ref)
        assert resp.status_code == 201
        data = resp.json()
        assert data["department"]["status"] in ("error", "abstained")
        assert data["department"]["top3"] == []
        assert data["confirmed_department"] is None
        assert sorted(a["rule_id"] for a in data["alerts"]) == BY_REF[ref].gold.red_flag_rules
        assert "secret internals" not in resp.text


def test_model_cannot_suppress_alerts():
    hostile = [
        FakeProvider(output={"ranking": [], "alerts": [], "urgency": "none", "escalation_required": False}),
        FakeProvider(output={"ranking": [{"code": "MED", "score": 1.0, "evidence_refs": []}], "alerts": []}),
        FakeProvider(output={"ranking": [], "urgency": "none"}),
    ]
    lost = 0
    for provider in hostile:
        for e in RED:
            a = engine.assess(e.case, e.as_of, invoker(provider), actor_id=1)
            ref_alerts, _ = redflags.evaluate(Snapshot(e.case, e.as_of))
            if [x.model_dump() for x in a.alerts] != [x.model_dump() for x in ref_alerts] or not a.escalation_required:
                lost += 1
            assert a.department.top3 == []
    assert lost == 0


def test_alerts_survive_provider_error():
    for provider in (FakeProvider(raises=True), FakeProvider(status="error", reason="provider_timeout")):
        for e in RED:
            a = engine.assess(e.case, e.as_of, invoker(provider), actor_id=1)
            assert sorted(x.rule_id for x in a.alerts) == e.gold.red_flag_rules
            assert a.escalation_required is True
            assert a.department.status in ("error", "abstained") and a.department.top3 == []


def test_evidence_refs_time_valid():
    invoke = mock()
    checked = 0
    for e in ENTRIES:
        times = [e.as_of] + ([e.gold.temporal.early_as_of] if e.gold.temporal else [])
        fact_time = {f.fact_id: f.available_at_time for f in e.case.facts}
        for as_of in times:
            a = engine.assess(e.case, as_of, invoke, actor_id=1)
            refs = [r for x in a.alerts for r in x.evidence_refs] + [r for d in a.department.top3 for r in d.evidence_refs]
            for r in refs:
                assert fact_time[r] <= as_of, (e.case.case_ref, r)
                checked += 1
            if a.alerts:
                assert all(x.evidence_refs for x in a.alerts)
    assert checked > 50


def test_assessment_deterministic(client, login):
    login("nurse1")

    def strip(d):
        return {k: v for k, v in d.items() if k not in ("assessment_id", "created_at")}

    for ref in ("SYN-S4-002", "SYN-S4-026", "SYN-S4-036"):
        a, b = _assess(client, ref).json(), _assess(client, ref).json()
        assert a["assessment_id"] != b["assessment_id"]
        assert json.dumps(strip(a), sort_keys=True).encode() == json.dumps(strip(b), sort_keys=True).encode()


def test_mock_task_registry_backward_compatible(client, login):
    login("nurse1")
    # Unregistered tasks keep the s0 hash-based placeholder output.
    data = client.post("/api/gateway/invoke", json={"task": "echo", "inputs": {"x": 1}, "data_class": "synthetic"}).json()
    assert data["output"]["label"] == "MOCK — not clinical"
    assert data["output"]["mock_id"] == data["request_sha256"][:16]
    assert data["model_version"] == "mock-0.1.0"
    # Registered tasks dispatch to their handler.
    assert mock_tasks.lookup(department.TASK) is not None
    body = {"task": department.TASK, "data_class": "synthetic",
            "inputs": {"chief_complaint": {"fact_id": "X-1", "text": "ear pain"}, "symptoms_present": []}}
    data = client.post("/api/gateway/invoke", json=body).json()
    assert data["status"] == "ok" and data["output"]["ranking"][0]["code"] == "ENT"
    assert data["model_version"].startswith("mock-0.1.0+baseline-")
    mock_tasks.register("unit.test.v1", lambda i: {"n": 1}, version="t")
    with pytest.raises(ValueError):
        mock_tasks.register("unit.test.v1", lambda i: {"n": 2}, version="t")
