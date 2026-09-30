"""Slice v2t T2-T6, T10: ambient (transcription-only) realtime mint. Vendor fully mocked (httpx.MockTransport)."""

from __future__ import annotations

import ast
import json
import logging

import httpx
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import inspect, text

from app import voice_realtime as vr
from app.voice.db import voice_sessions

from .conftest import REPO_ROOT
from .test_voice_realtime import (
    CODE, KEY, SECRET, SESSION_SECRET, Vendor, demo_nurse, login, make, new_session, rows, rt_rows,
)

TX_MODEL = "gpt-4o-mini-transcribe"
VENDOR_TX = {
    "value": SECRET, "expires_at": 1_900_000_000,
    "session": {"id": "sess_tx1", "object": "realtime.transcription_session", "type": "transcription"},
}
GOLD_BODY = {
    "expires_after": {"anchor": "created_at", "seconds": 60},
    "session": {
        "type": "transcription",
        "audio": {"input": {
            "transcription": {"model": TX_MODEL, "language": "th"},
            "noise_reduction": {"type": "near_field"},
            "turn_detection": {"type": "server_vad", "threshold": 0.5, "prefix_padding_ms": 300, "silence_duration_ms": 700},
        }},
    },
}
GOLD_RESPONSE = {
    "client_secret": SECRET, "expires_at": 1_900_000_000, "connect_url": "https://api.openai.com/v1/realtime/calls",
    "data_channel": "oai-events", "model": TX_MODEL, "transcribe_model": TX_MODEL, "vendor_label": "OpenAI",
    "max_session_seconds": 300, "instructions_version": "v2-transcribe-0.1.0",
}
GUIDED_RESPONSE = {  # today's B4 dict
    "client_secret": SECRET, "expires_at": 1_900_000_000, "connect_url": "https://api.openai.com/v1/realtime/calls",
    "data_channel": "oai-events", "model": "gpt-realtime-2.1-mini", "transcribe_model": TX_MODEL,
    "vendor_label": "OpenAI", "max_session_seconds": 300, "instructions_version": "v1-live-0.1.0",
}
FORBIDDEN = {
    "model", "instructions", "tools", "tool_choice", "output_modalities", "output", "max_output_tokens",
    "reasoning", "create_response", "interrupt_response", "idle_timeout_ms", "include",
}
GUIDED_SNAPSHOT = (REPO_ROOT / "backend" / "tests" / "fixtures" / "v2t_guided_mint_body.json").read_bytes()


def tx_vendor(handler=None) -> Vendor:
    return Vendor(handler or (lambda req: httpx.Response(200, json=VENDOR_TX)))


def ambient_session(c: TestClient, app) -> str:
    """An ambient voice session. Uses v2a's API once ``mode`` exists; on this branch adds the column in-test."""
    if "mode" in voice_sessions.c:
        r = c.post("/api/voice/sessions", json={"patient_ref": "SYN-LIVE-A1B2C3", "data_class": "synthetic",
                                                 "mode": "ambient"})
        assert r.status_code == 201, r.text
        return r.json()["session"]["session_id"]
    sid = new_session(c)
    engine = app.state.engine
    with engine.begin() as conn:
        if "mode" not in {col["name"] for col in inspect(conn).get_columns("voice_sessions")}:
            conn.execute(text("ALTER TABLE voice_sessions ADD COLUMN mode VARCHAR(16)"))
        conn.execute(text("UPDATE voice_sessions SET mode='ambient' WHERE session_id=:sid"), {"sid": sid})
    return sid


def amint(c, sid, purpose="ambient", code=None, expect=None):
    body = {"voice_session_id": sid, "access_code": code}
    if purpose is not None:
        body["purpose"] = purpose
    r = c.post("/api/voice/realtime/session", json=body)
    if expect is not None:
        assert r.status_code == expect, r.text
    return r


def all_keys(obj) -> set[str]:
    if isinstance(obj, dict):
        return set(obj) | {k for v in obj.values() for k in all_keys(v)}
    if isinstance(obj, list):
        return {k for v in obj for k in all_keys(v)}
    return set()


# ------------------------------------------------------------------ T2
def test_t2_ambient_upstream_request_exact(tmp_path):
    app, vendor = make(tmp_path, tx_vendor())
    with login(app) as c:
        r = amint(c, ambient_session(c, app), expect=200)
    assert r.headers["cache-control"] == "no-store"
    assert r.json() == GOLD_RESPONSE
    (req,) = vendor.requests
    assert req.method == "POST" and str(req.url) == "https://api.openai.com/v1/realtime/client_secrets"
    assert req.headers["authorization"] == f"Bearer {KEY}"
    assert req.headers["content-type"] == "application/json"
    assert json.loads(req.content) == GOLD_BODY


def test_t2_ambient_no_output_keys(tmp_path):
    app, vendor = make(tmp_path, tx_vendor())
    with login(app) as c:
        amint(c, ambient_session(c, app), expect=200)
    session = json.loads(vendor.requests[0].content)["session"]
    # "model" is only allowed nested under transcription.
    transcription = session["audio"]["input"].pop("transcription")
    assert set(transcription) == {"model", "language"}
    assert all_keys(session) & FORBIDDEN == set()
    assert set(session["audio"]) == {"input"}


def test_t2_ambient_model_flows_through(tmp_path):
    app, vendor = make(tmp_path, tx_vendor(), voice_transcribe_model="m-tr", voice_realtime_model="m-rt")
    with login(app) as c:
        r = amint(c, ambient_session(c, app), expect=200)
    body = json.loads(vendor.requests[0].content)
    assert body["session"]["audio"]["input"]["transcription"]["model"] == "m-tr"
    assert "m-rt" not in vendor.requests[0].content.decode()
    assert (r.json()["model"], r.json()["transcribe_model"]) == ("m-tr", "m-tr")
    assert rt_rows(app)[-1]["details"]["model"] == "m-tr"


# ------------------------------------------------------------------ T3
def test_t3_guided_bytes_snapshot(tmp_path):
    app, vendor = make(tmp_path)
    with login(app) as c:
        r = amint(c, new_session(c), purpose="guided", expect=200)
    assert vendor.requests[0].content == GUIDED_SNAPSHOT
    assert r.json() == GUIDED_RESPONSE


def test_t3_purpose_omitted_equals_guided(tmp_path):
    app, vendor = make(tmp_path)
    with login(app) as c:
        omitted = amint(c, new_session(c), purpose=None, expect=200)
        explicit = amint(c, new_session(c), purpose="guided", expect=200)
    a, b = vendor.requests
    assert a.content == b.content == GUIDED_SNAPSHOT
    assert omitted.json() == explicit.json() == GUIDED_RESPONSE


# ------------------------------------------------------------------ T4
def test_t4_ambient_session_rules(tmp_path):
    app, vendor = make(tmp_path, tx_vendor())
    with login(app) as c:
        r = amint(c, new_session(c), expect=409)  # guided session
        assert r.json()["detail"] == "voice session mode does not match purpose"
        sid = ambient_session(c, app)
        c.post(f"/api/voice/sessions/{sid}/finish").raise_for_status()
        assert amint(c, sid, expect=409).json()["detail"] == "voice session is not active"
        assert amint(c, "doesnotexist", expect=404).json()["detail"] == "voice session not found"
    assert vendor.requests == []
    assert [r["details"]["reason"] for r in rt_rows(app)] == [
        "session_mode_mismatch", "session_not_active", "session_not_found",
    ]


def test_t4_guided_on_ambient_refused(tmp_path):
    app, vendor = make(tmp_path)
    with login(app) as c:
        sid = ambient_session(c, app)
        for purpose in ("guided", None):
            r = amint(c, sid, purpose=purpose, expect=409)
            assert r.json()["detail"] == "voice session mode does not match purpose"
    assert vendor.requests == []
    assert [(r["details"]["purpose"], r["details"]["reason"]) for r in rt_rows(app)] == [
        ("guided", "session_mode_mismatch"), ("guided", "session_mode_mismatch"),
    ]


@pytest.mark.parametrize("purpose", ["x", "AMBIENT", "", 1])
def test_t4_purpose_validation(tmp_path, purpose):
    app, vendor = make(tmp_path)
    with login(app) as c:
        amint(c, new_session(c), purpose=purpose, expect=422)
    assert vendor.requests == [] and rt_rows(app) == []


@pytest.mark.parametrize("who", ["physician1", "pharmacist1"])
def test_t4_roles_ambient(tmp_path, who):
    app, vendor = make(tmp_path, tx_vendor())
    with login(app) as nurse:
        sid = ambient_session(nurse, app)
    with login(app, who) as c:
        amint(c, sid, expect=403)
    with TestClient(app) as anon:
        amint(anon, sid, expect=401)
    assert vendor.requests == [] and rt_rows(app) == []


def test_t4_access_code_ambient(tmp_path):
    app, vendor = make(tmp_path, tx_vendor(), public_demo=True, session_secret=SESSION_SECRET, voice_access_code=CODE)
    with demo_nurse(app) as c:
        sid = ambient_session(c, app)
        assert amint(c, sid, expect=403).json()["detail"] == {"reason": "access_code_invalid"}
        amint(c, sid, code="wrong", expect=403)
        assert vendor.requests == []
        assert amint(c, sid, code=CODE, expect=200).json() == GOLD_RESPONSE
    assert [(r["outcome"], r["details"]["purpose"]) for r in rt_rows(app)] == [
        ("denied", "ambient"), ("denied", "ambient"), ("success", "ambient"),
    ]


def test_t4_rate_limit_shared_across_purposes(tmp_path):
    app, vendor = make(tmp_path, tx_vendor())
    with login(app) as c:
        amb, gui = ambient_session(c, app), new_session(c)
        for i in range(vr.RATE_LIMIT_MAX):
            amint(c, amb if i % 2 else gui, purpose="ambient" if i % 2 else "guided", expect=200)
        r = amint(c, amb, expect=429)  # the 11th, ambient
        assert r.json()["detail"] == {"reason": "rate_limited"}
        amint(c, gui, purpose="guided", expect=429)
    assert len(vendor.requests) == vr.RATE_LIMIT_MAX
    assert [(r["outcome"], r["details"]["purpose"]) for r in rt_rows(app)[-2:]] == [
        ("rate_limited", "ambient"), ("rate_limited", "guided"),
    ]


# ------------------------------------------------------------------ T5
def test_t5_ambient_audit_rows(tmp_path):
    app, _ = make(tmp_path, tx_vendor())
    with login(app) as c:
        sid = ambient_session(c, app)
        amint(c, sid, expect=200)
        amint(c, "doesnotexist", expect=404)
    ok, err = rt_rows(app)
    assert (ok["outcome"], ok["target"], err["outcome"]) == ("success", f"voice_session/{sid}", "error")
    assert ok["details"] == {
        "purpose": "ambient", "model": TX_MODEL, "transcribe_model": TX_MODEL,
        "instructions_version": "v2-transcribe-0.1.0", "instructions_sha256": None, "max_session_seconds": 300,
        "expires_at": 1_900_000_000, "upstream_status": 200, "upstream_session_id": "sess_tx1",
    }
    assert err["details"]["purpose"] == "ambient" and err["details"]["reason"] == "session_not_found"


@pytest.mark.parametrize("over,reason", [({"voice_enabled": False}, "voice_disabled"), ({"voice_api_key": ""}, "not_configured")])
def test_t5_unavailable_row_has_purpose(tmp_path, over, reason):
    app, vendor = make(tmp_path, tx_vendor(), **over)
    with login(app) as c:
        assert amint(c, ambient_session(c, app), expect=503).json()["detail"] == {"reason": reason}
    (row,) = rt_rows(app)
    assert (row["outcome"], row["details"]["purpose"]) == ("unavailable", "ambient")
    assert vendor.requests == []


def test_t5_ambient_no_secret_leaks(tmp_path, caplog):
    caplog.set_level(logging.DEBUG)
    app, _ = make(tmp_path, tx_vendor(), public_demo=True, session_secret=SESSION_SECRET, voice_access_code=CODE)
    bodies = []
    with demo_nurse(app) as c:
        sid = ambient_session(c, app)
        bodies.append(amint(c, sid, code="wrong-code-attempt", expect=403).text)
        amint(c, sid, code=CODE, expect=200)
        bodies.append(amint(c, "doesnotexist", code=CODE, expect=404).text)
    blob = json.dumps(rows(app), default=str) + caplog.text + "".join(bodies)
    for needle in (KEY, CODE, SECRET, "ek_", "wrong-code-attempt"):
        assert needle not in blob, needle


# ------------------------------------------------------------------ T6
def test_t6_config_ambient_fields(tmp_path):
    app, _ = make(tmp_path)
    with login(app) as c:
        cfg = c.get("/api/voice/realtime/config").json()
    assert cfg["ambient_supported"] is True and cfg["ambient_model"] == TX_MODEL
    (tmp_path / "o").mkdir()
    app2, _ = make(tmp_path / "o", voice_transcribe_model="m-tr")
    with login(app2) as c2:
        cfg2 = c2.get("/api/voice/realtime/config").json()
    assert cfg2["ambient_supported"] is True and cfg2["ambient_model"] == "m-tr"


# ------------------------------------------------------------------ T10
def _timeout(req):
    raise httpx.ReadTimeout("slow", request=req)


@pytest.mark.parametrize(
    "handler,status,detail",
    [
        (lambda req: httpx.Response(500, json={"error": {"message": "VENDOR-BODY-LEAK"}}), 502,
         {"reason": "upstream_error", "upstream_status": 500}),
        (_timeout, 504, {"reason": "upstream_timeout"}),
        (lambda req: httpx.Response(200, json={"value": "sk-notephemeral", "expires_at": 1}), 502, None),
        (lambda req: httpx.Response(200, json={"value": SECRET, "expires_at": "soon"}), 502, None),
        (lambda req: httpx.Response(200, json={"value": SECRET}), 502, None),
        (lambda req: httpx.Response(200, json=["not", "a", "dict"]), 502, None),
    ],
    ids=["500", "timeout", "not-ek", "bad-exp", "no-exp", "not-dict"],
)
def test_t10_ambient_upstream_failures(tmp_path, handler, status, detail):
    app, vendor = make(tmp_path, tx_vendor(handler))
    with login(app) as c:
        r = amint(c, ambient_session(c, app), expect=status)
    assert len(vendor.requests) == 1
    if detail is not None:
        assert r.json()["detail"] == detail
    assert r.json()["detail"]["reason"] in {"upstream_error", "upstream_timeout"}
    for needle in ("VENDOR-BODY-LEAK", "sk-notephemeral", SECRET):
        assert needle not in r.text
    row = rt_rows(app)[-1]
    assert (row["outcome"], row["details"]["purpose"]) == ("error", "ambient")


# ------------------------------------------------------------------ T9
def test_t9_no_vendor_sdk_imports():
    src = (REPO_ROOT / "backend" / "app" / "voice_realtime.py").read_text(encoding="utf-8")
    mods = [a.name for n in ast.walk(ast.parse(src)) if isinstance(n, ast.Import) for a in n.names]
    mods += [n.module or "" for n in ast.walk(ast.parse(src)) if isinstance(n, ast.ImportFrom)]
    assert not any(m.split(".")[0] in {"openai", "livekit"} or "gateway" in m for m in mods), mods
