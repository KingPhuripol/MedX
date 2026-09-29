"""Slice v1 (MedX Live): short-lived realtime client secret for browser speech in/out.

The vendor realtime model is used for speech only. Questions come from the deterministic voice policy;
facts come from the rules-based intake. This module mints a 60 s client secret and nothing else. It is
kept outside ``app.voice`` (which forbids network imports) and never touches the Model Gateway.
The vendor key, minted secret and access code are never logged or written to the audit trail.
"""

from __future__ import annotations

import hashlib
import hmac
import time
from collections import deque
from typing import Any

import httpx
from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select

from .audit import write_audit
from .config import Settings
from .deps import CurrentUser, get_engine, get_settings, request_id
from .voice.db import voice_sessions
from .voice.router import require_nurse

router = APIRouter(prefix="/api/voice/realtime")

VENDOR_LABEL = "OpenAI"
MINT_URL = "https://api.openai.com/v1/realtime/client_secrets"
CONNECT_URL = "https://api.openai.com/v1/realtime/calls"
DATA_CHANNEL = "oai-events"
SECRET_TTL_S = 60
MINT_TIMEOUT_S = 10.0
RATE_LIMIT_MAX = 10  # attempts per window, per app instance (tests monkeypatch)
RATE_LIMIT_WINDOW_S = 600
INSTRUCTIONS_VERSION = "v1-live-0.1.0"
INSTRUCTIONS = (
    "คุณคือเสียงอ่านของ MedX ซึ่งเป็นต้นแบบเพื่อการวิจัย ใช้กับบทสังเคราะห์เท่านั้น "
    "หน้าที่เดียวของคุณคืออ่านออกเสียงข้อความภาษาไทยในข้อความผู้ใช้ล่าสุดให้ตรงตามตัวอักษรทุกคำ "
    "ด้วยน้ำเสียงสุภาพ ชัดเจน ไม่เร่งรีบ แล้วหยุด ห้ามเพิ่ม ตัด เปลี่ยน แปล หรือตอบคำถาม "
    "ห้ามให้คำแนะนำทางการแพทย์ ห้ามคาดเดาโรค ห้ามปลอบใจหรือให้ความมั่นใจ ห้ามพูดสิ่งอื่นใด\n"
    "Speak ONLY the exact Thai text in the latest user message, verbatim, then stop. "
    "Never answer, advise, reassure, name a disease, or add any words."
)
INSTRUCTIONS_SHA256 = hashlib.sha256(INSTRUCTIONS.encode("utf-8")).hexdigest()


class SessionBody(BaseModel):
    model_config = ConfigDict(extra="forbid")
    voice_session_id: str = Field(min_length=1, max_length=64)
    access_code: str | None = Field(default=None, max_length=128)


def unavailable_reason(s: Settings) -> str | None:
    if not s.voice_enabled:
        return "voice_disabled"
    if not s.voice_api_key:
        return "not_configured"
    if s.public_demo and not s.voice_access_code:
        return "access_code_not_configured"
    return None


def _code_required(s: Settings) -> bool:
    return s.public_demo or s.voice_access_code != ""


def _mint_body(s: Settings) -> dict[str, Any]:
    return {
        "expires_after": {"anchor": "created_at", "seconds": SECRET_TTL_S},
        "session": {
            "type": "realtime",
            "model": s.voice_realtime_model,
            "output_modalities": ["audio"],
            "instructions": INSTRUCTIONS,
            "audio": {
                "input": {
                    "transcription": {"model": s.voice_transcribe_model, "language": "th"},
                    "noise_reduction": {"type": "near_field"},
                    "turn_detection": {
                        "type": "server_vad", "threshold": 0.5, "prefix_padding_ms": 300,
                        "silence_duration_ms": 700, "create_response": False, "interrupt_response": False,
                    },
                },
                "output": {"voice": "marin"},
            },
            "tools": [],
            "tool_choice": "none",
            "max_output_tokens": 1024,
            "reasoning": {"effort": "minimal"},
        },
    }


@router.get("/config")
def realtime_config(request: Request, user: CurrentUser = Depends(require_nurse)) -> dict:
    s = get_settings(request)
    reason = unavailable_reason(s)
    return {
        "enabled": reason is None, "reason": reason, "access_code_required": _code_required(s),
        "max_session_seconds": s.voice_max_session_seconds, "vendor_label": VENDOR_LABEL,
        "model": s.voice_realtime_model, "transcribe_model": s.voice_transcribe_model,
    }


def _rate_limited(request: Request) -> int | None:
    """Record this attempt; return Retry-After seconds if over the limit. Every attempt counts."""
    state = request.app.state
    if not hasattr(state, "realtime_attempts"):
        state.realtime_attempts = deque()
    attempts: deque[float] = state.realtime_attempts
    now = time.monotonic()
    while attempts and now - attempts[0] >= RATE_LIMIT_WINDOW_S:
        attempts.popleft()
    if len(attempts) >= RATE_LIMIT_MAX:
        return max(1, int(RATE_LIMIT_WINDOW_S - (now - attempts[0])) + 1)
    attempts.append(now)
    return None


def _mint(request: Request, s: Settings) -> tuple[dict[str, Any] | None, int, str | None]:
    """Returns (parsed vendor body, upstream_status, failure reason)."""
    transport = getattr(request.app.state, "realtime_transport", None)
    try:
        with httpx.Client(transport=transport, timeout=MINT_TIMEOUT_S) as http:
            resp = http.post(
                MINT_URL, json=_mint_body(s),
                headers={"Authorization": f"Bearer {s.voice_api_key}", "Content-Type": "application/json"},
            )
    except httpx.TimeoutException:
        return None, 0, "upstream_timeout"
    except httpx.HTTPError:
        return None, 0, "upstream_error"
    if not 200 <= resp.status_code < 300:
        return None, resp.status_code, "upstream_error"
    try:
        data = resp.json()
    except ValueError:
        return None, resp.status_code, "upstream_error"
    value, exp = (data.get("value"), data.get("expires_at")) if isinstance(data, dict) else (None, None)
    if not (isinstance(value, str) and value.startswith("ek_") and isinstance(exp, int) and not isinstance(exp, bool)):
        return None, resp.status_code, "upstream_error"
    return data, resp.status_code, None


@router.post("/session")
def realtime_session(body: SessionBody, request: Request, user: CurrentUser = Depends(require_nurse)):
    s = get_settings(request)
    engine = get_engine(request)
    target = f"voice_session/{body.voice_session_id}"
    base = {"model": s.voice_realtime_model, "transcribe_model": s.voice_transcribe_model,
            "instructions_version": INSTRUCTIONS_VERSION, "instructions_sha256": INSTRUCTIONS_SHA256,
            "max_session_seconds": s.voice_max_session_seconds}

    def audit(outcome: str, **extra: Any) -> None:
        write_audit(
            engine, action="voice.realtime.session", target=target, outcome=outcome,
            request_id=request_id(request), actor_id=user.id, actor_role=user.role.value,
            details={**base, **extra},
        )

    def fail(status: int, reason: str, outcome: str, headers: dict | None = None, **extra: Any):
        audit(outcome, reason=reason, **extra)
        raise HTTPException(status_code=status, detail={"reason": reason, **extra}, headers=headers)

    if (reason := unavailable_reason(s)) is not None:
        fail(503, reason, "unavailable")
    if (retry := _rate_limited(request)) is not None:
        fail(429, "rate_limited", "rate_limited", headers={"Retry-After": str(retry)})
    if _code_required(s):
        supplied = (body.access_code or "").encode("utf-8")
        if not supplied or not hmac.compare_digest(supplied, s.voice_access_code.encode("utf-8")):
            fail(403, "access_code_invalid", "denied")
    with engine.connect() as conn:
        row = conn.execute(
            select(voice_sessions.c.status).where(voice_sessions.c.session_id == body.voice_session_id)
        ).first()
    if row is None:
        audit("error", reason="session_not_found")
        raise HTTPException(status_code=404, detail="voice session not found")
    if row.status != "active":
        audit("error", reason="session_not_active")
        raise HTTPException(status_code=409, detail="voice session is not active")

    data, upstream_status, failure = _mint(request, s)
    if failure is not None:
        if failure == "upstream_timeout":
            fail(504, failure, "error")
        fail(502, failure, "error", upstream_status=upstream_status)
    assert data is not None
    sess = data.get("session")
    sess_id = sess.get("id") if isinstance(sess, dict) else None
    audit(
        "success", expires_at=data["expires_at"], upstream_status=upstream_status,
        upstream_session_id=sess_id if isinstance(sess_id, str) and sess_id.startswith("sess_") else None,
    )
    return JSONResponse(
        {
            "client_secret": data["value"], "expires_at": data["expires_at"], "connect_url": CONNECT_URL,
            "data_channel": DATA_CHANNEL, "model": s.voice_realtime_model,
            "transcribe_model": s.voice_transcribe_model, "vendor_label": VENDOR_LABEL,
            "max_session_seconds": s.voice_max_session_seconds, "instructions_version": INSTRUCTIONS_VERSION,
        },
        headers={"Cache-Control": "no-store"},
    )
