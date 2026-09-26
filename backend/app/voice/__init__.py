"""Voice Agent — Thai intake, text cascade first (slice s3). Research prototype — not for clinical use.

A module separate from the Case Graph. It controls the dialogue, picks the next question with a
deterministic policy, and calls the LLM only through the Model Gateway.
"""

from __future__ import annotations

from ..gateway import register_mock_task
from .db import create_voice_schema
from .mock_rules import extract
from .models import EXTRACT_TASK
from .router import router

register_mock_task(EXTRACT_TASK, extract)

__all__ = ["create_voice_schema", "router"]
