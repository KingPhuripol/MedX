"""Deployment configuration in one place.

Every knob the service has is declared here rather than read from `os.environ` at the
point of use. Two reasons, and the second is the load-bearing one:

1. `GET /health` can report what the process is actually running under, which is the
   difference between "the demo behaved oddly" and "the demo was pointed at the wrong
   provider".
2. Settings that matter for safety — whether an external provider is permitted, whether
   authentication is on, what the service is bound to — become inspectable and testable
   together instead of being discovered one `os.environ.get` at a time.

Secrets never appear in `__repr__` or in `/health`. `scripts/` stays stdlib-only and does
not import this module.
"""

from __future__ import annotations

import ipaddress
from pathlib import Path
from typing import Literal

from pydantic import Field, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

#: Shown on every screen, in every error body, and in the OpenAPI description. The claim
#: boundary in `CLAUDE.md` is not a documentation exercise: it travels with the payload.
BANNER = "RESEARCH PROTOTYPE - HUMAN REVIEW REQUIRED"

AuthMode = Literal["none", "token", "public_demo"]


class Settings(BaseSettings):
    """Everything the deployment decides. Nothing here is reachable from a request."""

    model_config = SettingsConfigDict(
        env_prefix="FRONT_DOOR_", env_file=".env", extra="ignore", frozen=True
    )

    # ------------------------------------------------------------------ transport
    host: str = "127.0.0.1"
    port: int = Field(default=8000, ge=1, le=65535)

    # ------------------------------------------------------------------- storage
    #: Unset means in-memory: the offline demo leaves nothing patient-shaped on disk.
    db: Path | None = None
    audit_log: Path | None = None

    # ------------------------------------------------------------------ providers
    provider: str = "mock"
    allow_external: bool = False
    external_provider_url: str = "https://api.openai.com/v1"
    external_provider_api_key: str = Field(default="", repr=False)
    external_model: str = "gpt-4o-mini"
    external_timeout_seconds: float = Field(default=15.0, ge=1.0, le=120.0)
    #: Threads available for provider calls. It was fixed at one, which serialised the
    #: entire API behind a single provider thread.
    provider_concurrency: int = Field(default=4, ge=1, le=32)

    # V2 is a separate synthetic workflow; disable to roll back without deleting data.
    v2_enabled: bool = True
    v2_readiness_report: Path | None = None
    v2_experiment_dir: Path = Path("artifacts/v2/experiments")
    v2_transport: Literal["gateway", "openai_compatible"] = "gateway"
    v2_local_free: bool = False
    v2_json_mode: Literal["json_schema", "json_object"] = "json_schema"
    v2_max_tokens: int = Field(default=2048, ge=64, le=8192)
    v2_speech_model: str = "unconfigured"
    v2_speech_token: str = Field(default="", repr=False)

    v2_provider_url: str | None = None
    v2_provider_token: str = Field(default="", repr=False)
    v2_model: str = "unconfigured"
    v2_paid_budget_usd: float = Field(default=0, ge=0, allow_inf_nan=False)
    v2_call_reservation_usd: float = Field(default=0, ge=0, allow_inf_nan=False)
    v2_budget_db: Path | None = None
    v2_capabilities: tuple[str, ...] = ("summary", "conversation", "tools")
    v2_differential: bool = False
    v2_speech_url: str | None = None
    v2_synthesis_url: str | None = None
    v2_synthesis_token: str = Field(default="", repr=False)
    v2_synthesis_model: str = "unconfigured"
    v2_synthesis_voice: str = "alloy"

    # ----------------------------------------------------------------------- auth
    auth_mode: AuthMode = "none"
    principals_file: Path | None = None
    #: Role of the single local user when auth_mode=none (loopback only); lets one laptop demo each station.
    demo_role: Literal["intake", "physician", "pharmacist", "evaluator"] = "physician"
    #: auth_mode=public_demo (DEC-0022): anonymous visitors each get a private sandbox
    #: workspace seeded with synthetic cases; model-backed calls are capped per sandbox.
    public_calls_per_hour: int = Field(default=30, ge=1, le=1000)
    contact_email: str = ""
    #: Run agent jobs inside the request (serverless hosts may freeze background threads).
    v2_inline_jobs: bool = False

    # -------------------------------------------------------------------- logging
    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR"] = "INFO"
    log_format: Literal["json", "text"] = "json"

    # ---------------------------------------------------------------------- misc
    #: Empty means CORS is off. The UI is same-origin and ships no JavaScript, so this
    #: exists mainly so that nobody reaches for `allow_origins=["*"]` under deadline
    #: pressure.
    cors_origins: tuple[str, ...] = ()

    @field_validator("cors_origins", mode="before")
    @classmethod
    def _split_origins(cls, value):
        if isinstance(value, str):
            return tuple(part.strip() for part in value.split(",") if part.strip())
        return value

    @property
    def binds_publicly(self) -> bool:
        """Whether this host reaches beyond the machine it runs on."""
        if self.host in {"localhost", ""}:
            return False
        try:
            return not ipaddress.ip_address(self.host).is_loopback
        except ValueError:
            # A hostname that is not an IP literal. Assume it resolves off-box.
            return True

    @model_validator(mode="after")
    def _refuse_unauthenticated_exposure(self) -> "Settings":
        """An unauthenticated service must not be reachable from outside the machine.

        The human-confirmation gate rests on `reviewer_id`. With `auth_mode=none` that is
        a string the caller chooses, so the gate is decoration — fine on a laptop for a
        demo, not fine on a network. Refusing at startup is the only control that cannot
        be forgotten, and it is a startup failure rather than a warning because a warning
        scrolls past.
        """
        if self.auth_mode == "none" and self.binds_publicly:
            raise ValueError(
                f"refusing to bind {self.host} with auth_mode=none: the human-review gate "
                "would rest on a caller-supplied reviewer_id. Set FRONT_DOOR_AUTH_MODE=token "
                "and FRONT_DOOR_PRINCIPALS_FILE, or bind to loopback."
            )
        if self.auth_mode == "none" and (self.allow_external or self.v2_provider_url or self.v2_speech_url or self.v2_synthesis_url):
            raise ValueError(
                "refusing to enable an external provider with auth_mode=none: an "
                "unauthenticated caller could cause content to leave the process."
            )
        if self.auth_mode == "public_demo" and (self.v2_speech_url or self.v2_synthesis_url):
            raise ValueError("public_demo refuses speech/synthesis providers: raw visitor audio cannot be screened (DEC-0022)")
        if self.auth_mode == "public_demo" and self.v2_provider_url:
            # Blocked until a shared (cross-instance) cost cap exists and a data-governance/PDPA
            # approval is recorded; enabling a model publicly is a code change plus re-review.
            raise ValueError("public_demo refuses a model provider until the shared cost cap is in place (DEC-0022)")
        if self.auth_mode == "token" and self.principals_file is None:
            raise ValueError("auth_mode=token requires FRONT_DOOR_PRINCIPALS_FILE")
        if self.v2_provider_url or self.v2_speech_url or self.v2_synthesis_url:
            if not self.allow_external or not self.v2_budget_db:
                raise ValueError("v2 external adapters require allow_external and a dedicated persistent budget DB")
            if self.db and self.v2_budget_db.resolve() == self.db.resolve():
                raise ValueError("budget DB must be separate from clinical data DB")
        return self

    def public_view(self) -> dict:
        """What may be shown on /health. No paths, no secrets — locations are a detail of
        the deployment, and a health endpoint is often the most exposed thing there is."""
        return {
            "provider": self.provider,
            "allow_external": self.allow_external,
            "auth_mode": self.auth_mode,
            "persistent": self.db is not None,
            "audit_log_enabled": self.audit_log is not None,
            "provider_concurrency": self.provider_concurrency,
        }

    def __repr__(self) -> str:  # pragma: no cover - trivial
        return f"Settings({self.public_view()})"
