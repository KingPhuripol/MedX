"""Deterministic offline mock provider.

The default implementation path is the mock provider and an offline synthetic demo
(`innovation/README.md`), so the whole flow is demonstrable with no network and no
external dependency — which is also what makes the contract fixtures reproducible.

It is deliberately not clinically intelligent. It applies a small, explicit and
conservative policy so that the *plumbing and the safety behaviour* can be tested
without anyone mistaking its output for a model prediction.
"""

from __future__ import annotations

from shared.contracts.model_api import (
    CarePathway,
    GatewayRequest,
    NextInformation,
    RedFlag,
    Uncertainty,
    Urgency,
)
from innovation.gateway.providers.base import ProviderFailure, ProviderOutput, ProviderTimeout

#: Event types the mock treats as warranting a red-flag question. It cannot read
#: payloads, so it reasons about presence, and answers UNKNOWN rather than guessing.
FLAGGABLE_EVENT_TYPES = {"CHIEF_COMPLAINT", "TRIAGE_NOTE"}


class MockProvider:
    """A provider that always returns the same output for the same request."""

    name = "mock"

    def __init__(
        self,
        *,
        model_version: str = "mock-v1",
        provider_version: str = "mock-provider-v1",
        config_version: str = "mock-config-v1",
        fail_with: Exception | None = None,
        modalities: frozenset[str] | None = None,
    ) -> None:
        self.model_version = model_version
        self.provider_version = provider_version
        self.config_version = config_version
        # Injected failures let the timeout and provider-error contract cases be tested
        # without waiting on or breaking a real service.
        self._fail_with = fail_with
        self._modalities = modalities if modalities is not None else frozenset(
            {"TEXT", "STRUCTURED", "IMAGE_2D", "REFERENCE"}
        )

    def supported_modalities(self) -> frozenset[str]:
        return self._modalities

    def infer(self, request: GatewayRequest) -> ProviderOutput:
        if self._fail_with is not None:
            raise self._fail_with

        usable = [e for e in request.evidence if e.modality in self._modalities]
        unsupported = tuple(
            e.evidence_id for e in request.evidence if e.modality not in self._modalities
        )
        evidence_ids = [e.evidence_id for e in usable]

        # The mock never claims a flag is absent. It can see that a complaint exists and
        # that it cannot read it, so UNKNOWN is the truthful state — and under SR-002
        # that escalates rather than reassures.
        red_flags = tuple(
            RedFlag(
                code="COMPLAINT_REQUIRES_CLINICIAN_REVIEW",
                state="UNKNOWN",
                evidence_ids=[e.evidence_id],
            )
            for e in usable
            if e.event_type in FLAGGABLE_EVENT_TYPES
        )

        next_information = tuple(
            NextInformation(information_type=item, rank=i, reason_code="DECLARED_INFORMATION_GAP")
            for i, item in enumerate(request.missing_information, start=1)
        )

        return ProviderOutput(
            urgency=Urgency(
                level="INSUFFICIENT_INFORMATION" if not evidence_ids else "ROUTINE_REVIEW",
                confidence=None,
                evidence_ids=evidence_ids,
            ),
            red_flags=red_flags,
            care_pathways=(
                CarePathway(
                    code="CLINICIAN_ASSESSMENT",
                    rank=1,
                    confidence=None,
                    evidence_ids=evidence_ids,
                ),
            ),
            next_information=next_information,
            uncertainty=Uncertainty(
                method="deterministic-mock-policy",
                limitations=[
                    "Mock provider output is not a clinical model prediction and carries no "
                    "diagnostic meaning.",
                ],
                out_of_distribution=None,
                abstention_reason=None if evidence_ids else "No usable evidence at decision time",
            ),
            model_version=self.model_version,
            provider_version=self.provider_version,
            config_version=self.config_version,
            graph_id=f"graph-{request.request_id}",
            graph_ref=f"synthetic://graph-{request.request_id}",
            graph_schema_version="1.0.0",
            unsupported_evidence_ids=unsupported,
        )


__all__ = ["MockProvider", "ProviderTimeout", "ProviderFailure"]
