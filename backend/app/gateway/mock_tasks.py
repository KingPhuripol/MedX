"""The single registry of deterministic mock handlers per gateway task (slice i2: one registry).

A client module registers ``fn(inputs) -> output`` for its task with ``register(task, fn, version=...)``.
Only the offline mock provider consults this registry. Every mock output carries
``label: "MOCK — not clinical"`` and ``model_version`` ``mock-0.1.0+<version>`` (MOCK label rule);
unregistered tasks keep the s0 hash-placeholder output. Handlers must be pure and offline.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

Handler = Callable[[dict[str, Any]], dict[str, Any]]

_REGISTRY: dict[str, tuple[Handler, str]] = {}


def register(task: str, fn: Handler, *, version: str) -> None:
    """Register (or idempotently re-register) the mock handler for ``task``.

    Re-registering a task with a different handler or version raises ``ValueError``.
    """
    if not version:
        raise ValueError(f"mock task {task!r} needs a non-empty version")
    current = _REGISTRY.get(task)
    if current is not None and current != (fn, version):
        raise ValueError(f"mock task already registered with a different handler: {task}")
    _REGISTRY[task] = (fn, version)


def lookup(task: str) -> tuple[Handler, str] | None:
    return _REGISTRY.get(task)


def registered() -> dict[str, str]:
    """task -> handler version, for manifests and tests."""
    return {task: version for task, (_, version) in sorted(_REGISTRY.items())}
