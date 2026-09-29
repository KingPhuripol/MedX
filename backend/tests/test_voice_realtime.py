"""Slice v1 B1-B11: MedX Live realtime client-secret endpoint. Vendor fully mocked (httpx.MockTransport)."""

from __future__ import annotations

import ast
import json
import logging

import httpx
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from app import voice_realtime as vr
from app.config import Settings
from app.db import audit_events
from app.main import create_app
from app.seed import seed_dev_users

from .conftest import PASSWORDS, REPO_ROOT
from .voice.helpers import VoiceAPI

KEY = "SENTINEL-KEY-4f2a91"
CODE = "SENTINEL-CODE-77b3"
SECRET = "ek_SENTINEL_c0ffee"
SESSION_SECRET = "s" * 40
VENDOR_OK = {"value": SECRET, "expires_at": 1_900_000_000, "session": {"id": "sess_abc123", "type": "realtime"}}


class Vendor:
    """Records every upstream request; ``handler`` decides the answer."""

    def __init__(self, handler=None) -> None:
        self.requests: list[httpx.Request] = []
        self.handler = handler or (lambda req: httpx.Response(200, json=VENDOR_OK))
        self.transport = httpx.MockTransport(self._handle)

    def _handle(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        return self.handler(request)


def make(tmp_path, vendor: Vendor | None = None, **over):
    kw = dict(database_url=f"sqlite:///{tmp_path / 'rt.db'}", voice_enabled=True, voice_api_key=KEY)
    kw.update(over)
    app = create_app(Settings(**kw))
    if not kw.get("public_demo"):
        seed_dev_users(app.state.engine)
    vendor = vendor or Vendor()
    app.state.realtime_transport = vendor.transport
    return app, vendor


def login(app, username="nurse1") -> TestClient:
    c = TestClient(app)
    r = c.post("/api/auth/login", json={"username": username, "password": PASSWORDS[username]})
    assert r.status_code == 200, r.text
    return c


def demo_nurse(app) -> TestClient:
    c = TestClient(app)
    c.post("/api/auth/demo-login", json={"role": "nurse"}).raise_for_status()
    return c


def new_session(c: TestClient) -> str:
    r = c.post("/api/voice/sessions", json={"patient_ref": "SYN-LIVE-A1B2C3", "data_class": "synthetic"})
    assert r.status_code == 201, r.text
    return r.json()["session"]["session_id"]


def mint(c, sid, code=None, expect=None):
    r = c.post("/api/voice/realtime/session", json={"voice_session_id": sid, "access_code": code})
    if expect is not None:
        assert r.status_code == expect, r.text
    return r


def rows(app) -> list[dict]:
    with app.state.engine.connect() as conn:
        return [
            dict(r) | {"details": json.loads(r["details_json"])}
            for r in conn.execute(select(audit_events).order_by(audit_events.c.id)).mappings()
        ]


def rt_rows(app) -> list[dict]:
    return [r for r in rows(app) if r["action"] == "voice.realtime.session"]


@pytest.fixture
def env(tmp_path):
    app, vendor = make(tmp_path)
    with login(app) as c:
        yield app, vendor, c


# ------------------------------------------------------------------ B1
@pytest.mark.parametrize(
    "over,reason",
    [({"voice_enabled": False}, "voice_disabled"), ({"voice_api_key": ""}, "not_configured")],
)
def test_b1_disabled_reasons(tmp_path, over, reason):
    app, vendor = make(tmp_path, **over)
    with login(app) as c:
        cfg = c.get("/api/voice/realtime/config").json()
        assert cfg["enabled"] is False and cfg["reason"] == reason
        r = mint(c, new_session(c), expect=503)
        assert r.json()["detail"] == {"reason": reason}
    assert vendor.requests == []
    assert [r["outcome"] for r in rt_rows(app)] == ["unavailable"]


def test_b1_public_demo_without_code(tmp_path):
    app, vendor = make(tmp_path, public_demo=True, session_secret=SESSION_SECRET)
    with demo_nurse(app) as c:
        cfg = c.get("/api/voice/realtime/config").json()
        assert (cfg["enabled"], cfg["reason"], cfg["access_code_required"]) == (
            False, "access_code_not_configured", True,
        )
        r = mint(c, new_session(c), expect=503)
        assert r.json()["detail"] == {"reason": "access_code_not_configured"}
    assert vendor.requests == []


def test_b1_config_enabled_shape(env):
    _, _, c = env
    assert c.get("/api/voice/realtime/config").json() == {
        "enabled": True, "reason": None, "access_code_required": False, "max_session_seconds": 300,
        "vendor_label": "OpenAI", "model": "gpt-realtime-2.1-mini", "transcribe_model": "gpt-4o-mini-transcribe",
    }


# ------------------------------------------------------------------ B2
@pytest.mark.parametrize("who", ["physician1", "pharmacist1"])
def test_b2_other_roles_forbidden(tmp_path, who):
    app, vendor = make(tmp_path)
    with login(app, who) as c:
        assert c.get("/api/voice/realtime/config").status_code == 403
        r = mint(c, "x" * 8, expect=403)
        assert r.json()["detail"] == "voice intake is for the nurse role"
    assert vendor.requests == [] and rt_rows(app) == []


def test_b2_anonymous(tmp_path):
    app, _ = make(tmp_path)
    with TestClient(app) as c:
        assert c.get("/api/voice/realtime/config").status_code == 401
        assert mint(c, "abc").status_code == 401
    assert rt_rows(app) == []


# ------------------------------------------------------------------ B3
def test_b3_public_demo_access_code(tmp_path):
    app, vendor = make(tmp_path, public_demo=True, session_secret=SESSION_SECRET, voice_access_code=CODE)
    with demo_nurse(app) as c:
        assert c.get("/api/voice/realtime/config").json()["access_code_required"] is True
        sid = new_session(c)
        assert mint(c, sid, expect=403).json()["detail"] == {"reason": "access_code_invalid"}
        mint(c, sid, code="wrong", expect=403)
        assert vendor.requests == []
        assert mint(c, sid, code=CODE, expect=200).json()["client_secret"] == SECRET
    assert [r["outcome"] for r in rt_rows(app)] == ["denied", "denied", "success"]


def test_b3_code_enforced_outside_demo_when_set(tmp_path):
    app, _ = make(tmp_path, voice_access_code=CODE)
    with login(app) as c:
        sid = new_session(c)
        mint(c, sid, expect=403)
        mint(c, sid, code=CODE, expect=200)


# ------------------------------------------------------------------ B4
def test_b4_upstream_request_exact(env):
    app, vendor, c = env
    r = mint(c, new_session(c), expect=200)
    assert r.headers["cache-control"] == "no-store"
    assert r.json() == {
        "client_secret": SECRET, "expires_at": 1_900_000_000,
        "connect_url": "https://api.openai.com/v1/realtime/calls", "data_channel": "oai-events",
        "model": "gpt-realtime-2.1-mini", "transcribe_model": "gpt-4o-mini-transcribe", "vendor_label": "OpenAI",
        "max_session_seconds": 300, "instructions_version": "v1-live-0.1.0",
    }
    (req,) = vendor.requests
    assert req.method == "POST" and str(req.url) == "https://api.openai.com/v1/realtime/client_secrets"
    assert req.headers["authorization"] == f"Bearer {KEY}"
    assert req.headers["content-type"] == "application/json"
    body = json.loads(req.content)
    assert body == {
        "expires_after": {"anchor": "created_at", "seconds": 60},
        "session": {
            "type": "realtime", "model": "gpt-realtime-2.1-mini", "output_modalities": ["audio"],
            "instructions": vr.INSTRUCTIONS,
            "audio": {
                "input": {
                    "transcription": {"model": "gpt-4o-mini-transcribe", "language": "th"},
                    "noise_reduction": {"type": "near_field"},
                    "turn_detection": {
                        "type": "server_vad", "threshold": 0.5, "prefix_padding_ms": 300,
                        "silence_duration_ms": 700, "create_response": False, "interrupt_response": False,
                    },
                },
                "output": {"voice": "marin"},
            },
            "tools": [], "tool_choice": "none", "max_output_tokens": 1024, "reasoning": {"effort": "minimal"},
        },
    }
    assert "idle_timeout_ms" not in json.dumps(body)
    assert "ห้ามปลอบใจ" in vr.INSTRUCTIONS and "verbatim" in vr.INSTRUCTIONS


def test_b4_configured_models_flow_through(tmp_path):
    app, vendor = make(
        tmp_path, voice_realtime_model="m-rt", voice_transcribe_model="m-tr", voice_max_session_seconds=120
    )
    with login(app) as c:
        r = mint(c, new_session(c), expect=200)
    body = json.loads(vendor.requests[0].content)
    assert body["session"]["model"] == "m-rt"
    assert body["session"]["audio"]["input"]["transcription"]["model"] == "m-tr"
    assert r.json()["max_session_seconds"] == 120


# ------------------------------------------------------------------ B5 / V1-A05
def test_b5_no_secret_leaks(tmp_path, caplog):
    caplog.set_level(logging.DEBUG)
    app, _ = make(tmp_path, public_demo=True, session_secret=SESSION_SECRET, voice_access_code=CODE)
    with demo_nurse(app) as c:
        sid = new_session(c)
        mint(c, sid, code="wrong-code-attempt")
        mint(c, sid, code=CODE, expect=200)
    blob = json.dumps(rows(app), default=str) + caplog.text
    for needle in (KEY, CODE, SECRET, "ek_", "wrong-code-attempt"):
        assert needle not in blob, needle
    (ok,) = [r for r in rt_rows(app) if r["outcome"] == "success"]
    assert set(ok["details"]) == {
        "model", "transcribe_model", "instructions_version", "instructions_sha256", "max_session_seconds",
        "expires_at", "upstream_status", "upstream_session_id",
    }
    assert ok["details"]["upstream_session_id"] == "sess_abc123"
    assert ok["details"]["instructions_sha256"] == vr.INSTRUCTIONS_SHA256
    text = repr(Settings(voice_enabled=True, voice_api_key=KEY, voice_access_code=CODE))
    assert KEY not in text and CODE not in text


def test_b5_exactly_one_success_row(env):
    app, _, c = env
    sid = new_session(c)
    mint(c, sid, expect=200)
    (row,) = rt_rows(app)
    assert row["outcome"] == "success" and row["target"] == f"voice_session/{sid}"


# ------------------------------------------------------------------ B6
def test_b6_rate_limit_counts_bad_codes(tmp_path):
    app, vendor = make(tmp_path, voice_access_code=CODE)
    with login(app) as c:
        sid = new_session(c)
        for _ in range(vr.RATE_LIMIT_MAX - 1):
            mint(c, sid, code="bad", expect=403)
        mint(c, sid, code=CODE, expect=200)  # the 10th attempt
        r = mint(c, sid, code=CODE, expect=429)  # the 11th
        assert r.json()["detail"] == {"reason": "rate_limited"}
        assert int(r.headers["retry-after"]) >= 1
    assert len(vendor.requests) == 1
    assert rt_rows(app)[-1]["outcome"] == "rate_limited"


def test_b6_limit_is_per_app_instance(tmp_path, monkeypatch):
    monkeypatch.setattr(vr, "RATE_LIMIT_MAX", 1)
    app, _ = make(tmp_path)
    with login(app) as c:
        sid = new_session(c)
        mint(c, sid, expect=200)
        mint(c, sid, expect=429)
    (tmp_path / "other").mkdir()
    app2, _ = make(tmp_path / "other")
    with login(app2) as c2:
        mint(c2, new_session(c2), expect=200)


# ------------------------------------------------------------------ B7
def test_b7_upstream_500(tmp_path):
    vendor = Vendor(lambda req: httpx.Response(500, json={"error": {"message": "VENDOR-BODY-LEAK"}}))
    app, _ = make(tmp_path, vendor)
    with login(app) as c:
        r = mint(c, new_session(c), expect=502)
    assert r.json()["detail"] == {"reason": "upstream_error", "upstream_status": 500}
    assert "VENDOR-BODY-LEAK" not in r.text
    row = rt_rows(app)[-1]
    assert row["outcome"] == "error" and row["details"]["upstream_status"] == 500


def test_b7_timeout(tmp_path):
    def boom(req):
        raise httpx.ReadTimeout("slow", request=req)

    app, _ = make(tmp_path, Vendor(boom))
    with login(app) as c:
        r = mint(c, new_session(c), expect=504)
    assert r.json()["detail"] == {"reason": "upstream_timeout"}
    assert rt_rows(app)[-1]["details"]["reason"] == "upstream_timeout"


@pytest.mark.parametrize(
    "payload",
    [
        {"value": "sk-notephemeral", "expires_at": 1},
        {"value": SECRET, "expires_at": "soon"},
        {"value": SECRET},
        ["not", "a", "dict"],
    ],
)
def test_b7_malformed_body(tmp_path, payload):
    app, _ = make(tmp_path, Vendor(lambda req: httpx.Response(200, json=payload)))
    with login(app) as c:
        r = mint(c, new_session(c), expect=502)
    assert r.json()["detail"]["reason"] == "upstream_error"
    assert "sk-notephemeral" not in r.text and SECRET not in r.text


# ------------------------------------------------------------------ B8
def test_b8_unknown_and_finished_session(env):
    app, vendor, c = env
    mint(c, "doesnotexist", expect=404)
    sid = new_session(c)
    c.post(f"/api/voice/sessions/{sid}/finish").raise_for_status()
    mint(c, sid, expect=409)
    assert vendor.requests == []


# ------------------------------------------------------------------ B9
def test_b9_public_demo_still_mock_only(tmp_path):
    s = Settings(
        database_url=f"sqlite:///{tmp_path / 'd.db'}", public_demo=True, session_secret=SESSION_SECRET,
        voice_enabled=True, voice_api_key="x", voice_access_code="c",
    )
    with TestClient(create_app(s)) as c:
        assert c.get("/api/health").json()["default_provider"] == "mock"
    with pytest.raises(ValueError):
        Settings(public_demo=True, session_secret=SESSION_SECRET, external_api_key="x")


def test_b9_key_never_becomes_external_key(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", KEY)
    s = Settings.from_env()
    assert s.voice_api_key == KEY and s.external_api_key == ""


def test_b9_public_demo_env_allows_voice_but_refuses_external(monkeypatch):
    monkeypatch.setenv("PUBLIC_DEMO", "1")
    monkeypatch.setenv("SESSION_SECRET", SESSION_SECRET)
    monkeypatch.setenv("OPENAI_API_KEY", KEY)
    monkeypatch.setenv("VOICE_ENABLED", "1")
    assert Settings.from_env().voice_enabled is True
    monkeypatch.setenv("EXTERNAL_API_KEY", "sk-test")
    with pytest.raises(ValueError):
        Settings.from_env()


def test_b9_module_isolation():
    src = (REPO_ROOT / "backend" / "app" / "voice_realtime.py").read_text(encoding="utf-8")
    for node in ast.walk(ast.parse(src)):
        if isinstance(node, ast.Import):
            mods = [a.name for a in node.names]
        elif isinstance(node, ast.ImportFrom):
            mods = [node.module or ""]
        else:
            continue
        assert not any("gateway" in m for m in mods), mods
    for path in (REPO_ROOT / "backend" / "app" / "gateway").rglob("*.py"):
        assert "voice_" not in path.read_text(encoding="utf-8"), path


# ------------------------------------------------------------------ B10
def test_b10_turn_provenance(env):
    app, _, c = env
    api = VoiceAPI(c, app)
    api.start()
    api.turn("เจ็บหน้าอกมาสองชั่วโมงค่ะ", expect=422, source="asr")
    api.turn("เจ็บหน้าอกมาสองชั่วโมงค่ะ", expect=422, source="typed", asr_model="m")
    api.turn("เจ็บหน้าอกมาสองชั่วโมงค่ะ", expect=422, source="bogus")
    api.turn("เจ็บหน้าอกมาสองชั่วโมงค่ะ", source="asr", asr_model="gpt-4o-mini-transcribe")
    api.turn("ไม่เคยแพ้ยาค่ะ")
    adds = [r["details"] for r in rows(app) if r["action"] == "voice.turn.add"]
    assert (adds[0]["source"], adds[0]["asr_model"]) == ("asr", "gpt-4o-mini-transcribe")
    assert (adds[1]["source"], adds[1]["asr_model"]) == ("typed", None)


# ------------------------------------------------------------------ B11
@pytest.mark.parametrize("val", ["30", "59", "901"])
def test_b11_max_session_range(monkeypatch, val):
    monkeypatch.setenv("VOICE_MAX_SESSION_SECONDS", val)
    with pytest.raises(ValueError):
        Settings.from_env()


@pytest.mark.parametrize("val", ["60", "900"])
def test_b11_bounds_ok(monkeypatch, val):
    monkeypatch.setenv("VOICE_MAX_SESSION_SECONDS", val)
    assert Settings.from_env().voice_max_session_seconds == int(val)
