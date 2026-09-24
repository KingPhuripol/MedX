"""Vercel entry point for the MedX public demo (DEC-0022).

Serverless instances only have /tmp, so every sandbox lives in that instance's SQLite
file and resets when the instance is recycled. Agent jobs run inside the request.
The public demo runs offline: model and speech providers are refused by config (DEC-0022).
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

defaults = {
    'FRONT_DOOR_AUTH_MODE': 'public_demo',
    'FRONT_DOOR_DB': '/tmp/medx-demo.sqlite3',
    'FRONT_DOOR_V2_INLINE_JOBS': 'true',
}
for key, value in defaults.items():
    os.environ.setdefault(key, value)

from innovation.api.app import create_app  # noqa: E402

app = create_app()
