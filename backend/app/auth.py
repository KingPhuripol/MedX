"""Login, logout, current user, and role-home placeholder routes."""

from __future__ import annotations

import time

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from pydantic import BaseModel, Field
from sqlalchemy import delete, select

from .audit import write_audit
from .db import sessions, users
from .deps import (
    SESSION_COOKIE,
    CurrentUser,
    get_engine,
    get_settings,
    optional_user,
    request_id,
    require_user,
)
from .roles import Role
from .security import DUMMY_HASH, new_session_token, token_digest, verify_password

router = APIRouter(prefix="/api")


class LoginBody(BaseModel):
    # Defaults allow empty/missing fields to reach the handler and be rejected as 401.
    username: str = Field(default="", max_length=128)
    password: str = Field(default="", max_length=256)


def _user_payload(user: CurrentUser) -> dict[str, str | int]:
    return {"id": user.id, "username": user.username, "role": user.role.value, "home": f"/{user.role.value}"}


@router.post("/auth/login")
def login(body: LoginBody, request: Request, response: Response) -> dict:
    engine = get_engine(request)
    row = None
    if body.username:
        with engine.connect() as conn:
            row = conn.execute(select(users).where(users.c.username == body.username)).first()
    password_ok = verify_password(body.password, row.password_hash if row else DUMMY_HASH)
    ok = bool(body.username and body.password and row is not None and password_ok)
    write_audit(
        engine,
        action="auth.login",
        target="session",
        outcome="success" if ok else "failure",
        request_id=request_id(request),
        actor_id=row.id if row is not None else None,
        actor_role=row.role if row is not None else None,
        details={} if ok else {"reason": "invalid_credentials"},
    )
    if not ok:
        raise HTTPException(status_code=401, detail="invalid username or password")

    settings = get_settings(request)
    token = new_session_token()
    now = int(time.time())
    ttl = settings.session_ttl_minutes * 60
    with engine.begin() as conn:
        conn.execute(
            sessions.insert().values(
                token_sha256=token_digest(token), user_id=row.id, created_at=now, expires_at=now + ttl
            )
        )
    response.set_cookie(
        SESSION_COOKIE,
        token,
        max_age=ttl,
        httponly=True,
        samesite="lax",
        secure=settings.cookie_secure,
        path="/",
    )
    return {"user": _user_payload(CurrentUser(id=row.id, username=row.username, role=Role(row.role)))}


@router.post("/auth/logout", status_code=204)
def logout(request: Request, response: Response) -> Response:
    engine = get_engine(request)
    user = optional_user(request)
    token = request.cookies.get(SESSION_COOKIE)
    if token:
        with engine.begin() as conn:
            conn.execute(delete(sessions).where(sessions.c.token_sha256 == token_digest(token)))
    write_audit(
        engine,
        action="auth.logout",
        target="session",
        outcome="success" if user else "no_session",
        request_id=request_id(request),
        actor_id=user.id if user else None,
        actor_role=user.role.value if user else None,
    )
    response.delete_cookie(SESSION_COOKIE, path="/")
    response.status_code = 204
    return response


@router.get("/me")
def me(user: CurrentUser = Depends(require_user)) -> dict:
    return {"user": _user_payload(user)}


@router.get("/home/{role}")
def role_home(role: str, request: Request, user: CurrentUser = Depends(require_user)) -> dict:
    try:
        wanted = Role(role)
    except ValueError:
        raise HTTPException(status_code=404, detail="unknown role home") from None
    if wanted is not user.role:
        write_audit(
            get_engine(request),
            action="home.access",
            target=f"home/{wanted.value}",
            outcome="denied",
            request_id=request_id(request),
            actor_id=user.id,
            actor_role=user.role.value,
        )
        raise HTTPException(status_code=403, detail="this home belongs to another role")
    return {
        "role": user.role.value,
        "placeholder": True,
        "message": "features arrive in later slices",
    }
