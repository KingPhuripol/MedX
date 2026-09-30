"""Slice v2t T8: optional live mint of one ambient (transcription-only) client secret. Not part of ``make test``.

    python3 scripts/voice_ambient_live_check.py     # exit 0 PASS, 1 FAIL, 3 SKIPPED

Runs only when ``OPENAI_API_KEY`` and ``VOICE_ENABLED=1`` are in the process environment (``.env`` is never read).
Goes through the real ``POST /api/voice/realtime/session`` endpoint on a throwaway SQLite app with a synthetic
session. No audio is sent and no WebRTC connection is made (~US$0). Prints status, booleans and model names only;
the key and the minted secret are never printed.
"""

from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def main() -> int:
    if not (os.environ.get("OPENAI_API_KEY", "").strip() and os.environ.get("VOICE_ENABLED", "").strip().lower()
            in {"1", "true", "yes", "on"}):
        print("SKIPPED: needs OPENAI_API_KEY and VOICE_ENABLED=1 in the environment")
        return 3
    venv_py = ROOT / ".venv" / "bin" / "python"
    try:
        import fastapi  # noqa: F401
    except ImportError:
        if venv_py.exists() and Path(sys.executable).resolve() != venv_py.resolve():
            os.execv(str(venv_py), [str(venv_py), *sys.argv])
        raise
    sys.path.insert(0, str(ROOT / "backend"))

    import httpx
    from fastapi.testclient import TestClient
    from sqlalchemy import text

    from app.config import Settings
    from app.main import create_app
    from app.seed import DEV_USERS, dev_password, seed_dev_users

    echoes: list = []

    class Recording(httpx.HTTPTransport):
        def handle_request(self, request: httpx.Request) -> httpx.Response:
            resp = super().handle_request(request)
            resp.read()
            try:
                echoes.append(resp.json())
            except ValueError:
                echoes.append(None)
            return resp

    tx_model = os.environ.get("VOICE_TRANSCRIBE_MODEL", "").strip() or Settings().voice_transcribe_model
    with tempfile.TemporaryDirectory() as tmp:
        s = Settings(database_url=f"sqlite:///{tmp}/live.db", voice_enabled=True,
                     voice_api_key=os.environ["OPENAI_API_KEY"].strip(), voice_transcribe_model=tx_model)
        app = create_app(s)
        seed_dev_users(app.state.engine)
        app.state.realtime_transport = Recording()
        _, _, env_var, default = DEV_USERS[0]
        with TestClient(app) as c:
            c.post("/api/auth/login", json={"username": "nurse1", "password": dev_password(env_var, default)}
                   ).raise_for_status()
            r = c.post("/api/voice/sessions", json={"patient_ref": "SYN-LIVE-A1B2C3", "data_class": "synthetic"})
            r.raise_for_status()
            sid = r.json()["session"]["session_id"]
            with app.state.engine.begin() as conn:  # this branch has no mode column yet (v2a adds it)
                cols = {row[1] for row in conn.execute(text("PRAGMA table_info(voice_sessions)"))}
                if "mode" not in cols:
                    conn.execute(text("ALTER TABLE voice_sessions ADD COLUMN mode VARCHAR(16)"))
                conn.execute(text("UPDATE voice_sessions SET mode='ambient' WHERE session_id=:sid"), {"sid": sid})
            r = c.post("/api/voice/realtime/session", json={"voice_session_id": sid, "purpose": "ambient"})
    echo = echoes[-1] if echoes else None
    session = echo.get("session") if isinstance(echo, dict) else None
    session = session if isinstance(session, dict) else {}
    tx = (((session.get("audio") or {}).get("input") or {}).get("transcription") or {})
    checks = {
        "status_200": r.status_code == 200,
        "secret_is_ephemeral": r.status_code == 200 and str(r.json().get("client_secret", "")).startswith("ek_"),
        "session_type_transcription": session.get("type") == "transcription",
        "transcription_model_matches": tx.get("model") == tx_model,
    }
    print(f"status={r.status_code} model={tx_model} upstream_model={tx.get('model')}")
    for k, v in checks.items():
        print(f"{k}={v}")
    ok = all(checks.values())
    print("PASS" if ok else "FAIL")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
