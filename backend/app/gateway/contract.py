"""Stable Model Gateway contract. Clients depend only on these types."""

from __future__ import annotations

import hashlib
import json
from enum import Enum
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

CONTRACT_VERSION = "0.1.0"


class DataClass(str, Enum):
    SYNTHETIC = "synthetic"
    MIMIC = "mimic"
    HOSPITAL = "hospital"
    REAL = "real"
    UNKNOWN = "unknown"


class GatewayRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    task: str = Field(pattern=r"^[a-z0-9][a-z0-9_.-]{0,63}$")
    inputs: dict[str, Any]
    data_class: DataClass  # required, no default


class GatewayResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    status: Literal["ok", "rejected", "error"]
    provider: str
    model_version: str
    contract_version: str = CONTRACT_VERSION
    output: dict[str, Any] | None
    reason: str | None
    latency_ms: float
    request_sha256: str


def canonical_sha256(request: GatewayRequest) -> str:
    payload = json.dumps(
        request.model_dump(mode="json"), sort_keys=True, separators=(",", ":"), ensure_ascii=False
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()
