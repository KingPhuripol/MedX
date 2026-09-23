"""MedX acceptance: real routing, gateway boundaries, replay and role separation."""
from copy import deepcopy
from datetime import datetime, timezone, timedelta
import pytest
from pydantic import ValidationError
from innovation.v2.models import ClinicalFact, CaseRevision, DesignSpec, EncounterCreate, EventRequest, TurnRequest, ReviewDecision
from innovation.v2.runtime import Runtime, DESIGNS
from innovation.v2.providers import MockProvider
from innovation.v2.graph import compile_graph, WorkflowGraph, replay
from innovation.v2.store import Store, DomainError, digest
from innovation.v2.service import Service, Principal

T = datetime(2026, 9, 22, tzinfo=timezone.utc)

def fact(kind, state="KNOWN"):
    return ClinicalFact(event_id=kind, kind=kind, state=state, value="synthetic" if state == "KNOWN" else None, observed_at=T, available_at_time=T)

def snapshot(facts=()):
    payload = dict(encounter_id="synthetic-1", case_revision=len(facts), decision_time=T, evidence=list(facts))
    return CaseRevision(**payload, checksum=digest([f.model_dump(mode="json") for f in facts]))

def test_adaptive_graph_changes_with_case_and_has_types():
    sparse = compile_graph(snapshot(), DESIGNS["adaptive"])
    complete = compile_graph(snapshot([fact(k) for k in ("CHIEF_COMPLAINT","HISTORY","MEDICATION","ALLERGY","VITAL")]), DESIGNS["adaptive"])
    assert [n.operator for n in sparse.nodes] == ["intake", "check", "draft", "verify"]
    assert [n.operator for n in complete.nodes] == ["draft", "verify"]
    invalid = complete.model_dump()
    invalid["nodes"][0]["depends_on"] = ["verify"]
    with pytest.raises(ValidationError): WorkflowGraph.model_validate(invalid)
    invalid = complete.model_dump(); invalid["nodes"][1]["input_type"] = "snapshot"
    with pytest.raises(ValidationError): WorkflowGraph.model_validate(invalid)

def test_replay_is_exact_and_tampering_is_rejected():
    class Counting(MockProvider):
        count = 0
        def infer(self,*args):
            self.count += 1
            return super().infer(*args)
    provider = Counting()
    run, content = Runtime(provider).execute(snapshot([fact("CHIEF_COMPLAINT")]), "synthetic", DESIGNS["adaptive"])
    assert run.status == "COMPLETED"
    artifact = run.provenance["execution"]
    assert artifact["steps"][-1]["tool"] == "verify_draft"
    assert replay(artifact)["result"]["content"] == content.model_dump(mode="json")
    assert provider.count == 1
    changed = deepcopy(artifact); changed["result"]["content"]["summary"] = "tampered"
    with pytest.raises(DomainError, match="GRAPH_ARTIFACT_INTEGRITY_FAILURE"): replay(changed)

def test_temporal_boundary_blocks_before_adapter():
    class Forbidden(MockProvider):
        def infer(self, *args): pytest.fail("future evidence reached provider")
    future = fact("HISTORY").model_copy(update={"available_at_time": T + timedelta(days=1)})
    run, content = Runtime(Forbidden()).execute(snapshot([future]), "synthetic", DESIGNS["fixed"])
    assert run.error_code == "TEMPORAL_VIOLATION" and content is None

def test_gateway_screens_before_provider_and_preserves_floor(monkeypatch):
    calls = []
    import innovation.gateway.workflow as gateway
    original = gateway.screen_case
    def screen(value): calls.append("screen"); return original(value)
    monkeypatch.setattr(gateway, "screen_case", screen)
    class Overconfident(MockProvider):
        def infer(self,*args):
            calls.append("provider")
            result = super().infer(*args)
            result.content.urgency.level = "ROUTINE_REVIEW"
            result.content.urgency.confidence = .99
            result.content.uncertainty.calibrated = True
            result.content.uncertainty.abstained = False
            return result
    run, content = Runtime(Overconfident()).execute(snapshot(), "synthetic", DESIGNS["form"])
    assert calls.index("screen") < calls.index("provider")
    assert content.urgency.level == "URGENT_REVIEW"
    assert content.urgency.confidence is None and not content.uncertainty.calibrated
    assert content.uncertainty.abstained
    assert run.provenance["gateway_contract"] == "workflow-gateway-1.0"

def test_intake_to_review_audit_stale_and_idempotency():
    store = Store(); service = Service(store, Runtime(MockProvider()))
    intake = Principal("nurse", "intake"); doctor = Principal("reviewer", "physician")
    try:
        service.create(EncounterCreate(encounter_id="medx-case", age=40), "create", intake)
        service.append_event("medx-case", EventRequest(expected_revision=0, idempotency_key="fact", fact=fact("CHIEF_COMPLAINT")), intake)
        request = TurnRequest(expected_revision=1, idempotency_key="draft", text="synthetic", decision_time=T, design_id="adaptive")
        run = service.turn("medx-case", request, intake)
        assert service.turn("medx-case", request, intake) == run
        body = ReviewDecision(expected_revision=1, idempotency_key="confirm", draft_revision=1, expected_review_sequence=0, action="CONFIRM")
        with pytest.raises(DomainError): service.review(run["draft_id"], body, intake)
        reviewed = service.review(run["draft_id"], body, doctor)
        assert reviewed["effective"]
        records = store.all("audit", "medx-case")
        review = next(r for r in records if r["event"] == "HUMAN_REVIEW_RECORDED")
        assert review["actor"] == "reviewer" and review["model"] and review["provider"]
        service.append_event("medx-case", EventRequest(expected_revision=1, idempotency_key="new", fact=fact("HISTORY")), intake)
        assert not service.draft(run["draft_id"], doctor)["effective"]
        with pytest.raises(DomainError): service.review(run["draft_id"], body.model_copy(update={"idempotency_key":"stale"}), doctor)
        assert replay(run["provenance"]["execution"])["external_calls"] == 0
    finally: store.close()
