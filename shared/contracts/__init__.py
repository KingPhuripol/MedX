"""Versioned, executable form of the shared contracts.

`schemas/` remains the machine source of truth. These models bind to those schemas
rather than restating them: `tests/test_contracts.py` validates the same fixtures
through both paths, so a divergence fails the test suite instead of drifting
silently (RISK-0006).
"""

from shared.contracts.errors import ErrorCode, ContractViolation
from shared.contracts.journey import (
    PatientJourney,
    JourneyEvent,
    JourneySource,
    EventSourceRef,
    SourceRef,
    NON_EVIDENTIAL_STATUSES,
)
from shared.contracts.model_api import (
    GatewayRequest,
    GatewayResponse,
    EvidenceRef,
    Authorization,
    ProviderConstraints,
    Urgency,
    RedFlag,
    CarePathway,
    NextInformation,
    Uncertainty,
    HumanReview,
    Provenance,
    ResponseError,
    URGENCY_SEVERITY,
)

CONTRACT_VERSION = "1.0.0"

__all__ = [
    "CONTRACT_VERSION",
    "ErrorCode",
    "ContractViolation",
    "PatientJourney",
    "JourneyEvent",
    "JourneySource",
    "EventSourceRef",
    "SourceRef",
    "NON_EVIDENTIAL_STATUSES",
    "GatewayRequest",
    "GatewayResponse",
    "EvidenceRef",
    "Authorization",
    "ProviderConstraints",
    "Urgency",
    "RedFlag",
    "CarePathway",
    "NextInformation",
    "Uncertainty",
    "HumanReview",
    "Provenance",
    "ResponseError",
    "URGENCY_SEVERITY",
]
