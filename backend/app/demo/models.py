from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


RoleName = Literal["nurse", "physician", "pharmacist"]
CaseStage = Literal["intake", "triage_review", "care_review", "medication_review", "complete"]


class ClaimBody(BaseModel):
    run_id: str = Field(min_length=1, max_length=36)
    version: int = Field(ge=1)


class HandoffBody(BaseModel):
    run_id: str = Field(min_length=1, max_length=36)
    to_role: RoleName
    note: str = Field(default="", max_length=500)
    version: int = Field(ge=1)
    acknowledged_alerts: list[str] = Field(default_factory=list, max_length=20)


class TaskReviewBody(BaseModel):
    run_id: str = Field(min_length=1, max_length=36)
    version: int = Field(ge=1)
    reason: str = Field(default="", max_length=500)
    acknowledged_alerts: list[str] = Field(default_factory=list, max_length=20)


class MedicationReviewBody(BaseModel):
    run_id: str = Field(min_length=1, max_length=36)
    version: int = Field(ge=1)
    reason: str = Field(default="", max_length=500)
    final_value: str | None = Field(default=None, max_length=500)
