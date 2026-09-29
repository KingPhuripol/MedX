"""Vercel Python function: the MedX FastAPI backend for the public demo (slice d1; DECISIONS.md 2026-09-29).

Always PUBLIC_DEMO: mock provider only (external provider config is refused at startup), synthetic data
only, one-click role login, HMAC-signed sessions (needs env SESSION_SECRET, >= 32 chars). The SQLite DB
lives in this instance's /tmp and resets when the instance is recycled.

Voice exception (DECISIONS.md 2026-09-29, slice v1): OPENAI_API_KEY / VOICE_* env vars are read only by
the /api/voice/realtime session endpoint (short-lived browser client secret, access code, rate limit).
The Model Gateway stays mock; they never populate external provider settings.
"""

import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path[:0] = [os.path.join(ROOT, "backend"), ROOT]

os.environ["PUBLIC_DEMO"] = "1"  # forced: this entry point only ever serves the public demo
os.environ.setdefault("CARE_DATASET", os.path.join(ROOT, "data", "synthetic", "v1"))

from app.main import create_app  # noqa: E402

app = create_app()
