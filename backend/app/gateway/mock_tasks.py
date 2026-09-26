"""Registry of deterministic mock handlers per gateway task.

A client module registers ``fn(inputs) -> output`` for its task. The mock provider dispatches
registered tasks to ``fn``; unregistered tasks keep the hash-based placeholder output. Handlers
must be pure and offline. Only the mock provider consults this registry.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

Handler = Callable[[dict[str, Any]], dict[str, Any]]

_REGISTRY: dict[str, tuple[Handler, str]] = {}


def register(task: str, fn: Handler, *, version: str) -> None:
    """Register (or idempotently re-register) the mock handler for ``task``."""
    current = _REGISTRY.get(task)
    if current is not None and current != (fn, version):
        raise ValueError(f"mock task already registered with a different handler: {task}")
    _REGISTRY[task] = (fn, version)


def lookup(task: str) -> tuple[Handler, str] | None:
    return _REGISTRY.get(task)
