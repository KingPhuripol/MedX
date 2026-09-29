"""Configuration read from environment variables only (no secrets in code)."""

from __future__ import annotations

import os
from dataclasses import dataclass, field

DEFAULT_DATABASE_URL = "sqlite:///./backend/dev.db"
# Slice d1: public Vercel demo (DECISIONS.md 2026-09-29). Serverless instances can only write /tmp.
PUBLIC_DEMO_DATABASE_URL = "sqlite:////tmp/medx-demo.sqlite3"
MIN_SESSION_SECRET_LEN = 32
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
    # Slice i2: Case Graph state/outputs behind triage assessments. Empty: beside a file SQLite DB, else in memory.
    casegraph_dir: str = ""
    # Slice d1: public demo mode — mock provider only, one-click role login, HMAC-signed stateless sessions.
    public_demo: bool = False
    session_secret: str = field(default="", repr=False)

    def __post_init__(self) -> None:
        if not self.public_demo:
            return
        # Fail closed at startup: the public demo never reaches an external provider.
        if self.gateway_provider != "mock" or self.external_enabled or self.external_base_url or self.external_api_key:
            raise ValueError("PUBLIC_DEMO=1 refuses any external provider configuration (mock only)")
        if len(self.session_secret) < MIN_SESSION_SECRET_LEN:
            raise ValueError(f"PUBLIC_DEMO=1 needs SESSION_SECRET of at least {MIN_SESSION_SECRET_LEN} characters")

    @classmethod
    def from_env(cls) -> "Settings":
        env = os.environ
        provider = env.get("GATEWAY_PROVIDER", "mock").strip() or "mock"
        if provider not in KNOWN_PROVIDERS:
            raise ValueError(f"GATEWAY_PROVIDER must be one of {KNOWN_PROVIDERS}")
        public_demo = _bool(env.get("PUBLIC_DEMO"))
        default_db = PUBLIC_DEMO_DATABASE_URL if public_demo else DEFAULT_DATABASE_URL
        return cls(
            database_url=env.get("DATABASE_URL", "").strip() or default_db,
            gateway_provider=provider,
            external_enabled=_bool(env.get("GATEWAY_EXTERNAL_ENABLED")),
            external_base_url=env.get("EXTERNAL_BASE_URL", "").strip(),
            external_api_key=env.get("EXTERNAL_API_KEY", ""),
            external_model=env.get("EXTERNAL_MODEL", "").strip() or "external-unset",
            gateway_timeout_s=float(env.get("GATEWAY_TIMEOUT_S", "10") or 10),
            session_ttl_minutes=int(env.get("SESSION_TTL_MINUTES", "480") or 480),
            # Vercel sets VERCEL=1; its HTTPS-only public demo then gets Secure cookies by default.
            cookie_secure=_bool(env.get("SESSION_COOKIE_SECURE"), default=public_demo and _bool(env.get("VERCEL"))),
            triage_as_of_skew_s=float(env.get("TRIAGE_AS_OF_SKEW_S", "300") or 300),
            casegraph_dir=env.get("CASEGRAPH_DIR", "").strip(),
            public_demo=public_demo,
            session_secret=env.get("SESSION_SECRET", ""),
        )
