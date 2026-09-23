"""Bounded shared tool runtime. Designs alter orchestration, never safety controls."""
from time import monotonic
from uuid import uuid4
from innovation.v2.tools import invoke
from innovation.v2.providers import CALL_RESERVATION
from innovation.v2.models import AgentRun, DesignSpec, DraftContent, ToolEvent
from innovation.v2.store import DomainError, digest
from innovation.v2.graph import compile_graph, finish_artifact
from pydantic_core import to_jsonable_python

DESIGNS = {
    "adaptive": DesignSpec(design_id="adaptive", nodes=["intake", "check", "draft", "verify"], routing="adaptive"),
    "random": DesignSpec(design_id="random", nodes=["draft"], routing="random"),
    "static_dag": DesignSpec(design_id="static_dag", nodes=["intake", "check", "draft", "verify"]),
    "form": DesignSpec(design_id="form", nodes=["draft"]),
    "single": DesignSpec(design_id="single", nodes=["intake", "draft"]),
    "fixed": DesignSpec(design_id="fixed", nodes=["intake", "check", "draft", "verify"]),
}
POLICY = "synthetic-workflow-v2"
# This registry is workflow guidance only; no unreviewed medical guidelines are shipped.
REFERENCES = [{"id": "workflow-v1", "text": "Unknown is not absent. Drafts require current-revision human review."}]


def validate_content(content: DraftContent, snapshot, allow_differential=False):
    ids = {f.event_id for f in snapshot.evidence}
    cited = set(content.evidence_ids)
    if not cited <= ids:
        raise DomainError(502, "INVALID_EVIDENCE_REFERENCE")
    if content.differentials and not allow_differential:
        raise DomainError(422, "UNSUPPORTED_CAPABILITY")
    for item in content.differentials:
        if not set(item.evidence_ids) <= ids:
            raise DomainError(502, "INVALID_EVIDENCE_REFERENCE")
    if not set(content.urgency.evidence_ids) <= ids:
        raise DomainError(502, "INVALID_EVIDENCE_REFERENCE")
    for pathway in content.care_pathways:
        if not set(pathway.evidence_ids) <= ids:
            raise DomainError(502, "INVALID_EVIDENCE_REFERENCE")
    return content


class Runtime:
    def __init__(self, provider, allow_differential=False, timeout_seconds=30):
        from innovation.gateway.gateway import ModelGateway
        self.provider = ModelGateway.for_workflow(provider)
        self.allow_differential = allow_differential
        self.timeout_seconds = timeout_seconds

    @property
    def provider(self):
        return self._provider

    @provider.setter
    def provider(self, value):
        from innovation.gateway.gateway import ModelGateway
        self._provider = ModelGateway.for_workflow(value)

    def execute(self, snapshot, text, design, prior_calls=0, prior_turns=0, intent="draft", role="physician", cancel_check=None, history=None):
        design = DesignSpec.model_validate(design.model_dump())
        run = AgentRun(run_id=uuid4().hex, encounter_id=snapshot.encounter_id,
            case_revision=snapshot.case_revision, status="FAILED_SAFE", response="ยังสร้างร่างไม่ได้",
            provenance={"contract": "2.2.0", "policy": POLICY, "provider": self.provider.name,
                "model": self.provider.model_version, "design": design.model_dump(),
                "snapshot_checksum": snapshot.checksum, "reference_version": "workflow-v1",
                "config_hash": digest({"timeout": self.timeout_seconds, "differential": self.allow_differential})})
        if prior_turns >= 20 or prior_calls >= 30:
            run.status, run.error_code = "BUDGET_EXCEEDED", "CASE_BUDGET_EXCEEDED"
            finish_artifact(run, None)
            return run, None
        graph = compile_graph(snapshot, design, self.timeout_seconds)
        if intent == "draft":
            run.provenance["execution"] = {"graph": graph.model_dump(mode="json"),
                "input": {"snapshot": snapshot.model_dump(mode="json"), "text": text}, "steps": []}
        run.provenance["gateway_contract"] = self.provider.contract_version
        start = monotonic()
        content = None
        missing = []

        def tool(name, fn):
            if cancel_check and cancel_check():
                raise DomainError(409, 'JOB_CANCELLED')
            if len(run.trace) >= 8 or prior_calls + len(run.trace) >= 30:
                raise DomainError(429, "TOOL_BUDGET_EXCEEDED")
            if monotonic() - start > self.timeout_seconds:
                raise DomainError(504, "RUN_TIMEOUT")
            CALL_RESERVATION.set(0.0)
            began = monotonic()
            event = ToolEvent(sequence=len(run.trace)+1, tool=name,
                evidence_ids=[f.event_id for f in snapshot.evidence], status="COMPLETED")
            try:
                result = invoke(name, {"snapshot": snapshot, "text": text, "role": role}, fn)
                if cancel_check and cancel_check():
                    raise DomainError(409, 'JOB_CANCELLED')
                if monotonic() - start > self.timeout_seconds:
                    raise DomainError(504, "RUN_TIMEOUT")
                if "execution" in run.provenance:
                    run.provenance["execution"]["steps"].append({"tool": name, "output": to_jsonable_python(result)})
                return result
            except Exception:
                event.status = "FAILED"
                raise
            finally:
                event.elapsed_ms = (monotonic()-began)*1000
                run.trace.append(event)
                run.provenance['reserved_cost_usd'] = run.provenance.get('reserved_cost_usd',0.0) + CALL_RESERVATION.get()

        try:
            # Pre-inference screen is independent of selected nodes and provider output.
            screen = self.provider.prepare(snapshot)
            run.provenance["safety_screen"] = screen.model_dump(mode="json")
            tool("read_snapshot", lambda: snapshot)
            if intent == "conversation":
                if 'conversation' not in self.provider.capabilities or not hasattr(self.provider, 'converse'):
                    raise DomainError(422, 'UNSUPPORTED_CAPABILITY')
                result = tool('conversation', lambda: self.provider.converse_with_history(snapshot, text, design, history or [])
                              if hasattr(self.provider, 'converse_with_history') else self.provider.converse(snapshot, text, design))
                available = {f.event_id for f in snapshot.evidence}
                if not set(result.evidence_ids) <= available:
                    raise DomainError(502, 'INVALID_EVIDENCE_REFERENCE')
                from innovation.v2.models import FactProposal
                for fact in result.facts:
                    if fact.kind == 'LABEL' or (fact.supersedes_event_id and fact.supersedes_event_id not in available):
                        raise DomainError(502, 'INVALID_PROPOSAL')
                    run.proposals.append(FactProposal(proposal_id=uuid4().hex, fact=fact).model_dump(mode='json'))
                run.status, run.response = 'COMPLETED', result.response
                finish_artifact(run, None)
                return run, None
            executed_design = design.model_copy(update={"nodes": [n.operator for n in graph.nodes], "routing": "static"})
            for node in executed_design.nodes:
                if node == "intake":
                    def propose():
                        if text:
                            run.proposals.append({"kind": "UNCONFIRMED_TEXT", "text": text, "requires_confirmation": True})
                        known = {f.kind for f in snapshot.evidence}
                        absent = [k for k in ("CHIEF_COMPLAINT", "HISTORY", "MEDICATION", "ALLERGY") if k not in known]
                        if absent:
                            run.proposals.append({"kind": "QUESTION", "text": "กรุณาตรวจและเพิ่มข้อมูล " + absent[0], "requires_confirmation": False})
                        return run.proposals
                    tool("propose_information", propose)
                elif node == "check":
                    def check():
                        known = {f.kind for f in snapshot.evidence}
                        missing.extend(k for k in ("CHIEF_COMPLAINT", "HISTORY", "MEDICATION", "ALLERGY") if k not in known)
                        available_ids = {f.event_id for f in snapshot.evidence}
                        for f in snapshot.evidence:
                            if set(f.conflicts_with_event_ids) & available_ids:
                                missing.append(f"ตรวจข้อขัดแย้ง: {f.kind} ({f.event_id})")
                        return missing
                    tool("check_information", check)
                    tool("retrieve_reference", lambda: REFERENCES)
                elif node == "draft":
                    if 'summary' not in self.provider.capabilities:
                        raise DomainError(422, "UNSUPPORTED_CAPABILITY")
                    result = tool("create_draft", lambda: self.provider.infer(snapshot, text, executed_design))
                    # Every design must pass this gate, even without a verify reasoning node.
                    content = validate_content(result.content, snapshot,
                        self.allow_differential and 'differential' in self.provider.capabilities)
                    run.provenance.update(model=result.model_version, provider_version=result.provider_version)
                    content.outstanding = list(dict.fromkeys(content.outstanding + missing))
                elif node == "verify":
                    tool("verify_draft", lambda: validate_content(content, snapshot, self.allow_differential))
            run.status = "COMPLETED"
            run.response = "เตรียมร่างแล้ว กรุณาตรวจข้อมูลและยืนยันก่อนใช้"
            questions = [p["text"] for p in run.proposals if p["kind"] == "QUESTION"]
            if questions:
                run.response += " · " + questions[0]
            finish_artifact(run, content)
            return run, content
        except Exception as exc:
            code = exc.code if isinstance(exc, DomainError) else "INVALID_PROVIDER_OUTPUT"
            run.error_code = code
            run.status = "BUDGET_EXCEEDED" if 'BUDGET' in code else "FAILED_SAFE"
            if run.trace:
                run.trace[-1].status = "FAILED"
                run.trace[-1].error_code = code
            finish_artifact(run, None)
            return run, None
