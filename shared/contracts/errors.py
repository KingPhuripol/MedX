"""Error codes from the Model API Contract, and the exception that carries them."""

from __future__ import annotations

from enum import Enum


class ErrorCode(str, Enum):
    """Exactly the codes in `docs/shared/MODEL_API_CONTRACT.md` and the response schema.

    Adding a member here without adding it to `schemas/model-api-response.schema.json`
    produces a response the gateway itself would reject, so the two move together.
    """

    INVALID_REQUEST = "INVALID_REQUEST"
    TEMPORAL_VIOLATION = "TEMPORAL_VIOLATION"
    UNAUTHORIZED_DATA = "UNAUTHORIZED_DATA"
    UNSUPPORTED_MODALITY = "UNSUPPORTED_MODALITY"
    PROVIDER_TIMEOUT = "PROVIDER_TIMEOUT"
    INVALID_PROVIDER_OUTPUT = "INVALID_PROVIDER_OUTPUT"
    BUDGET_EXCEEDED = "BUDGET_EXCEEDED"
    LOW_CONFIDENCE = "LOW_CONFIDENCE"
    INTERNAL_SAFE_FAILURE = "INTERNAL_SAFE_FAILURE"


#: Codes the gateway raises before a provider is ever called. The contract requires
#: these to be blocked at the boundary, not handled by the provider.
PRE_PROVIDER_CODES = frozenset(
    {
        ErrorCode.INVALID_REQUEST,
        ErrorCode.TEMPORAL_VIOLATION,
        ErrorCode.UNAUTHORIZED_DATA,
    }
)


class ContractViolation(Exception):
    """A request or response that the contract forbids.

    `message` is written for an audit log and a clinician-facing error surface, so it
    never carries evidence payloads, patient content, or provider-native text.
    """

    def __init__(self, code: ErrorCode, message: str, *, retryable: bool = False) -> None:
        super().__init__(f"{code.value}: {message}")
        self.code = code
        self.message = message
        self.retryable = retryable
