"""Shared helpers for the voice tests (synthetic data only, offline)."""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

from sqlalchemy import select

from app.db import users
from app.deps import CurrentUser
from app.gateway import ProviderResult
from app.roles import Role
from app.voice.service import VoiceContext
from app.voice.simulate import simulate

FIXTURE_DIR = Path(__file__).parent / "fixtures"
T0 = datetime(2026, 3, 1, 2, 0, tzinfo=timezone.utc)
ALL_FIELDS = (
    "chief_complaint", "onset_duration", "severity", "allergy_status", "current_medications", "relevant_history",
)


def load_fixtures() -> list[dict]:
    return [json.loads(p.read_text(encoding="utf-8")) for p in sorted(FIXTURE_DIR.glob("th_intake_*.json"))]


def fixture(num: int) -> dict:
    return json.loads((FIXTURE_DIR / f"th_intake_{num:02d}.json").read_text(encoding="utf-8"))


def nurse_ctx(app) -> VoiceContext:
    with app.state.engine.connect() as conn:
        row = conn.execute(select(users).where(users.c.username == "nurse1")).first()
    actor = CurrentUser(id=row.id, username=row.username, role=Role.NURSE)
    return VoiceContext(engine=app.state.engine, provider=app.state.provider, actor=actor, request_id="test")


def simulate_all(app, fixtures: list[dict] | None = None):
    ctx = nurse_ctx(app)
    return [simulate(ctx, fx) for fx in (fixtures or load_fixtures())]


class Clock:
    def __init__(self, t: datetime) -> None:
        self.t = t

    def __call__(self) -> datetime:
        return self.t


class VoiceAPI:
    """Drives /api/voice with a controllable server clock and monotonic synthetic turn times."""

    def __init__(self, client, app) -> None:
        self.c = client
        self.clock = Clock(T0)
        app.state.voice_clock = self.clock
        self.cursor = T0
        self.sid: str | None = None

    def start(self, ref: str = "SYN-S3-T1", expect: int = 201):
        self.clock.t = self.cursor
        resp = self.c.post("/api/voice/sessions", json={"patient_ref": ref, "data_class": "synthetic"})
        assert resp.status_code == expect, resp.text
        if resp.status_code == 201:
            self.sid = resp.json()["session"]["session_id"]
        self.cursor += timedelta(seconds=1)
        return resp

    def turn(self, text: str, speaker: str = "patient", dur: float = 3, expect: int | None = 200, **override):
        start = self.cursor
        end = start + timedelta(seconds=dur)
        self.clock.t = end + timedelta(milliseconds=100)
        body = {"speaker": speaker, "text": text, "started_at": start.isoformat(), "ended_at": end.isoformat()}
        body.update(override)
        resp = self.c.post(f"/api/voice/sessions/{self.sid}/turns", json=body)
        if expect is not None:
            assert resp.status_code == expect, resp.text
        if resp.status_code == 200:
            self.cursor = end + timedelta(seconds=1)
        return resp

    def get(self):
        return self.c.get(f"/api/voice/sessions/{self.sid}")

    def facts(self, as_of: str | None = None):
        return self.c.get(f"/api/voice/sessions/{self.sid}/facts", params={"as_of": as_of} if as_of else None)

    def finish(self, expect: int = 200):
        resp = self.c.post(f"/api/voice/sessions/{self.sid}/finish")
        assert resp.status_code == expect, resp.text
        return resp


class StubProvider:
    """A provider returning a fixed result (or a function of the request) — used for fail-safe tests."""

    name = "stub"

    def __init__(self, fn) -> None:
        self.fn = fn
        self.calls: list = []

    def invoke(self, request, request_sha256):
        self.calls.append(request)
        return self.fn(request)


def ok(output: dict) -> ProviderResult:
    return ProviderResult(status="ok", model_version="stub-1", output=output)


def dict_keys_deep(obj) -> set[str]:
    keys: set[str] = set()
    if isinstance(obj, dict):
        for k, v in obj.items():
            keys.add(str(k))
            keys |= dict_keys_deep(v)
    elif isinstance(obj, list):
        for v in obj:
            keys |= dict_keys_deep(v)
    return keys
