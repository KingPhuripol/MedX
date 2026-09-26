"""Additive task-handler hook for the offline mock provider.

A handler is a pure, deterministic function ``inputs -> output dict``. Tasks without a
registered handler keep the default hash-based mock output, so the contract is unchanged.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

MockTaskHandler = Callable[[dict[str, Any]], dict[str, Any]]

_HANDLERS: dict[str, MockTaskHandler] = {}


def register_mock_task_handler(task: str, handler: MockTaskHandler) -> None:
    _HANDLERS[task] = handler


def get_mock_task_handler(task: str) -> MockTaskHandler | None:
    return _HANDLERS.get(task)
