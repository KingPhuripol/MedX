"""Seed a local MedX OPD demo: role accounts + four synthetic cases, one per journey stage.

    python3 scripts/opd_demo.py      # then `make opd-demo` serves it at http://127.0.0.1:8000/

Tokens are written to .secrets/opd-demo-principals.json (0600) and never printed.
Everything is synthetic; nothing here resembles a real patient.
"""
import json
import os
import secrets
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from innovation.v2.models import ClinicalFact, EncounterCreate, EventRequest, ReviewDecision, TurnRequest
from innovation.v2.providers import MockProvider
from innovation.v2.runtime import Runtime
from innovation.v2.service import Principal, Service
from innovation.v2.store import Store

PRINCIPALS = Path('.secrets/opd-demo-principals.json')
DB = Path('artifacts/opd-demo.sqlite3')
ROLES = [('nurse-1', 'intake'), ('doctor-1', 'physician'), ('pharmacist-1', 'pharmacist'), ('evaluator-1', 'evaluator')]
CASES = {  # encounter: (age, intake facts, orders, dispense outcomes, return precautions, confirm?)
    'opd-001': (34, [('CHIEF_COMPLAINT', 'ปวดศีรษะ 2 วัน')], [], [], [], False),
    'opd-002': (61, [('CHIEF_COMPLAINT', 'ไอ มีเสมหะ 5 วัน'), ('ALLERGY', 'ไม่มี'),
                     ('VITAL', {'name': 'temperature', 'value': 37.9, 'unit': 'Cel'})], [], [], [], False),
    'opd-003': (72, [('CHIEF_COMPLAINT', 'เจ็บคอ ไข้ 3 วัน'), ('ALLERGY', 'แพ้ penicillin ผื่นลมพิษ'),
                     ('MEDICATION', 'warfarin 3 mg วันละครั้ง')],
                [{'drug': 'amoxicillin', 'dose': '500 mg', 'route': 'PO', 'frequency': 'วันละ 3 ครั้ง', 'days': 7},
                 {'drug': 'ibuprofen', 'dose': '400 mg', 'route': 'PO', 'frequency': 'เมื่อปวด', 'days': 3}], [], [], True),
    'opd-004': (45, [('CHIEF_COMPLAINT', 'ไข้ ปวดเมื่อยตัว 1 วัน'), ('ALLERGY', 'ไม่มี'),
                     ('VITAL', {'name': 'temperature', 'value': 38.4, 'unit': 'Cel'})],
                [{'drug': 'paracetamol', 'dose': '500 mg', 'route': 'PO', 'frequency': 'ทุก 6 ชม. เมื่อมีไข้', 'days': 3}],
                ['DISPENSED'], ['ไข้เกิน 3 วัน หายใจเหนื่อย หรือซึมลง'], True),
}


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
    service = Service(store, Runtime(MockProvider()))
    try:
        for eid, (age, intake, orders, outcomes, precautions, confirm) in CASES.items():
            if store.all('encounter', eid):
                continue
            now = datetime.now(timezone.utc)
            service.create(EncounterCreate(encounter_id=eid, age=age, care_context='OPD_ADULT_GENERAL'), eid, who['intake'])
            revision = 0

            def add(kind, value, actor, suffix):
                nonlocal revision
                fact = ClinicalFact(event_id=f'{eid}-{suffix}', kind=kind, value=value, observed_at=now, available_at_time=now)
                service.append_event(eid, EventRequest(expected_revision=revision, idempotency_key=f'{eid}-{suffix}', fact=fact), actor)
                revision += 1

            for i, (kind, value) in enumerate(intake):
                add(kind, value, who['intake'], f'i{i}')
            if eid == 'opd-001':
                continue
            run = service.turn(eid, TurnRequest(expected_revision=revision, idempotency_key=f'{eid}-draft',
                               text='เตรียมร่างส่งต่อ', decision_time=now, design_id='fixed'), who['physician'])
            if confirm:
                service.review(run['draft_id'], ReviewDecision(expected_revision=revision, idempotency_key=f'{eid}-ok',
                               draft_revision=1, expected_review_sequence=0, action='CONFIRM'), who['physician'])
            for i, order in enumerate(orders):
                add('MEDICATION_ORDER', order, who['physician'], f'o{i}')
            for text in precautions:
                add('RETURN_PRECAUTION', text, who['physician'], 'rp')
            for i, outcome in enumerate(outcomes):
                add('DISPENSE', {'order_event_id': f'{eid}-o{i}', 'outcome': outcome}, who['pharmacist'], f'd{i}')
    finally:
        store.close()


if __name__ == '__main__':
    seed(principals())
    print(f'Seeded {len(CASES)} synthetic OPD cases into {DB}.')
    print(f'Sign-in tokens per role (nurse/doctor/pharmacist/evaluator) are in {PRINCIPALS} — keep that file private.')
