"""Shared request dependencies: engine, request id, current user."""

from __future__ import annotations

import time
from dataclasses import dataclass

from fastapi import HTTPException, Request
from sqlalchemy import Engine, select

from .config import Settings
from .db import sessions, users
from .roles import Role
from .security import token_digest

SESSION_COOKIE = "fd_session"


@dataclass(frozen=True)
class CurrentUser:
    id: int
    username: str
    role: Role


def get_engine(request: Request) -> Engine:
    return request.app.state.engine


def get_settings(request: Request) -> Settings:
    return request.app.state.settings


def request_id(request: Request) -> str:
    return getattr(request.state, "request_id", "unknown")


def optional_user(request: Request) -> CurrentUser | None:
    token = request.cookies.get(SESSION_COOKIE)
    if not token:
        return None
    stmt = (
        select(users.c.id, users.c.username, users.c.role)
        .join(sessions, sessions.c.user_id == users.c.id)
        .where(sessions.c.token_sha256 == token_digest(token))
        .where(sessions.c.expires_at > int(time.time()))
    )
    with get_engine(request).connect() as conn:
        row = conn.execute(stmt).first()
    if row is None:
        return None
    return CurrentUser(id=row.id, username=row.username, role=Role(row.role))


def require_user(request: Request) -> CurrentUser:
    user = optional_user(request)
    if user is None:
        raise HTTPException(status_code=401, detail="authentication required")
    return user
