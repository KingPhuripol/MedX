"""Vercel entry point for the MedX public demo (DEC-0022).

Serverless instances only have /tmp, so every sandbox lives in that instance's SQLite
file and resets when the instance is recycled. Agent jobs run inside the request.
Secrets (FRONT_DOOR_V2_PROVIDER_TOKEN) are set in the Vercel dashboard, never here.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

defaults = {
    'FRONT_DOOR_AUTH_MODE': 'public_demo',
    'FRONT_DOOR_DB': '/tmp/medx-demo.sqlite3',
    'FRONT_DOOR_V2_INLINE_JOBS': 'true',
}
if os.environ.get('FRONT_DOOR_V2_PROVIDER_URL') or os.environ.get('FRONT_DOOR_V2_SPEECH_URL'):
    # A model provider is configured: OpenAI-compatible transport, gpt-6-luna by default,
    # and a per-instance spending ceiling on top of the provider-side hard limit.
    defaults.update({
        'FRONT_DOOR_ALLOW_EXTERNAL': 'true',
        'FRONT_DOOR_V2_TRANSPORT': 'openai_compatible',
        'FRONT_DOOR_V2_MODEL': 'gpt-6-luna',
        'FRONT_DOOR_V2_BUDGET_DB': '/tmp/medx-budget.sqlite3',
        'FRONT_DOOR_V2_PAID_BUDGET_USD': '5',
        'FRONT_DOOR_V2_CALL_RESERVATION_USD': '0.05',
    })
for key, value in defaults.items():
    os.environ.setdefault(key, value)

from innovation.api.app import create_app  # noqa: E402

app = create_app()
