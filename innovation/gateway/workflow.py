"""Versioned workflow protocol of the Model Gateway.

The v1 reference-only protocol remains unchanged. This protocol accepts confirmed
synthetic snapshots and applies the same boundary before all workflow reasoning calls.
It makes no claim that a provider supports raw imaging or calibrated confidence.
"""
from innovation.v2.models import CaseRevision, ConversationResult, DesignSpec
from innovation.v2.providers import ProviderResult
from innovation.v2.safety import screen_case
from innovation.v2.store import DomainError


class WorkflowGateway:
    contract_version = "workflow-gateway-1.0"
    modalities = ("clinical_text", "structured", "longitudinal", "imaging_report_text")

    def __init__(self, provider):
        self.adapter = provider
        self.name = provider.name
        self.model_version = provider.model_version
        self.capabilities = provider.capabilities

    def prepare(self, snapshot):
        snapshot = CaseRevision.model_validate(snapshot.model_dump())
        if any(f.available_at_time > snapshot.decision_time or f.kind == "LABEL" for f in snapshot.evidence):
            raise DomainError(422, "TEMPORAL_VIOLATION")
        if len({f.event_id for f in snapshot.evidence}) != len(snapshot.evidence):
            raise DomainError(422, "DUPLICATE_EVIDENCE")
        return screen_case(snapshot)

    def infer(self, snapshot, text, design):
        screen = self.prepare(snapshot)  # Must run BEFORE the adapter, even on failures.
        if "summary" not in self.capabilities:
            raise DomainError(422, "UNSUPPORTED_CAPABILITY")
        result = ProviderResult.model_validate(self.adapter.infer(snapshot, text, DesignSpec.model_validate(design.model_dump())))
        content = result.content.model_copy(deep=True)
        ids = {f.event_id for f in snapshot.evidence}
        citations = content.evidence_ids + content.urgency.evidence_ids
        citations += [i for p in content.care_pathways for i in p.evidence_ids]
        citations += [i for p in content.differentials for i in p.evidence_ids]
        if not set(citations) <= ids:
            raise DomainError(502, "INVALID_EVIDENCE_REFERENCE")
        # Calibration is an evaluated property, never a provider's self-declaration.
        content.uncertainty.calibrated = False
        content.uncertainty.confidence = None
        content.urgency.confidence = None
        for candidate in content.care_pathways:
            candidate.confidence = None
        levels = {"INSUFFICIENT_INFORMATION": 0, "ROUTINE_REVIEW": 1, "URGENT_REVIEW": 2, "IMMEDIATE_REVIEW": 3}
        if levels[screen.urgency_floor] > levels[content.urgency.level]:
            content.urgency.level = screen.urgency_floor
        conflicts = any(f.conflicts_with_event_ids for f in snapshot.evidence)
        incomplete = any(f.state != "KNOWN" for f in snapshot.evidence)
        if screen.missing_required or conflicts or incomplete or any(f.state in {"TRIGGERED", "UNKNOWN"} for f in screen.red_flags):
            content.uncertainty.abstained = True
            content.uncertainty.escalation_required = True
            content.uncertainty.reasons = list(dict.fromkeys(content.uncertainty.reasons + ["Human review required by deterministic evidence/safety checks"]))
        content.limitations = list(dict.fromkeys(content.limitations + screen.limitations + ["Provider confidence is not clinically calibrated; raw 2D/3D image analysis is not supported by this workflow adapter."]))
        return result.model_copy(update={"content": content})

    def converse_with_history(self, snapshot, text, design, history):
        self.prepare(snapshot)
        if "conversation" not in self.capabilities:
            raise DomainError(422, "UNSUPPORTED_CAPABILITY")
        if hasattr(self.adapter, "converse_with_history"):
            raw = self.adapter.converse_with_history(snapshot, text, design, history)
        elif hasattr(self.adapter, "converse"):
            raw = self.adapter.converse(snapshot, text, design)
        else:
            raise DomainError(422, "UNSUPPORTED_CAPABILITY")
        result = ConversationResult.model_validate(raw)
        ids = {f.event_id for f in snapshot.evidence}
        if not set(result.evidence_ids) <= ids:
            raise DomainError(502, "INVALID_EVIDENCE_REFERENCE")
        return result

    def converse(self, snapshot, text, design):
        return self.converse_with_history(snapshot, text, design, [])

    def tool_step(self, messages, tools, output):
        # Function calling crosses the same gateway boundary; tools themselves stay local.
        if "tools" not in self.capabilities or not hasattr(self.adapter, "tool_step"):
            raise DomainError(422, "UNSUPPORTED_CAPABILITY")
        return self.adapter.tool_step(messages, tools, output)
