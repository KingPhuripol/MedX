"""Reproducible baseline provider.

`PRODUCT_SPEC.md` §Architecture lists a baseline provider alongside the mock, the
external prototype and the team model. It exists for two reasons:

1. It is the **controlled comparison** the research claim needs. A case-adaptive graph
   has to beat a fixed-path baseline under a comparable budget; without a baseline in the
   same contract there is nothing to compare against.
2. Until the team model exists it is the only way to *prove* provider independence rather
   than assert it. Two real adapters passing one unchanged contract suite is evidence;
   one adapter and a docstring is not.

It is a fixed-path scorer: the same evidence always produces the same output, by an
explicit published rule. It is deliberately simple and is not a clinical model.
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
from innovation.gateway.providers.base import ProviderOutput

#: Evidence types this baseline knows how to weigh. Anything else contributes nothing —
#: it does not guess, and it does not treat an unrecognised type as reassuring.
EVIDENCE_WEIGHTS: dict[str, int] = {
    "CHIEF_COMPLAINT": 2,
    "TRIAGE_NOTE": 2,
    "VITAL": 3,
    "ECG": 3,
    "LAB": 2,
    "EXAM": 1,
    "HISTORY": 1,
}

#: Red flags this baseline can evaluate, and the evidence type each one needs. Without
#: that evidence the flag is UNKNOWN, never NOT_TRIGGERED — "we could not check" is not
#: "we checked and it was clear".
FLAG_REQUIREMENTS: dict[str, str] = {
    "ABNORMAL_VITALS_REQUIRE_REVIEW": "VITAL",
    "COMPLAINT_REQUIRES_CLINICIAN_REVIEW": "CHIEF_COMPLAINT",
}


class BaselineProvider:
    """A fixed-path, fully reproducible scorer."""

    name = "baseline"

    def __init__(
        self,
        *,
        model_version: str = "baseline-v1",
        provider_version: str = "baseline-provider-v1",
        config_version: str = "baseline-config-v1",
        fail_with: Exception | None = None,
        modalities: frozenset[str] | None = None,
    ) -> None:
        self.model_version = model_version
        self.provider_version = provider_version
        self.config_version = config_version
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
        present_types = {e.event_type for e in usable}
        evidence_ids = [e.evidence_id for e in usable]

        score = sum(EVIDENCE_WEIGHTS.get(e.event_type, 0) for e in usable)

        # A published, deterministic band. It reflects how much evidence is in hand, not a
        # clinical judgement — a thin record scores low and therefore abstains.
        if not evidence_ids:
            level = "INSUFFICIENT_INFORMATION"
        elif score >= 5:
            level = "ROUTINE_REVIEW"
        else:
            level = "INSUFFICIENT_INFORMATION"

        red_flags = tuple(
            RedFlag(
                code=code,
                state="NOT_TRIGGERED" if required in present_types else "UNKNOWN",
                evidence_ids=[e.evidence_id for e in usable if e.event_type == required],
            )
            for code, required in sorted(FLAG_REQUIREMENTS.items())
        )

        pathways = (
            CarePathway(
                code="CLINICIAN_ASSESSMENT",
                rank=1,
                # Confidence here is a coverage score, not a probability. It is reported
                # with its method so it cannot be mistaken for a calibrated likelihood.
                confidence=min(score / 10, 1.0) if evidence_ids else None,
                evidence_ids=evidence_ids,
            ),
            CarePathway(
                code="REQUEST_MORE_INFORMATION",
                rank=2,
                confidence=None,
                evidence_ids=evidence_ids,
            ),
        )

        next_information = tuple(
            NextInformation(
                information_type=item,
                rank=i,
                reason_code="DECLARED_INFORMATION_GAP",
            )
            for i, item in enumerate(request.missing_information, start=1)
        )

        return ProviderOutput(
            urgency=Urgency(level=level, confidence=None, evidence_ids=evidence_ids),
            red_flags=red_flags,
            care_pathways=pathways,
            next_information=next_information,
            uncertainty=Uncertainty(
                method="fixed-path-evidence-coverage-score-v1",
                limitations=[
                    "Baseline output is an evidence-coverage score, not a clinical model "
                    "prediction, and its confidence is not a calibrated probability.",
                ],
                out_of_distribution=None,
                abstention_reason=None if evidence_ids else "No usable evidence at decision time",
            ),
            model_version=self.model_version,
            provider_version=self.provider_version,
            config_version=self.config_version,
            graph_id=f"baseline-graph-{request.request_id}",
            graph_ref=f"synthetic://baseline-graph-{request.request_id}",
            graph_schema_version="1.0.0",
            unsupported_evidence_ids=unsupported,
        )
