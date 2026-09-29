"""Slice d1: public Vercel demo mode (``PUBLIC_DEMO=1``; DECISIONS.md 2026-09-29).

- ``bootstrap``: schema + seeded synthetic users on cold start, idempotent and safe when several
  processes start on the same SQLite file at once.
- Stateless sessions: an HMAC-SHA256-signed cookie ``{username, role, exp}`` so a session survives a
  switch to another serverless instance (each has its own ``/tmp`` database).
- ``POST /api/auth/demo-login {role}``: one-click login as that role's seeded synthetic user. The router
  is only registered in demo mode; RBAC is unchanged.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import time

from fastapi import APIRouter, HTTPException, Request, Response
from pydantic import BaseModel
from sqlalchemy import Engine, select
from sqlalchemy.exc import IntegrityError, OperationalError

from .audit import write_audit
from .db import create_schema, users
from .roles import Role
from .seed import DEV_USERS, seed_dev_users

TOKEN_VERSION = "d1"
DEMO_USER_BY_ROLE = {role: username for username, role, _env, _default in DEV_USERS}


def bootstrap(engine: Engine, attempts: int = 6) -> None:
    """Create every schema and seed the synthetic users; retries lose-the-race errors between cold starts."""
    from .pharma.db import create_pharma_schema
    from .voice import create_voice_schema

    for attempt in range(attempts):
        try:
            create_schema(engine)
            create_voice_schema(engine)
            create_pharma_schema(engine)
            seed_dev_users(engine)
            return
        except (IntegrityError, OperationalError):
            if attempt == attempts - 1:
                raise
            time.sleep(0.1 * (attempt + 1))


def _b64(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode()


def _unb64(text: str) -> bytes:
    return base64.urlsafe_b64decode(text + "=" * (-len(text) % 4))


def _sig(secret: str, body: str) -> str:
    return _b64(hmac.new(secret.encode(), f"{TOKEN_VERSION}.{body}".encode(), hashlib.sha256).digest())


def sign_session(secret: str, username: str, role: Role, ttl_s: int, now: int | None = None) -> str:
    payload = {"u": username, "r": role.value, "exp": int(now if now is not None else time.time()) + ttl_s}
    body = _b64(json.dumps(payload, separators=(",", ":")).encode())
    return f"{TOKEN_VERSION}.{body}.{_sig(secret, body)}"


def verify_session(secret: str, token: str, now: int | None = None) -> tuple[str, Role] | None:
    """(username, role) for a valid unexpired token; ``None`` for anything else (never raises)."""
    try:
        version, body, sig = token.split(".")
        if version != TOKEN_VERSION or not hmac.compare_digest(sig, _sig(secret, body)):
            return None
        payload = json.loads(_unb64(body))
        if int(payload["exp"]) <= int(now if now is not None else time.time()):
            return None
        return str(payload["u"]), Role(payload["r"])
    except (ValueError, KeyError, TypeError):
        return None


class DemoLoginBody(BaseModel):
    role: Role


router = APIRouter(prefix="/api")


@router.post("/auth/demo-login")
def demo_login(body: DemoLoginBody, request: Request, response: Response) -> dict:
    from .deps import SESSION_COOKIE, get_engine, get_settings, request_id

    engine, settings = get_engine(request), get_settings(request)
    with engine.connect() as conn:
        row = conn.execute(select(users).where(users.c.username == DEMO_USER_BY_ROLE[body.role])).first()
    write_audit(
        engine,
        action="auth.demo_login",
        target="session",
        outcome="success" if row else "failure",
        request_id=request_id(request),
        actor_id=row.id if row else None,
        actor_role=body.role.value,
        details={} if row else {"reason": "demo_user_missing"},
    )
    if row is None:
        raise HTTPException(status_code=503, detail="demo user not seeded")
    ttl = settings.session_ttl_minutes * 60
    token = sign_session(settings.session_secret, row.username, Role(row.role), ttl)
    response.set_cookie(
        SESSION_COOKIE, token, max_age=ttl, httponly=True, samesite="lax", secure=settings.cookie_secure, path="/"
    )
    return {"user": {"id": row.id, "username": row.username, "role": row.role, "home": f"/{row.role}"}}
