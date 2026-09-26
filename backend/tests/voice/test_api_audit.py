"""S3-A09 gateway audit + isolation, S3-A12 authz/human-action audit, S3-A13 append-only,
S3-A15 local-only audio, S3-A16 s0 back-compat."""

import ast
import json
import re
from datetime import datetime, timedelta, timezone

import pytest
from fastapi.routing import APIRoute
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError

from app.config import Settings
from app.gateway import CONTRACT_VERSION, MOCK_LABEL, GatewayRequest, build_provider, register_mock_task
from app.gateway.contract import canonical_sha256
from app.voice.audio import ASRResult, LocalStubASR, LocalStubTTS, asr_to_turn
from app.voice.models import AddTurnBody, EXTRACT_TASK

from ..conftest import PASSWORDS, REPO_ROOT
from ..repo_files import read_text, repo_files
from .helpers import VoiceAPI, simulate_all

GATEWAY_KEYS = {"provider", "model_version", "contract_version", "data_class", "request_sha256", "status", "latency_ms"}
SENTINEL = "SENTINEL-ถอดความ-7c1e55"
VOICE_DIR = REPO_ROOT / "backend" / "app" / "voice"
NETWORK_MODULES = {"httpx", "requests", "socket", "urllib", "urllib3", "aiohttp", "http.client", "websockets"}
SPEECH_SDKS = {"whisper", "faster_whisper", "livekit", "openai", "google.cloud.speech", "azure", "boto3",
               "speech_recognition", "vosk", "deepgram", "elevenlabs"}
ADAPTERS_NEEDLE = ".".join(["gateway", "adapters"])


def _imports(path) -> set[str]:
    mods: set[str] = set()
    for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
        if isinstance(node, ast.Import):
            mods |= {a.name for a in node.names}
        elif isinstance(node, ast.ImportFrom) and node.module:
            mods.add(("." * node.level) + node.module)
    return mods


def _matches(mod: str, names: set[str]) -> bool:
    mod = mod.lstrip(".")
    return any(mod == n or mod.startswith(n + ".") for n in names)


# ---------------------------------------------------------------- A09


def test_voice_gateway_audit_rows(app, audit_rows):
    before = len(audit_rows())
    runs = simulate_all(app)
    n_calls = sum(len(r.posts) for r in runs)
    rows = audit_rows()[before:]
    gw = [r for r in rows if r["action"] == "gateway.invoke"]
    assert n_calls > 60
    assert len(gw) == n_calls
    for r in gw:
        assert r["target"] == f"task/{EXTRACT_TASK}"
        assert GATEWAY_KEYS <= set(r["details"])
        assert r["details"]["data_class"] == "synthetic"
        assert r["details"]["contract_version"] == CONTRACT_VERSION
        assert r["actor_role"] == "nurse"
    shas = {r["details"]["request_sha256"] for r in gw}
    for run in runs:
        for post in run.posts:
            for f in post["response"]["new_facts"]:
                assert f["request_sha256"] in shas


def test_voice_audit_no_transcript_text(client, login, app, audit_rows):
    login("nurse1")
    api = VoiceAPI(client, app)
    api.start()
    api.turn(f"มีไข้ค่ะ {SENTINEL}")
    api.turn(f"สามวันค่ะ {SENTINEL}", speaker="relative")
    api.finish()
    runs = simulate_all(app)
    dump = "\n".join(repr(r) for r in audit_rows())
    assert SENTINEL not in dump
    for run in runs:
        for post in run.posts:
            t = post["body"].text
            if len(t) >= 6:
                assert t not in dump, t


def test_voice_provider_isolation():
    violations = []
    py_files = sorted(VOICE_DIR.rglob("*.py"))
    assert len(py_files) >= 8
    for path in py_files:
        for mod in _imports(path):
            if _matches(mod, NETWORK_MODULES) or _matches(mod, SPEECH_SDKS):
                violations.append(f"{path.name}: imports {mod}")
            if "adapters" in mod:
                violations.append(f"{path.name}: imports gateway adapters ({mod})")
        if ADAPTERS_NEEDLE in path.read_text(encoding="utf-8"):
            violations.append(f"{path.name}: references gateway adapters")
    # Repo-wide: no speech / provider SDKs anywhere (python imports, lockfile, web deps).
    for path in repo_files(REPO_ROOT):
        if path.suffix == ".py":
            for mod in _imports(path):
                if _matches(mod, SPEECH_SDKS):
                    violations.append(f"{path}: imports {mod}")
    lock = read_text(REPO_ROOT / "requirements.lock") or ""
    pkg = json.loads((REPO_ROOT / "web" / "package.json").read_text())
    web_deps = set(pkg.get("dependencies", {})) | set(pkg.get("devDependencies", {}))
    for sdk in ("whisper", "openai-whisper", "faster-whisper", "livekit", "openai", "azure", "boto3", "deepgram"):
        if re.search(rf"^{re.escape(sdk)}[-_a-z]*==", lock, re.MULTILINE):
            violations.append(f"requirements.lock pins {sdk}")
        if any(d == sdk or d.startswith(f"{sdk}-") or d.startswith(f"@{sdk}") for d in web_deps):
            violations.append(f"web/package.json depends on {sdk}")
    assert violations == []


# ---------------------------------------------------------------- A12


def _switch(client, username):
    client.post("/api/auth/logout")
    if username:
        assert client.post("/api/auth/login", json={"username": username, "password": PASSWORDS[username]}).status_code == 200


def test_voice_auth_matrix(client, login, app):
    login("nurse1")
    api = VoiceAPI(client, app)
    api.start()
    sid = api.sid

    def turn_body():
        start = api.cursor
        api.clock.t = start + timedelta(seconds=5)
        api.cursor = start + timedelta(seconds=4)
        return {"speaker": "patient", "text": "มีไข้ค่ะ", "started_at": start.isoformat(),
                "ended_at": (start + timedelta(seconds=3)).isoformat()}

    endpoints = [
        ("start", lambda: client.post("/api/voice/sessions", json={"patient_ref": "SYN-S3-M", "data_class": "synthetic"})),
        ("turn", lambda: client.post(f"/api/voice/sessions/{sid}/turns", json=turn_body())),
        ("get", lambda: client.get(f"/api/voice/sessions/{sid}")),
        ("facts", lambda: client.get(f"/api/voice/sessions/{sid}/facts")),
        ("finish", lambda: client.post(f"/api/voice/sessions/{sid}/finish")),
    ]
    cells = {}
    for name, call in endpoints:
        for who, expected in (("physician1", 403), ("pharmacist1", 403), (None, 401), ("nurse1", "2xx")):
            _switch(client, who)
            status = call().status_code
            cells[(name, who)] = status
            if expected == "2xx":
                assert 200 <= status < 300, (name, who, status)
            else:
                assert status == expected, (name, who, status)
    assert len(cells) == 20


@pytest.mark.parametrize("data_class", ["mimic", "hospital", "real", "unknown", "SYNTHETIC"])
def test_voice_start_validation(client, login, app, data_class):
    login("nurse1")
    bad_class = client.post("/api/voice/sessions", json={"patient_ref": "SYN-S3-X", "data_class": data_class})
    assert bad_class.status_code == 422
    for ref in ("HN-12345", "syn-1", "SYN-", "SYN-../x", "1234567890123"):
        assert client.post("/api/voice/sessions", json={"patient_ref": ref, "data_class": "synthetic"}).status_code == 422
    assert client.post("/api/voice/sessions", json={"patient_ref": "SYN-S3-X"}).status_code == 422
    api = VoiceAPI(client, app)
    api.start()
    assert api.turn("ข้อความ", speaker="agent", expect=422).status_code == 422  # agent turns are server-only
    assert api.turn("x", expect=422, extra="field").status_code == 422
    assert client.get("/api/voice/sessions/does-not-exist").status_code == 404


def test_turn_after_finish_409(client, login, app):
    login("nurse1")
    api = VoiceAPI(client, app)
    api.start()
    api.turn("ไอค่ะ")
    api.finish()
    assert api.turn("สามวันค่ะ", expect=409).status_code == 409
    api.finish(expect=409)
    assert api.get().json()["session"]["status"] == "finished"


def test_voice_human_action_audit(client, login, app, audit_rows):
    login("nurse1")
    api = VoiceAPI(client, app)

    def delta(fn):
        before = len(audit_rows())
        fn()
        return audit_rows()[before:]

    rows = delta(api.start)
    assert [r["action"] for r in rows] == ["voice.session.start"]
    rows = delta(lambda: api.turn("มีไข้ค่ะ"))
    assert sorted(r["action"] for r in rows) == ["gateway.invoke", "voice.turn.add"]
    rows = delta(api.finish)
    assert [r["action"] for r in rows] == ["voice.session.finish"]
    assert rows[0]["details"]["status_change"] == "active->finished"
    rows = delta(lambda: (api.get(), api.facts()))
    assert rows == []
    voice_rows = [r for r in audit_rows() if r["action"].startswith("voice.")]
    assert len(voice_rows) == 3
    for r in voice_rows:
        assert r["actor_id"] is not None and r["actor_role"] == "nurse"
        assert r["target"] == f"voice_session/{api.sid}"


# ---------------------------------------------------------------- A13


def test_voice_append_only_sqlite(client, login, app):
    login("nurse1")
    api = VoiceAPI(client, app)
    api.start()
    api.turn("ปวดหัวค่ะ")
    engine = app.state.engine
    stmts = [
        "UPDATE voice_turns SET text = 'tampered'", "DELETE FROM voice_turns",
        "UPDATE voice_facts SET state = 'KNOWN'", "DELETE FROM voice_facts",
        "UPDATE voice_extractions SET status = 'ok'", "DELETE FROM voice_extractions",
        "UPDATE voice_sessions SET patient_ref = 'SYN-OTHER'", "DELETE FROM voice_sessions",
    ]
    for stmt in stmts:
        with pytest.raises(DBAPIError, match="append-only|cannot be deleted|only voice_sessions.status"):
            with engine.begin() as conn:
                conn.execute(text(stmt))
    with engine.begin() as conn:  # the one mutable column
        conn.execute(text("UPDATE voice_sessions SET status = 'active'"))
    assert all(t["text"] != "tampered" for t in api.get().json()["turns"])


def test_no_voice_mutation_routes(app):
    # FastAPI >= 0.14x wraps included routers, so inspect both the router and the served OpenAPI schema.
    from app.voice import router as voice_router

    voice_routes = [r for r in voice_router.routes if isinstance(r, APIRoute)]
    assert len(voice_routes) == 5
    for route in voice_routes:
        assert not (route.methods & {"PUT", "PATCH", "DELETE"}), route.path
    paths = {p: ops for p, ops in app.openapi()["paths"].items() if p.startswith("/api/voice")}
    assert len(paths) == 5
    methods = {m.upper() for ops in paths.values() for m in ops}
    assert methods == {"GET", "POST"}


# ---------------------------------------------------------------- A15 / A16


def test_audio_stubs_local_only():
    asr = LocalStubASR().transcribe(b"\x00\x01" * 100, lang="th")
    assert (asr.status, asr.transcript, asr.lang) == ("not_configured", None, "th")
    tts = LocalStubTTS()
    a, b = tts.synthesize("สวัสดีค่ะ"), tts.synthesize("สวัสดีค่ะ")
    assert a == b and a and set(a) == {0}
    t0 = datetime(2026, 1, 1, tzinfo=timezone.utc)
    with pytest.raises(ValueError):
        asr_to_turn(asr, "patient", t0, t0)
    ok = ASRResult(status="ok", transcript="มีไข้ค่ะ", lang="th", engine="test")
    typed = AddTurnBody(speaker="patient", text="มีไข้ค่ะ", started_at=t0, ended_at=t0 + timedelta(seconds=2))
    assert asr_to_turn(ok, "patient", t0, t0 + timedelta(seconds=2)) == typed


def test_mock_task_registry_backcompat():
    provider = build_provider("mock", Settings())
    req = GatewayRequest(task="echo", inputs={"note": "synthetic fixture"}, data_class="synthetic")
    sha = canonical_sha256(req)
    out = provider.invoke(req, sha).output
    assert out == {"label": MOCK_LABEL, "mock_id": sha[:16], "text": f"{MOCK_LABEL}. Placeholder output; no model was run."}
    assert CONTRACT_VERSION == "0.1.0"
    vreq = GatewayRequest(
        task=EXTRACT_TASK,
        inputs={"turns": [{"turn_id": "a", "speaker": "patient", "text": "มีไข้ค่ะ", "ended_at": "x"}],
                "last_asked_field": "chief_complaint"},
        data_class="synthetic",
    )
    r1, r2 = provider.invoke(vreq, canonical_sha256(vreq)), provider.invoke(vreq, canonical_sha256(vreq))
    assert r1 == r2 and r1.output["label"] == MOCK_LABEL
    assert [f["value"] for f in r1.output["facts"]] == ["fever"]
    # A registered handler cannot drop the mock label.
    register_mock_task("test.unlabelled", lambda inputs: {"label": "clinical!", "x": 1})
    lreq = GatewayRequest(task="test.unlabelled", inputs={}, data_class="synthetic")
    assert provider.invoke(lreq, canonical_sha256(lreq)).output == {"label": MOCK_LABEL, "x": 1}
