"""Provider selection by configuration only.

Acceptance criterion A5 requires that "provider swap requires configuration only, not
client/UI logic changes". Building the registry now — before the team model exists —
means the swap path is exercised from the start rather than retrofitted, and the UI never
learns a provider's name.

External providers are opt-in and refused by default. A prototype that reaches an
external service because someone forgot to configure it is the failure DEC-0006 exists to
prevent, so the default is the one that cannot leave the machine.
"""

from __future__ import annotations

import os

from innovation.gateway.providers.base import Provider
from innovation.gateway.providers.baseline import BaselineProvider
from innovation.gateway.providers.mock import MockProvider

#: Providers that run entirely locally with no network access.
LOCAL_PROVIDERS: dict[str, type] = {
    "mock": MockProvider,
    "baseline": BaselineProvider,
}

#: Providers that would reach outside the process. None is implemented yet; the mapping
#: exists so that adding one is a registry entry plus an approval, not an edit to a client.
EXTERNAL_PROVIDERS: dict[str, type] = {}

ENV_VAR = "FRONT_DOOR_PROVIDER"
ENV_ALLOW_EXTERNAL = "FRONT_DOOR_ALLOW_EXTERNAL"

DEFAULT_PROVIDER = "mock"


class ProviderNotAvailable(ValueError):
    """The requested provider is unknown, or known but not permitted here."""


def available_providers(*, include_external: bool = False) -> tuple[str, ...]:
    names = set(LOCAL_PROVIDERS)
    if include_external:
        names |= set(EXTERNAL_PROVIDERS)
    return tuple(sorted(names))


def build_provider(name: str | None = None, **kwargs) -> Provider:
    """Construct the configured provider.

    Resolution order: explicit argument, then `FRONT_DOOR_PROVIDER`, then the local mock.
    Nothing about this function is reachable from a client payload — a caller cannot ask
    the API to use a different provider, because provider choice is deployment
    configuration, not request data.
    """
    requested = name or os.environ.get(ENV_VAR) or DEFAULT_PROVIDER

    if requested in LOCAL_PROVIDERS:
        return LOCAL_PROVIDERS[requested](**kwargs)

    if requested in EXTERNAL_PROVIDERS:
        if os.environ.get(ENV_ALLOW_EXTERNAL, "").lower() not in {"1", "true", "yes"}:
            raise ProviderNotAvailable(
                f"provider {requested!r} is external and is disabled. Set "
                f"{ENV_ALLOW_EXTERNAL}=1 and record an approval under the Human Approval "
                "Policy before enabling it."
            )
        return EXTERNAL_PROVIDERS[requested](**kwargs)

    raise ProviderNotAvailable(
        f"unknown provider {requested!r}; available: {available_providers()}"
    )
