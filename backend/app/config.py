"""Configuration read from environment variables only (no secrets in code)."""

from __future__ import annotations

import os
from dataclasses import dataclass, field

DEFAULT_DATABASE_URL = "sqlite:///./backend/dev.db"
KNOWN_PROVIDERS = ("mock", "openai_compatible")


def _bool(value: str | None, default: bool = False) -> bool:
    if value is None or value.strip() == "":
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


@dataclass(frozen=True)
class Settings:
    database_url: str = DEFAULT_DATABASE_URL
    gateway_provider: str = "mock"
    external_enabled: bool = False
    external_base_url: str = ""
    external_api_key: str = field(default="", repr=False)
    external_model: str = "external-unset"
    gateway_timeout_s: float = 10.0
    session_ttl_minutes: int = 480
    cookie_secure: bool = False
    # Slice i2 (C3, D-I2-2): /api/triage assess rejects as_of later than the latest evidence + this skew.
    triage_as_of_skew_s: float = 300.0

    @classmethod
    def from_env(cls) -> "Settings":
        env = os.environ
        provider = env.get("GATEWAY_PROVIDER", "mock").strip() or "mock"
        if provider not in KNOWN_PROVIDERS:
            raise ValueError(f"GATEWAY_PROVIDER must be one of {KNOWN_PROVIDERS}")
        return cls(
            database_url=env.get("DATABASE_URL", "").strip() or DEFAULT_DATABASE_URL,
            gateway_provider=provider,
            external_enabled=_bool(env.get("GATEWAY_EXTERNAL_ENABLED")),
            external_base_url=env.get("EXTERNAL_BASE_URL", "").strip(),
            external_api_key=env.get("EXTERNAL_API_KEY", ""),
            external_model=env.get("EXTERNAL_MODEL", "").strip() or "external-unset",
            gateway_timeout_s=float(env.get("GATEWAY_TIMEOUT_S", "10") or 10),
            session_ttl_minutes=int(env.get("SESSION_TTL_MINUTES", "480") or 480),
            cookie_secure=_bool(env.get("SESSION_COOKIE_SECURE")),
            triage_as_of_skew_s=float(env.get("TRIAGE_AS_OF_SKEW_S", "300") or 300),
        )
