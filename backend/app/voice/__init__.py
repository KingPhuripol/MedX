"""Voice Agent — Thai intake, text cascade first (slice s3). Research prototype — not for clinical use.

A module separate from the Case Graph. It controls the dialogue, picks the next question with a
deterministic policy, and calls the LLM only through the Model Gateway.
"""

from __future__ import annotations

from ..gateway import mock_tasks
from . import symptoms  # noqa: F401  (registers voice.symptom_extract.v1)
from .db import create_voice_schema
from .mock_rules import EXTRACTOR_VERSION, extract
from .models import EXTRACT_TASK
from .router import router

mock_tasks.register(EXTRACT_TASK, extract, version=EXTRACTOR_VERSION)

__all__ = ["create_voice_schema", "router"]
