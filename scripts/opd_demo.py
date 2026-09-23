"""Seed a local MedX OPD demo: role accounts + four synthetic cases, one per journey stage.

    python3 scripts/opd_demo.py      # then `make opd-demo` serves it at http://127.0.0.1:8000/

Tokens are written to .secrets/opd-demo-principals.json (0600) and never printed.
Everything is synthetic; nothing here resembles a real patient.
"""
import json
import os
import secrets
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from innovation.v2.demo_cases import CASES, seed_cases
from innovation.v2.providers import MockProvider
from innovation.v2.runtime import Runtime
from innovation.v2.service import Principal, Service
from innovation.v2.store import Store

PRINCIPALS = Path('.secrets/opd-demo-principals.json')
DB = Path('artifacts/opd-demo.sqlite3')
ROLES = [('nurse-1', 'intake'), ('doctor-1', 'physician'), ('pharmacist-1', 'pharmacist'), ('evaluator-1', 'evaluator')]


def principals():
    if not PRINCIPALS.exists():
        PRINCIPALS.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        fd = os.open(PRINCIPALS, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
        with os.fdopen(fd, 'w') as f:
            json.dump({'principals': [{'subject': s, 'role': r, 'workspace': 'default', 'token': secrets.token_urlsafe(24)}
                                      for s, r in ROLES]}, f, indent=2)
    return {p['role']: Principal(p['subject'], p['role'], p['workspace']) for p in json.loads(PRINCIPALS.read_text())['principals']}


def seed(who):
    DB.parent.mkdir(parents=True, exist_ok=True)
    store = Store(DB)
    try:
        seed_cases(Service(store, Runtime(MockProvider())), who['intake'].workspace)
    finally:
        store.close()


if __name__ == '__main__':
    seed(principals())
    print(f'Seeded {len(CASES)} synthetic OPD cases into {DB}.')
    print(f'Sign-in tokens per role (nurse/doctor/pharmacist/evaluator) are in {PRINCIPALS} — keep that file private.')
