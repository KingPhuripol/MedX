"""The interface every provider implements.

A provider returns a *proposal*, not a response. The gateway constructs the response
after applying the deterministic safety layer, so a provider cannot emit a client-facing
field the contract forbids, and swapping providers cannot change safety behaviour.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Protocol

from shared.contracts.model_api import (
    CarePathway,
    GatewayRequest,
    NextInformation,
    RedFlag,
    Uncertainty,
    Urgency,
)


class ProviderTimeout(Exception):
    """The provider did not answer inside `provider_constraints.timeout_ms`."""


class ProviderFailure(Exception):
    """The provider failed in a way that is not a timeout."""


@dataclass(frozen=True)
class ProviderOutput:
    """What a provider proposes. The gateway decides what becomes of it."""

    urgency: Urgency
    red_flags: tuple[RedFlag, ...]
    care_pathways: tuple[CarePathway, ...]
    next_information: tuple[NextInformation, ...]
    uncertainty: Uncertainty
    model_version: str
    provider_version: str
    config_version: str
    graph_id: str | None = None
    graph_ref: str | None = None
    graph_schema_version: str | None = None
    #: Evidence the provider could not use. The gateway surfaces this rather than
    #: letting an unsupported modality be silently ignored.
    unsupported_evidence_ids: tuple[str, ...] = field(default=())


class Provider(Protocol):
    """Structural interface — an adapter need not inherit from anything."""

    name: str

    def supported_modalities(self) -> frozenset[str]:
        """Modalities this provider can actually consume."""
        ...

    def infer(self, request: GatewayRequest) -> ProviderOutput:
        """Produce a proposal for the request, or raise ProviderTimeout/ProviderFailure."""
        ...
